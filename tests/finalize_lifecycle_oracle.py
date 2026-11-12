"""Frozen acceptance oracle: real private HTTP service and published runtime.

The Figma API surface is simulated; this does not claim live native acceptance.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_control as control
import figma_workspace as workspace


class FinalizeLifecycle(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'workspace'
        assigned = self.directory / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.root, assigned)
        prepared = workspace.prepare(self.root, 'discovery', 'Read values', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])
        self.server = control.ThreadingHTTPServer(('127.0.0.1', 0), control.Handler)
        self.addCleanup(self.server.server_close)
        control.enable(self.root, self.server.server_port)
        with workspace.locked(self.root):
            workspace.publish(self.root, workspace.current(self.root))
        self.server.workspace = self.root
        self.server.token = control.config(self.root)['token']
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.runtime = workspace.current(self.root)['runtime']
        self.request = control.enqueue(self.root, 'discovery', 'read', 'fixturefile', '12:1', prepared['revision'], 120)

    def post(self, payload, token=None):
        request = Request(f'http://localhost:{self.server.server_port}/control/history',
                          data=json.dumps(payload).encode(), headers={
                              'Authorization': 'Bearer ' + (self.server.token if token is None else token),
                              'Content-Type': 'application/json'})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def scope(self):
        return {'session_id': 'oracle-session', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': self.runtime}

    def test_authenticated_scope_bound_safe_history(self):
        with self.assertRaises(HTTPError) as rejected:
            self.post(self.scope(), token='wrong')
        self.assertEqual(rejected.exception.code, 403)
        rows = self.post(self.scope())['journalHistory']
        row = next(row for row in rows if row['operationId'] == self.request['id'])
        self.assertEqual((row['classification'], row['phase']), ('recorded', 'queued'))
        self.assertEqual([event['phase'] for event in row['phases']], ['queued'])
        self.assertLessEqual(len(rows), 80)
        self.assertFalse({'claim_id', 'readback_json', 'token', 'session_id', 'file_key', 'page_id'} & row.keys())
        self.assertNotIn(self.request['id'], json.dumps(self.post({**self.scope(), 'file_key': 'otherfile'})))
        for changes in ({'runtime': {**self.runtime, 'generation': '0' * 32}}, {'unexpected': True}):
            with self.assertRaises(HTTPError):
                self.post({**self.scope(), **changes})

    def run_runtime(self, mode):
        manifest = workspace.read(self.root / 'manifest.json')
        helper = ROOT / 'tests/helpers/finalize_lifecycle_runtime.cjs'
        result = subprocess.run(['node', str(helper), mode, str(self.root / manifest['main']), self.request['id']],
                                cwd=ROOT, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_published_host_projects_server_history_to_ui(self):
        self.run_runtime('history')

    def test_legacy_history_is_explicit_unknown_and_does_not_read_raw_payload(self):
        legacy = workspace.read(self.root / '.control/requests' / (self.request['id'] + '.json'), private=True)
        for key in ('lifecycle_version', 'operation_id', 'phase_events', 'recovery_of'):
            legacy.pop(key, None)
        legacy['readback_json'] = '{"private_node_text":"DO-NOT-PROJECT-ORACLE"}'
        control.save(self.root / '.control', legacy)
        reply = self.post(self.scope())
        row = next(row for row in reply['journalHistory'] if row['operationId'] == self.request['id'])
        self.assertEqual((row['classification'], row['phase'], row['phases']), ('legacy', 'unknown', []))
        self.assertNotIn('DO-NOT-PROJECT-ORACLE', json.dumps(reply))

    def test_stale_command_never_reports_native_started(self):
        self.run_runtime('stale')
        phases = [event['phase'] for event in control.status(self.root)['phase_events']]
        self.assertNotIn('native-started', phases)

    def test_expired_command_never_reports_native_started(self):
        self.run_runtime('expired')
        phases = [event['phase'] for event in control.status(self.root)['phase_events']]
        self.assertNotIn('native-started', phases)


if __name__ == '__main__':
    unittest.main()
