"""Multi-tab concurrent control, isolated per-file uncertainty, and per-session profile tests."""
from __future__ import annotations

import contextlib
import http.client
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

import figma_control as control
import figma_workspace as workspace
from test_graph_sync import fixture as graph_fixture


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class MultiTabControlTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.root = self.dir / 'workspace'
        assigned = self.dir / 'assigned.json'
        assigned.write_text('{"id":"998877"}', encoding='utf-8')
        workspace.init(self.root, assigned)
        self.task_a = workspace.prepare(self.root, 'disc-a', 'Read File A', 'discover', ['--file-key', 'fileA', '--page-id', '12:1'])
        self.task_b = workspace.prepare(self.root, 'disc-b', 'Read File B', 'discover', ['--file-key', 'fileB', '--page-id', '12:2'])
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        control.enable(self.root, port, refresh=True)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        key = str(self.root.resolve())
        control.NATIVE_CLIENTS.pop(key, None)
        for k in [k for k in control.NATIVE_SESSIONS if k[0] == key]:
            control.NATIVE_SESSIONS.pop(k, None)
        with control.RELAY_LOCK:
            control.RELAY_STATES.pop(key, None)
        with control.METRICS_HUBS_LOCK:
            hub = control.METRICS_HUBS.pop(key, None)
        if hub is not None:
            hub.close()

    def start_server(self):
        settings = control.config(self.root)

        class _ReuseServer(ThreadingHTTPServer):
            allow_reuse_address = True

        server = _ReuseServer(('127.0.0.1', int(settings['port'])), control.Handler)
        server.workspace = self.root
        server.token = settings['token']
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, settings

    def post(self, server, settings, route, payload):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        conn.request(
            'POST',
            route,
            workspace.encode(payload),
            {
                'Host': f'localhost:{server.server_port}',
                'Authorization': 'Bearer ' + settings['token'],
                'Content-Type': 'application/json',
            },
        )
        resp = conn.getresponse()
        body = json.loads(resp.read())
        conn.close()
        return resp.status, body

    def _poll_payload(self, session_id, file_key, page_id, *, needs_setup=False, plan='unknown', seat='unknown', profile_result=None):
        runtime = workspace.current(self.root)['runtime']
        profile = {'declared': {'plan': plan, 'seat': seat}, 'needsSetup': needs_setup, 'storage': 'local'}
        relay = {'context': {'session_id': session_id, 'file_key': file_key, 'page_id': page_id, 'user_id': 'user-1', 'selection': [], 'profile': profile}}
        if profile_result is not None:
            relay['profile_result'] = profile_result
        return {'session_id': session_id, 'file_key': file_key, 'page_id': page_id, 'runtime': runtime, 'relay': relay}

    def _prepare_sync(self, key, file_key, page_id):
        graph, native = graph_fixture()
        native.update(fileKey=file_key, pageId=page_id)
        for node in native['nodes']:
            if node.get('parentId') == 'page':
                node['parentId'] = page_id
        src = self.dir / f'{key}-graph.json'
        base = self.dir / f'{key}-native.json'
        src.write_text(json.dumps(graph), encoding='utf-8')
        base.write_text(json.dumps(native), encoding='utf-8')
        return workspace.prepare(self.root, key, f'Sync {file_key}', 'sync', ['--graph', str(src), '--native-readback', str(base)])

    def test_two_tabs_run_concurrently_without_clobbering_native_started_or_status(self):
        server, settings = self.start_server()
        runtime = workspace.current(self.root)['runtime']

        # Both tabs poll concurrently
        c_a, _ = self.post(server, settings, '/control/poll', self._poll_payload('tab-session-a', 'fileA', '12:1'))
        c_b, _ = self.post(server, settings, '/control/poll', self._poll_payload('tab-session-b', 'fileB', '12:2'))
        self.assertEqual((c_a, c_b), (200, 200))

        # Sessions endpoint sees both tabs independently
        sessions = control.relay_request(self.root, 'sessions')
        self.assertEqual(sessions['state'], 'ok')
        self.assertEqual(sessions['count'], 2)
        self.assertEqual({row['file_key']: row['session_id'] for row in sessions['sessions']}, {'fileA': 'tab-session-a', 'fileB': 'tab-session-b'})
        self.assertTrue(all(row['native_status'] == 'current-self-reported' for row in sessions['sessions']))

        # Scoped context lookup
        ctx_a = control.relay_request(self.root, 'context', file_key='fileA')
        self.assertEqual(ctx_a['context']['session_id'], 'tab-session-a')
        self.assertTrue(ctx_a['multiple_sessions'])
        self.assertEqual(ctx_a['sessions_count'], 2)

        # Concurrent enqueue across different files succeeds; second enqueue on same file still rejects
        op_a = control.enqueue(self.root, 'disc-a', 'read', 'fileA', '12:1', self.task_a['revision'], 120)
        op_b = control.enqueue(self.root, 'disc-b', 'read', 'fileB', '12:2', self.task_b['revision'], 120)
        with self.assertRaisesRegex(ValueError, 'already active'):
            control.enqueue(self.root, 'disc-a', 'read', 'fileA', '12:1', self.task_a['revision'], 120)

        # Both tabs claim their own operations
        _, poll_a = self.post(server, settings, '/control/poll', self._poll_payload('tab-session-a', 'fileA', '12:1'))
        _, poll_b = self.post(server, settings, '/control/poll', self._poll_payload('tab-session-b', 'fileB', '12:2'))
        claim_a = poll_a['operation']
        claim_b = poll_b['operation']
        self.assertEqual(claim_a['id'], op_a['id'])
        self.assertEqual(claim_b['id'], op_b['id'])

        # Tab B polls again BEFORE Tab A sends /control/native-started -> Tab A MUST NOT get 409!
        self.post(server, settings, '/control/poll', self._poll_payload('tab-session-b', 'fileB', '12:2'))

        ns_a, _ = self.post(server, settings, '/control/native-started', {
            'id': claim_a['id'], 'claim_id': claim_a['claim_id'], 'session_id': 'tab-session-a',
            'file_key': 'fileA', 'page_id': '12:1', 'revision': claim_a['revision'], 'runtime': runtime,
        })
        ns_b, _ = self.post(server, settings, '/control/native-started', {
            'id': claim_b['id'], 'claim_id': claim_b['claim_id'], 'session_id': 'tab-session-b',
            'file_key': 'fileB', 'page_id': '12:2', 'revision': claim_b['revision'], 'runtime': runtime,
        })
        self.assertEqual((ns_a, ns_b), (200, 200))

        # Status shows both active operations simultaneously
        st = control.status(self.root)
        self.assertEqual({row['file_key'] for row in st['active_operations']}, {'fileA', 'fileB'})

        # Both complete independently
        res_a, _ = self.post(server, settings, '/control/result', {
            'id': claim_a['id'], 'claim_id': claim_a['claim_id'], 'session_id': 'tab-session-a',
            'file_key': 'fileA', 'page_id': '12:1', 'revision': claim_a['revision'],
            'status': 'ok', 'readback_json': '{"file":"fileA"}',
        })
        res_b, _ = self.post(server, settings, '/control/result', {
            'id': claim_b['id'], 'claim_id': claim_b['claim_id'], 'session_id': 'tab-session-b',
            'file_key': 'fileB', 'page_id': '12:2', 'revision': claim_b['revision'],
            'status': 'ok', 'readback_json': '{"file":"fileB"}',
        })
        self.assertEqual((res_a, res_b), (200, 200))
        self.assertEqual(control.status(self.root, file_key='fileA')['state'], 'ok')
        self.assertEqual(control.status(self.root, file_key='fileB')['state'], 'ok')

        # CLI sessions / context --file-key / status --file-key
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(control.main(['sessions', '--workspace', str(self.root)]), 0)
            self.assertEqual(control.main(['context', '--workspace', str(self.root), '--file-key', 'fileA']), 0)
            self.assertEqual(control.main(['status', '--workspace', str(self.root), '--file-key', 'fileB']), 0)
        lines = [json.loads(line) for line in out.getvalue().strip().splitlines()]
        self.assertEqual(lines[0]['count'], 2)
        self.assertEqual(lines[1]['context']['file_key'], 'fileA')
        self.assertEqual(lines[2]['file_key'], 'fileB')

    def test_uncertainty_on_one_file_blocks_only_that_file_and_allows_other_tab(self):
        sync_a = self._prepare_sync('sync-a', 'fileA', '12:1')
        sync_b = self._prepare_sync('sync-b', 'fileB', '12:2')

        # File A mutation times out -> uncertain
        req_a = control.enqueue(self.root, 'sync-a', 'apply', 'fileA', '12:1', sync_a['revision'], 1)
        control.poll(self.root, self._poll_payload('tab-a', 'fileA', '12:1'))
        with patch.object(control.time, 'time', return_value=req_a['deadline'] + 1):
            self.assertEqual(control.status(self.root, file_key='fileA')['state'], 'uncertain')

        # File A further writes blocked
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            control.enqueue(self.root, 'sync-a', 'apply', 'fileA', '12:1', sync_a['revision'], 30)

        # File B mutation succeeds even while File A is uncertain!
        control.enqueue(self.root, 'sync-b', 'apply', 'fileB', '12:2', sync_b['revision'], 30)
        claim_b = control.poll(self.root, self._poll_payload('tab-b', 'fileB', '12:2'))['operation']
        self.assertIsNotNone(claim_b)
        control.result(self.root, {
            'id': claim_b['id'], 'claim_id': claim_b['claim_id'], 'session_id': 'tab-b',
            'file_key': 'fileB', 'page_id': '12:2', 'revision': claim_b['revision'],
            'status': 'ok', 'readback_json': '{"schema":"figma-flow-graph-token-readback-v1","file_key":"fileB","page_id":"12:2","status":"success"}',
        })
        self.assertEqual(control.status(self.root, file_key='fileB')['state'], 'ok')

        # File A recovery read clears File A's uncertainty
        control.enqueue(self.root, 'disc-a', 'read', 'fileA', '12:1', self.task_a['revision'], 30)
        rec_a = control.poll(self.root, self._poll_payload('tab-a', 'fileA', '12:1'))['operation']
        control.result(self.root, {
            'id': rec_a['id'], 'claim_id': rec_a['claim_id'], 'session_id': 'tab-a',
            'file_key': 'fileA', 'page_id': '12:1', 'revision': rec_a['revision'],
            'status': 'ok',
            'readback_json': json.dumps({
                'schema': 'figma-flow-graph-native-discovery-v1',
                'fileKey': 'fileA',
                'pageId': '12:1',
                'allowed_page_ids': ['12:1'],
                'nodes': [], 'variables': [], 'collections': [],
            }),
        })
        self.assertEqual(control.status(self.root, file_key='fileA')['uncertain_operations'], [])
        # File A mutations allowed again
        self.assertEqual(control.enqueue(self.root, 'sync-a', 'apply', 'fileA', '12:1', sync_a['revision'], 30)['state'], 'pending')

    def test_per_session_profile_mailbox_avoids_cross_tab_race(self):
        server, settings = self.start_server()
        self.post(server, settings, '/control/poll', self._poll_payload('tab-a', 'fileA', '12:1', needs_setup=True))
        self.post(server, settings, '/control/poll', self._poll_payload('tab-b', 'fileB', '12:2', needs_setup=True))

        fp_a = control.relay_request(self.root, 'context', file_key='fileA')['context_fingerprint']
        fp_b = control.relay_request(self.root, 'context', file_key='fileB')['context_fingerprint']

        # Interleaved polls on Tab B do NOT cause scope-changed for Tab A's fingerprint!
        self.post(server, settings, '/control/poll', self._poll_payload('tab-b', 'fileB', '12:2', needs_setup=True))

        req_a = control.relay_request(self.root, 'profile-set', profile={'plan': 'professional', 'seat': 'full'}, expected_context=fp_a)
        req_b = control.relay_request(self.root, 'profile-set', profile={'plan': 'starter', 'seat': 'dev'}, expected_context=fp_b)
        self.assertEqual(req_a['state'], 'pending')
        self.assertEqual(req_b['state'], 'pending')

        # setup-status reports both connected tabs and needs profile confirmation
        ss_before = control.setup_status(self.root)
        self.assertEqual(ss_before['connected_session_count'], 2)
        self.assertFalse(ss_before['profile_confirmed'])

        # Each tab receives ONLY its own profile_request
        _, poll_b = self.post(server, settings, '/control/poll', self._poll_payload('tab-b', 'fileB', '12:2', needs_setup=True))
        _, poll_a = self.post(server, settings, '/control/poll', self._poll_payload('tab-a', 'fileA', '12:1', needs_setup=True))
        self.assertEqual(poll_b['relay']['profile_request']['request_id'], req_b['request_id'])
        self.assertEqual(poll_b['relay']['profile_request']['profile'], {'plan': 'starter', 'seat': 'dev'})
        self.assertEqual(poll_a['relay']['profile_request']['request_id'], req_a['request_id'])
        self.assertEqual(poll_a['relay']['profile_request']['profile'], {'plan': 'professional', 'seat': 'full'})

        # Confirm both
        self.post(server, settings, '/control/poll', self._poll_payload(
            'tab-a', 'fileA', '12:1', needs_setup=False, plan='professional', seat='full',
            profile_result={'request_id': req_a['request_id'], 'status': 'ok',
                            'profile': {'declared': {'plan': 'professional', 'seat': 'full'}, 'needsSetup': False, 'storage': 'local'}},
        ))
        self.post(server, settings, '/control/poll', self._poll_payload(
            'tab-b', 'fileB', '12:2', needs_setup=False, plan='starter', seat='dev',
            profile_result={'request_id': req_b['request_id'], 'status': 'ok',
                            'profile': {'declared': {'plan': 'starter', 'seat': 'dev'}, 'needsSetup': False, 'storage': 'local'}},
        ))
        ss_after = control.setup_status(self.root)
        self.assertEqual(ss_after['connected_session_count'], 2)
        self.assertTrue(ss_after['profile_confirmed'])
        self.assertTrue(ss_after['ready_for_work'])

    def test_reopen_same_file_supersedes_old_session_without_affecting_other_file(self):
        runtime = workspace.current(self.root)['runtime']
        control.poll(self.root, self._poll_payload('tab-a1', 'fileA', '12:1'))
        control.poll(self.root, self._poll_payload('tab-b1', 'fileB', '12:2'))
        # Reopen plugin on fileA with tab-a2
        control.poll(self.root, self._poll_payload('tab-a2', 'fileA', '12:1'))

        self.assertEqual(control.native_state(self.root, session_id='tab-a1', file_key='fileA')['native_status'], 'unverified')
        self.assertEqual(control.native_state(self.root, session_id='tab-a2', file_key='fileA')['native_status'], 'current-self-reported')
        self.assertEqual(control.native_state(self.root, session_id='tab-b1', file_key='fileB')['native_status'], 'current-self-reported')
        self.assertEqual(control._cli_context(self.root, {'session_id': 'tab-b1', 'file_key': 'fileB', 'page_id': '12:2', 'runtime': runtime})['native_status'], 'current-self-reported')


if __name__ == '__main__':
    unittest.main()
