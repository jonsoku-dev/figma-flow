"""Normal local asset inventory must not invent a scalar from unrelated CSS gaps.

File preparation is tested here; browser rendering and valid production font bytes
are separate acceptance evidence.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import input_effect


class NormalInputTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'brief.md').write_text('정상 예약 앱', encoding='utf-8')
        (self.root / 'facts.json').write_text(json.dumps({'service_name': '정상 예약 앱'}), encoding='utf-8')
        self.authority = {'facts': {'service_name': {'priority': ['brief']}}}
        self.write_authority()
        (self.root / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>정상 예약 앱</title>'
            '<link rel="stylesheet" href="app.css"><img src="photo.svg" alt="한 잔의 커피">', encoding='utf-8')
        (self.root / 'app.css').write_text('@font-face{font-family:Local;src:url(font.woff2)}'
            '.header{gap:12px}.schedule{gap:24px}', encoding='utf-8')
        (self.root / 'photo.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>')
        (self.root / 'font.woff2').write_bytes(b'wOF2' + bytes(44))
        self.spec = {'schema': input_effect.SCHEMA, 'brief': 'brief.md', 'facts': 'facts.json',
            'authority': 'authority.json', 'inputs': {'html': 'index.html'}}

    def write_authority(self):
        (self.root / 'authority.json').write_text(json.dumps(self.authority), encoding='utf-8')

    def test_unrequested_layout_ambiguity_keeps_real_asset_inventory(self):
        record = input_effect.project(self.root, self.spec)
        html = record['channels']['html']
        self.assertEqual(record['status'], 'projected')
        self.assertNotIn('surface-gap', html['facts'])
        self.assertEqual(html['unresolved_facts']['surface-gap'], ['12px', '24px'])
        self.assertNotIn('surface-gap', record['consumption']['html']['facts'])
        self.assertEqual({(row['path'], row['kind'], row['status']) for row in html['assets']},
            {('app.css', 'stylesheet', 'present'), ('photo.svg', 'image', 'present'), ('font.woff2', 'font', 'present')})
        self.assertEqual(html['render'], 'unverified')
        self.assertEqual(input_effect.freshness(record, self.root)['status'], 'current')
        (self.root / 'app.css').write_text('.header{gap:16px}.schedule{gap:24px}', encoding='utf-8')
        self.assertEqual(input_effect.freshness(record, self.root)['status'], 'stale')

    def test_explicit_scalar_gap_and_legacy_direct_fact_read_still_reject_ambiguity(self):
        self.authority['facts']['surface-gap'] = {'priority': ['html']}
        self.write_authority()
        with self.assertRaisesRegex(ValueError, 'one gap fact'):
            input_effect.project(self.root, self.spec)
        with self.assertRaisesRegex(ValueError, 'one gap fact'):
            input_effect.html_channel(self.root / 'index.html', self.root)
        (self.root / 'app.css').write_text('.header{gap:12px}', encoding='utf-8')
        self.assertEqual(input_effect.project(self.root, self.spec)['channels']['html']['facts']['surface-gap'], '12px')

    def test_read_only_browser_inventory_does_not_request_unrelated_layout_facts(self):
        result = input_effect.contrast_css_browser_loading(self.root,
            requested_paths=['app.css', 'photo.svg', 'font.woff2'])
        self.assertEqual(result['browser']['source'], 'provided-observation')
        self.assertTrue(result['separate'])
        self.assertEqual({row['path'] for row in result['list']}, {'app.css', 'photo.svg', 'font.woff2'})


if __name__ == '__main__':
    unittest.main()
