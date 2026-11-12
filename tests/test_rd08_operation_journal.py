"""Server operation identity and additive phase journal.

Synthetic plugin responses are not live Figma evidence.
"""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import figma_control as control
import figma_workspace as workspace
from test_graph_sync import fixture


PHASE_TIME = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class OperationJournalTests(unittest.TestCase):
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

    def enqueue(self, **changes):
        values = dict(root=self.root, key='discovery', operation='read', file_key='fixturefile', page_id='12:1', revision=self.prepared['revision'], timeout=120)
        values.update(changes)
        return control.enqueue(**values)

    def claim(self, **changes):
        payload = {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': workspace.current(self.root)['runtime']}
        payload.update(changes)
        return control.poll(self.root, payload)['operation']

    def finish(self, claim, **changes):
        payload = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        payload.update(status='ok', readback_json='{"scope":"synthetic-test-only"}')
        payload.update(changes)
        return control.result(self.root, payload)

    def stored(self, operation_id):
        return workspace.read(self.root / '.control' / 'requests' / (operation_id + '.json'), private=True, limit=32768)

    def assert_server_events(self, request, phases):
        self.assertEqual([event['phase'] for event in request['phase_events']], phases)
        self.assertTrue(all(event['source'] == 'server' and PHASE_TIME.fullmatch(event['time']) for event in request['phase_events']))
        self.assertNotIn('native-started', json.dumps(request))

    def test_server_operation_journal_is_additive_and_rejects_client_authority(self):
        request = self.enqueue()
        self.assertEqual(request.get('lifecycle_version'), 1, 'server lifecycle journal must be stored with the operation')
        self.assertEqual(request['operation_id'], request['id'])
        self.assertTrue(re.fullmatch(r'[a-f0-9]{32}', request['operation_id']))
        self.assertIsNone(request['recovery_of'])
        self.assert_server_events(request, ['queued'])
        self.assertEqual(self.stored(request['id'])['phase_events'], request['phase_events'])

        claim = self.claim()
        claimed = control.status(self.root)
        self.assert_server_events(claimed, ['queued', 'claimed'])
        self.assertEqual(claimed['operation_id'], request['operation_id'])
        with self.assertRaises(ValueError):
            self.finish(claim, operation_id='client-forged')
        self.assertEqual(control.status(self.root)['operation_id'], request['operation_id'])
        self.assert_server_events(control.status(self.root), ['queued', 'claimed'])
        self.finish(claim)
        completed = control.status(self.root)
        self.assert_server_events(completed, ['queued', 'claimed', 'result-received'])
        self.assertIsNone(completed['recovery_of'])
        self.assertEqual(completed['state'], 'ok')

        expired = self.enqueue(timeout=1)
        with patch.object(control.time, 'time', return_value=expired['deadline'] + 1):
            current = control.status(self.root)
        self.assertEqual(current['state'], 'expired')
        self.assert_server_events(current, ['queued'])

        uncertain_read = self.enqueue(timeout=1)
        read_claim = self.claim()
        with patch.object(control.time, 'time', return_value=uncertain_read['deadline'] + 1):
            current = control.status(self.root)
            with self.assertRaises(ValueError):
                self.finish(read_claim)
        self.assertEqual(current['state'], 'uncertain')
        self.assert_server_events(current, ['queued', 'claimed', 'uncertain'])

        legacy = self.enqueue()
        bare = self.stored(legacy['id'])
        for key in ('lifecycle_version', 'operation_id', 'phase_events', 'recovery_of'):
            bare.pop(key)
        control.save(self.root / '.control', bare)
        legacy_claim = self.claim()
        self.finish(legacy_claim)
        legacy_stored = self.stored(legacy['id'])
        self.assertNotIn('phase_events', legacy_stored)
        self.assertNotIn('native-started', json.dumps(legacy_stored))

        graph, native = fixture()
        native.update(fileKey='fixturefile', pageId='12:1')
        for node in native['nodes']:
            if node.get('parentId') == 'page':
                node['parentId'] = '12:1'
        source, baseline = self.directory / 'graph.json', self.directory / 'native.json'
        source.write_text(json.dumps(graph))
        baseline.write_text(json.dumps(native))
        mutating = workspace.prepare(self.root, 'mutation', 'Apply graph', 'sync', ['--graph', str(source), '--native-readback', str(baseline)])
        original = self.enqueue(key='mutation', operation='apply', revision=mutating['revision'], timeout=1)
        self.claim()
        with patch.object(control.time, 'time', return_value=original['deadline'] + 1):
            uncertain = control.status(self.root)
        self.assertEqual(uncertain['state'], 'uncertain')
        self.assert_server_events(uncertain, ['queued', 'claimed', 'uncertain'])
        receipt = (self.root / '.control' / 'receipts' / (original['id'] + '.json')).read_bytes()
        recovery = self.enqueue()
        raw = json.dumps({'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1',
                          'allowed_page_ids': ['12:1'], 'nodes': [], 'variables': [], 'collections': []})
        self.finish(self.claim(), readback_json=raw)
        recovered = control.status(self.root)
        self.assertEqual(recovered['reconciles'], [original['id']])
        self.assertEqual(recovered['recovery_of'], [original['id']])
        self.assert_server_events(recovered, ['queued', 'claimed', 'result-received', 'reconciled'])
        self.assertEqual((self.root / '.control' / 'receipts' / (original['id'] + '.json')).read_bytes(), receipt)
        self.assertEqual(self.stored(original['id'])['state'], 'uncertain')
        self.assertEqual(recovered['operation_id'], recovery['operation_id'])

        malformed = self.enqueue()
        tampered = self.stored(malformed['id'])
        tampered['lifecycle_version'] = 0
        control.save(self.root / '.control', tampered)
        with self.assertRaisesRegex(ValueError, 'Invalid operation lifecycle'):
            self.claim()
        self.assertEqual(control.status(self.root)['state'], 'pending')
        self.assertEqual(self.stored(malformed['id'])['lifecycle_version'], 0)
        self.assertNotIn('native-started', json.dumps(self.stored(malformed['id'])))
