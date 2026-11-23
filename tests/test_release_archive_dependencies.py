from hashlib import sha256
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import major_release as gate


class ReleaseArchiveDependenciesTests(unittest.TestCase):
    def test_real_esm_witness_can_find_explicit_dependency_in_disposable_archive(self):
        with tempfile.TemporaryDirectory(prefix='figma-flow-release-dep-test-') as scratch:
            root = Path(scratch)
            tree = root / 'archive'
            (tree / 'panel-ui').mkdir(parents=True)
            (tree / 'tests').mkdir()
            deps = root / 'installed/node_modules'
            package = deps / 'release-fixture-package'
            package.mkdir(parents=True)
            (package / 'package.json').write_text(json.dumps({
                'name': 'release-fixture-package', 'type': 'module', 'exports': './index.js',
            }))
            (package / 'index.js').write_text('export const value = 42;\n')
            (tree / 'panel-ui/fixture.mjs').write_text("export { value } from 'release-fixture-package';\n")
            test = tree / 'tests/witness.mjs'
            test.write_text(
                "import assert from 'node:assert/strict';\nimport test from 'node:test';\n"
                "import { value } from '../panel-ui/fixture.mjs';\n"
                "test('uses the staged ESM dependency', () => assert.equal(value, 42));\n"
            )
            files = {p.relative_to(tree).as_posix() for p in tree.rglob('*') if p.is_file()}
            check = {'test': 'tests/witness.mjs', 'case': 'uses the staged ESM dependency',
                     'testSha256': sha256(test.read_bytes()).hexdigest()}
            with self.assertRaisesRegex(ValueError, 'Named test case did not pass'):
                gate.rerun_witness(tree, check, deps)

            def replay(candidate, given_files, installed):
                self.assertEqual(files, given_files)
                gate.rerun_witness(candidate, check, installed)
                return {'status': 'passed'}

            with patch.object(gate, 'audit', side_effect=replay):
                self.assertEqual({'status': 'passed'}, gate.audit_archived_tree(tree, files, deps))
            self.assertFalse((tree / 'panel-ui/node_modules').is_symlink())
            self.assertFalse((tree / 'panel-ui/node_modules').exists())


if __name__ == '__main__':
    unittest.main()
