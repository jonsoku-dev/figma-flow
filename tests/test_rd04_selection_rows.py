"""Selection rows expose a count, select-all, and affected targets.

Synthetic changes are not a live Figma apply.
"""
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
import { graphSelection } from './panel-ui/src/graphSelection.mjs';
const input = JSON.parse(process.argv[1]);
const before = JSON.stringify(input.changes);
const view = graphSelection(input.changes, input.selected);
if (JSON.stringify(input.changes) !== before) {
  process.stderr.write('selection mutated changes');
  process.exit(3);
}
process.stdout.write(JSON.stringify(view));
"""


class SelectionRowTests(unittest.TestCase):
    def run_selection(self, changes, selected):
        completed = subprocess.run(
            ['node', '--input-type=module', '--eval', RUNNER, json.dumps({'changes': changes, 'selected': selected})],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_rows_show_the_count_select_all_and_targets(self):
        module = ROOT / 'panel-ui/src/graphSelection.mjs'
        source = module.read_text(encoding='utf-8') if module.is_file() else ''
        self.assertIn('export function graphSelection', source, 'selection rows must show the count and affected targets')
        changes = [
            {'identity': 'a', 'name': 'color/action', 'targets': ['button.fill']},
            {'identity': 'b', 'name': 'color/quiet', 'targets': ['quiet.icon']},
            {'name': 'space/gap'},
        ]
        one = self.run_selection(changes, ['a'])
        self.assertEqual(one['count'], 1)
        self.assertEqual(one['rows'][0]['targets'], ['button.fill'])
        self.assertTrue(one['rows'][0]['selected'])
        self.assertFalse(one['rows'][1]['selected'] or one['rows'][2]['selected'])
        self.assertEqual(one['rows'][2]['identity'], 'space/gap')
        self.assertEqual(one['rows'][2]['targets'], ['space/gap'])
        self.assertEqual(self.run_selection(changes, None)['count'], 3)
        self.assertEqual(self.run_selection(changes, [])['count'], 0)
        self.assertEqual(self.run_selection(changes, one['identities'])['count'], 3)

        html = (ROOT / 'figma-bridge/graph-panel.html').read_text(encoding='utf-8')
        self.assertIn('function graphSelection', html)
        self.assertIn('id="select-all"', html)
        self.assertIn('graph-selection-targets', html)
        self.assertIn('applyBlocked', html)
        ui = (ROOT / 'panel-ui/src/GraphPanel.jsx').read_text(encoding='utf-8')
        self.assertIn('graphSelection(', ui)
        self.assertIn('graph-selection-count', ui)
        self.assertIn('graph-selection-targets', ui)
        bundle = (ROOT / 'figma-bridge/assets/panels.js').read_text(encoding='utf-8')
        self.assertIn('graph-selection-count', bundle)
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-04-selective-sync/tasks.md').read_text(encoding='utf-8')
        self.assertIn('graphSelection', tasks_doc)
        self.assertIn('전체 선택', tasks_doc)
