"""Verify the package and script entrypoints in fresh interpreters without PYTHONPATH."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VerifierImportTests(unittest.TestCase):
    def run_python(self, *args):
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        return subprocess.run([sys.executable, '-E', '-s', '-B', *args], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=20)

    def test_package_imports_use_sibling(self):
        for name in ('maintenance', 'patch_knowledge_check'):
            with self.subTest(module=name):
                result = self.run_python('-c', f'from tools import {name}; '
                                         f'from tools.test_env import private_test_config; '
                                         f'assert {name}.private_test_config is private_test_config')
                self.assertEqual(result.returncode, 0, 'package import must resolve its sibling helper')

    def test_standalone_and_module_cli_preserve_help(self):
        for name in ('maintenance', 'patch_knowledge_check'):
            direct = self.run_python(f'tools/{name}.py', '--help')
            module = self.run_python('-m', 'tools.' + name, '--help')
            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertEqual(module.returncode, 0, module.stderr)
            # argparse renders the script or module invocation in its usage line.
            self.assertEqual(module.stdout.split('\n\n', 1)[1], direct.stdout.split('\n\n', 1)[1])


if __name__ == '__main__':
    unittest.main()
