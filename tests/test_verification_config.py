"""Observe the private XDG from real verification children, including unsuccessful runs."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import graph_governance
import maintenance
import major_release


class VerificationConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.tests = self.root / 'tests'
        self.tests.mkdir()
        self.logs = self.root / 'logs'
        self.logs.mkdir()
        self.parent_config = self.root / 'parent-config'
        self.parent_config.mkdir(mode=0o700)
        self.sentinel = self.parent_config / 'sentinel'
        self.sentinel.write_bytes(b'preserve')
        env = patch.dict(os.environ, XDG_CONFIG_HOME=str(self.parent_config))
        env.start()
        self.addCleanup(env.stop)
        self.trace = self.root / 'trace.json'
        self.seen = set()
        self.observe = ("import json, os\nfrom pathlib import Path\n"
                        "xdg = Path(os.environ['XDG_CONFIG_HOME'])\n"
                        f"Path({str(self.trace)!r}).write_text(json.dumps([str(xdg), xdg.stat().st_mode & 0o777]))\n")

    def verify_observation(self):
        path, mode = json.loads(self.trace.read_bytes())
        self.trace.unlink()
        self.assertNotEqual(Path(path), self.parent_config, 'direct verifier must isolate its child XDG')
        self.assertNotIn(path, self.seen)
        self.seen.add(path)
        self.assertEqual(mode, 0o700)
        self.assertFalse(Path(path).exists(), 'verification child XDG must be cleaned')
        self.assertEqual(self.sentinel.read_bytes(), b'preserve')

    def test_maintenance_keeps_exit_and_cleans_config(self):
        for code in (0, 17):
            step = {'id': f'step-{code}', 'argv': ['python3', '-c', self.observe + f'raise SystemExit({code})']}
            result = maintenance.run_step(step, self.root, self.logs, False)
            self.assertEqual(result['returncode'], code)
            self.verify_observation()

    def test_archive_witness_keeps_verdict_and_cleans_config(self):
        witness = self.tests / 'test_local.py'
        for expected in (True, False):
            body = ''.join('        ' + line + '\n' for line in self.observe.splitlines())
            witness.write_text("import unittest\nclass Witness(unittest.TestCase):\n    def test_config(self):\n"
                               + body + f'        self.assertTrue({expected})\n')
            check = {'test': 'tests/test_local.py', 'testSha256': hashlib.sha256(witness.read_bytes()).hexdigest(),
                     'case': 'Witness.test_config'}
            if expected:
                major_release.rerun_witness(self.root, check)
            else:
                with self.assertRaises(ValueError):
                    major_release.rerun_witness(self.root, check)
            self.verify_observation()

    def test_node_suites_keep_exit_and_clean_config(self):
        script = self.tests / 'test-config.cjs'
        for fail in (False, True):
            script.write_text("const fs=require('node:fs');require('node:test')('config',()=>{"
                              "const p=process.env.XDG_CONFIG_HOME;"
                              f"fs.writeFileSync({json.dumps(str(self.trace))},JSON.stringify([p,fs.statSync(p).mode & 0o777]));"
                              + ("throw Error('expected fixture failure');" if fail else "") + "});\n")
            self.assertEqual(graph_governance.test_other_suites(self.root, []) == 0, not fail)
            self.verify_observation()


if __name__ == '__main__':
    unittest.main()
