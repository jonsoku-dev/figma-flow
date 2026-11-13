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

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts'
sys.path.insert(0, str(SCRIPT_ROOT))
from graph import validate_graph as validate_canonical_graph

SCHEMA = 'figma-flow-web-design-v1'
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
        or set(graph) != {'version', 'id', 'title', 'nodes', 'edges'}
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
                    'textAlign',
                    'textAlignHorizontal',
                    'color',
                    'linearGradient',
                    'paintApproximation',
                }:
                    raise ValueError('Unsupported observed text fields')
                if e.get('kind') == 'text' and not isinstance(text.get('characters'), str):
                    raise ValueError('Text characters required')
                for key in ('fontSize', 'fontWeight', 'lineHeight'):
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
    return screens


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
