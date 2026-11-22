"""Browser-level alignment oracle for the built Codex relay viewer."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from plugin_panel import render_app


class RelayAlignmentTests(unittest.TestCase):
    def test_relay_sections_share_their_leading_edge_at_narrow_and_card_widths(self):
        with tempfile.TemporaryDirectory() as temp:
            html = Path(temp) / 'relay.html'
            html.write_text(render_app('relay'), encoding='utf-8')
            result = subprocess.run(
                ['node', str(ROOT / 'tests/helpers/relay_alignment.mjs'), str(html)],
                capture_output=True, text=True, timeout=30,
            )
        if result.returncode == 77:
            self.skipTest('Chromium executable unavailable')
        self.assertEqual(result.returncode, 0, result.stderr)
        samples = json.loads(result.stdout)
        self.assertEqual([sample['width'] for sample in samples], [320, 400])
        for sample in samples:
            self.assertEqual(sample['locale'], 'ko')
            self.assertEqual(sample['rowCount'], 2)
            self.assertLessEqual(sample['documentWidth'], sample['width'],
                                 'Relay document must not overflow horizontally')
            anchor = sample['edges']['brand']
            for target, edge in sample['edges'].items():
                if target == 'brand':
                    continue
                self.assertLessEqual(
                    abs(edge - anchor), 0.5,
                    f"Relay sections must share their leading edge: {target}={edge:.2f}px, "
                    f"brand={anchor:.2f}px at {sample['width']}px viewport",
                )


if __name__ == '__main__':
    unittest.main()
