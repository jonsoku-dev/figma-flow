"""Server restart and missed result delivery on the HTTP control path.

This uses the local control server. It does not open Figma Desktop.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import figma_control as control
import figma_workspace as workspace
from test_graph_sync import fixture


EXPECTED = {
    'schema': 'figma-flow-control-restart-v1',
    'state': 'uncertain',
    'phases': ['queued', 'claimed', 'native-started', 'uncertain'],
    'same_operation_id': True,
    'mutation_reenqueued': 'blocked',
    'plugin_rerun_redelivers': False,
    'result_delivered': False,
    'request_count': 1,
}


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class RestartDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'workspace'
        assigned = self.directory / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.root, assigned)
        workspace.prepare(self.root, 'discovery', 'Read values', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])
        control.enable(self.root, 49221)

    def test_restart_keeps_journal_when_result_delivery_fails(self):
        report = getattr(control, 'restart_delivery_report', None)
        self.assertTrue(callable(report), 'restart must keep the journal when result delivery fails')
        graph, native = fixture()
        native.update(fileKey='fixturefile', pageId='12:1')
        for node in native['nodes']:
            if node.get('parentId') == 'page':
                node['parentId'] = '12:1'
        source, baseline = self.directory / 'graph.json', self.directory / 'native.json'
        source.write_text(json.dumps(graph))
        baseline.write_text(json.dumps(native))
        mutating = workspace.prepare(self.root, 'mutation', 'Apply graph', 'sync', ['--graph', str(source), '--native-readback', str(baseline)])
        self.assertEqual(report(self.root, mutating['revision']), EXPECTED)
