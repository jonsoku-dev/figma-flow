"""Acceptance oracle for indirect local CSS dependencies in input freshness."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path.cwd()
FIXTURE = ROOT / 'examples/regression-program'
sys.path.insert(0, str(ROOT / 'tools'))
import input_effect


def spec_for(inputs):
    return {
        'schema': input_effect.SCHEMA,
        'brief': 'atlas/brief.md',
        'facts': 'atlas/brief-facts.json',
        'authority': 'atlas/authority.json',
        'expected_package_version': '0.1.0',
        'inputs': inputs,
    }


class CssDependencyFreshnessTests(unittest.TestCase):
    def test_css_import_font_and_image_changes_make_html_projection_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURE / 'atlas', root / 'atlas')
            page = root / 'html/index.html'
            page.parent.mkdir(parents=True)
            page.write_text('<title>CSS dependency</title><link rel="stylesheet" href="styles/site.css">', encoding='utf-8')
            styles = page.parent / 'styles'
            (styles / 'nested').mkdir(parents=True)
            (styles / 'site.css').write_text('@import "nested/theme.css"; main { gap: 12px; }', encoding='utf-8')
            (styles / 'nested/theme.css').write_text(
                '@font-face { font-family: Room; src: url("../../../fonts/Room.woff2"); } '
                'main { background-image: url("../../../images/paper.png"); }',
                encoding='utf-8',
            )
            (root / 'fonts').mkdir()
            (root / 'images').mkdir()
            (root / 'fonts/Room.woff2').write_bytes(b'initial font')
            (root / 'images/paper.png').write_bytes(b'initial image')

            record = input_effect.project(root, spec_for({'html': 'html/index.html'}))
            for relative in ('html/styles/nested/theme.css', 'fonts/Room.woff2', 'images/paper.png'):
                with self.subTest(path=relative):
                    path = root / relative
                    original = path.read_bytes()
                    self.assertEqual(input_effect.freshness(record, root)['status'], 'current')
                    try:
                        path.write_bytes(original + b' changed')
                        freshness = input_effect.freshness(record, root)
                        self.assertEqual(
                            freshness['status'], 'stale',
                            f'{relative} changed but CSS-dependent HTML projection stayed {freshness["status"]}',
                        )
                        self.assertIn(relative, freshness['changed'])
                    finally:
                        path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
