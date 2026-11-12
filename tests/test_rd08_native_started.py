"""Explicit native-started delivery with claim and runtime checks.

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
class NativeStartedTests(unittest.TestCase):
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
        self.runtime = workspace.current(self.root)['runtime']

    def enqueue(self):
        return control.enqueue(self.root, 'discovery', 'read', 'fixturefile', '12:1', self.prepared['revision'], 120)

    def claim(self):
        return control.poll(self.root, {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': self.runtime})['operation']

    def started_payload(self, claim, **changes):
        payload = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        payload['runtime'] = self.runtime
        payload.update(changes)
        return payload

    def test_native_started_requires_explicit_authenticated_runtime(self):
        report = getattr(control, 'note_native_started', None)
        self.assertIsNotNone(report, 'native-started must be an explicit authenticated runtime event')
        plugin = (ROOT / 'figma-bridge' / 'workspace_control.js').read_text(encoding='utf-8')
        server = (ROOT / 'tools' / 'figma_control.py').read_text(encoding='utf-8')
        started = plugin.index("controlRequest('native-started'")
        execute = plugin.index('controlExecute(workspaceTasks.get(cmd.key), cmd)')
        self.assertLess(started, execute)
        self.assertIn("'/control/native-started'", server)

        request = self.enqueue()
        claim = self.claim()
        current = control.status(self.root)
        self.assertEqual([event['phase'] for event in current['phase_events']], ['queued', 'claimed'])
        self.assertEqual(current['state'], 'claimed')
        self.assertNotIn('native-started', json.dumps(current))

        bad_runtime = dict(self.runtime)
        bad_runtime['generation'] = '0' * 32 if self.runtime['generation'] != '0' * 32 else '1' * 32
        with self.assertRaises(ValueError):
            report(self.root, self.started_payload(claim, runtime=bad_runtime))
        with self.assertRaises(ValueError):
            report(self.root, self.started_payload(claim, operation_id='client-forged'))
        with self.assertRaises(ValueError):
            report(self.root, self.started_payload(claim, claim_id='0' * 32))
        self.assertEqual([event['phase'] for event in control.status(self.root)['phase_events']], ['queued', 'claimed'])
        self.assertEqual(control.status(self.root)['state'], 'claimed')

        accepted = report(self.root, self.started_payload(claim))
        self.assertEqual(accepted['state'], 'claimed')
        self.assertEqual(accepted['phase'], 'native-started')
        self.assertNotEqual(accepted['state'], 'ok')
        recorded = control.status(self.root)
        self.assertEqual([event['phase'] for event in recorded['phase_events']], ['queued', 'claimed', 'native-started'])
        self.assertEqual(recorded['operation_id'], request['operation_id'])
        self.assertTrue(all(event['source'] == 'server' for event in recorded['phase_events']))
        with self.assertRaises(ValueError):
            report(self.root, self.started_payload(claim))
        self.assertEqual([event['phase'] for event in control.status(self.root)['phase_events']], ['queued', 'claimed', 'native-started'])

        payload = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        payload.update(status='ok', readback_json='{"scope":"synthetic-test-only"}')
        done = control.result(self.root, payload)
        self.assertEqual(done['state'], 'ok')
        self.assertEqual([event['phase'] for event in control.status(self.root)['phase_events']], ['queued', 'claimed', 'native-started', 'result-received'])

        legacy = self.enqueue()
        bare = control.status(self.root)
        for key in ('lifecycle_version', 'operation_id', 'phase_events', 'recovery_of'):
            bare.pop(key, None)
        bare.pop('uncertain_operations', None)
        control.save(self.root / '.control', bare)
        legacy_claim = self.claim()
        with self.assertRaises(ValueError):
            report(self.root, self.started_payload(legacy_claim))
        stored = workspace.read(self.root / '.control' / 'requests' / (legacy['id'] + '.json'), private=True, limit=32768)
        self.assertNotIn('phase_events', stored)
        self.assertNotIn('native-started', json.dumps(stored))
