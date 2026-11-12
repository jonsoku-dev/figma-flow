"""Duplicate font ingress stays one asset, and a byte change is stale.

The fixture is not a browser load of the font.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import input_effect


class AssetFreshnessFixtureTests(unittest.TestCase):
    def test_duplicate_font_ingress_goes_stale_when_bytes_change(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'css').mkdir()
        (root / 'fonts').mkdir()
        font = root / 'fonts' / 'body.woff2'
        font.write_bytes(b'font-v1')
        (root / 'css' / 'a.css').write_text('@font-face { src: url(../fonts/body.woff2); }', encoding='utf-8')
        (root / 'css' / 'b.css').write_text('@font-face { src: url(../fonts/body.woff2); }', encoding='utf-8')
        page = root / 'index.html'
        page.write_text('<link rel="stylesheet" href="css/a.css"><link rel="stylesheet" href="css/b.css">', encoding='utf-8')
        channel = input_effect.html_channel(page, root)
        fonts = [asset for asset in channel['assets'] if asset.get('path') == 'fonts/body.woff2']
        self.assertEqual(len(fonts), 1)
        self.assertEqual(fonts[0].get('sources'), ['css/a.css', 'css/b.css'], 'duplicate font ingress must stay one asset and a byte change must go stale')
        pinned = {
            'schema': input_effect.RESULT_SCHEMA,
            'sources': [{'path': 'fonts/body.woff2', 'sha256': input_effect.digest(font.read_bytes())}],
            'digest': 'c' * 64,
        }
        self.assertEqual(input_effect.freshness(pinned, root)['status'], 'current')
        font.write_bytes(b'font-v2')
        fresh = input_effect.freshness(pinned, root)
        self.assertEqual(fresh['status'], 'stale')
        self.assertEqual(fresh['changed'], ['fonts/body.woff2'])
        tasks_doc = (Path(__file__).resolve().parents[1] / 'docs/development-roadmap/RD-05-asset-inventory/tasks.md').read_text(encoding='utf-8')
        self.assertIn('fonts/body.woff2', tasks_doc)
