"""Filtered vectors remain present when their source paint cannot be recolored."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from web_design_source import bind_screens


class WebDesignSvgFilterLimitTests(unittest.TestCase):
    def test_unsupported_svg_paint_keeps_source_vector_and_reports_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M0 0h2v2z"/></svg>'
            (root / 'logo.svg').write_bytes(raw)
            url = 'https://assets.example/logo.svg'
            origin = 'http://localhost:8000'
            index = root / 'index.json'
            index.write_text(json.dumps({'assets': [{
                'origin': origin, 'requestTarget': url, 'fetchUrl': url, 'fetchStatus': 200,
                'status': 'available', 'path': 'logo.svg', 'sha256': hashlib.sha256(raw).hexdigest(),
                'mimeType': 'image/svg+xml',
            }]}))
            capture = root / 'capture.json'
            capture.write_text(json.dumps({
                'screen': {'id': 'WEB-svg-limit', 'type': 'screen', 'title': 'SVG limit', 'status': 'observed',
                           'layout': {'width': 20, 'height': 20}, 'elements': []},
                'origin': origin, 'pathname': '/', 'observedAt': 'now', 'extent': 'viewport',
                'viewport': {'width': 20, 'height': 20}, 'limitations': [],
                'images': [{'id': 'logo', 'box': {'x': 0, 'y': 0, 'width': 20, 'height': 20},
                            'paint': {'cssFilter': [{'name': 'brightness', 'value': 0}],
                                      'svgSilhouetteColor': '#ffffff'},
                            'path': [], 'requestTarget': url, 'position': 0}],
            }))
            graph = root / 'graph.json'
            bind_screens([capture], 'svg-limit', 'SVG limit', graph, index)
            data = json.loads(graph.read_bytes())

        layer = data['nodes'][0]['elements'][0]
        evidence = data['nodes'][1]
        self.assertEqual(layer['kind'], 'vector')
        self.assertIn('fill="currentColor"', layer['svg'])
        self.assertNotIn('svgSilhouetteColor', layer['paint'])
        self.assertIn('unsupported CSS filter on SVG paint', evidence['limitations'])
        self.assertEqual(evidence['omitted_images'], {})
