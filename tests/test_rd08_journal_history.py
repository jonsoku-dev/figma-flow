"""History reads the server journal and distinguishes legacy from unknown.

Synthetic plugin responses are not live Figma evidence.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_control as control
import figma_workspace as workspace


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class JournalHistoryTests(unittest.TestCase):
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

    def test_history_reads_the_server_journal_without_inferring_phases(self):
        view = getattr(control, 'journal_history', None)
        self.assertTrue(callable(view), 'execution history must read the server journal')
        host = (ROOT / 'figma-bridge' / 'workspace_host.js').read_text(encoding='utf-8')
        self.assertIn('function workspaceJournalHistory', host)
        self.assertLess(host.index('function workspaceRecord'), host.index('if (journal)'))

        request = control.enqueue(self.root, 'discovery', 'read', 'fixturefile', '12:1', self.prepared['revision'], 120)
        control.poll(self.root, {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': workspace.current(self.root)['runtime']})
        recorded = view(control.status(self.root))
        self.assertEqual(recorded['classification'], 'recorded')
        self.assertEqual(recorded['phase'], 'claimed')
        self.assertEqual([item['phase'] for item in recorded['phases']], ['queued', 'claimed'])
        self.assertEqual(recorded['operation_id'], request['operation_id'])
        self.assertEqual(control.status(self.root)['journal'], recorded)
        rendered = json.dumps(recorded)
        self.assertNotIn('native-started', rendered)
        self.assertNotIn('readback', rendered)
        self.assertNotIn('private failure text', rendered)

        dirty = workspace.read(self.root / '.control' / 'requests' / (request['id'] + '.json'), private=True, limit=32768)
        dirty['error'] = 'private failure text'
        dirty['readback'] = '/secret/path'
        safe = view(dirty)
        self.assertNotIn('private failure text', json.dumps(safe))
        self.assertNotIn('/secret/path', json.dumps(safe))
        self.assertEqual([item['phase'] for item in safe['phases']], ['queued', 'claimed'])

        for key in ('lifecycle_version', 'operation_id', 'phase_events', 'recovery_of'):
            dirty.pop(key)
        legacy = view(dirty)
        self.assertEqual(legacy, {'operation_id': request['id'], 'classification': 'legacy', 'phase': 'unknown', 'phases': []})

        malformed = dict(dirty, lifecycle_version=0, operation_id=request['id'], phase_events=[], recovery_of=None)
        unknown = view(malformed)
        self.assertEqual(unknown['classification'], 'unknown')
        self.assertEqual(unknown['phase'], 'unknown')
        self.assertEqual(unknown['phases'], [])
        self.assertIsNone(unknown['operation_id'])
        self.assertNotIn('native-started', json.dumps(unknown))
