import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from web_design import validate_svg
from web_design_media import _detected_raster_mime, _no_redirect, _request_policy, normalize_svg
from web_design_source import bind_screens


class WebDesignMediaTests(unittest.TestCase):
    def test_redirect_handler_refuses_redirect_without_network(self):
        class Request:
            full_url = 'https://public.example.test/image.png'

        with self.assertRaises(urllib.error.HTTPError) as caught:
            _no_redirect(None, Request(), None, 302, 'Found', {}, 'https://other.example.test/image.png')
        self.assertEqual(caught.exception.code, 302)
        self.assertIn('redirect refused', str(caught.exception))

    def test_media_policy_rejects_unreviewed_private_hosts_and_allows_exact_local_origin(self):
        reviewed = {'http://127.0.0.1:8871'}
        _request_policy('http://127.0.0.1:8871/asset.png', 'http://127.0.0.1:8871', reviewed)
        with self.assertRaisesRegex(ValueError, 'reviewed local app origin'):
            _request_policy('http://127.0.0.1:9999/asset.png', 'http://127.0.0.1:8871', reviewed)
        with self.assertRaisesRegex(ValueError, 'Private'):
            _request_policy('http://169.254.169.254/latest/meta-data', 'https://example.com', reviewed)
        with patch('web_design_media._public_addresses', return_value=[__import__('ipaddress').ip_address('10.0.0.4')]):
            with self.assertRaisesRegex(ValueError, 'Private'):
                _request_policy('https://internal.example.test/image.svg', 'https://example.com', reviewed)

    def test_svg_normalizes_metadata_comments_and_short_hex(self):
        raw = b'''<?xml version="1.0"?>\n<!--export note--><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" preserveAspectRatio="xMidYMid"><title>mark</title><g id="shape" fill="#0D0"><path d="M0 0h2v2z"/></g></svg>'''
        svg = normalize_svg(raw)
        self.assertNotIn('export note', svg)
        self.assertNotIn('preserveAspectRatio', svg)
        self.assertIn('fill="#00DD00"', svg)

    def test_svg_refuses_external_paint_and_unknown_elements(self):
        for raw in (
            b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="url(https://evil)" d="M0 0"/></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            b'<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>',
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_svg(raw)

    def test_svg_keeps_only_resolved_local_clip_paths(self):
        raw = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" fill="none"><defs><clipPath id="clip0"><rect width="2" height="2" fill="white"/></clipPath></defs><g clip-path="url(#clip0)"><path fill="black" d="M0 0h2v2z"/></g></svg>'''
        normalized = normalize_svg(raw)
        self.assertIn('clip-path="url(#clip0)"', normalized)
        self.assertIn('fill="#000000"', normalized)
        with self.assertRaisesRegex(ValueError, 'resolve'):
            normalize_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><g clip-path="url(#missing)"/></svg>')

    def test_svg_keeps_bounded_internal_gradients_and_local_paints(self):
        raw = b'''<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="warm" gradientUnits="userSpaceOnUse" x1="-10" y1="0" x2="10" y2="1"><stop offset="0%" stopColor="#abc"/><stop offset="1" stop-color="white"/></linearGradient></defs><path fill="url(#warm)" d="M0 0h2v2z"/></svg>'''
        normalized = normalize_svg(raw)
        validate_svg(normalized)
        self.assertIn('fill="url(#warm)"', normalized)
        self.assertIn('stop-color="#aabbcc"', normalized)
        with self.assertRaisesRegex(ValueError, 'resolve'):
            normalize_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="url(#missing)" d="M0 0"/></svg>')

    def test_raster_type_follows_verified_signature_and_keeps_response_type(self):
        self.assertEqual(_detected_raster_mime(b'\x89PNG\r\n\x1a\nrest', 'image/jpeg'), 'image/png')
        self.assertEqual(_detected_raster_mime(b'\xff\xd8\xffrest', 'image/png'), 'image/jpeg')
        self.assertIsNone(_detected_raster_mime(b'not an image', 'image/png'))

    def test_external_media_binds_only_exact_verified_request(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path fill="#abc" d="M0 0h2v2z"/></svg>'
            (root / 'media.svg').write_bytes(raw)
            url = 'https://assets.example.test/mark.svg?rev=4'
            index = root / 'index.json'
            index.write_text(json.dumps({'assets': [{
                'origin': 'http://localhost:8000', 'requestTarget': url,
                'fetchUrl': url, 'fetchStatus': 200, 'status': 'available',
                'path': 'media.svg', 'sha256': hashlib.sha256(raw).hexdigest(),
                'mimeType': 'image/svg+xml',
            }]}))
            box = {'x': 0, 'y': 0, 'width': 20, 'height': 20}
            capture = root / 'capture.json'
            capture.write_text(json.dumps({
                'screen': {'id': 'WEB-mark', 'type': 'screen', 'title': 'Mark', 'status': 'observed',
                           'layout': {'width': 30, 'height': 30}, 'elements': []},
                'origin': 'http://localhost:8000', 'pathname': '/', 'observedAt': 'now',
                'extent': 'viewport', 'viewport': {'width': 30, 'height': 30}, 'limitations': [],
                'images': [{'id': 'mark', 'box': box, 'paint': {}, 'path': [],
                            'requestTarget': url, 'position': 0}],
            }))
            graph = root / 'graph.json'
            bind_screens([capture], 'site', 'Site', graph, index)
            node = json.loads(graph.read_bytes())['nodes'][0]['elements'][0]
            self.assertEqual(node['kind'], 'vector')
        self.assertIn('fill="#aabbcc"', node['svg'])

    def test_external_fetch_provenance_requires_exact_url_and_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            index = root / 'index.json'
            index.write_text(json.dumps([{
                'origin': 'http://localhost:8000', 'requestTarget': 'https://a.example/image.png',
                'fetchUrl': 'https://a.example/redirected.png', 'fetchStatus': 200,
                'path': 'image.png', 'sha256': '0' * 64, 'mimeType': 'image/png',
            }]))
            with self.assertRaisesRegex(ValueError, 'without redirects'):
                bind_screens([], 'site', 'Site', root / 'graph.json', index)


if __name__ == '__main__':
    unittest.main()
