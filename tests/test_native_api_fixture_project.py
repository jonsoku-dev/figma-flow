import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeApiFixtureProjectTest(unittest.TestCase):
    def test_generator_writes_a_design_only_private_offline_plugin(self):
        private_root = ROOT / '.figma-flow'
        created_private_root = not private_root.exists()
        private_root.mkdir(mode=0o700, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=private_root) as temporary:
                output = Path(temporary) / 'fixture-project'
                subprocess.run([sys.executable, '-B', str(ROOT / 'tools/native_api_fixture_project.py'),
                    '--plugin-id', '1234567890123456789', '--file-key', 'TEST_FILE_KEY', '--out', str(output)],
                    check=True, capture_output=True, text=True)
                manifest = json.loads((output / 'manifest.json').read_text())
                code = (output / 'code.js').read_text()
                self.assertEqual(manifest['id'], '1234567890123456789')
                self.assertTrue(manifest['enablePrivatePluginApi'])
                self.assertEqual(manifest['editorType'], ['figma'])
                self.assertEqual(manifest['networkAccess']['allowedDomains'], ['none'])
                self.assertIn('TEST_FILE_KEY', code)
                self.assertIn('native-api-lab-fixtures', code)
                self.assertIn('native-api-lab-owned-reads', code)
                self.assertIn('native-api-lab-owned-writes', code)
                subprocess.run(['node', '--check', str(output / 'code.js')], check=True)
                with self.assertRaises(FileExistsError):
                    output.mkdir(mode=0o700)
        finally:
            if created_private_root:
                try:
                    private_root.rmdir()
                except OSError:
                    pass

    def test_generator_rejects_unscoped_or_invalid_private_outputs(self):
        subprocess.run([sys.executable, '-B', str(ROOT / 'tools/native_api_fixture_project.py'),
            '--plugin-id', 'not-a-figma-id', '--file-key', 'TEST_FILE_KEY',
            '--out', str(ROOT / '.figma-flow/invalid-fixture-project')],
            check=False, capture_output=True, text=True)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/native_api_fixture_project.py'),
                '--plugin-id', '1234567890123456789', '--file-key', 'TEST_FILE_KEY',
                '--out', str(Path(temporary) / 'outside-private')], check=False, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('inside the private .figma-flow workspace', result.stderr)


if __name__ == '__main__':
    unittest.main()
