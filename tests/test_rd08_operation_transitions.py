"""Pin the current control transitions before lifecycle fields are added.

Synthetic plugin responses are not live Figma evidence.
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
    'schema': 'figma-flow-operation-transition-fixture-v1',
    'read': ['pending', 'claimed', 'ok'],
    'timeout_before_claim': 'expired',
    'timeout_after_claim': 'uncertain',
    'result_after_claimed_timeout': 'rejected',
    'read_claim_timeout_blocks_later_commands': False,
    'mutation_claim_timeout': 'uncertain',
    'mutation_reenqueued_while_uncertain': 'blocked',
    'other_page_read_reconciles': False,
    'same_scope_discovery_reconciles': True,
    'duplicate_terminal_result': 'rejected',
    'native_started': False,
}


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class OperationTransitionFixtureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'workspace'
        assigned = self.directory / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.root, assigned)
        self.prepared = workspace.prepare(self.root, 'discovery', 'Read values', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])
        control.enable(self.root, 49198)

    def test_current_operation_transitions_are_pinned(self):
        report = getattr(control, 'pinned_operation_transitions', None)
        self.assertIsNotNone(report, 'current operation transitions must be pinned before lifecycle changes')
        graph, native = fixture()
        native.update(fileKey='fixturefile', pageId='12:1')
        for node in native['nodes']:
            if node.get('parentId') == 'page':
                node['parentId'] = '12:1'
        source, baseline = self.directory / 'graph.json', self.directory / 'native.json'
        source.write_text(json.dumps(graph))
        baseline.write_text(json.dumps(native))
        mutating = workspace.prepare(self.root, 'mutation', 'Apply graph', 'sync', ['--graph', str(source), '--native-readback', str(baseline)])
        other = workspace.prepare(self.root, 'other-page', 'Other scope', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:9'])
        observed = report(self.root, self.prepared['revision'], mutating['revision'], other['revision'])
        self.assertEqual(observed, EXPECTED)
