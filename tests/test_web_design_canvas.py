"""Canvas pixels stay local, immutable and hash-pinned during graph binding."""
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from PIL import Image
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from web_design_source import bind_screens
from web_design_canvas_crop import canvas_capture


def png_1x1():
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0\xff'))
            + chunk(b'IEND', b''))


class CanvasSourceTests(unittest.TestCase):
    def test_captured_canvas_becomes_pinned_raster_and_keeps_source_measurements(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = png_1x1()
            capture = {
                'screen': {'id': 'WEB-canvas', 'type': 'screen', 'title': 'Canvas', 'status': 'observed',
                           'layout': {'width': 300, 'height': 200}, 'elements': []},
                'origin': 'http://localhost:3000', 'pathname': '/', 'observedAt': '2026-11-14T00:00:00Z',
                'extent': 'viewport', 'viewport': {'width': 300, 'height': 200}, 'limitations': [], 'images': [],
                'canvases': [{'id': 'el-1', 'path': [], 'box': {'x': 2, 'y': 3, 'width': 120, 'height': 60},
                    'paint': {}, 'position': 0, 'canvas': {'width': 240, 'height': 120, 'devicePixelRatio': 2,
                    'pixelRatioX': 2, 'pixelRatioY': 2, 'captureMode': 'canvas.toDataURL',
                    'status': 'captured', 'mimeType': 'image/png',
                    'dataUrl': 'data:image/png;base64,' + base64.b64encode(raw).decode()}}],
            }
            capture_path = root / 'capture.json'
            capture_path.write_text(json.dumps(capture))
            graph_path = root / 'graph.json'
            bind_screens([capture_path], 'app', 'Canvas', graph_path)
            graph = json.loads(graph_path.read_bytes())
            image = graph['nodes'][0]['elements'][0]
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(image['kind'], 'image')
            self.assertEqual(image['sourceRole'], 'canvas')
            self.assertEqual(image['sourceDimensions'], {'width': 240, 'height': 120})
            self.assertEqual(image['sourcePixelRatio'], {'x': 2, 'y': 2})
            self.assertEqual(image['asset'], {'path': f'assets/canvas-{digest}.png', 'sha256': digest, 'mimeType': 'image/png'})
            self.assertEqual((root / image['asset']['path']).read_bytes(), raw)
            self.assertEqual(graph['nodes'][1]['canvas_observations'][0]['sha256'], digest)

    def test_unavailable_canvas_is_explicit_and_does_not_fabricate_an_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capture = {'screen': {'id': 'WEB-canvas', 'type': 'screen', 'title': 'Canvas', 'status': 'observed',
                        'layout': {'width': 300, 'height': 200}, 'elements': []},
                'origin': 'http://localhost:3000', 'pathname': '/', 'observedAt': '2026-11-14T00:00:00Z',
                'extent': 'viewport', 'viewport': {'width': 300, 'height': 200},
                'limitations': ['canvas pixels unavailable'], 'images': [],
                'canvases': [{'id': 'el-1', 'path': [], 'box': {'x': 2, 'y': 3, 'width': 120, 'height': 60},
                    'paint': {}, 'position': 0, 'canvas': {'width': 240, 'height': 120,
                    'captureMode': 'canvas.toDataURL', 'status': 'unavailable', 'reason': 'canvas is not origin-clean'}}]}
            capture_path = root / 'capture.json'
            capture_path.write_text(json.dumps(capture))
            graph_path = root / 'graph.json'
            bind_screens([capture_path], 'app', 'Canvas', graph_path)
            graph = json.loads(graph_path.read_bytes())
            self.assertEqual(graph['nodes'][0]['elements'], [])
            self.assertEqual(graph['nodes'][1]['canvas_observations'][0]['status'], 'unavailable')
            self.assertEqual(list(root.glob('assets/*')), [])

    def test_screenshot_fallback_crops_only_measured_canvas_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            screenshot = Image.new('RGB', (600, 400), 'white')
            for x in range(40, 280):
                for y in range(60, 180):
                    screenshot.putpixel((x, y), (12, 34, 56))
            screenshot_path = root / 'screen.png'
            screenshot.save(screenshot_path)
            capture = {'screen': {'id': 'WEB-canvas', 'type': 'screen', 'title': 'Canvas', 'status': 'observed',
                        'layout': {'width': 300, 'height': 200}, 'elements': []},
                'origin': 'http://localhost:3000', 'pathname': '/', 'observedAt': '2026-11-14T00:00:00Z',
                'extent': 'viewport', 'viewport': {'width': 300, 'height': 200}, 'scrollPosition': {'x': 0, 'y': 420},
                'limitations': ['canvas pixels unavailable'], 'images': [],
                'canvases': [{'id': 'el-1', 'path': [], 'box': {'x': 20, 'y': 30, 'width': 120, 'height': 60},
                    'paint': {}, 'position': 0, 'canvas': {'width': 240, 'height': 120,
                    'captureMode': 'canvas.toDataURL', 'status': 'unavailable', 'reason': 'not origin-clean'}}]}
            source_path = root / 'capture.json'
            source_path.write_text(json.dumps(capture))
            fallback = canvas_capture(source_path, screenshot_path, 'el-1', 'viewport')
            canvas = fallback['canvases'][0]['canvas']
            self.assertEqual(canvas['captureMode'], 'user-supplied-screenshot-crop')
            self.assertEqual(canvas['originalDimensions'], {'width': 240, 'height': 120})
            self.assertEqual((canvas['width'], canvas['height']), (240, 120))
            raw = base64.b64decode(canvas['dataUrl'].split(',', 1)[1])
            cropped = Image.open(__import__('io').BytesIO(raw))
            self.assertEqual(cropped.size, (240, 120))
            self.assertEqual(cropped.getpixel((0, 0)), (12, 34, 56, 255))
            self.assertEqual(cropped.getpixel((239, 119)), (12, 34, 56, 255))


if __name__ == '__main__':
    unittest.main()
