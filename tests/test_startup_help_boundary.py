"""The package diagnostic must be able to show help before importing a missing native runtime."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class StartupHelpTests(unittest.TestCase):
    def test_help_is_readable_before_the_native_runtime_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cli=root/'plugin_startup.py'
            shutil.copyfile(ROOT/'tools/plugin_startup.py',cli)
            env=dict(os.environ,PYTHONPATH='',PYTHONNOUSERSITE='1')
            env.pop('PYTHONDONTWRITEBYTECODE',None)
            before=cli.read_bytes()
            result=subprocess.run([sys.executable,str(cli),'--help'],cwd=root,env=env,capture_output=True,text=True)
            self.assertTrue(result.returncode==0,'Help must work before the native runtime loads')
            self.assertIn('ensure',result.stdout)
            self.assertEqual({f.name for f in root.iterdir()},{'plugin_startup.py'})
            self.assertEqual(cli.read_bytes(),before)


if __name__=='__main__':
    unittest.main()
