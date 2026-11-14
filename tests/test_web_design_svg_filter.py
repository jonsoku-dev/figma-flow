"""Keep browser-filtered external SVG images editable after media binding."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from web_design_source import bind_screens


class WebDesignSvgFilterTests(unittest.TestCase):
    def test_brightness_zero_chain_keeps_opacity_and_recolors_solid_paints(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                   b'<path fill="#f008" stroke="#0f08" stroke-width="1" d="M0 0h10v10z"/>'
                   b'<path fill="none" stroke="none" d="M1 1h2v2z"/></svg>')
            (root / 'logo.svg').write_bytes(raw)
            url = 'https://assets.example/logo.svg'
            origin = 'http://localhost:8000'
            index = root / 'index.json'
            index.write_text(json.dumps({'assets': [{
                'origin': origin, 'requestTarget': url, 'fetchUrl': url, 'fetchStatus': 200,
                'status': 'available', 'path': 'logo.svg', 'sha256': hashlib.sha256(raw).hexdigest(),
                'mimeType': 'image/svg+xml',
            }]}))
            box = {'x': 0, 'y': 0, 'width': 20, 'height': 20}
            capture = root / 'capture.json'
            capture.write_text(json.dumps({
                'screen': {'id': 'WEB-svg-filter', 'type': 'screen', 'title': 'SVG filter', 'status': 'observed',
                           'layout': {'width': 30, 'height': 30}, 'elements': []},
                'origin': origin, 'pathname': '/', 'observedAt': 'now', 'extent': 'viewport',
                'viewport': {'width': 30, 'height': 30}, 'limitations': [],
                'images': [{'id': 'logo', 'box': box, 'paint': {
                    'opacity': 0.3,
                    'cssFilter': [
                        {'name': 'brightness', 'value': 0},
                        {'name': 'grayscale', 'value': 1},
                        {'name': 'invert', 'value': 1},
                    ],
                    'svgSilhouetteColor': '#ffffff',
                }, 'path': [], 'requestTarget': url, 'position': 0}],
            }))
            graph = root / 'graph.json'
            bind_screens([capture], 'svg-filter', 'SVG filter', graph, index)
            elements = json.loads(graph.read_bytes())['nodes'][0]['elements']
            self.assertEqual(len(elements), 1, 'bound SVG silhouette remains a visible vector')
            layer = elements[0]

        self.assertEqual(layer['kind'], 'vector')
        self.assertEqual(layer['paint']['opacity'], 0.3)
        self.assertEqual(layer['paint']['svgSilhouetteColor'], '#ffffff')
        self.assertIn('fill="#ffffff88"', layer['svg'])
        self.assertIn('stroke="#ffffff88"', layer['svg'])
        self.assertEqual(layer['svg'].count('fill="none"'), 1)
        self.assertEqual(layer['svg'].count('stroke="none"'), 1)


if __name__ == '__main__':
    unittest.main()
