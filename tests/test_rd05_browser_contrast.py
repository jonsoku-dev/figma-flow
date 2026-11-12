"""Inventory and caller-provided browser observations are separate evidence."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import input_effect


class CssBrowserContrastTests(unittest.TestCase):
    def test_present_list_does_not_mean_the_browser_loaded_every_file(self):
        contrast = getattr(input_effect, 'contrast_css_browser_loading', None)
        self.assertTrue(callable(contrast), 'css asset list and browser loading must stay separate')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'css').mkdir()
        (root / 'fonts').mkdir()
        (root / 'photos').mkdir()
        (root / 'fonts' / 'body.woff2').write_bytes(b'wOFF' + b'\0' * 16)
        (root / 'fonts' / 'spare.woff2').write_bytes(b'wOFF' + b'\1' * 16)
        (root / 'photos' / 'mark.png').write_bytes(b'\x89PNG\r\n\x1a\n')
        (root / 'css' / 'site.css').write_text(
            '@font-face { font-family: Body; src: url(../fonts/body.woff2); }'
            '@font-face { font-family: Spare; src: url(../fonts/spare.woff2); }'
            'p { font-family: Body, sans-serif; background: url(../photos/mark.png); }',
            encoding='utf-8')
        (root / 'index.html').write_text('<!doctype html><link rel="stylesheet" href="css/site.css"><p>가</p>', encoding='utf-8')
        result = contrast(root, requested_paths=['css/site.css', 'fonts/body.woff2', 'photos/mark.png'])
        listed = {item['path']: item['status'] for item in result['list']}
        self.assertEqual(listed['photos/mark.png'], 'present')
        self.assertEqual(listed['fonts/body.woff2'], 'present')
        self.assertEqual(listed['fonts/spare.woff2'], 'present')
        requested = set(result['browser']['requested'])
        self.assertIn('photos/mark.png', requested)
        self.assertIn('fonts/body.woff2', requested)
        self.assertNotIn('fonts/spare.woff2', requested)
        self.assertTrue(result['separate'])
        self.assertEqual(result['browser']['source'], 'provided-observation')
        with self.assertRaises(ValueError):
            contrast(root)
        self.assertNotIn('fetch(', Path(input_effect.__file__).read_text(encoding='utf-8')[Path(input_effect.__file__).read_text(encoding='utf-8').index('def contrast_css_browser_loading'):])
        tasks_doc = (Path(__file__).resolve().parents[1] / 'docs/development-roadmap/RD-05-asset-inventory/tasks.md').read_text(encoding='utf-8')
        self.assertIn('contrast_css_browser_loading', tasks_doc)
