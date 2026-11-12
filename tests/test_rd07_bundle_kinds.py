"""Run the assembled runtime for every task kind, including an error and uncertainty."""
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace


class BundleKindTests(unittest.TestCase):
    def test_generated_bundle_runs_every_kind(self):
        source = (ROOT / 'tools/figma_workspace.py').read_text(encoding='utf-8')
        if 'def bundle_task_kinds' not in source:
            raise AssertionError('generated bundle must run every task kind')
        self.assertEqual(workspace.bundle_task_kinds(), ('discover', 'import', 'native-edit', 'review', 'sync'))
        bundle = workspace.assemble_shared_runtime(ROOT / 'figma-bridge')
        self.assertIn('async function controlRequest', bundle)
        self.assertIn('async function controlExecute', bundle)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bundle.js'
            path.write_text(bundle, encoding='utf-8')
            completed = subprocess.run(
                ['node', str(ROOT / 'tests/rd07_bundle_kinds.cjs'), str(path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('bundle-kinds-ok', completed.stdout)
        tasks = (ROOT / 'docs/development-roadmap/RD-07-runtime-boundaries/tasks.md').read_text(encoding='utf-8')
        self.assertIn('bundle_task_kinds', tasks)


if __name__ == '__main__':
    unittest.main()
