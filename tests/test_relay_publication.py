import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import figma_workspace as workspace
from plugin_panel import render_app


class RelayPublicationTests(unittest.TestCase):
    def test_registered_home_is_passive_and_example_is_a_file_scoped_replayable_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            issued = folder/'issued.json'
            issued.write_text('{"id":"12345"}')
            root = folder/'workspace'
            workspace.init(root, issued)
            args = ['--recipe','design-grid','--file-key','fixture','--page-id','2:3']
            task = workspace.prepare(root,'grid','Grid','native-edit',args,infer_thread=False)
            manifest = json.loads((root/'manifest.json').read_bytes())
            self.assertNotIn('menu', manifest)
            self.assertIn('data-flow-view="relay"', (root/manifest['ui']).read_text())
            self.assertIn('const WORKSPACE_RELAY_VIEWER = true;', (root/manifest['main']).read_text())
            result = subprocess.run(['node', str(ROOT/'tests/helpers/relay_example.cjs'),task['artifacts']],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with self.assertRaises(ValueError):
                workspace.prepare(root,'unknown','unknown','native-edit',['--recipe','unknown','--file-key','fixture','--page-id','2:3'],infer_thread=False)

    def test_viewer_receives_forwarded_state_and_polls_only_its_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / 'panel.html'
            html.write_text(render_app('relay'))
            result = subprocess.run(
                ['node', str(ROOT / 'tests/helpers/relay_viewer.mjs'), str(html)],
                capture_output=True, text=True, timeout=30)
            if result.returncode == 77:
                self.skipTest('Chromium executable unavailable')
            self.assertEqual(result.returncode, 0, result.stderr)
