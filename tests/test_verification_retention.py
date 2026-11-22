"""Keep compact check receipts and reclaim owned files after verification."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import maintenance


class VerificationRetentionTests(unittest.TestCase):
    def test_owned_scratch_is_cleaned_on_success_failure_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            root = outer / 'root'
            (root / 'tools').mkdir(parents=True)
            scratch = outer / 'temp'
            scratch.mkdir()
            unrelated = scratch / 'user-backup.keep'
            unrelated.write_text('keep this')
            probe = root / 'probe.py'
            probe.write_text(
                "from pathlib import Path\nimport sys,tempfile,time\n"
                "Path(tempfile.gettempdir(),'owned.fixture').write_bytes(b'x'*1000000)\n"
                "print('LOCAL_ONLY_EVIDENCE',flush=True)\n"
                "if sys.argv[1]=='timeout': time.sleep(30)\n"
                "raise SystemExit(int(sys.argv[1]))\n"
            )
            for name, expected in [('0', 'passed'), ('2', 'failed'), ('timeout', 'unavailable')]:
                (root/maintenance.CONTRACT).write_text(json.dumps({
                    'schema':'figma-flow-maintenance-v1',
                    'artifactRetention':{'receiptBytes':65536},
                    'profiles':{'cli':[{'id':'probe','argv':['python3','-B','probe.py',name],'timeoutSeconds':1}]},
                }))
                out = outer / ('out-' + name)
                with patch.object(maintenance, 'ROOT', root), patch.dict(os.environ, {'TMPDIR':str(scratch)}), patch.object(tempfile, 'tempdir', str(scratch)):
                    maintenance.verify('cli',out)
                record = json.loads((out / 'evidence.json').read_bytes())
                self.assertTrue({p.name for p in out.iterdir()} == {'evidence.json'} and set(scratch.iterdir()) == {unrelated},
                                'Verification must leave only its compact receipt and remove its owned temporary files')
                self.assertEqual(record['steps'][0]['status'],expected)
                self.assertEqual(unrelated.read_text(),'keep this')
                self.assertNotIn('LOCAL_ONLY_EVIDENCE',(out/'evidence.json').read_text())
                self.assertLess((out/'evidence.json').stat().st_size,65536)

    def test_ui_keeps_only_screenshot_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            outer=Path(directory)
            for name in ('base','candidate'):
                root=outer/name
                (root/'tools').mkdir(parents=True)
                (root/'probe.py').write_text(
                    "import os\nfrom pathlib import Path\n"
                    "Path(os.environ['FIGMA_FLOW_PANEL_WORKSPACE_SCREENSHOT']).write_bytes(b'screenshot-bytes')\n"
                )
            (root/maintenance.CONTRACT).write_text(json.dumps({
                'schema':'figma-flow-maintenance-v1',
                'artifactRetention':{'receiptBytes':65536},
                'profiles':{'ui':[{'id':name,'argv':['python3','-B','probe.py']} for name in ('panel-before','panel-after')]},
            }))
            out=outer/'out'
            with patch.object(maintenance,'ROOT',root):
                self.assertEqual(maintenance.verify('ui',out,outer/'base'),0)
            self.assertEqual({p.name for p in out.iterdir()},{'evidence.json'})
            record=json.loads((out/'evidence.json').read_bytes())
            self.assertEqual(record['steps'][0]['screenshot'],record['steps'][1]['screenshot'])
            self.assertEqual(record['steps'][0]['screenshot']['bytes'],len(b'screenshot-bytes'))


if __name__ == '__main__':
    unittest.main()
