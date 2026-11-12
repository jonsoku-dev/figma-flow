"""Task identity stays independent of a control operation id.

Synthetic workspace setup is not a live Figma panel observation.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_control as control
import figma_workspace as workspace


EXPECTED = {
    'schema': 'figma-flow-identity-boundary-v1',
    'task_key': 'discovery',
    'revision_length': 64,
    'operation_id_length': 32,
    'identities_differ': True,
    'operation_uses_task_key': True,
    'catalogue_contains_operation_id': False,
    'catalogue_revision_unchanged': True,
    'journal_operation_id_matches': True,
    'dependency_inferred': False,
    'request_count': 1,
}


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class IdentityBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'workspace'
        assigned = self.directory / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.root, assigned)
        self.prepared = workspace.prepare(self.root, 'discovery', 'Read values', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])
        control.enable(self.root, 49231)

    def test_task_identity_is_not_a_control_operation(self):
        report = getattr(control, 'task_operation_boundary', None)
        self.assertTrue(callable(report), 'task identity must stay independent of the operation id')
        self.assertEqual(report(self.root, self.prepared['revision']), EXPECTED)
