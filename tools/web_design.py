"""Prepare a bounded, pinned Web-to-Figma native design import."""

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zlib

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts'
sys.path.insert(0, str(SCRIPT_ROOT))
from graph import validate_graph as validate_canonical_graph

SCHEMA = 'figma-flow-web-design-v1'
CAROUSEL_TRIGGERS = {'next', 'previous', 'swipe_left', 'swipe_right', 'autoplay'}
KINDS = {'frame', 'text', 'component', 'image', 'video', 'vector', 'annotation'}
COLORS = re.compile(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z')


def _box(box):
    if (
        not isinstance(box, dict)
        or set(box) != {'x', 'y', 'width', 'height'}
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in box.values())
        or abs(box['x']) > 100_000
        or abs(box['y']) > 100_000
        or box['width'] < 0
        or box['height'] < 0
        or box['width'] > 32768
        or box['height'] > 32768
    ):
        raise ValueError('Finite bounded viewport-relative element bounds required')


def validate_svg(svg):
    if not isinstance(svg, str) or len(svg) > 200_000 or re.search(r'<!|<\?|javascript:', svg, re.I):
        raise ValueError('Bounded standalone SVG required')
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        raise ValueError('Malformed SVG vector') from error
    allowed = {
        'svg': {'viewBox', 'width', 'height', 'xmlns', 'fill', 'stroke'},
        'g': {'fill', 'stroke', 'stroke-width', 'opacity', 'transform', 'fill-rule', 'clip-rule', 'clip-path'},
        'path': {'d', 'fill', 'stroke', 'stroke-width', 'fill-rule', 'clip-rule', 'opacity', 'transform'},
        'rect': {'x', 'y', 'width', 'height', 'rx', 'ry', 'fill', 'stroke', 'stroke-width', 'opacity'},
        'circle': {'cx', 'cy', 'r', 'fill', 'stroke', 'stroke-width', 'opacity'},
        'ellipse': {'cx', 'cy', 'rx', 'ry', 'fill', 'stroke', 'stroke-width', 'opacity'},
        'line': {'x1', 'y1', 'x2', 'y2', 'fill', 'stroke', 'stroke-width', 'opacity'},
        'polyline': {'points', 'fill', 'stroke', 'stroke-width', 'opacity'},
        'polygon': {'points', 'fill', 'stroke', 'stroke-width', 'opacity'},
        'defs': set(),
        'clipPath': {'id'},
        'linearGradient': {'id', 'x1', 'y1', 'x2', 'y2', 'gradientUnits'},
        'radialGradient': {'id', 'cx', 'cy', 'r', 'fx', 'fy', 'gradientUnits'},
        'stop': {'offset', 'stop-color', 'stop-opacity'},
    }
    if root.tag.split('}')[-1] != 'svg':
        raise ValueError('SVG root required')
    count = 0
    parents = {child: parent for parent in root.iter() for child in parent}
    clip_ids = set()
    clip_refs = set()
    gradient_ids = set()
    gradient_refs = set()
    safe_id = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,79}\Z')
    for node in root.iter():
        tag = node.tag.split('}')[-1]
        count += 1
        if tag not in allowed or count > 2000 or node.text and node.text.strip():
            raise ValueError('Unsupported SVG element or text')
        parent_tag = parents.get(node).tag.split('}')[-1] if parents.get(node) is not None else None
        if tag == 'defs' and parent_tag != 'svg':
            raise ValueError('SVG definitions must be direct root children')
        if tag == 'clipPath':
            clip_id = node.attrib.get('id')
            if parent_tag != 'defs' or not clip_id or not safe_id.fullmatch(clip_id) or clip_id in clip_ids:
                raise ValueError('SVG clip paths need unique bounded local IDs')
            clip_ids.add(clip_id)
            if any(child.tag.split('}')[-1] not in {'path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline'} for child in node):
                raise ValueError('Unsupported SVG clip geometry')
        if tag in {'linearGradient', 'radialGradient'}:
            gradient_id = node.attrib.get('id')
            if parent_tag != 'defs' or not gradient_id or not safe_id.fullmatch(gradient_id) or gradient_id in clip_ids or gradient_id in gradient_ids:
                raise ValueError('SVG gradients need unique bounded local IDs')
            gradient_ids.add(gradient_id)
            if node.attrib.get('gradientUnits', 'objectBoundingBox') not in {'objectBoundingBox', 'userSpaceOnUse'}:
                raise ValueError('Unsupported SVG gradient coordinate system')
            if not 1 <= len(node) <= 32 or any(child.tag.split('}')[-1] != 'stop' for child in node):
                raise ValueError('SVG gradients need one to thirty two stops')
        if tag == 'defs' and any(child.tag.split('}')[-1] not in {'clipPath', 'linearGradient', 'radialGradient'} for child in node):
            raise ValueError('Unsupported SVG definition')
        if tag == 'stop' and len(node):
            raise ValueError('SVG gradient stops cannot have child elements')
        for key, value in node.attrib.items():
            name = key.split('}')[-1]
            if name == 'clip-path':
                match = re.fullmatch(r'url\(#([A-Za-z_][A-Za-z0-9_.-]{0,79})\)', value)
                if tag != 'g' or not match:
                    raise ValueError('SVG clip path references need a local ID on a group')
                clip_refs.add(match.group(1))
                continue
            if name in {'fill', 'stroke'} and value.startswith('url('):
                match = re.fullmatch(r'url\(#([A-Za-z_][A-Za-z0-9_.-]{0,79})\)', value)
                if not match:
                    raise ValueError('SVG paint server references need a bounded local ID')
                gradient_refs.add(match.group(1))
                continue
            if (
                name not in allowed[tag]
                or name.lower().startswith('on')
                or re.search(r'javascript:|data:|https?:|file:', value, re.I)
            ):
                raise ValueError('Unsupported or external SVG attribute')
            if name in {'fill-rule', 'clip-rule'} and value not in {'evenodd', 'nonzero'}:
                raise ValueError('SVG fill and clip rules must be evenodd or nonzero')
            if name in {'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'fx', 'fy'} and tag in {'linearGradient', 'radialGradient'}:
                if not re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)%?', value) or abs(float(value.rstrip('%'))) > 32768:
                    raise ValueError('SVG gradient coordinate is outside bounded numeric values')
            if name == 'gradientUnits' and value not in {'objectBoundingBox', 'userSpaceOnUse'}:
                raise ValueError('Unsupported SVG gradient coordinate system')
            if name == 'offset':
                if not re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?|\d+(?:\.\d+)?%)', value):
                    raise ValueError('SVG gradient stop offset must be normalized')
                amount = float(value[:-1]) / 100 if value.endswith('%') else float(value)
                if not 0 <= amount <= 1:
                    raise ValueError('SVG gradient stop offset must be between zero and one')
            if name == 'stop-opacity' and (not re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?)', value) or float(value) > 1):
                raise ValueError('SVG gradient stop opacity must be between zero and one')
            if name == 'stop-color' and value.lower() not in {'black', 'white', 'currentcolor'} and not COLORS.fullmatch(value):
                raise ValueError('SVG gradient stop color must be literal')
            if (
                name in {'fill', 'stroke'}
                and value.lower() not in {'none', 'currentcolor', 'black', 'white'}
                and not COLORS.fullmatch(value)
            ):
                raise ValueError('SVG paint must use literal hex colors')
            if tag == 'line' and name == 'fill' and value != 'none':
                raise ValueError('SVG line fill must be none')
    if clip_refs - clip_ids or gradient_refs - gradient_ids:
        raise ValueError('SVG clip and gradient references must resolve locally')
    return svg


def image_signature(data, mime):
    return {
        'image/png': data.startswith(b'\x89PNG\r\n\x1a\n'),
        'image/jpeg': data.startswith(b'\xff\xd8\xff'),
        'image/webp': len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP',
    }.get(mime, False)


def video_signature(data, mime):
    return {
        'video/mp4': len(data) >= 12 and data[4:8] == b'ftyp',
        'video/webm': data.startswith(b'\x1a\x45\xdf\xa3'),
    }.get(mime, False)


def embed_local_assets(web, max_total=8_000_000):
    graph_dir = Path(web['source_graph_path']).resolve().parent
    pins = []
    total = 0
    assets = {}
    for screen in web['screens']:
        for element in screen['elements']:
            if element['kind'] not in ('image', 'video'):
                continue
            for key in (('asset', 'fallbackAsset') if element['kind'] == 'video' else ('asset',)):
                asset = element[key]
                relative = Path(asset['path'])
                path = graph_dir
                for part in relative.parts:
                    path = path / part
                    if path.is_symlink():
                        raise ValueError('Media asset path crosses a symbolic link')
                if not path.is_file() or not path.resolve().is_relative_to(graph_dir):
                    raise ValueError('Media asset must stay under the graph directory')
                data = path.read_bytes()
                valid = video_signature(data, asset['mimeType']) if key == 'asset' and element['kind'] == 'video' else image_signature(data, asset['mimeType'])
                if hashlib.sha256(data).hexdigest() != asset['sha256'] or not valid:
                    raise ValueError('Media asset hash or file signature is invalid')
                if asset['sha256'] not in assets:
                    total += len(data)
                    if len(data) > 8_000_000 or total > max_total:
                        raise ValueError('Unique embedded assets exceed the 8 MB total limit')
                    assets[asset['sha256']] = base64.b64encode(data).decode('ascii')
                pins.append({'path': str(path.resolve()), 'sha256': asset['sha256']})
    web['assets'] = assets
    return pins


def validate_graph(graph, require_embedded=False):
    errors, _ = validate_canonical_graph(graph)
    if errors:
        raise ValueError('Invalid canonical graph: ' + '; '.join(errors[:3]))
    if (
        not isinstance(graph, dict)
        or set(graph) - {'version', 'id', 'title', 'nodes', 'edges', 'carousel', 'tabs'}
        or not {'version', 'id', 'title', 'nodes', 'edges'} <= graph.keys()
        or graph.get('version') != 1
        or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', str(graph.get('id', '')))
        or not isinstance(graph.get('title'), str)
        or not graph['title'].strip()
        or len(graph['title']) > 160
    ):
        raise ValueError('Versioned web design graph with stable id required')
    nodes = graph['nodes']
    edges = graph['edges']
    if (
        not isinstance(nodes, list)
        or not isinstance(edges, list)
        or not 1 <= len(nodes) <= 2000
        or len(edges) > 4000
    ):
        raise ValueError('Bounded canonical graph nodes and edges required')
    node_ids = set()
    for node in nodes:
        if (
            not isinstance(node, dict)
            or not isinstance(node.get('id'), str)
            or not node['id']
            or len(node['id']) > 160
            or not isinstance(node.get('type'), str)
            or not node['type']
            or not isinstance(node.get('title'), str)
            or not node['title'].strip()
        ):
            raise ValueError('Canonical graph nodes need stable ID, type and title')
        if node['id'] in node_ids:
            raise ValueError('Duplicate canonical graph node ID')
        node_ids.add(node['id'])
    for edge in edges:
        if (
            not isinstance(edge, dict)
            or set(edge) != {'from', 'to', 'type'}
            or edge.get('from') not in node_ids
            or edge.get('to') not in node_ids
            or not isinstance(edge.get('type'), str)
            or not edge['type'].strip()
            or len(edge['type']) > 120
        ):
            raise ValueError('Canonical graph edges must connect declared node IDs')
    carousel = graph.get('carousel')
    screens = [
        node for node in nodes if node.get('type') == 'screen' and node.get('id', '').startswith('WEB-')
    ]
    if not 1 <= len(screens) <= 256:
        raise ValueError('Source graph requires one to 256 WEB screen nodes')
    ids = set()
    for screen in screens:
        if set(screen) - {'id', 'type', 'title', 'detail', 'status', 'layout', 'elements'}:
            raise ValueError('Unsupported WEB screen fields')
        if screen['id'] in ids:
            raise ValueError('Duplicate web screen id')
        ids.add(screen['id'])
        layout = screen.get('layout')
        elements = screen.get('elements')
        if (
            not isinstance(layout, dict)
            or set(layout) - {'width', 'height', 'background'}
            or any(
                type(layout.get(k)) not in (int, float)
                or not math.isfinite(layout[k])
                or layout[k] <= 0
                or layout[k] > 32768
                for k in ('width', 'height')
            )
        ):
            raise ValueError('Finite bounded actual viewport dimensions required')
        if layout.get('background') is not None and not COLORS.fullmatch(layout['background']):
            raise ValueError('Hex screen background required')
        if not isinstance(elements, list) or len(elements) > 1500:
            raise ValueError('Bounded flat screen element list required')
        element_ids = set()
        for e in elements:
            if (
                not isinstance(e, dict)
                or e.get('kind') not in KINDS
                or not isinstance(e.get('id'), str)
                or not e['id']
                or len(e['id']) > 120
            ):
                raise ValueError('Stable typed element id required')
            if e['id'] in element_ids:
                raise ValueError('Duplicate screen element ID')
            element_ids.add(e['id'])
            if 'name' in e and (not isinstance(e['name'], str) or len(e['name']) > 100):
                raise ValueError('Layer name must be a bounded string')
            if 'componentKey' in e:
                key = e['componentKey']
                valid_component = e['kind'] == 'component' and isinstance(key, str) and 0 < len(key) <= 160
                valid_image = e['kind'] == 'image' and isinstance(key, str) and re.fullmatch(
                    r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}', key
                )
                if not (valid_component or valid_image):
                    raise ValueError('Image and component family keys must be bounded stable strings')
            if 'clipsContent' in e and (e['kind'] != 'frame' or type(e['clipsContent']) is not bool):
                raise ValueError('Only frames can clip their children')
            if 'path' in e and (
                not isinstance(e['path'], list)
                or len(e['path']) > 64
                or any(not isinstance(part, str) or not part or len(part) > 120 for part in e['path'])
            ):
                raise ValueError('Bounded ancestor path required')
            if e.get('kind') in ('text', 'component') and e.get('text') is not None:
                text = e.get('text')
                if not isinstance(text, dict) or set(text) - {
                    'characters',
                    'fontFamily',
                    'fontSize',
                    'fontWeight',
                    'lineHeight',
                    'letterSpacing',
                    'textAlign',
                    'textAlignHorizontal',
                    'color',
                    'linearGradient',
                    'paintApproximation',
                }:
                    raise ValueError('Unsupported observed text fields')
                if e.get('kind') == 'text' and not isinstance(text.get('characters'), str):
                    raise ValueError('Text characters required')
                for key in ('fontSize', 'fontWeight', 'lineHeight', 'letterSpacing'):
                    if key in text and (
                        type(text[key]) not in (int, float)
                        and not (key == 'fontWeight' and isinstance(text[key], str) and text[key].isdigit())
                        or not math.isfinite(float(text[key]))
                    ):
                        raise ValueError(f'Finite text {key} required')
                if 'color' in text and text['color'] is not None and not COLORS.fullmatch(text['color']):
                    raise ValueError('Text color must be a literal hex color')
                if 'paintApproximation' in text and text['paintApproximation'] != 'first-gradient-stop':
                    raise ValueError('Unsupported text paint approximation')
                gradient = text.get('linearGradient')
                if gradient is not None and ('color' in text or 'paintApproximation' in text):
                    raise ValueError('Text gradient paint cannot mix with solid text paint')
                if text.get('paintApproximation') and not isinstance(text.get('color'), str):
                    raise ValueError('Text paint approximation needs a visible representative color')
                if gradient is not None:
                    if (not isinstance(gradient, dict) or set(gradient) != {'angle', 'stops'}
                        or type(gradient['angle']) not in (int, float) or not math.isfinite(gradient['angle'])
                        or not isinstance(gradient['stops'], list) or not 2 <= len(gradient['stops']) <= 16):
                        raise ValueError('Text linear gradient needs a finite angle and two to sixteen stops')
                    previous = -1
                    for stop in gradient['stops']:
                        if (not isinstance(stop, dict) or set(stop) != {'position', 'color'}
                            or type(stop['position']) not in (int, float) or not math.isfinite(stop['position'])
                            or not 0 <= stop['position'] <= 1 or stop['position'] < previous
                            or not isinstance(stop['color'], str) or not COLORS.fullmatch(stop['color'])):
                            raise ValueError('Text linear gradient stops must be sorted normalized literal colors')
                        previous = stop['position']
            _box(e.get('box'))
            label_box = e.get('props', {}).get('labelBox') if isinstance(e.get('props', {}), dict) else None
            if label_box is not None:
                _box(label_box)
                if (
                    e.get('kind') != 'component'
                    or label_box['x'] < 0
                    or label_box['y'] < 0
                    or label_box['x'] + label_box['width'] > e['box']['width'] + 1
                    or label_box['y'] + label_box['height'] > e['box']['height'] + 1
                ):
                    raise ValueError('Component labelBox must fit its observed component bounds')
            if e['kind'] == 'text' and (
                not isinstance(e.get('text'), dict)
                or not isinstance(e['text'].get('characters'), str)
                or len(e['text']['characters']) > 10000
            ):
                raise ValueError('Bounded text characters required')
            if e['kind'] in ('image', 'video') and e.get('objectFit', 'cover') not in ('cover', 'contain'):
                raise ValueError('Image objectFit must be cover or contain')
            if e['kind'] == 'vector':
                validate_svg(e.get('svg'))
            if e['kind'] == 'image':
                asset = e.get('asset')
                if (
                    not isinstance(asset, dict)
                    or set(asset) != {'path', 'sha256', 'mimeType'}
                    or asset['mimeType'] not in ('image/png', 'image/jpeg', 'image/webp')
                    or not re.fullmatch(r'[a-f0-9]{64}', str(asset['sha256']))
                    or not isinstance(asset['path'], str)
                    or any(char in asset['path'] for char in ':\\\0\n\r')
                    or Path(asset['path']).is_absolute()
                    or '..' in Path(asset['path']).parts
                    or not Path(asset['path']).parts
                ):
                    raise ValueError('Image needs a hash-pinned local raster asset')
                if require_embedded:
                    raise ValueError(
                        'Raster bytes are loaded from pinned local paths during native preparation'
                    )
            if e['kind'] == 'video':
                def media_ref(value, mime_types):
                    return (isinstance(value, dict) and set(value) == {'path', 'sha256', 'mimeType'}
                        and value['mimeType'] in mime_types and re.fullmatch(r'[a-f0-9]{64}', str(value['sha256']))
                        and isinstance(value['path'], str) and not Path(value['path']).is_absolute()
                        and '..' not in Path(value['path']).parts and bool(Path(value['path']).parts)
                        and not any(char in value['path'] for char in ':\\\0\n\r'))
                if not media_ref(e.get('asset'), {'video/mp4', 'video/webm'}) or not media_ref(e.get('fallbackAsset'), {'image/png', 'image/jpeg', 'image/webp'}):
                    raise ValueError('Video needs hash-pinned MP4/WebM bytes and a supported raster fallback')
            paint = e.get('paint', {})
            if not isinstance(paint, dict) or set(paint) - {
                'background',
                'color',
                'borderColor',
                'borderWidth',
                'borderRadius',
                'opacity',
                'radialGradient',
                'effects',
                'alphaMask',
                'alphaMasks',
                'alphaMaskComposite',
                'cssFilter',
                'svgSilhouetteColor',
            }:
                raise ValueError('Unsupported paint fields')
            for key in ('background', 'color', 'borderColor'):
                if paint.get(key) is not None and not COLORS.fullmatch(paint[key]):
                    raise ValueError('Paint must use literal hex colors')
            bounds = {'borderWidth': 128, 'borderRadius': 1_000_000_000, 'opacity': 1}
            for key, maximum in bounds.items():
                if key in paint and (
                    type(paint[key]) not in (int, float)
                    or not math.isfinite(paint[key])
                    or paint[key] < 0
                    or paint[key] > maximum
                ):
                    raise ValueError(f'Finite bounded {key} required')
            css_filter = paint.get('cssFilter')
            if css_filter is not None:
                names = {'brightness', 'contrast', 'saturate', 'grayscale', 'sepia', 'invert', 'opacity', 'hue-rotate'}
                if e.get('kind') not in {'image', 'vector'} or not isinstance(css_filter, list) or not 1 <= len(css_filter) <= 16:
                    raise ValueError('Bounded CSS color filter chain required on media')
                for operation in css_filter:
                    if not isinstance(operation, dict) or set(operation) != {'name', 'value'} or operation.get('name') not in names:
                        raise ValueError('CSS color filters need a known operation and numeric value')
                    value = operation.get('value')
                    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000:
                        raise ValueError('CSS color filter value must be finite and bounded')
                    if operation['name'] in {'grayscale', 'sepia', 'invert', 'opacity'} and not 0 <= value <= 1:
                        raise ValueError('CSS amount filter must be between zero and one')
                    if operation['name'] in {'brightness', 'contrast', 'saturate'} and value < 0:
                        raise ValueError('CSS color filter amount cannot be negative')
            silhouette = paint.get('svgSilhouetteColor')
            if silhouette is not None and (
                e.get('kind') != 'vector' or css_filter is None or not re.fullmatch(r'#[0-9a-fA-F]{6}', str(silhouette))
                or not any(item['name'] == 'brightness' and item['value'] == 0 for item in css_filter)
                or any(item['name'] == 'opacity' for item in css_filter)
            ):
                raise ValueError('SVG silhouette color requires a brightness-zero vector filter')
            gradient = paint.get('radialGradient')
            if gradient is not None:
                if (
                    not isinstance(gradient, dict)
                    or set(gradient) != {'centerX', 'centerY', 'stops'}
                    or any(
                        type(gradient[key]) not in (int, float)
                        or not math.isfinite(gradient[key])
                        or not 0 <= gradient[key] <= 1
                        for key in ('centerX', 'centerY')
                    )
                    or not isinstance(gradient['stops'], list)
                    or not 2 <= len(gradient['stops']) <= 16
                ):
                    raise ValueError('Radial gradient requires normalized center and two to sixteen stops')
                previous = -1
                for stop in gradient['stops']:
                    if (
                        not isinstance(stop, dict)
                        or set(stop) != {'position', 'color'}
                        or type(stop['position']) not in (int, float)
                        or not math.isfinite(stop['position'])
                        or not 0 <= stop['position'] <= 1
                        or stop['position'] < previous
                        or not isinstance(stop['color'], str)
                        or not COLORS.fullmatch(stop['color'])
                    ):
                        raise ValueError(
                            'Radial gradient stops must use sorted normalized positions and literal colors'
                        )
                    previous = stop['position']
            effects = paint.get('effects', [])
            if not isinstance(effects, list) or len(effects) > 8:
                raise ValueError('At most eight bounded native effects are supported')
            for effect in effects:
                if not isinstance(effect, dict) or effect.get('type') not in {'DROP_SHADOW', 'INNER_SHADOW', 'LAYER_BLUR'}:
                    raise ValueError('Unsupported native effect')
                if effect['type'] == 'LAYER_BLUR':
                    if set(effect) != {'type', 'radius'} or type(effect['radius']) not in (int, float) or not 0 <= effect['radius'] <= 100:
                        raise ValueError('Layer blur radius must be between 0 and 100')
                elif (
                    set(effect) != {'type', 'x', 'y', 'blur', 'spread', 'color'}
                    or any(type(effect[k]) not in (int, float) or not math.isfinite(effect[k]) or abs(effect[k]) > 1000 for k in ('x', 'y', 'blur', 'spread'))
                    or effect['blur'] < 0 or not isinstance(effect['color'], str) or not COLORS.fullmatch(effect['color'])
                ):
                    raise ValueError('Shadow needs bounded geometry and a literal color')
            mask = paint.get('alphaMask')
            if mask is not None:
                if (not isinstance(mask, dict) or set(mask) != {'angle', 'stops'}
                    or type(mask['angle']) not in (int, float) or not math.isfinite(mask['angle'])
                    or not isinstance(mask['stops'], list) or not 2 <= len(mask['stops']) <= 16):
                    raise ValueError('Linear alpha mask needs an angle and two to sixteen stops')
                previous = -1
                for stop in mask['stops']:
                    if (not isinstance(stop, dict) or set(stop) != {'position', 'color'}
                        or type(stop['position']) not in (int, float) or not 0 <= stop['position'] <= 1
                        or stop['position'] < previous or not isinstance(stop['color'], str)
                        or not COLORS.fullmatch(stop['color'])):
                        raise ValueError('Linear alpha mask stops must be sorted normalized literal colors')
                    previous = stop['position']
            mask_layers = paint.get('alphaMasks')
            if mask_layers is not None:
                if paint.get('alphaMaskComposite') != 'intersect' or mask is not None or not isinstance(mask_layers, list) or not 1 <= len(mask_layers) <= 8:
                    raise ValueError('Intersecting CSS alpha masks require one to eight mask layers')
                for layer in mask_layers:
                    if not isinstance(layer, dict) or layer.get('kind') not in {'linear', 'radial'}:
                        raise ValueError('CSS alpha mask needs a supported linear or radial layer')
                    keys = {'kind', 'stops', 'angle'} if layer['kind'] == 'linear' else {'kind', 'stops', 'centerX', 'centerY'}
                    if set(layer) != keys or not isinstance(layer['stops'], list) or not 2 <= len(layer['stops']) <= 16:
                        raise ValueError('CSS alpha mask needs bounded gradient stops and geometry')
                    if layer['kind'] == 'linear' and layer['angle'] not in {90, 180}:
                        raise ValueError('Linear alpha mask angle must be 90 or 180 degrees')
                    if layer['kind'] == 'radial' and any(
                        type(layer[key]) not in (int, float) or not math.isfinite(layer[key]) or not 0 <= layer[key] <= 1
                        for key in ('centerX', 'centerY')
                    ):
                        raise ValueError('Radial alpha mask center must be normalized')
                    previous = -1
                    for stop in layer['stops']:
                        if (not isinstance(stop, dict) or set(stop) != {'position', 'color'}
                            or type(stop['position']) not in (int, float) or not math.isfinite(stop['position'])
                            or not 0 <= stop['position'] <= 1 or stop['position'] < previous
                            or not isinstance(stop['color'], str) or not COLORS.fullmatch(stop['color'])):
                            raise ValueError('CSS alpha mask stops must be sorted normalized literal colors')
                        previous = stop['position']
            elif 'alphaMaskComposite' in paint:
                raise ValueError('CSS alpha mask composite requires mask layers')
        frame_ids = {element['id'] for element in elements if element['kind'] == 'frame'}
        for element in elements:
            path = element.get('path', [])
            if any(frame_id not in frame_ids for frame_id in path) or element['id'] in path:
                raise ValueError('Element path must name existing ancestor frame IDs')
    if carousel is not None and graph.get('tabs') is not None:
        raise ValueError('A canonical web graph owns at most one observed interaction')
    if carousel is not None:
        validate_carousel(carousel, screens)
    if graph.get('tabs') is not None:
        validate_tabs(graph['tabs'], screens)
    validate_image_component_families(screens)
    return screens


def image_component_signature(screen, element):
    by_id = {candidate['id']: candidate for candidate in screen['elements']}
    ancestors = []
    for frame_id in element.get('path', []):
        frame = by_id[frame_id]
        ancestors.append({
            'box': frame['box'],
            'clipsContent': frame.get('clipsContent', False),
            'paint': frame.get('paint', {}),
        })
    visible = {
        'asset': {'sha256': element['asset']['sha256'], 'mimeType': element['asset']['mimeType']},
        'objectFit': element.get('objectFit', 'cover'),
        'size': {'width': element['box']['width'], 'height': element['box']['height']},
        'paint': element.get('paint', {}),
        'ancestors': ancestors,
    }
    return json.dumps(visible, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def validate_image_component_families(screens):
    families = {}
    for screen in screens:
        for element in screen['elements']:
            key = element.get('componentKey')
            if element['kind'] == 'image' and key:
                families.setdefault(key, []).append((screen['id'], image_component_signature(screen, element)))
    for key, occurrences in families.items():
        screen_ids = [screen_id for screen_id, _ in occurrences]
        signatures = {signature for _, signature in occurrences}
        if len(occurrences) < 2 or len(set(screen_ids)) != len(screen_ids) or len(signatures) != 1:
            raise ValueError(f'Image component family {key} must repeat once per screen with identical appearance')


def derive_repeated_carousel_images(graph):
    """Assign component identity only to identical image occurrences in every carousel state."""
    carousel = graph.get('carousel')
    screens = {node['id']: node for node in graph['nodes'] if node.get('type') == 'screen'}
    selected = [screens[state['screenId']] for state in carousel['states']]
    grouped = []
    for screen in selected:
        per_signature = {}
        for element in screen['elements']:
            if element['kind'] == 'image':
                signature = image_component_signature(screen, element)
                per_signature.setdefault(signature, []).append(element)
        grouped.append(per_signature)
    common = set.intersection(*(set(groups) for groups in grouped)) if grouped else set()
    assigned = 0
    for signature in sorted(common):
        elements = [groups[signature][0] for groups in grouped if len(groups[signature]) == 1]
        if len(elements) != len(selected) or any('componentKey' in element for element in elements):
            continue
        identity = json.dumps({
            'graphId': graph['id'],
            'frameKey': carousel['frameKey'],
            'signature': signature,
        }, sort_keys=True, separators=(',', ':'))
        key = 'carousel-image-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
        for element in elements:
            element['componentKey'] = key
        assigned += 1
    return assigned


def validate_capture_source(source, label):
    if (not isinstance(source, dict) or set(source) != {'url', 'title', 'browser', 'viewport', 'dpr', 'capturedAt'}
            or not isinstance(source['url'], str) or not re.fullmatch(r'https?://[^\s]{1,500}', source['url'])
            or not isinstance(source['title'], str) or not source['title'].strip() or len(source['title']) > 160
            or not isinstance(source['browser'], str) or not source['browser'].strip() or len(source['browser']) > 120
            or not isinstance(source['viewport'], dict) or set(source['viewport']) != {'width', 'height'}
            or any(type(source['viewport'][key]) is not int or not 1 <= source['viewport'][key] <= 32768 for key in ('width', 'height'))
            or type(source['dpr']) not in (int, float) or not math.isfinite(source['dpr']) or not 0.1 <= source['dpr'] <= 8
            or not isinstance(source['capturedAt'], str) or len(source['capturedAt']) > 64):
        raise ValueError(label + ' source must pin its page, browser, viewport, DPR, and capture time')


def _evidence_pin(value):
    return (isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and isinstance(value['path'], str) and value['path'] and len(value['path']) <= 500
            and re.fullmatch(r'[a-f0-9]{64}', str(value['sha256'])) is not None)


def validate_tabs(tabs, screens):
    """Validate click-selected panel states. Only observed browser transitions are allowed."""
    if (not isinstance(tabs, dict)
            or set(tabs) != {'frameKey', 'source', 'states', 'initialState', 'transitions'}
            or not isinstance(tabs['frameKey'], str) or not re.fullmatch(r'[\w.-]{1,120}', tabs['frameKey'])):
        raise ValueError('Tabs need a stable frame key and an observed state contract')
    validate_capture_source(tabs['source'], 'Tabs')
    states = tabs['states']
    if not isinstance(states, list) or not 2 <= len(states) <= 16:
        raise ValueError('Tabs require two to sixteen observed panel states')
    by_screen = {screen['id']: screen for screen in screens}
    state_screens, contents = {}, set()
    for index, state in enumerate(states):
        if (not isinstance(state, dict) or set(state) != {'id', 'screenId', 'index', 'label', 'contentSha256', 'capture'}
                or not isinstance(state['id'], str) or not re.fullmatch(r'[\w.-]{1,120}', state['id'])
                or state['id'] in state_screens or type(state['index']) is not int or state['index'] != index
                or state['screenId'] not in by_screen or state['screenId'] in state_screens.values()
                or not isinstance(state['label'], str) or not state['label'].strip() or len(state['label']) > 160
                or not re.fullmatch(r'[a-f0-9]{64}', str(state['contentSha256'])) or state['contentSha256'] in contents
                or not _evidence_pin(state['capture'])):
            raise ValueError('Tab states need unique screens, panel content hashes, labels, and screenshot pins')
        state_screens[state['id']] = state['screenId']
        contents.add(state['contentSha256'])
    if tabs['initialState'] not in state_screens:
        raise ValueError('Tabs must name their observed initial state')
    transitions = tabs['transitions']
    if not isinstance(transitions, list) or not 1 <= len(transitions) <= 80:
        raise ValueError('Tabs need a bounded list of observed transitions')
    ids, sources, reached = set(), set(), {tabs['initialState']}
    for edge in transitions:
        if (not isinstance(edge, dict)
                or set(edge) != {'id', 'from', 'to', 'trigger', 'controlElementId', 'observed', 'evidence'}
                or not isinstance(edge['id'], str) or not re.fullmatch(r'[\w.-]{1,120}', edge['id']) or edge['id'] in ids
                or edge['from'] not in state_screens or edge['to'] not in state_screens or edge['from'] == edge['to']
                or edge['trigger'] != 'click' or edge['observed'] is not True or not _evidence_pin(edge['evidence'])
                or not isinstance(edge['controlElementId'], str)):
            raise ValueError('Tab transitions must be observed clicks between two different states with screenshot evidence')
        control = (edge['from'], edge['controlElementId'])
        if control in sources:
            raise ValueError('A tab control can lead to only one observed destination')
        source_screen = by_screen[state_screens[edge['from']]]
        if not any(element['id'] == edge['controlElementId'] and element['kind'] == 'frame'
                   for element in source_screen['elements']):
            raise ValueError('Tab transitions must start at a captured frame in the source state screen')
        ids.add(edge['id'])
        sources.add(control)
        reached.add(edge['to'])
    if reached != set(state_screens):
        raise ValueError('Every tab state must be the initial state or an observed destination')
    for state in states:
        layout = by_screen[state['screenId']]['layout']
        viewport = tabs['source']['viewport']
        if layout['height'] != viewport['height'] or not 0 <= viewport['width'] - layout['width'] <= 24:
            raise ValueError('Captured tab screens must match the browser viewport, allowing only a scrollbar gutter')
    return tabs


def validate_carousel(carousel, screens):
    """Validate a finite, ordered carousel and its explicit deterministic edges."""
    required = {'frameKey', 'states', 'initialState', 'autoplay', 'wrap', 'transitions', 'source'}
    optional = {'controls'}
    if (not isinstance(carousel, dict) or not required <= carousel.keys()
            or carousel.keys() - required - optional
            or not isinstance(carousel['frameKey'], str)
            or not re.fullmatch(r'[\w.-]{1,120}', carousel['frameKey'])):
        raise ValueError('Carousel needs a stable frame key and bounded finite-state contract')
    validate_capture_source(carousel['source'], 'Carousel')
    states = carousel['states']
    if not isinstance(states, list) or not 2 <= len(states) <= 16:
        raise ValueError('Carousel requires two to sixteen ordered states')
    state_ids, screen_ids = set(), set()
    for index, state in enumerate(states):
        if (not isinstance(state, dict) or set(state) != {'id', 'screenId', 'index', 'railBounds', 'capture'}
                or not isinstance(state['id'], str) or not re.fullmatch(r'[\w.-]{1,120}', state['id'])
                or not isinstance(state['screenId'], str) or not re.fullmatch(r'WEB-[A-Za-z0-9_.:-]{1,120}', state['screenId'])
                or type(state['index']) is not int or state['index'] != index
                or state['id'] in state_ids or state['screenId'] in screen_ids):
            raise ValueError('Carousel states need unique IDs, screens, and consecutive ordered indices')
        _box(state['railBounds'])
        state_ids.add(state['id'])
        screen_ids.add(state['screenId'])
    wrap = carousel['wrap']
    if (not isinstance(carousel['initialState'], str) or carousel['initialState'] not in state_ids
            or not isinstance(wrap, dict) or set(wrap) != {'manual', 'autoplay'}
            or any(type(value) is not bool for value in wrap.values())):
        raise ValueError('Carousel initial state and trigger-specific wrap settings must be declared')
    autoplay = carousel['autoplay']
    if (not isinstance(autoplay, dict) or set(autoplay) != {'enabled', 'intervalMs'}
            or type(autoplay['enabled']) is not bool or type(autoplay['intervalMs']) is not int
            or not 1000 <= autoplay['intervalMs'] <= 60000):
        raise ValueError('Carousel autoplay interval must be bounded from 1000 to 60000 ms')
    transitions = carousel['transitions']
    if not isinstance(transitions, list) or not 1 <= len(transitions) <= 80:
        raise ValueError('Carousel transitions must be a bounded explicit edge list')
    seen_ids, pairs, triggers = set(), set(), set()
    state_order = [state['id'] for state in states]
    for transition in transitions:
        if (not isinstance(transition, dict) or set(transition) - {'id', 'from', 'trigger', 'to', 'evidence', 'observed'}
                or not {'id', 'from', 'trigger', 'to', 'observed'} <= transition.keys()
                or not isinstance(transition['id'], str) or not re.fullmatch(r'[\w.-]{1,120}', transition['id'])
                or transition['id'] in seen_ids
                or not all(isinstance(transition[field], str) for field in ('from', 'to', 'trigger'))
                or transition['from'] not in state_ids or transition['to'] not in state_ids
                or transition['trigger'] not in CAROUSEL_TRIGGERS):
            raise ValueError('Carousel transitions need unique IDs and declared state/trigger endpoints')
        if type(transition['observed']) is not bool:
            raise ValueError('Carousel transition observation status must be boolean')
        if transition['observed'] and 'evidence' not in transition:
            raise ValueError('Observed carousel transitions need a concrete evidence reference')
        evidence = transition.get('evidence')
        if transition['observed'] and (not isinstance(evidence, dict) or set(evidence) != {'path', 'sha256'}
                or not isinstance(evidence['path'], str) or not evidence['path'] or len(evidence['path']) > 500
                or not re.fullmatch(r'[a-f0-9]{64}', str(evidence['sha256']))):
            raise ValueError('Observed carousel transitions need a screenshot path and SHA-256 receipt')
        if evidence is not None and not transition['observed']:
            raise ValueError('Inferred carousel transitions cannot claim observed screenshot evidence')
        seen_ids.add(transition['id'])
        pair = (transition['from'], transition['trigger'])
        if pair in pairs:
            raise ValueError('Carousel must have at most one deterministic edge per state and trigger')
        pairs.add(pair)
        triggers.add(transition['trigger'])
        index = state_order.index(transition['from'])
        forward = transition['trigger'] in {'next', 'swipe_left', 'autoplay'}
        target_index = (index + (1 if forward else -1)) % len(states)
        does_wrap = wrap['autoplay'] if transition['trigger'] == 'autoplay' else wrap['manual']
        if not does_wrap and ((forward and index == len(states) - 1) or (not forward and index == 0)):
            target_index = index
        if transition['to'] != state_order[target_index]:
            raise ValueError('Carousel transition destination must match its declared order and wrap behavior')
    if autoplay['enabled'] != ('autoplay' in triggers):
        raise ValueError('Enabled carousel autoplay requires explicit autoplay edges, and disabled autoplay forbids them')
    if any((state_id, trigger) not in pairs for state_id in state_ids for trigger in triggers):
        raise ValueError('Every carousel state requires one edge for every declared trigger')
    controls = carousel.get('controls', {})
    if (not isinstance(controls, dict) or set(controls) - {'nextElementId', 'previousElementId'}
            or any(not isinstance(value, str) or not value for value in controls.values())):
        raise ValueError('Carousel controls must reference captured next/previous elements')
    if (('nextElementId' in controls and 'next' not in triggers)
            or ('previousElementId' in controls and 'previous' not in triggers)):
        raise ValueError('Each captured carousel control requires its matching transition edges')
    if (('next' in triggers and not controls.get('nextElementId'))
            or ('previous' in triggers and not controls.get('previousElementId'))):
        raise ValueError('Next and previous transitions require their captured controls')
    if screens is not None:
        by_screen = {screen['id']: screen for screen in screens}
        if not screen_ids <= by_screen.keys():
            raise ValueError('Carousel state screens must exist in the canonical graph')
        for state in states:
            bounds = state['railBounds']
            layout = by_screen[state['screenId']]['layout']
            if (bounds['x'] < 0 or bounds['y'] < 0 or bounds['width'] <= 0 or bounds['height'] <= 0
                    or bounds['x'] + bounds['width'] > layout['width'] + 1
                    or bounds['y'] + bounds['height'] > layout['height'] + 1):
                raise ValueError('Carousel rail bounds must fit each captured screen viewport')
            capture = state.get('capture')
            if (not isinstance(capture, dict) or set(capture) != {'path', 'sha256'}
                    or not isinstance(capture['path'], str) or not capture['path'] or len(capture['path']) > 500
                    or not re.fullmatch(r'[a-f0-9]{64}', str(capture['sha256']))):
                raise ValueError('Each carousel state needs a screenshot path and SHA-256 capture pin')
        if controls:
            if any(any(value not in {element['id'] for element in screen['elements']} for screen in screens)
                   for value in controls.values()):
                raise ValueError('Carousel controls must reference elements captured in every state screen')
    return carousel


def validate_interaction_evidence(graph_path, graph):
    interaction = graph.get('carousel') or graph.get('tabs')
    if interaction is None:
        return
    root = Path(graph_path).resolve().parent
    pins = [state['capture'] for state in interaction['states']]
    pins.extend(edge['evidence'] for edge in interaction['transitions'] if edge['observed'])
    unique = {}
    total = 0
    for pin in pins:
        relative = Path(pin['path'])
        if (relative.is_absolute() or '..' in relative.parts or not relative.parts
                or any(char in pin['path'] for char in ':\\\0\n\r')):
            raise ValueError('Interaction evidence paths must stay relative to the canonical graph')
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError('Interaction evidence path cannot cross a symbolic link')
        if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
            raise ValueError('Pinned interaction evidence file is missing or outside the graph directory')
        data = candidate.read_bytes()
        if len(data) > 8_000_000 or not valid_png(data):
            raise ValueError('Interaction evidence must be a bounded PNG screenshot')
        if hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise ValueError('Pinned interaction evidence SHA-256 changed')
        if pin['sha256'] not in unique:
            unique[pin['sha256']] = len(data)
            total += len(data)
            if total > 8_000_000:
                raise ValueError('Unique interaction screenshots exceed the 8 MB evidence limit')


def valid_png(data):
    """Check PNG chunk bounds, CRCs, and viewport dimensions without decoding pixels."""
    if not isinstance(data, bytes) or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    offset, width, height, saw_idat, saw_iend = 8, None, None, False, False
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset:offset + 4], 'big')
        chunk_type = data[offset + 4:offset + 8]
        end = offset + 8 + size
        if end + 4 > len(data):
            return False
        payload = data[offset + 8:end]
        crc = int.from_bytes(data[end:end + 4], 'big')
        if zlib.crc32(chunk_type + payload) & 0xffffffff != crc:
            return False
        if offset == 8:
            if chunk_type != b'IHDR' or size != 13:
                return False
            width = int.from_bytes(payload[:4], 'big')
            height = int.from_bytes(payload[4:8], 'big')
            if not 1 <= width <= 32768 or not 1 <= height <= 32768:
                return False
        elif chunk_type == b'IHDR':
            return False
        if chunk_type == b'IDAT':
            saw_idat = True
        if chunk_type == b'IEND':
            if size != 0 or end + 4 != len(data):
                return False
            saw_iend = True
            break
        offset = end + 4
    return bool(width and height and saw_idat and saw_iend)


def _read_join_inputs(graph_path, observation_path, out_path):
    source = Path(graph_path).expanduser().absolute()
    observations_file = Path(observation_path).expanduser().absolute()
    output = Path(out_path).expanduser().absolute()
    if any(path.is_symlink() or not path.is_file() for path in (source, observations_file)):
        raise ValueError('Graph and browser observation inputs must be regular local files')
    graph_bytes, observation_bytes = source.read_bytes(), observations_file.read_bytes()
    if len(graph_bytes) > 12_000_000 or len(observation_bytes) > 4_000_000:
        raise ValueError('Bounded canonical graph and browser observation inputs required')
    graph, observations = json.loads(graph_bytes), json.loads(observation_bytes)
    if not isinstance(graph, dict) or not isinstance(observations, dict):
        raise ValueError('Canonical graph and browser observations must be JSON objects')
    if graph.get('carousel') is not None or graph.get('tabs') is not None:
        raise ValueError('Refusing to replace an existing canonical interaction')
    if output.parent != observations_file.parent:
        raise ValueError('Joined graph must stay beside its browser evidence so relative pins remain valid')
    return graph, observations, output


def _write_joined_graph(output, graph):
    validate_interaction_evidence(output, graph)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing to overwrite canonical graph: {output}')
    output.write_text(json.dumps(graph, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    output.chmod(0o600)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def join_tab_observations(graph_path, observation_path, out_path):
    """Join observed tab clicks to an existing captured-screen graph without inferring unobserved edges."""
    graph, observations, output = _read_join_inputs(graph_path, observation_path, out_path)
    if (observations.get('schemaVersion') != 1 or not isinstance(observations.get('tabs'), dict)
            or not isinstance(observations.get('states'), list) or not isinstance(observations.get('transitions'), list)):
        raise ValueError('Versioned browser tab observations are required')
    validate_graph(graph)
    screen_ids = [state.get('id') if isinstance(state, dict) else None for state in observations['states']]
    if not 2 <= len(screen_ids) <= 16 or any(not isinstance(item, str) for item in screen_ids) or len(set(screen_ids)) != len(screen_ids):
        raise ValueError('Browser evidence must contain two to sixteen distinct tab states')
    keys = {screen_id: f'tab-{index + 1}' for index, screen_id in enumerate(screen_ids)}
    measured = observations['tabs']
    if measured.get('initialState') not in keys:
        raise ValueError('Browser evidence must name its observed initial tab state')
    transitions = []
    for index, item in enumerate(observations['transitions']):
        if not isinstance(item, dict) or item.get('from') not in keys or item.get('to') not in keys or item.get('input') != 'click':
            raise ValueError('Browser tab receipts must be clicks between known states')
        transitions.append({'id': f'edge-{index + 1}', 'from': keys[item['from']], 'to': keys[item['to']], 'trigger': 'click',
                            'controlElementId': item.get('controlElementId'), 'observed': item.get('observed'),
                            'evidence': item.get('evidence')})
    graph['tabs'] = {
        'frameKey': measured.get('frameKey'),
        'source': observations.get('source'),
        'states': [{'id': keys[state['id']], 'screenId': state['id'], 'index': index, 'label': state.get('label'),
                    'contentSha256': state.get('contentSha256'), 'capture': state.get('capture')}
                   for index, state in enumerate(observations['states'])],
        'initialState': keys[measured['initialState']],
        'transitions': transitions,
    }
    validate_graph(graph)
    graph_sha256 = _write_joined_graph(output, graph)
    return {'graph': str(output), 'state_count': len(screen_ids), 'transition_count': len(transitions),
            'graph_sha256': graph_sha256, 'status': 'compiled-not-applied'}


def join_carousel_observations(graph_path, observation_path, out_path):
    """Join bounded browser interaction receipts to an existing captured-screen graph."""
    graph, observations, output = _read_join_inputs(graph_path, observation_path, out_path)
    if (not isinstance(observations, dict) or observations.get('schemaVersion') != 1
            or not isinstance(observations.get('carousel'), dict)
            or not isinstance(observations.get('states'), list)
            or not isinstance(observations.get('transitions'), list)):
        raise ValueError('Versioned browser carousel observations are required')
    captured_screens = validate_graph(graph)
    measured = observations['carousel']
    state_ids = measured.get('stateIds')
    states_by_id = {state.get('id'): state for state in observations['states']
                    if isinstance(state, dict) and isinstance(state.get('id'), str)}
    if (not isinstance(state_ids, list) or not 2 <= len(state_ids) <= 16
            or any(not isinstance(state_id, str) for state_id in state_ids) or len(set(state_ids)) != len(state_ids)
            or len(observations['states']) != len(state_ids) or set(states_by_id) != set(state_ids)):
        raise ValueError('Browser evidence must contain two to sixteen ordered carousel states')
    for index, state in enumerate(observations['states']):
        if (not isinstance(state, dict) or state.get('id') != state_ids[index]
                or ('index' in state and (type(state['index']) is not int or state['index'] != index))):
            raise ValueError('Browser state records must match the declared state order and indices')
    screen_ids = {screen['id'] for screen in captured_screens}
    if not set(state_ids) <= screen_ids:
        raise ValueError('Each observed carousel state must have its captured canonical WEB screen')
    index_by_id = {screen_id: index for index, screen_id in enumerate(state_ids)}
    state_keys = {screen_id: f'feature-{index + 1}' for screen_id, index in index_by_id.items()}
    transitions = []
    for index, item in enumerate(observations['transitions']):
        if not isinstance(item, dict):
            raise ValueError('Browser transition receipt must be an object')
        source_id = item.get('from')
        target_id = item.get('to')
        raw_trigger = item.get('input')
        if type(item.get('observed')) is not bool:
            raise ValueError('Browser transition receipt must mark observed status as a boolean')
        if not all(isinstance(value, str) for value in (source_id, target_id, raw_trigger)):
            raise ValueError('Browser transition receipt must use string state and input IDs')
        trigger = {'swipe-left': 'swipe_left', 'swipe_right': 'swipe_right', 'swipe-right': 'swipe_right',
                   'swipe_left': 'swipe_left', 'next': 'next', 'previous': 'previous', 'autoplay': 'autoplay'}.get(raw_trigger)
        if source_id not in state_keys or target_id not in state_keys or trigger is None:
            raise ValueError('Browser transition receipt must name known states and supported input')
        transition = {'id': f"edge-{index + 1}", 'from': state_keys[source_id], 'to': state_keys[target_id],
                      'trigger': trigger, 'observed': item['observed']}
        evidence = item.get('evidence')
        if evidence is not None:
            transition['evidence'] = evidence
        transitions.append(transition)
    wrap = measured.get('wrap')
    if isinstance(wrap, dict):
        manual_wrap, autoplay_wrap = wrap.get('manual'), wrap.get('autoplay')
    else:
        manual_wrap, autoplay_wrap = measured.get('manualWrap'), measured.get('wrapAutoplay')
    if type(manual_wrap) is not bool or type(autoplay_wrap) is not bool:
        raise ValueError('Browser evidence must explicitly establish manual and autoplay wrap behavior')
    active_id = measured.get('initialState')
    if not isinstance(active_id, str) or active_id not in state_keys:
        raise ValueError('Browser evidence must name its observed initial state')
    rail = measured.get('rail')
    rail_bounds = rail.get('rect') if isinstance(rail, dict) else None
    autoplay_enabled = measured.get('autoplayEnabled', type(measured.get('intervalMs')) is int and measured['intervalMs'] > 0)
    if type(autoplay_enabled) is not bool:
        raise ValueError('Browser autoplay enabled state must be boolean')
    carousel = {
        'frameKey': measured.get('frameKey'),
        'source': observations.get('source'),
        'states': [{'id': state_keys[screen_id], 'screenId': screen_id, 'index': index,
                    'railBounds': rail_bounds, 'capture': states_by_id[screen_id].get('capture')}
                   for index, screen_id in enumerate(state_ids)],
        'initialState': state_keys[active_id],
        'autoplay': {'enabled': autoplay_enabled,
                     'intervalMs': measured.get('intervalMs')},
        'wrap': {'manual': manual_wrap, 'autoplay': autoplay_wrap},
        'transitions': transitions,
    }
    graph['carousel'] = carousel
    shared_image_main_count = derive_repeated_carousel_images(graph)
    screens = validate_graph(graph)
    screens_by_id = {screen['id']: screen for screen in screens}
    for state_id in state_ids:
        layout = screens_by_id[state_id]['layout']
        if (layout['width'] != observations['source'].get('viewport', {}).get('width')
                or layout['height'] != observations['source'].get('viewport', {}).get('height')):
            raise ValueError('Captured screen dimensions must match the browser observation viewport')
    if len({screen['id'] for screen in screens} & set(state_ids)) != len(state_ids):
        raise ValueError('Canonical graph carousel must resolve every captured state screen')
    graph_sha256 = _write_joined_graph(output, graph)
    return {'graph': str(output), 'state_count': len(state_ids), 'transition_count': len(transitions),
            'shared_image_main_count': shared_image_main_count,
            'graph_sha256': graph_sha256, 'status': 'compiled-not-applied'}


def build_plan(graph_path, file_key, page_id, out, screen_ids=None, preview_width=None, readback_scope='page'):
    source = Path(graph_path).expanduser().absolute()
    if source.is_symlink() or not source.is_file():
        raise ValueError('Canonical graph must be a regular local file')
    raw = source.read_bytes()
    if len(raw) > 12_000_000:
        raise ValueError('Bounded source graph required')
    graph = json.loads(raw)
    screens = validate_graph(graph)
    if screen_ids:
        unknown = set(screen_ids) - {screen['id'] for screen in screens}
        if unknown:
            raise ValueError('Requested WEB screen ID is not in source graph: ' + ', '.join(sorted(unknown)))
        screens = [screen for screen in screens if screen['id'] in set(screen_ids)]
    if len(screens) > 16:
        raise ValueError('Select at most sixteen screens per native edit with --screen')
    if preview_width is not None and (type(preview_width) is not int or not 360 <= preview_width <= 480):
        raise ValueError('Preview width must be between 360 and 480 pixels')
    screens = json.loads(json.dumps(screens))
    web = {
        'schema': SCHEMA,
        'graph_id': graph['id'],
        'graph_sha256': hashlib.sha256(raw).hexdigest(),
        'source_graph_path': str(source.resolve()),
        'screens': screens,
    }
    if graph.get('carousel') is not None:
        carousel = json.loads(json.dumps(graph['carousel']))
        if not {state['screenId'] for state in carousel['states']} <= {screen['id'] for screen in screens}:
            raise ValueError('Selected screens must include every carousel state')
        web['carousel'] = carousel
    if graph.get('tabs') is not None:
        if not {state['screenId'] for state in graph['tabs']['states']} <= {screen['id'] for screen in screens}:
            raise ValueError('Selected screens must include every tab state')
        web['tabs'] = json.loads(json.dumps(graph['tabs']))
    if readback_scope not in ('page', 'screens'):
        raise ValueError('Unknown web design readback scope')
    if readback_scope == 'screens':
        web['readback_scope'] = readback_scope
    if preview_width is not None:
        web['preview_width'] = preview_width
    plan = {
        'schema': 'figma-flow-native-edit-plan-v1',
        'file_key': file_key,
        'page_id': page_id,
        'web_design': web,
    }
    output = Path(out).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing to overwrite web design plan: {output}')
    output.write_text(
        json.dumps(plan, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8'
    )
    output.chmod(0o600)
    return {
        'plan': str(output),
        'screen_count': len(screens),
        'graph_sha256': plan['web_design']['graph_sha256'],
        'status': 'prepared-not-executed',
    }
