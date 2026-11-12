"""A validated selection applies only its values and limits the baseline.

Synthetic values are not a live Figma readback.
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
const {commitGraphSelection} = require('./figma-bridge/graph_token_sync.js');
const input = JSON.parse(process.argv[1]);
const before = JSON.stringify(input.observed);
let result;
try {
  result = commitGraphSelection(input.payload, input.selection, input.observed);
} catch (error) {
  process.stderr.write(String(error && error.message));
  process.exit(2);
}
if (JSON.stringify(input.observed) !== before) {
  process.stderr.write('selective apply mutated observed values');
  process.exit(3);
}
process.stdout.write(JSON.stringify(result));
"""


class SelectiveApplyTests(unittest.TestCase):
    def js(self, payload, selection, observed):
        return subprocess.run(
            ['node', '--eval', RUNNER, json.dumps({'payload': payload, 'selection': selection, 'observed': observed})],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def test_partial_apply_keeps_skipped_values_and_limits_the_baseline(self):
        commit = getattr(graph_sync, 'commit_selective_apply', None)
        self.assertTrue(callable(commit), 'selective apply must keep skipped values and limit the baseline')
        raw = json.loads((ROOT / 'tests/fixtures/rd04/partial-apply.json').read_text(encoding='utf-8'))
        observed = {item['key']: item['before'] for item in raw['independent']}
        before = json.dumps(observed)
        result = commit(raw, ['color/quiet', 'color/action'], observed)
        self.assertEqual(json.dumps(observed), before)
        self.assertEqual(result['applied'], [
            {'key': 'color/action', 'value': '#0055ff'},
            {'key': 'color/quiet', 'value': '#8899aa'},
        ])
        self.assertEqual([item['key'] for item in result['skipped']], ['space/gap', 'type/body', 'type/size'])
        self.assertEqual(result['values']['space/gap'], 8)
        self.assertEqual(result['readback'], result['values'])
        self.assertEqual(result['baseline'], {'color/action': '#0055ff', 'color/quiet': '#8899aa'})
        self.assertNotIn('space/gap', result['baseline'])
        self.assertFalse(result['full_apply'])
        self.assertEqual(result['plan_sha256'], graph_sync.serialize_selection(raw, ['color/action', 'color/quiet'])['document']['plan_sha256'])

        drifted = dict(observed, **{'color/action': '#000000'})
        drifted_before = json.dumps(drifted)
        with self.assertRaisesRegex(ValueError, 'stale before value'):
            commit(raw, ['color/action', 'color/quiet'], drifted)
        self.assertEqual(json.dumps(drifted), drifted_before)
        with self.assertRaisesRegex(ValueError, 'empty selection'):
            commit(raw, [], observed)
        with self.assertRaisesRegex(ValueError, 'partial alias bundle'):
            commit(raw, ['type/body'], observed)
        bundle = commit(raw, ['type/size', 'type/body'], observed)
        self.assertEqual(bundle['values'], observed)
        self.assertEqual(bundle['baseline'], {})
        self.assertEqual([item['key'] for item in bundle['applied']], ['type/body', 'type/size'])

        completed = self.js(raw, ['color/quiet', 'color/action'], observed)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), result)
        stale = self.js(raw, ['color/action', 'color/quiet'], drifted)
        self.assertEqual(stale.returncode, 2)
        self.assertIn('stale before value', stale.stderr)
        source = (ROOT / 'figma-bridge/graph_token_sync.js').read_text(encoding='utf-8')
        self.assertLess(source.index('const plan = graphSyncPlanForMessage(GRAPH_SYNC_PLAN, message)'), source.index('graphTokenSync(figma, plan,'))
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-04-selective-sync/tasks.md').read_text(encoding='utf-8')
        self.assertIn('commit_selective_apply', tasks_doc)
        self.assertIn('baseline', tasks_doc)
