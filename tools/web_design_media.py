"""Collect exact, public browser media requests as hash-pinned local bytes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import ipaddress
from pathlib import Path
import re
import shutil
import socket
import subprocess
import struct
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
import argparse


MAX_MEDIA_BYTES = 8_000_000
MAX_VIDEO_BYTES = 100_000_000
SVG_TAGS = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'defs', 'clipPath', 'linearGradient', 'radialGradient', 'stop'}
SVG_ATTRS = {
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
SVG_COLOR = re.compile(r'#[0-9a-fA-F]{3,4}(?:[0-9a-fA-F]{2})?\Z')


def normalize_svg(data):
    """Strip XML declaration/comments/metadata and emit only native vector primitives."""
    text = data.decode('utf-8')
    if len(data) > 200_000 or re.search(r'<!\s*DOCTYPE|<!\s*ENTITY|<\?(?!xml\s)', text, re.I):
        raise ValueError('SVG has unsafe declarations or exceeds 200 KB')
    text = re.sub(r'<\?xml\s+[^?]*\?>', '', text, count=1, flags=re.I)
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    root = ET.fromstring(text)
    if root.tag.split('}')[-1] != 'svg':
        raise ValueError('SVG root required')
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    count = 0
    clip_ids = set()
    clip_refs = set()
    gradient_ids = set()
    gradient_refs = set()
    safe_id = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,79}\Z')

    def color(value):
        named = {'black': '#000000', 'white': '#ffffff'}
        if value.lower() in named:
            return named[value.lower()]
        if not SVG_COLOR.fullmatch(value):
            return value
        raw = value[1:]
        if len(raw) in (3, 4):
            raw = ''.join(c * 2 for c in raw)
        return '#' + raw

    def clean(node, parent_tag=None):
        nonlocal count
        tag = node.tag.split('}')[-1]
        if tag in ('title', 'desc', 'metadata'):
            return None
        count += 1
        if tag not in SVG_TAGS or count > 1200 or (node.text and node.text.strip()):
            raise ValueError('SVG contains unsupported content')
        attrs = {}
        if tag == 'defs' and parent_tag is not None and parent_tag != 'svg':
            raise ValueError('SVG definitions must be direct children of the root')
        if tag == 'clipPath':
            if parent_tag != 'defs':
                raise ValueError('SVG clipPath definitions must be inside defs')
            if not node.get('id') or not safe_id.fullmatch(node.get('id')) or node.get('id') in clip_ids:
                raise ValueError('SVG clip path needs a unique bounded local ID')
            clip_ids.add(node.get('id'))
        if tag in {'linearGradient', 'radialGradient'}:
            gradient_id = node.get('id')
            if parent_tag != 'defs' or not gradient_id or not safe_id.fullmatch(gradient_id) or gradient_id in gradient_ids:
                raise ValueError('SVG gradients need unique bounded local IDs')
            gradient_ids.add(gradient_id)
            units = node.get('gradientUnits', 'objectBoundingBox')
            if units not in {'objectBoundingBox', 'userSpaceOnUse'}:
                raise ValueError('Unsupported SVG gradient coordinate system')
        for key, value in node.attrib.items():
            name = key.split('}')[-1]
            name = {'stopColor': 'stop-color', 'stopOpacity': 'stop-opacity'}.get(name, name)
            if name in ('id', 'class'):
                if name == 'id' and tag in {'clipPath', 'linearGradient', 'radialGradient'}:
                    attrs[name] = value
                continue
            if tag == 'svg' and name == 'preserveAspectRatio':
                continue
            if name == 'clip-path':
                match = re.fullmatch(r'url\(#([A-Za-z_][A-Za-z0-9_.-]{0,79})\)', value)
                if not match:
                    raise ValueError('SVG clip path references must use a bounded local ID')
                clip_refs.add(match.group(1))
                attrs[name] = value
                continue
            if name in ('fill', 'stroke') and value.startswith('url('):
                match = re.fullmatch(r'url\(#([A-Za-z_][A-Za-z0-9_.-]{0,79})\)', value)
                if not match:
                    raise ValueError('SVG gradient references need a bounded local ID')
                gradient_refs.add(match.group(1))
                attrs[name] = value
                continue
            if name not in SVG_ATTRS[tag] or name.lower().startswith('on') or re.search(
                r'url\s*\(|javascript:|data:|https?:|file:', value, re.I
            ):
                raise ValueError('SVG contains an unsupported or external attribute')
            if name in ('fill', 'stroke') and value not in ('none', 'currentColor'):
                if value.lower() not in ('black', 'white') and not SVG_COLOR.fullmatch(value):
                    raise ValueError('SVG paint must be literal hex colors')
                value = color(value)
            if tag == 'line' and name == 'fill' and value != 'none':
                raise ValueError('SVG line fill must be none')
            if name == 'gradientUnits' and value not in {'objectBoundingBox', 'userSpaceOnUse'}:
                raise ValueError('Unsupported SVG gradient coordinate system')
            if name in {'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'fx', 'fy'}:
                if not re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)%?', value) or abs(float(value.rstrip('%'))) > 32768:
                    raise ValueError('SVG gradient coordinate is outside bounded numeric values')
            if name == 'offset':
                if not re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?|\d+(?:\.\d+)?%)', value):
                    raise ValueError('SVG gradient stop offset must be a normalized number or percentage')
                amount = float(value[:-1]) / 100 if value.endswith('%') else float(value)
                if not 0 <= amount <= 1:
                    raise ValueError('SVG gradient stop offset must be between zero and one')
                value = f'{amount:.6f}'.rstrip('0').rstrip('.')
            if name == 'stop-opacity' and (not re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?)', value) or float(value) > 1):
                raise ValueError('SVG gradient stop opacity must be between zero and one')
            if name == 'stop-color':
                if value.lower() not in ('black', 'white', 'currentcolor') and not SVG_COLOR.fullmatch(value):
                    raise ValueError('SVG gradient stop color must be literal')
                value = color(value)
            attrs[name] = value
        children = [result for child in list(node) if (result := clean(child, tag)) is not None]
        child_tags = [child.tag for child in children]
        if tag == 'defs' and any(child.split('}')[-1] not in {'clipPath', 'linearGradient', 'radialGradient'} for child in child_tags):
            raise ValueError('Only bounded vector definitions are allowed inside SVG defs')
        if tag == 'clipPath' and any(child.split('}')[-1] not in {'path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline'} for child in child_tags):
            raise ValueError('Unsupported geometry in SVG clipPath')
        if tag in {'linearGradient', 'radialGradient'} and (not 1 <= len(children) <= 32 or any(child.split('}')[-1] != 'stop' for child in child_tags)):
            raise ValueError('SVG gradients need one to thirty two literal stop colors')
        if tag == 'stop' and children:
            raise ValueError('SVG gradient stops cannot have child elements')
        out = ET.Element(tag, attrs)
        out.extend(children)
        return out

    tree = clean(root)
    if clip_refs - clip_ids or gradient_refs - gradient_ids:
        raise ValueError('SVG clip or gradient references must resolve to local definitions')
    normalized = ET.tostring(tree, encoding='unicode', short_empty_elements=True)
    if len(normalized) > 200_000:
        raise ValueError('Normalized SVG exceeds 200 KB')
    return normalized


def apply_svg_silhouette(svg, color):
    """Apply a brightness-zero SVG filter result to bounded literal vector paints."""
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(color)):
        return None
    root = ET.fromstring(svg)
    solid = color.lower()
    for node in root.iter():
        for key in ('fill', 'stroke', 'stop-color'):
            value = node.get(key)
            if value is None or value == 'none':
                continue
            if value.lower() == 'currentcolor' or value.startswith('url('):
                return None
            if not re.fullmatch(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?', value):
                return None
            alpha = value[-2:] if len(value) == 9 else ''
            node.set(key, solid + alpha)
    if 'fill' not in root.attrib:
        root.set('fill', solid)
    return ET.tostring(root, encoding='unicode', short_empty_elements=True)


def _no_redirect(self, req, fp, code, msg, headers, newurl):
    raise urllib.error.HTTPError(req.full_url, code, 'redirect refused', headers, fp)


def _origin_tuple(value):
    parts = urlsplit(value)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.path not in ('', '/') or parts.query or parts.fragment):
        raise ValueError('Capture origin must be a credential-free HTTP(S) origin')
    try:
        port = parts.port or (443 if parts.scheme == 'https' else 80)
    except ValueError as error:
        raise ValueError('Capture origin has an invalid port') from error
    return parts.scheme.lower(), parts.hostname.lower().rstrip('.'), port


def _is_local_host(host):
    if host.lower().rstrip('.') == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _public_addresses(host, port):
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        try:
            return [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        except OSError as error:
            raise ValueError('Media hostname did not resolve') from error


def _detected_raster_mime(raw, response_mime):
    if response_mime not in {'image/png', 'image/jpeg', 'image/webp'}:
        return None
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'image/webp'
    return None


def _request_policy(url, page_origin, reviewed_origins):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError('Media URL must be credential-free HTTP(S) without a fragment')
    try:
        target = (parts.scheme.lower(), parts.hostname.lower().rstrip('.'), parts.port or (443 if parts.scheme == 'https' else 80))
    except ValueError as error:
        raise ValueError('Media URL has an invalid port') from error
    page = _origin_tuple(page_origin)
    if _is_local_host(target[1]):
        if target != page or page_origin not in reviewed_origins or target[2] not in {8871, 8872, 8873, 8874}:
            raise ValueError('Loopback media is allowed only at an explicitly reviewed local app origin')
        return
    addresses = _public_addresses(target[1], target[2])
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError('Private, loopback, link-local, and metadata-service media hosts are refused')


def _video_fallback(source, output_dir):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return {'status': 'unavailable', 'reason': 'ffmpeg not installed'}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp = output_dir / (source.stem + '.first-frame.tmp.png')
    result = subprocess.run([
        ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file,pipe',
        '-ss', '0.5', '-i', str(source), '-frames:v', '1', '-vf',
        'scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2', '-an', '-sn', str(temp),
    ], capture_output=True, text=True, timeout=45)
    if result.returncode or not temp.is_file() or not temp.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
        temp.unlink(missing_ok=True)
        return {'status': 'unavailable', 'reason': 'ffmpeg could not extract frame at 0.5 seconds'}
    raw = temp.read_bytes()
    width, height = struct.unpack('>II', raw[16:24])
    digest = hashlib.sha256(raw).hexdigest()
    target = output_dir / (digest + '.png')
    if not target.exists():
        temp.replace(target)
    else:
        temp.unlink(missing_ok=True)
    return {'status': 'available', 'path': target.name, 'sha256': digest, 'mimeType': 'image/png',
            'timestampSeconds': 0.5, 'width': width, 'height': height}


def _video_metadata(source):
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return {'metadataStatus': 'unavailable', 'reason': 'ffprobe not installed'}
    try:
        result = subprocess.run([
            ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-show_entries', 'stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,size',
            '-of', 'json', str(source),
        ], capture_output=True, text=True, timeout=30, check=True)
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        stream = next((item for item in streams if item.get('codec_type') == 'video'), {})
        audio_streams = [item for item in streams if item.get('codec_type') == 'audio']
        fmt = data.get('format', {})
        return {'metadataStatus': 'available', 'codec': stream.get('codec_name'), 'width': stream.get('width'),
                'height': stream.get('height'), 'durationSeconds': float(fmt['duration']) if fmt.get('duration') else None,
                'frameRate': stream.get('avg_frame_rate'), 'audioPresent': bool(audio_streams),
                'audioCodecs': [item.get('codec_name') for item in audio_streams],
                'bytes': int(fmt['size']) if fmt.get('size') else source.stat().st_size}
    except Exception as error:
        return {'metadataStatus': 'unavailable', 'reason': type(error).__name__ + ': ' + str(error)}


def _video_derivative(source, output_dir, source_metadata):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return {'status': 'unavailable', 'reason': 'ffmpeg not installed'}
    if source_metadata.get('metadataStatus') != 'available':
        return {'status': 'unavailable', 'reason': 'source video metadata unavailable'}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp = output_dir / (source.stem + '.bounded.tmp.mp4')
    command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file,pipe',
               '-i', str(source), '-map', '0:v:0', '-map', '0:a?', '-vf',
               'scale=480:-2:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=12',
               '-c:v', 'libx264', '-crf', '29', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart']
    if source_metadata.get('audioPresent'):
        command += ['-c:a', 'aac', '-b:a', '96k']
    else:
        command += ['-an']
    command.append(str(temp))
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode or not temp.is_file():
        temp.unlink(missing_ok=True)
        return {'status': 'unavailable', 'reason': 'ffmpeg could not produce bounded MP4'}
    raw = temp.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    target = output_dir / (digest + '.mp4')
    if not target.exists():
        temp.replace(target)
    else:
        temp.unlink(missing_ok=True)
    metadata = _video_metadata(target)
    if metadata.get('metadataStatus') != 'available' or metadata.get('audioPresent') != source_metadata.get('audioPresent'):
        target.unlink(missing_ok=True)
        return {'status': 'unavailable', 'reason': 'derived video metadata failed input contract validation'}
    if metadata['width'] > 480 or not metadata['durationSeconds'] or abs(metadata['durationSeconds'] - source_metadata['durationSeconds']) > 0.08:
        target.unlink(missing_ok=True)
        return {'status': 'unavailable', 'reason': 'derived video exceeds width or duration fidelity bound'}
    return {'status': 'available', 'path': target.name, 'sha256': digest, 'mimeType': 'video/mp4',
            'bytes': len(raw), 'encoding': {'tool': 'ffmpeg', 'videoCodec': 'libx264', 'crf': 29,
                'frameRate': '12 fps', 'maxWidth': 480, 'audio': 'AAC 96 kbps preserved' if source_metadata.get('audioPresent') else 'source has no audio',
                'durationSeconds': metadata['durationSeconds'], 'width': metadata['width'], 'height': metadata['height']}}


def _fetch(url, is_video=False, page_origin=None, reviewed_origins=()):
    try:
        if not page_origin:
            raise ValueError('Capture page origin is required for media fetch policy')
        _request_policy(url, page_origin, reviewed_origins)
        no_redirect = type('NoRedirect', (urllib.request.HTTPRedirectHandler,), {'redirect_request': _no_redirect})()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), no_redirect)
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; figma-flow-reviewed-media/1.0)'})
        with opener.open(request, timeout=15) as response:
            final_url = response.geturl()
            if final_url != url:
                return {'url': url, 'status': 'unavailable', 'reason': 'request redirected'}
            mime = response.headers.get_content_type().lower()
            allowed = ('video/mp4', 'video/webm', 'video/quicktime') if is_video else ('image/png', 'image/jpeg', 'image/webp', 'image/svg+xml')
            if mime not in allowed:
                return {'url': url, 'status': 'unavailable', 'reason': f'unsupported media type: {mime}'}
            max_bytes = MAX_VIDEO_BYTES if is_video else MAX_MEDIA_BYTES
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return {'url': url, 'status': 'unavailable', 'reason': f'media exceeds {max_bytes // 1_000_000} MB'}
            response_mime = mime
            if is_video:
                if not ((mime == 'video/mp4' and len(raw) >= 12 and raw[4:8] == b'ftyp')
                        or (mime == 'video/webm' and raw.startswith(b'\x1a\x45\xdf\xa3'))):
                    return {'url': url, 'status': 'unavailable', 'reason': 'video response MIME and container signature do not match'}
            elif mime != 'image/svg+xml':
                detected = _detected_raster_mime(raw, mime)
                if not detected:
                    return {'url': url, 'status': 'unavailable', 'reason': 'image response MIME and raster signature do not match'}
                mime = detected
            source_raw = raw
            source_digest = hashlib.sha256(source_raw).hexdigest()
            if mime == 'image/svg+xml':
                raw = normalize_svg(source_raw).encode('utf-8')
            digest = hashlib.sha256(raw).hexdigest()
            ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/svg+xml': '.svg',
                   'video/mp4': '.mp4', 'video/webm': '.webm', 'video/quicktime': '.mov'}[mime]
            return {'url': url, 'status': 'available', 'fetchUrl': final_url, 'fetchStatus': response.status,
                    'mimeType': mime, 'responseMimeType': response_mime, 'sha256': digest, 'sourceSha256': source_digest,
                    'sourceBytes': source_raw if mime == 'image/svg+xml' else None,
                    'bytes': raw, 'filename': digest + ext}
    except Exception as error:
        return {'url': url, 'status': 'unavailable', 'reason': type(error).__name__ + ': ' + str(error)}


def collect(surveys, directory, index_path, captures=()):
    """Fetch unique observed img/video-poster/background media and retain failures."""
    targets = set()
    video_targets = set()
    for path in surveys:
        survey = json.loads(Path(path).read_bytes())
        for image in survey.get('images', []):
            if image.get('url'):
                targets.add((survey['origin'], image['url']))
        for video in survey.get('videos', []):
            if video.get('url'):
                video_targets.add((survey['origin'], video['url']))
            if video.get('poster'):
                targets.add((survey['origin'], video['poster']))
        for paint in survey.get('paint', []):
            if paint.get('url'):
                targets.add((survey['origin'], paint['url']))
    for path in captures:
        capture = json.loads(Path(path).read_bytes())
        for media in capture.get('images', []):
            if media.get('requestTarget'):
                target = (capture['origin'], media['requestTarget'])
                (video_targets if media.get('mediaKind') == 'video' else targets).add(target)
            if media.get('fallbackRequestTarget'):
                targets.add((capture['origin'], media['fallbackRequestTarget']))
    video_targets -= targets
    reviewed_origins = {origin for origin, _ in [*targets, *video_targets]}
    for origin in reviewed_origins:
        _origin_tuple(origin)
    target_kind = {target: False for target in targets}
    target_kind.update({target: True for target in video_targets})
    target_pairs = sorted(target_kind)
    fetched = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch, url, target_kind[(origin, url)], origin, reviewed_origins): (origin, url)
                   for origin, url in target_pairs}
        for future in as_completed(futures):
            fetched[futures[future]] = future.result()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    all_targets = sorted([*targets, *video_targets])
    for origin, url in all_targets:
        result = fetched[(origin, url)]
        record = {'origin': origin, 'requestTarget': url}
        if result['status'] == 'available':
            file = directory / result['filename']
            if not file.exists():
                file.write_bytes(result['bytes'])
            relative = file.resolve().relative_to(Path(index_path).resolve().parent)
            is_video = (origin, url) in video_targets
            record.update(fetchUrl=result['fetchUrl'], fetchStatus=result['fetchStatus'], path=relative.as_posix(),
                          sha256=result['sha256'], sourceSha256=result['sourceSha256'],
                          mimeType=result['mimeType'], mediaKind='video' if is_video else 'image', status='available')
            if is_video:
                metadata = _video_metadata(file)
                record['videoMetadata'] = metadata
                derivative = _video_derivative(file, directory / 'derivatives', metadata)
                if derivative['status'] == 'available':
                    derivative_path = directory / 'derivatives' / derivative['path']
                    derivative['path'] = derivative_path.resolve().relative_to(Path(index_path).resolve().parent).as_posix()
                    record['derivedAsset'] = derivative
                else:
                    record['derivativeStatus'] = derivative
                fallback = _video_fallback(file, directory / 'fallbacks')
                if fallback['status'] == 'available':
                    record['fallbackAsset'] = fallback
                    record['fallbackAsset']['path'] = (Path('media') / 'fallbacks' / fallback['path']).as_posix()
                else:
                    record['fallbackStatus'] = fallback
            if result['sourceBytes'] is not None:
                source_file = directory / 'source' / (result['sourceSha256'] + '.svg')
                source_file.parent.mkdir(parents=True, exist_ok=True)
                if not source_file.exists():
                    source_file.write_bytes(result['sourceBytes'])
                record['sourcePath'] = source_file.resolve().relative_to(Path(index_path).resolve().parent).as_posix()
        else:
            record.update(status=result['status'], reason=result['reason'])
        records.append(record)
    Path(index_path).write_text(json.dumps({'schema': 'figma-flow-pinned-media-v1', 'assets': records}, indent=2) + '\n')
    return {'requests': len(records), 'available': sum(r['status'] == 'available' for r in records),
            'unavailable': sum(r['status'] != 'available' for r in records), 'index': str(index_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--survey', action='append', required=True, type=Path)
    parser.add_argument('--capture', action='append', default=[], type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--index', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(args.survey, args.out_dir, args.index, args.capture), ensure_ascii=False))


if __name__ == '__main__':
    main()
