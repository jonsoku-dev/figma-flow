"""Exercise capture-to-graph admission with self-contained local input bytes."""

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from web_design_source import bind_screens


class WebSourceTests(unittest.TestCase):
    def test_binds_only_explicit_local_bytes_and_keeps_paint_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def chunk(tag, data):
                return (
                    struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
                )

            raw = (
                b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(b'\0\0\0\0'))
                + chunk(b'IEND', b'')
            )
            (root / 'pixel.png').write_bytes(raw)
            binding = dict(
                origin='http://localhost:8000',
                requestTarget='/pixel.png',
                path='pixel.png',
                sha256=hashlib.sha256(raw).hexdigest(),
                mimeType='image/png',
            )
            box = dict(x=0, y=0, width=20, height=20)
            element = {'id': 'frame', 'kind': 'frame', 'path': [], 'box': box}
            screen = {
                'id': 'WEB-page',
                'type': 'screen',
                'title': 'Page',
                'status': 'observed',
                'layout': {'width': 300, 'height': 200},
                'elements': [element],
            }
            image = {
                'id': 'photo',
                'path': ['frame'],
                'box': box,
                'paint': {},
                'requestTarget': '/pixel.png',
                'position': 1,
            }
            obs = {
                'screen': screen,
                'origin': binding['origin'],
                'pathname': '/',
                'observedAt': '2026-11-14T00:00:00Z',
                'extent': 'document',
                'viewport': {'width': 300, 'height': 200},
                'limitations': [],
                'images': [image, {**image, 'id': 'missing', 'requestTarget': '/missing.png'}],
            }
            capture = root / 'capture.json'
            capture.write_text(json.dumps(obs))
            index = root / 'index.json'
            index.write_text(json.dumps([binding]))
            graph = root / 'graph.json'
            bind_screens([capture], 'app', 'App', graph, index)
            nodes = json.loads(graph.read_bytes())['nodes']
            self.assertEqual([row['id'] for row in nodes[0]['elements']], ['frame', 'photo'])
            self.assertEqual(nodes[0]['elements'][1]['asset']['sha256'], binding['sha256'])
            self.assertEqual(nodes[1]['omitted_images'], {'unbound local image': 1})
            with self.assertRaises(ValueError):
                bind_screens([capture], 'app', 'App', graph, index)
            (root / 'pixel.png').write_bytes(raw + b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                bind_screens([capture], 'app', 'App', root / 'stale.json', index)
            self.assertFalse((root / 'stale.json').exists())
