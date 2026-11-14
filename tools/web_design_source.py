#!/usr/bin/env python3
"""Bind reviewed browser observations and pinned local images to a canonical graph."""
import argparse
import base64
import binascii
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from web_design import image_signature, validate_graph, validate_svg
from web_design_media import apply_svg_silhouette, normalize_svg


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def video_signature(raw, mime):
    if mime == 'video/mp4':
        return len(raw) >= 12 and raw[4:8] == b'ftyp'
    if mime == 'video/webm':
        return raw.startswith(b'\x1aE\xdf\xa3')
    if mime == 'video/quicktime':
        return len(raw) >= 12 and raw[4:8] == b'ftyp'
    return False


def bind_screens(captures, graph_id, title, output, asset_index=None, *, responsive=False):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new graph output; keep the original observation.')
    bindings = {}
    if asset_index is not None:
        data = json.loads(Path(asset_index).read_bytes())
        records = data.get('assets', []) if isinstance(data, dict) else data
        if not isinstance(records, list):
            raise ValueError('Media index must contain an assets list')
        for asset in records:
            uri = (asset['origin'], asset['requestTarget'])
            if uri in bindings:
                raise ValueError('Ambiguous image binding')
            target = urlsplit(asset['requestTarget'])
            if asset.get('status') == 'unavailable':
                bindings[uri] = asset
                continue
            if target.scheme or target.netloc:
                if target.scheme not in ('http', 'https') or not target.netloc or target.username or target.password:
                    raise ValueError('External media request must be an absolute HTTP(S) URL without credentials')
                if asset.get('fetchUrl') != asset['requestTarget'] or asset.get('fetchStatus') != 200:
                    raise ValueError('External media must pin the exact successful request URL without redirects')
            bindings[uri] = asset
    nodes, edges = [], []
    for path in captures:
        raw = Path(path).read_bytes()
        capture = json.loads(raw)
        screen = capture['screen']
        screen_id = screen['id']
        canvases = capture.get('canvases', [])
        if not isinstance(canvases, list):
            raise ValueError('Canvas observations must be a list')
        if any(not isinstance(e.get('path'), list) for e in [*screen['elements'], *capture['images'], *canvases]):
            raise ValueError('Capture did not retain ancestor paths; remeasure this screen.')
        if any(node['id'] == screen_id for node in nodes):
            raise ValueError('Duplicate captured screen ID')
        # The paint list keeps DOM order, including images at the same index.
        omissions = Counter()
        bound_media = []
        canvas_observations = []
        limitations = list(capture.get('limitations', []))
        media_candidates = sorted([*capture['images'], *canvases], key=lambda item: item.get('position', -1), reverse=True)
        for item in media_candidates:
            if 'canvas' in item:
                canvas = item.get('canvas')
                if not isinstance(canvas, dict) or canvas.get('status') != 'captured':
                    reason = canvas.get('reason', 'canvas pixels unavailable') if isinstance(canvas, dict) else 'canvas pixels unavailable'
                    omissions['canvas pixels unavailable: ' + reason] += 1
                    canvas_observations.append({'id': item.get('id'), 'status': 'unavailable', 'reason': reason})
                    continue
                data_url = canvas.get('dataUrl')
                prefix = 'data:image/png;base64,'
                if not isinstance(data_url, str) or not data_url.startswith(prefix):
                    raise ValueError('Captured canvas must contain a PNG data URL')
                if len(data_url) - len(prefix) > 4 * ((8_000_000 + 2) // 3):
                    raise ValueError('Encoded canvas PNG exceeds the 8 MB limit')
                try:
                    content = base64.b64decode(data_url[len(prefix):], validate=True)
                except (ValueError, binascii.Error) as error:
                    raise ValueError('Captured canvas PNG base64 is invalid') from error
                if len(content) > 8_000_000 or not image_signature(content, 'image/png'):
                    raise ValueError('Captured canvas PNG is invalid or exceeds 8 MB')
                digest = sha(content)
                rel = Path('assets') / f'canvas-{digest}.png'
                asset_dir = output.parent / rel.parent
                if asset_dir.is_symlink() or not asset_dir.resolve().is_relative_to(output.parent.resolve()):
                    raise ValueError('Canvas asset directory must stay inside the graph directory')
                asset_dir.mkdir(parents=True, exist_ok=True)
                file = output.parent / rel
                if file.is_symlink() or not file.resolve().is_relative_to(output.parent.resolve()):
                    raise ValueError('Canvas asset must stay inside the graph directory')
                if file.exists():
                    if not file.is_file() or sha(file.read_bytes()) != digest:
                        raise ValueError('Canvas asset path already contains different bytes')
                else:
                    with file.open('xb') as asset_file:
                        asset_file.write(content)
                layer = {k: item[k] for k in ('id', 'box', 'paint', 'path')}
                layer.update(kind='image', objectFit='contain', sourceRole='canvas',
                             sourceDimensions={'width': canvas.get('width'), 'height': canvas.get('height')},
                             sourcePixelRatio={'x': canvas.get('pixelRatioX'), 'y': canvas.get('pixelRatioY')},
                             asset={'path': rel.as_posix(), 'sha256': digest, 'mimeType': 'image/png'})
                if canvas.get('originalDimensions'):
                    layer['originalCanvasDimensions'] = canvas['originalDimensions']
                screen['elements'].insert(item['position'], layer)
                canvas_observations.append({'id': item.get('id'), 'status': 'captured', 'captureMode': canvas.get('captureMode'),
                    'dimensions': {'width': canvas.get('width'), 'height': canvas.get('height')},
                    'devicePixelRatio': canvas.get('devicePixelRatio'), 'pixelRatioX': canvas.get('pixelRatioX'),
                    'pixelRatioY': canvas.get('pixelRatioY'), 'sha256': digest,
                    **({'originalDimensions': canvas['originalDimensions']} if canvas.get('originalDimensions') else {}),
                    **({'screenshotExtent': canvas['screenshotExtent'], 'screenshotCrop': canvas['screenshotCrop']}
                       if canvas.get('screenshotExtent') and canvas.get('screenshotCrop') else {}),
                    **({'screenshotSha256': canvas['screenshotSha256']} if canvas.get('screenshotSha256') else {})})
                continue
            request_target = item['requestTarget']
            bound_fallback = None
            if not request_target:
                if item.get('mediaKind') == 'video-poster':
                    omissions['video poster absent; generated frame fallback is used'] += 1
                else:
                    omissions['media request unavailable'] += 1
                continue
            key = capture['origin'], request_target
            asset = bindings.get(key)
            if asset is None:
                target = urlsplit(request_target)
                origin = urlsplit(capture['origin'])
                if (target.scheme, target.netloc) == (origin.scheme, origin.netloc) and target.path.startswith('/') and not target.fragment:
                    asset = bindings.get((capture['origin'], target.path + (('?' + target.query) if target.query else '')))
            if not asset:
                omissions['unbound external media' if urlsplit(request_target).scheme and urlsplit(request_target).netloc != urlsplit(capture['origin']).netloc else 'unbound local image'] += 1
                continue
            if asset.get('status') == 'unavailable':
                omissions['unavailable media: ' + asset.get('reason', 'fetch failed')] += 1
                continue
            target = urlsplit(item['requestTarget'])
            origin = urlsplit(capture['origin'])
            external = bool(target.scheme or target.netloc) and (target.scheme, target.netloc) != (origin.scheme, origin.netloc)
            if external:
                if target.scheme not in ('http', 'https') or not target.netloc or target.username or target.password or target.fragment:
                    raise ValueError('Expected an exact external HTTP(S) media request')
                if asset.get('requestTarget') != item['requestTarget']:
                    raise ValueError('External media request does not match the captured URL')
            elif not target.path.startswith('/') or target.fragment:
                raise ValueError('Expected a captured root-relative media request')
            rel = Path(asset['path'])
            if rel.is_absolute() or '..' in rel.parts or not rel.parts:
                raise ValueError('Expected a graph-relative asset file')
            file = output.parent / rel
            if not file.resolve().is_relative_to(output.parent.resolve()) or any(
                part.is_symlink() for part in (file, *file.parents) if part.is_relative_to(output.parent)
            ):
                raise ValueError('Image binding must stay inside the graph asset directory')
            content = file.read_bytes()
            if sha(content) != asset['sha256']:
                raise ValueError('Media content does not match declared SHA-256')
            if asset.get('sourcePath'):
                source_rel = Path(asset['sourcePath'])
                if source_rel.is_absolute() or '..' in source_rel.parts or not source_rel.parts:
                    raise ValueError('Original media bytes must stay under the graph asset directory')
                source_file = output.parent / source_rel
                if not source_file.resolve().is_relative_to(output.parent.resolve()) or any(
                    part.is_symlink() for part in (source_file, *source_file.parents) if part.is_relative_to(output.parent)
                ):
                    raise ValueError('Original media bytes must stay inside the graph asset directory')
                if not source_file.is_file() or sha(source_file.read_bytes()) != asset.get('sourceSha256'):
                    raise ValueError('Original media bytes do not match their source SHA-256')
            layer = {k: item[k] for k in ('id', 'box', 'paint', 'path')}
            layer['paint'] = dict(layer.get('paint') or {})
            if asset.get('mediaKind') == 'video':
                if not video_signature(content, asset['mimeType']):
                    omissions['unsupported video signature'] += 1
                    continue
                derived = asset.get('derivedAsset')
                if not isinstance(derived, dict) or derived.get('status') != 'available':
                    omissions['video derivative unavailable'] += 1
                    continue
                derived_path = Path(derived['path'])
                if derived_path.is_absolute() or '..' in derived_path.parts or not derived_path.parts:
                    raise ValueError('Video derivative must stay under the graph asset directory')
                derived_file = output.parent / derived_path
                if not derived_file.resolve().is_relative_to(output.parent.resolve()) or any(
                    part.is_symlink() for part in (derived_file, *derived_file.parents) if part.is_relative_to(output.parent)
                ):
                    raise ValueError('Video derivative must stay inside the graph asset directory')
                derived_bytes = derived_file.read_bytes()
                if derived['mimeType'] != 'video/mp4' or sha(derived_bytes) != derived['sha256'] or not video_signature(derived_bytes, derived['mimeType']):
                    raise ValueError('Video derivative does not match its pinned MP4 bytes')
                fallback = asset.get('fallbackAsset')
                if not isinstance(fallback, dict) or fallback.get('status') != 'available':
                    omissions['video fallback unavailable'] += 1
                    continue
                poster_target = item.get('fallbackRequestTarget')
                if poster_target:
                    poster = bindings.get((capture['origin'], poster_target))
                    if not poster or poster.get('status') != 'available':
                        omissions['video poster unavailable; generated frame fallback used'] += 1
                    elif poster['mimeType'] not in ('image/png', 'image/jpeg', 'image/webp'):
                        omissions['unsupported video poster type; generated frame fallback used'] += 1
                    else:
                        fallback = {k: poster[k] for k in ('path', 'sha256', 'mimeType')}
                fallback_path = Path(fallback['path'])
                if fallback_path.is_absolute() or '..' in fallback_path.parts or not fallback_path.parts:
                    raise ValueError('Video fallback must stay under the graph asset directory')
                fallback_file = output.parent / fallback_path
                if not fallback_file.resolve().is_relative_to(output.parent.resolve()) or any(
                    part.is_symlink() for part in (fallback_file, *fallback_file.parents) if part.is_relative_to(output.parent)
                ):
                    raise ValueError('Video fallback must stay inside the graph asset directory')
                fallback_bytes = fallback_file.read_bytes()
                if sha(fallback_bytes) != fallback['sha256'] or not image_signature(fallback_bytes, fallback['mimeType']):
                    raise ValueError('Video fallback does not match its pinned PNG bytes')
                layer.update(
                    kind='video',
                    asset={k: derived[k] for k in ('path', 'sha256', 'mimeType')},
                    fallbackAsset={k: fallback[k] for k in ('path', 'sha256', 'mimeType')},
                )
                bound_fallback = fallback
            elif asset['mimeType'] == 'image/svg+xml':
                try:
                    svg = normalize_svg(content)
                    silhouette = layer['paint'].get('svgSilhouetteColor')
                    if layer['paint'].get('cssFilter') and silhouette:
                        filtered = apply_svg_silhouette(svg, silhouette)
                        if filtered is None:
                            layer['paint'].pop('svgSilhouetteColor', None)
                            message = 'unsupported CSS filter on SVG paint'
                            if message not in limitations:
                                limitations.append(message)
                        else:
                            svg = filtered
                    elif layer['paint'].get('cssFilter'):
                        if 'unsupported CSS filter chain' not in limitations:
                            limitations.append('unsupported CSS filter chain')
                    validate_svg(svg)
                except (UnicodeDecodeError, ValueError) as error:
                    omissions['unsupported SVG media'] += 1
                    continue
                layer.update(kind='vector', svg=svg)
            elif asset['mimeType'] in ('image/png', 'image/jpeg', 'image/webp') and image_signature(content, asset['mimeType']):
                if layer['paint'].get('cssFilter'):
                    layer['paint'].pop('svgSilhouetteColor', None)
                    message = 'unsupported CSS filter on raster media'
                    if message not in limitations:
                        limitations.append(message)
                layer.update(kind='image', objectFit=item.get('objectFit', 'cover'),
                             asset={k: asset[k] for k in ('path', 'sha256', 'mimeType')})
            else:
                omissions['unsupported media type or signature'] += 1
                continue
            if target.scheme or target.netloc:
                pin = {'requestTarget': item['requestTarget'], 'path': asset['path'],
                       'sha256': asset['sha256'], 'mimeType': asset['mimeType'],
                       'responseMimeType': asset.get('responseMimeType', asset['mimeType'])}
                if asset.get('mediaKind') == 'video':
                    pin['fallbackAsset'] = {k: bound_fallback[k] for k in ('path', 'sha256', 'mimeType')}
                    pin['sourceAsset'] = {k: asset[k] for k in ('path', 'sha256', 'mimeType')}
                    pin['asset'] = {k: asset['derivedAsset'][k] for k in ('path', 'sha256', 'mimeType')}
                    pin['encoding'] = asset['derivedAsset']['encoding']
                if asset.get('sourcePath'):
                    pin.update(sourcePath=asset['sourcePath'], sourceSha256=asset['sourceSha256'])
                bound_media.append(pin)
            screen['elements'].insert(item['position'], layer)
        evidence_id = 'OBS-' + screen_id
        nodes += [
            screen,
            {
                'id': evidence_id,
                'type': 'reference',
                'title': screen['title'] + ' browser observation',
                'status': 'observed',
                'detail': 'Browser measurement of rendered geometry, CSS and visible text.',
                'capture_sha256': sha(raw),
                'observed_at': capture['observedAt'],
                'origin': capture['origin'],
                'page_path': capture['pathname'],
                'extent': capture['extent'],
                'viewport': capture['viewport'],
                'limitations': limitations,
                'omitted_images': dict(omissions),
                'bound_media': bound_media,
                'canvas_observations': canvas_observations,
            },
        ]
        edges.append({'from': screen_id, 'to': evidence_id, 'type': 'sourced from'})
    graph = {'version': 1, 'id': graph_id, 'title': title, 'nodes': nodes, 'edges': edges}
    if responsive:
        from web_route_graph import link_viewports
        link_viewports(graph)
    else:
        validate_graph(graph)
    with output.open('x', encoding='utf-8') as store:
        json.dump(graph, store, ensure_ascii=False, indent=2, allow_nan=False)
        store.write('\n')
    return {'graph': str(output), 'sha256': sha(output.read_bytes()), 'screens': len(captures)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--id', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--responsive', action='store_true', help='Link each route to its observed viewport screens.')
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                bind_screens(args.capture, args.id, args.title, args.out, args.assets, responsive=args.responsive),
                ensure_ascii=False,
            )
        )
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f'web-design-source: {error}\n')


if __name__ == '__main__':
    main()
