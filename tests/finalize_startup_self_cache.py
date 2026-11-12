"""The normal startup CLI must not change the package it verifies."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StartupPackageBytes(unittest.TestCase):
    def test_plain_python_help_preserves_package_bytes_on_repeated_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / 'tools', root / 'tools', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copytree(ROOT / 'library', root / 'library')
            (root / '.codex-plugin').mkdir()
            for relative in ('plugin.json', '.codex-plugin/plugin.json'):
                shutil.copy2(ROOT / relative, root / relative)
            def snapshot():
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob('*') if p.is_file()}
            before = snapshot()
            env = {**os.environ, 'PYTHONNOUSERSITE': '1', 'PYTHONPATH': ''}
            for key in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX'):
                env.pop(key, None)
            for attempt in range(2):
                result = subprocess.run([sys.executable, str(root / 'tools/plugin_startup.py'), '--help'],
                                        cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(snapshot(), before, 'startup CLI must preserve verified package bytes without requiring -B')


if __name__ == '__main__':
    unittest.main()
