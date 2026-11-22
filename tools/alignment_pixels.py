#!/usr/bin/env python3
"""Find rendered pixels removed by hiding one element in bounded viewport screenshots."""
import json
import sys

try:
    from PIL import Image, ImageChops
except ImportError:
    print(json.dumps({'reason': 'pillow-unavailable'}))
    raise SystemExit(0)


def difference_mask(left, right, threshold):
    diff = ImageChops.difference(left.convert('RGB'), right.convert('RGB'))
    largest = ImageChops.lighter(ImageChops.lighter(diff.getchannel('R'), diff.getchannel('G')), diff.getchannel('B'))
    return largest.point(lambda value: 255 if value > threshold else 0)


def main():
    if len(sys.argv) != 10:
        raise SystemExit('usage: alignment_pixels.py before.png hidden.png restored.png width height crop-x crop-y crop-width crop-height')
    before_path, hidden_path, restored_path = sys.argv[1:4]
    width, height = map(int, sys.argv[4:6])
    crop_x, crop_y, crop_width, crop_height = map(float, sys.argv[6:10])
    before, hidden, restored = (Image.open(path).convert('RGB') for path in (before_path, hidden_path, restored_path))
    if any(image.size != (width, height) for image in (before, hidden, restored)):
        print(json.dumps({'reason': 'unexpected-screenshot-size'}))
        return
    left = max(0, int(crop_x))
    top = max(0, int(crop_y))
    right = min(width, int(crop_x + crop_width + 0.999999))
    bottom = min(height, int(crop_y + crop_height + 0.999999))
    if right <= left or bottom <= top:
        print(json.dumps({'reason': 'empty-crop'}))
        return
    before_crop = before.crop((left, top, right, bottom))
    hidden_crop = hidden.crop((left, top, right, bottom))
    restored_crop = restored.crop((left, top, right, bottom))
    unstable = ImageChops.difference(before_crop, restored_crop).getbbox()
    if unstable:
        print(json.dumps({'reason': 'unstable-render'}))
        return
    ink = difference_mask(before_crop, hidden_crop, 0).getbbox()
    if not ink:
        print(json.dumps({'reason': 'empty-ink'}))
        return
    ink_left, ink_top, ink_right, ink_bottom = ink
    if ink_left == 0 or ink_top == 0 or ink_right == right - left or ink_bottom == bottom - top:
        print(json.dumps({'reason': 'ink-touches-crop-edge'}))
        return
    print(json.dumps({'paintedRect': {'x': left + ink_left, 'y': top + ink_top,
                                      'width': ink_right - ink_left, 'height': ink_bottom - ink_top}}))


if __name__ == '__main__':
    main()
