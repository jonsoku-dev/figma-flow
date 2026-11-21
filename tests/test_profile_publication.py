"""The registered workspace uses the same policy graph and local permission as the first-run spec."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace


class ProfilePublicationTest(unittest.TestCase):
    def test_workspace_embeds_one_policy_and_only_requests_current_user(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            identity = folder / 'assigned.json'
            identity.write_text('{"id":"12345"}')
            workspace = folder / 'workspace'
            figma_workspace.init(workspace, identity)
            manifest = json.loads((workspace / 'manifest.json').read_bytes())
            self.assertEqual(manifest['editorType'], ['figma'])
            self.assertEqual(manifest['permissions'], ['currentuser'])
            self.assertEqual(manifest['networkAccess'], {'allowedDomains': ['none']})
            code = (workspace / manifest['main']).read_text()
            embedded = re.findall(r'^const WORKSPACE_PROFILE_POLICY = (.+);$', code, re.M)
            self.assertEqual(len(embedded), 1)
            self.assertEqual(json.loads(embedded[0]), json.loads((ROOT/'library/figma-profile/policy.json').read_bytes()))
            for name in ('profile_policy.js','workspace_profile.js'):
                self.assertEqual(code.count((ROOT/'figma-bridge'/name).read_text()), 1)

    def test_spec_graph_resolves_all_feature_sources_and_edges(self):
        folder = ROOT/'specs/local-profile-init'
        graph = json.loads((folder/'graph.json').read_bytes())
        node_ids = {n['id'] for n in graph['nodes']}
        self.assertEqual(len(node_ids), len(graph['nodes']))
        for node in graph['nodes']:
            self.assertTrue((folder/node['source']).is_file(), node['source'])
        for edge in graph['edges']:
            self.assertIn(edge['from'], node_ids)
            self.assertIn(edge['to'], node_ids)
