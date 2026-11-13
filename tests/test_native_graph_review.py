"""Graph review plans pin canonical source bytes and prepare a local review plugin."""
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_edit


class NativeGraphReviewPlanTests(unittest.TestCase):
    def _graph_copy(self, folder):
        graph = json.loads((ROOT / 'examples/native-direction-review/bulletin/graph.json').read_text())
        graph['id'] = 'test.bulletin'
        graph['title'] = 'Bulletin review fixture'
        path = Path(folder) / 'graph.json'
        path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n')
        return path

    def test_cli_plan_and_private_plugin_pin_graph_and_strip_source_path_from_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            graph = self._graph_copy(root)
            plan_path = root / 'review-plan.json'
            result = native_edit.build_graph_review_plan(graph, ['screen-bulletin-overview', 'component-bulletin-open'], 'file', '1:1', plan_path)
            raw = plan_path.read_bytes()
            plan = json.loads(raw)
            self.assertEqual(result['graph_sha256'], hashlib.sha256(graph.read_bytes()).hexdigest())
            self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)
            output = root / 'plugin'
            receipt = native_edit.prepare(plan_path, output, '123456789')
            self.assertEqual(receipt['status'], 'prepared-not-executed')
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            runtime = (output / 'code.js').read_text()
            self.assertIn('graphReviewApply', runtime)
            self.assertIn(plan['graph_review']['source_graph_sha256'], runtime)
            self.assertNotIn(str(graph.resolve()), runtime)
            pins = json.loads((output / 'source-inputs.json').read_text())['pins']
            self.assertIn({'path': str(graph.resolve()), 'sha256': result['graph_sha256']}, pins)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['networkAccess']['allowedDomains'], ['none'])
            self.assertEqual(manifest['id'], '123456789')

    def test_source_drift_selection_bounds_and_existing_outputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            graph = self._graph_copy(root)
            original = graph.read_bytes()
            plan_path = root / 'plan.json'
            native_edit.build_graph_review_plan(graph, ['screen-bulletin-overview'], 'file', '1:1', plan_path)
            plan = json.loads(plan_path.read_text())
            graph.write_text(graph.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                native_edit.validate_plan(plan)
            graph.write_bytes(original)
            with self.assertRaises(FileExistsError):
                native_edit.build_graph_review_plan(graph, ['screen-bulletin-overview'], 'file', '1:1', plan_path)
            with self.assertRaises(ValueError):
                native_edit.build_graph_review_plan(graph, ['missing-node'], 'file', '1:1', root / 'bad-plan.json')
            with self.assertRaises(ValueError):
                native_edit.build_graph_review_plan(graph, ['screen-bulletin-overview'] * 25, 'file', '1:1', root / 'too-many.json')

    def test_cli_exposes_bounded_graph_review_plan_arguments(self):
        import subprocess
        result = subprocess.run([sys.executable, str(ROOT / 'tools/native_edit.py'), 'graph-review', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in ('--graph', '--node', '--file-key', '--page-id', '--out'):
            self.assertIn(option, result.stdout)


if __name__ == '__main__':
    unittest.main()
