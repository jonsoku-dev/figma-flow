#!/usr/bin/env python3
"""Create a new capture using an exact canvas-bounds crop from a supplied screenshot."""
import argparse
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import sys


def canvas_capture(source, screenshot, canvas_id, extent):
    try:
        from PIL import Image
    except ImportError as error:
        raise ValueError('Install Pillow to crop a supplied screenshot') from error

    capture = json.loads(Path(source).read_bytes())
    original = Path(screenshot).read_bytes()
    try:
        image = Image.open(io.BytesIO(original)).convert('RGBA')
    except Exception as error:
        raise ValueError('Supplied screenshot must be a readable raster image') from error

    captured_extent = capture.get('extent')
    if extent not in ('viewport', 'document') or captured_extent not in ('viewport', 'document'):
        raise ValueError('Capture and screenshot extents must be viewport or document')
    reference = capture['viewport'] if extent == 'viewport' else capture['screen']['layout']
    if extent == 'document' and captured_extent == 'viewport':
        raise ValueError('Document screenshots need a full-document capture with document dimensions')
    ratio_x = image.width / reference['width']
    ratio_y = image.height / reference['height']
    if captured_extent == 'document' and extent == 'viewport':
        if 'scrollPosition' not in capture:
            raise ValueError('Document capture needs its measured scroll position for a viewport screenshot')
        x_offset, y_offset = capture['scrollPosition']['x'], capture['scrollPosition']['y']
    else:
        x_offset = y_offset = 0
    if not math.isclose(ratio_x, ratio_y, rel_tol=0, abs_tol=0.002) or ratio_x <= 0:
        raise ValueError('Screenshot aspect scale does not match the declared screenshot extent')

    matches = [item for item in capture.get('canvases', []) if item.get('id') == canvas_id]
    if len(matches) != 1:
        raise ValueError('Choose exactly one canvas ID from the measured capture')
    item = matches[0]
    canvas = item.get('canvas')
    if not isinstance(canvas, dict):
        raise ValueError('Selected canvas has no measured metadata')
    if canvas.get('status') == 'captured':
        raise ValueError('Canvas already has origin-clean pixels; keep its native canvas capture')

    box = item['box']
    left = round((box['x'] - x_offset) * ratio_x)
    top = round((box['y'] - y_offset) * ratio_y)
    right = round((box['x'] + box['width'] - x_offset) * ratio_x)
    bottom = round((box['y'] + box['height'] - y_offset) * ratio_y)
    if left < 0 or top < 0 or right > image.width or bottom > image.height or right <= left or bottom <= top:
        raise ValueError('Canvas bounds fall outside the supplied screenshot; use a matching page extent and scroll')
    crop = image.crop((left, top, right, bottom))
    output = io.BytesIO()
    crop.save(output, format='PNG')
    png = output.getvalue()
    original_status = canvas.get('status')
    original_reason = canvas.get('reason')
    canvas['originalDimensions'] = {'width': canvas['width'], 'height': canvas['height']}
    canvas['width'], canvas['height'] = crop.size
    canvas['pixelRatioX'] = (right - left) / box['width'] if box['width'] else None
    canvas['pixelRatioY'] = (bottom - top) / box['height'] if box['height'] else None
    canvas.update(status='captured', captureMode='user-supplied-screenshot-crop', mimeType='image/png',
                  dataUrl='data:image/png;base64,' + base64.b64encode(png).decode('ascii'),
                  screenshotSha256=hashlib.sha256(original).hexdigest(), screenshotExtent=extent,
                  screenshotCrop={'x': left, 'y': top, 'width': right-left, 'height': bottom-top})
    canvas['previousStatus'] = original_status
    if original_reason:
        canvas['previousReason'] = original_reason
    return capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--screenshot', required=True, type=Path)
    parser.add_argument('--canvas-id', required=True)
    parser.add_argument('--screenshot-extent', choices=('viewport', 'document'), required=True,
                        help='Extent used when the supplied screenshot was made')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = canvas_capture(args.capture, args.screenshot, args.canvas_id, args.screenshot_extent)
    with args.out.open('x', encoding='utf-8') as destination:
        json.dump(result, destination, ensure_ascii=False, indent=2, allow_nan=False)
        destination.write('\n')
    canvas = next(item['canvas'] for item in result['canvases'] if item.get('id') == args.canvas_id)
    print(json.dumps({'capture': str(args.out.absolute()), 'canvas_id': args.canvas_id,
                      'capture_mode': canvas['captureMode']}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'web_design_canvas_crop: {error}', file=sys.stderr)
        raise SystemExit(2)
