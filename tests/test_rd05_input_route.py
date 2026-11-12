"""The HTML input record keeps one route into task preparation.

This pin is not a live browser or Figma asset render.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import input_effect


ROOT = Path(__file__).resolve().parents[1]


class InputRecordRouteTests(unittest.TestCase):
    def test_html_channel_is_the_only_route_into_prepare(self):
        route = getattr(input_effect, 'confirm_input_record_route', None)
        self.assertTrue(callable(route), 'input record route must stay on the html channel')
        self.assertEqual(route(), {
            'producer': 'input_effect.project',
            'channel': 'html_channel',
            'freshness': 'input_effect.freshness',
            'store': 'input_effect.write_record',
            'task_boundary': 'figma_workspace.prepare',
            'consumer': 'private task artifact',
            'not_consumer': 'ImportPanel',
            'cli_flag': '--input-record',
        })
        effect = Path(input_effect.__file__).read_text(encoding='utf-8')
        self.assertLess(effect.index('def project('), effect.index("channels['html'] = html_channel(path, root)"))
        self.assertLess(effect.index('def freshness('), effect.index('def write_record('))
        self.assertNotIn('--input-record', effect)
        workspace = (ROOT / 'tools/figma_workspace.py').read_text(encoding='utf-8')
        self.assertIn('def prepare(', workspace)
        self.assertIn('--input-record', workspace)
        self.assertIn('--input-root', workspace)
        design = (ROOT / 'docs/development-roadmap/RD-05-asset-inventory/design.md').read_text(encoding='utf-8')
        self.assertIn('확정 경로: input_effect.project', design)
        self.assertIn('--input-record', design)
        self.assertIn('--input-root', design)
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-05-asset-inventory/tasks.md').read_text(encoding='utf-8')
        self.assertIn('confirm_input_record_route', tasks_doc)
