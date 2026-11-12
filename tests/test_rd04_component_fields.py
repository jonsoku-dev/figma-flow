"""Component field selection keeps the main component and skips the other fields.

Synthetic field values are not a live Figma component edit.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import graph_sync


ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
const {commitComponentFields} = require('./figma-bridge/graph_token_sync.js');
const input = JSON.parse(process.argv[1]);
const before = JSON.stringify(input.observed);
const result = commitComponentFields(input.spec, input.selection, input.observed);
if (JSON.stringify(input.observed) !== before) {
  process.stderr.write('component field apply mutated observed values');
  process.exit(3);
}
process.stdout.write(JSON.stringify(result));
"""


class ComponentFieldSelectionTests(unittest.TestCase):
    def test_shared_padding_fields_apply_without_a_new_component(self):
        commit = getattr(graph_sync, 'commit_component_fields', None)
        self.assertTrue(callable(commit), 'component field selection must keep the main component')
        spec = json.loads((ROOT / 'tests/fixtures/rd04/component-fields.json').read_text(encoding='utf-8'))
        observed = {item['field']: item['before'] for item in spec['fields']}
        before = json.dumps(observed)
        result = commit(spec, ['paddingLeft', 'paddingRight'], observed)
        self.assertEqual(json.dumps(observed), before)
        self.assertEqual(result['node_id'], 'main-1')
        self.assertEqual(result['main_component_id'], 'main-1')
        self.assertEqual(result['applied'], [
            {'id': 'button', 'field': 'paddingLeft', 'value': 12},
            {'id': 'button', 'field': 'paddingRight', 'value': 12},
        ])
        self.assertEqual(result['values']['fontSize'], 14)
        self.assertEqual(result['readback'], result['values'])
        self.assertEqual(result['baseline'], {'paddingLeft': 12, 'paddingRight': 12})
        self.assertNotIn('fontSize', result['baseline'])
        self.assertFalse(result['full_apply'])
        drifted = dict(observed, paddingLeft=0)
        with self.assertRaisesRegex(ValueError, 'stale before value'):
            commit(spec, ['paddingLeft', 'paddingRight'], drifted)
        self.assertEqual(drifted['paddingRight'], 8)
        with self.assertRaisesRegex(ValueError, 'partial component closure'):
            commit(spec, ['paddingLeft'], observed)
        with self.assertRaisesRegex(ValueError, 'unknown component field'):
            commit(spec, ['paddingLeft', 'paddingRight', 'fills'], observed)
        completed = subprocess.run(
            ['node', '--eval', RUNNER, json.dumps({'spec': spec, 'selection': ['paddingRight', 'paddingLeft'], 'observed': observed})],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), result)
        source = (ROOT / 'figma-bridge/graph_token_sync.js').read_text(encoding='utf-8')
        self.assertIn('commitComponentFields(message.component_fields', source)
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-04-selective-sync/tasks.md').read_text(encoding='utf-8')
        self.assertIn('commit_component_fields', tasks_doc)
        self.assertIn('main_component_id', tasks_doc)
