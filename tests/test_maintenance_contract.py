"""Prove lints detect real violations and verify records reflect actual execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import maintenance


class MaintenanceContractTests(unittest.TestCase):
    def test_rejects_raw_json_decoders_under_direct_and_module_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'tools').mkdir()
            (root/maintenance.CONTRACT).write_text(json.dumps({
                'schema':'figma-flow-maintenance-v1',
                'graphDecoding':{'tools/read.py':['load_graph']},
            }))
            code = root/'tools/read.py'
            for imported, call in [('import json as wire','wire.loads(raw)'),
                                   ('from json import loads as unmarshal','unmarshal(raw)')]:
                code.write_text(f'{imported}\ndef load_graph(raw):\n    return {call}\n')
                findings = maintenance.graph_decode_findings(root)
                self.assertEqual(len(findings),1)
                self.assertEqual(findings[0]['line'],3)
                self.assertIn('Use graph_document',findings[0]['message'])
            code.write_text('from graph_document import decode_json\ndef load_graph(raw):\n    return decode_json(raw)\n')
            self.assertEqual(maintenance.graph_decode_findings(root),[])

    def test_record_retains_failed_step_and_refuses_output_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'
            root.mkdir()
            (root/'tools').mkdir()
            (root/maintenance.CONTRACT).write_text(json.dumps({
                'schema':'figma-flow-maintenance-v1',
                'profiles':{'cli':[{'id':'probe','argv':['python3','-B','probe.py']}]},
            }))
            (root/'probe.py').write_text('print("observable result")\nraise SystemExit(2)\n')
            out=Path(temp)/'out'
            with patch.object(maintenance,'ROOT',root):
                self.assertEqual(maintenance.verify('cli',out),1)
                with self.assertRaises(FileExistsError):
                    maintenance.verify('cli',out)
            record=json.loads((out/'evidence.json').read_bytes())
            self.assertEqual(record['status'],'incomplete')
            self.assertEqual(record['steps'][0]['status'],'failed')
            self.assertEqual({p.name for p in out.iterdir()}, {'evidence.json'})
            self.assertEqual(record['steps'][0]['output']['sha256'], hashlib.sha256(b'observable result\n').hexdigest())

    def test_ci_and_maintainer_handoff_use_the_declared_evidence_profiles(self):
        from tools import delivery_config
        root = maintenance.ROOT
        output = delivery_config.templates(root)
        self.assertIn('tools/maintenance.py check', output[Path('.github/workflows/test.yml')])
        self.assertIn('tools/maintenance.py verify --profile release', output[Path('.github/workflows/reference-guard.yml')])
        self.assertIn('graph-properties', {s['id'] for s in maintenance.policy(root)['profiles']['release']})
        for page in ('AGENTS.md', 'CONTRIBUTING.md', 'skills/patch-knowledge/SKILL.md',
                     'skills/figma-flow/SKILL.md', '.github/pull_request_template.md'):
            self.assertIn('maintenance-verification.md', (root/page).read_text(), page)


if __name__ == '__main__':
    unittest.main()
