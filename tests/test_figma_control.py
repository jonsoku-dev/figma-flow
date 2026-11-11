"""Relay protocol tests. Synthetic plugin responses are not live Figma evidence."""
import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_control as control
import figma_workspace as workspace


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class ControlTests(unittest.TestCase):
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

    def start_server(self, handler=control.Handler):
        settings = control.config(self.root)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.workspace, server.token = self.root, settings['token']
        settings['port'] = server.server_port
        workspace.atomic(self.root / 'control.json', workspace.encode(settings))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def run_args(self, *extra):
        return ['run', '--workspace', str(self.root), '--key', 'discovery', '--operation', 'read',
                '--file-key', 'fixturefile', '--page-id', '12:1', '--expected-revision', self.prepared['revision'], *extra]

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

    def claim(self, **changes):
        payload = {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1'}
        payload.update(changes)
        return control.poll(self.root, payload)['operation']

    def result(self, claim, **changes):
        payload = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        payload.update(status='ok', readback_json='{"scope":"synthetic-test-only"}\n')
        payload.update(changes)
        return control.result(self.root, payload)

    def mutation(self, **changes):
        if not hasattr(self, 'mutating'):
            from test_graph_sync import fixture
            graph, native = fixture()
            native.update(fileKey='fixturefile', pageId='12:1')
            for node in native['nodes']:
                if node.get('parentId') == 'page':
                    node['parentId'] = '12:1'
            source, baseline = self.directory / 'graph.json', self.directory / 'native.json'
            source.write_text(json.dumps(graph))
            baseline.write_text(json.dumps(native))
            self.mutating = workspace.prepare(self.root, 'mutation', 'Apply graph', 'sync', ['--graph', str(source), '--native-readback', str(baseline)])
        return self.enqueue(key='mutation', operation='apply', revision=self.mutating['revision'], **changes)

    def uncertain_mutation(self):
        request = self.mutation(timeout=1)
        self.claim()
        with patch.object(control.time, 'time', return_value=request['deadline'] + 1):
            self.assertEqual(control.status(self.root)['state'], 'uncertain')
        return request

    def discovery_readback(self, **changes):
        value = {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1',
                 'allowed_page_ids': ['12:1'], 'nodes': [], 'variables': [], 'collections': [], 'observed_at': 'synthetic-test-only'}
        value.update(changes)
        return json.dumps(value)

    def test_enable_is_private_idempotent_and_rejects_rotation(self):
        before = (self.root / 'control.json').read_bytes()
        control.enable(self.root, 49198)
        self.assertEqual(before, (self.root / 'control.json').read_bytes())
        self.assertEqual((self.root / 'control.json').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            control.enable(self.root, 49199)
        with self.assertRaises(ValueError):
            control.enable(self.root, 80)

    def test_revision_kind_scope_and_single_active_admission(self):
        self.assertEqual(control.OPERATIONS['review'], {'create'})
        for mutation in ({'revision': '0' * 64}, {'operation': 'apply'}, {'file_key': 'other'}, {'page_id': '12:2'}, {'timeout': float('nan')}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.enqueue(**mutation)
        self.enqueue()
        with self.assertRaises(ValueError):
            self.enqueue()

    def test_poll_never_enqueues_or_redelivers_claim(self):
        self.assertIsNone(self.claim())
        request = self.enqueue()
        self.assertIsNone(self.claim(page_id='12:9'))
        claim = self.claim()
        self.assertEqual(claim['id'], request['id'])
        self.assertIsNone(self.claim())
        self.assertIsNone(self.claim(session_id='other-session'))
        self.assertEqual(control.status(self.root)['state'], 'claimed')

    def test_explicit_focus_claims_only_same_file_and_returns_pinned_target(self):
        self.enqueue(focus_page=True)
        self.assertIsNone(self.claim(file_key='otherfile', page_id='12:9'))
        self.assertEqual(control.status(self.root)['state'], 'pending')
        claim = self.claim(page_id='12:9')
        self.assertTrue(claim['focus_page'])
        self.assertEqual(claim['file_key'], 'fixturefile')
        self.assertEqual(claim['page_id'], '12:1')
        self.result(claim)

    def test_focus_rejects_unpinned_signed_tasks_and_nonboolean_options(self):
        with self.assertRaises(ValueError):
            self.enqueue(focus_page='yes')
        with workspace.locked(self.root):
            catalogue = workspace.current(self.root)
            catalogue['tasks'][0].update(fileKey=None, pageId=None)
            workspace.publish(self.root, catalogue)
        with self.assertRaisesRegex(ValueError, 'exact signed task'):
            self.enqueue(focus_page=True)
        self.enqueue()
        self.assertIsNone(self.claim(page_id='12:9'))
        claim = self.claim()
        self.assertFalse(claim['focus_page'])

    def test_cli_explicit_focus_option_is_preserved(self):
        self.start_server()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = control.main(['run', '--workspace', str(self.root), '--key', 'discovery', '--operation', 'read', '--file-key', 'fixturefile', '--page-id', '12:1', '--expected-revision', self.prepared['revision'], '--focus-page', '--no-wait'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())['focus_page'])

    def test_result_exact_claim_and_scope_and_preserves_large_bytes(self):
        self.enqueue()
        claim = self.claim()
        for change in ({'session_id': 'other'}, {'claim_id': '0' * 32}, {'revision': '0' * 64}, {'file_key': 'other'}, {'page_id': '12:9'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.result(claim, **change)
        raw = '{"scope":"synthetic-test-only","payload":"' + 'x' * 3_000_000 + '"}\n'
        self.result(claim, readback_json=raw)
        receipt = control.status(self.root)
        self.assertEqual(receipt['state'], 'ok')
        self.assertEqual(Path(receipt['readback']).read_bytes(), raw.encode())
        self.assertEqual(Path(receipt['readback']).stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.root / '.control/receipts' / (claim['id'] + '.json')).is_file())
        with self.assertRaises(ValueError):
            self.result(claim)

    def test_error_receipt_and_required_readback(self):
        self.enqueue()
        claim = self.claim()
        with self.assertRaises(ValueError):
            self.result(claim, readback_json=None)
        self.result(claim, status='error', readback_json=None, error='Synthetic plugin failure')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(control.main(['status', '--workspace', str(self.root)]), 2)
        self.assertEqual(control.status(self.root)['error'], 'Synthetic plugin failure')

    def test_deadline_before_claim_expires_after_claim_is_uncertain(self):
        request = self.enqueue(timeout=1)
        with patch.object(control.time, 'time', return_value=request['deadline'] + 1):
            self.assertEqual(control.status(self.root)['state'], 'expired')
        request = self.enqueue(timeout=1)
        claim = self.claim()
        with patch.object(control.time, 'time', return_value=request['deadline'] + 1):
            self.assertEqual(control.status(self.root)['state'], 'uncertain')
            with self.assertRaises(ValueError):
                self.result(claim)
        self.assertIsNone(self.claim())
        self.assertEqual(control.status(self.root)['uncertain_operations'], [])
        self.enqueue()
        self.assertEqual(control.status(self.root)['state'], 'pending')
        self.assertEqual(control.status(self.root, request['id'])['state'], 'uncertain')

    def test_expired_or_failed_recovery_read_does_not_unblock_mutation(self):
        original = self.uncertain_mutation()
        receipt = (self.root / '.control/receipts' / (original['id'] + '.json')).read_bytes()
        read = self.enqueue(timeout=1)
        with patch.object(control.time, 'time', return_value=read['deadline'] + 1):
            self.assertEqual(control.status(self.root)['state'], 'expired')
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.mutation()
        self.enqueue()
        self.result(self.claim(), status='error', readback_json=None, error='Synthetic read failed')
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.mutation()
        self.assertEqual((self.root / '.control/receipts' / (original['id'] + '.json')).read_bytes(), receipt)

    def test_successful_unrelated_or_wrong_getter_read_does_not_reconcile(self):
        original = self.uncertain_mutation()
        other = workspace.prepare(self.root, 'other-page', 'Other scope', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:9'])
        self.enqueue(key='other-page', page_id='12:9', revision=other['revision'])
        self.result(self.claim(page_id='12:9'), readback_json=self.discovery_readback(pageId='12:9', allowed_page_ids=['12:9']))
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.mutation()
        for raw in ('{}', self.discovery_readback(pageId='12:9'), self.discovery_readback(fileKey='otherfile'), self.discovery_readback(status='failed'), self.discovery_readback(allowed_page_ids=None)):
            self.enqueue()
            self.result(self.claim(), readback_json=raw)
            with self.assertRaisesRegex(ValueError, 'uncertain'):
                self.mutation()
        self.assertEqual(control.status(self.root)['uncertain_operations'][0]['id'], original['id'])

    def test_signed_same_scope_discovery_recovers_and_audits_without_rewriting_original(self):
        original = self.uncertain_mutation()
        receipt = (self.root / '.control/receipts' / (original['id'] + '.json')).read_bytes()
        read = self.enqueue()
        self.result(self.claim(), readback_json=self.discovery_readback())
        self.assertEqual(control.status(self.root)['reconciles'], [original['id']])
        self.assertEqual(control.status(self.root)['uncertain_operations'], [])
        self.assertEqual((self.root / '.control/receipts' / (original['id'] + '.json')).read_bytes(), receipt)
        self.assertEqual(workspace.read(self.root / '.control/receipts' / (read['id'] + '.json'), private=True)['reconciles'], [original['id']])
        self.mutation()
        self.assertEqual(control.status(self.root)['state'], 'pending')

    def test_changed_mutating_revision_requires_scoped_discovery_not_new_revision_read(self):
        original = self.mutation()
        claim = self.claim()
        changed = workspace.prepare(self.root, 'mutation', 'Updated apply', 'sync', ['--graph', str(self.directory / 'graph.json'), '--native-readback', str(self.directory / 'native.json')], replace_expected=self.mutating['revision'])
        with self.assertRaises(ValueError):
            self.result(claim)
        self.enqueue(key='mutation', revision=changed['revision'])
        raw = json.dumps({'schema': 'figma-flow-graph-token-readback-v1', 'operation': 'inspect', 'file_key': 'fixturefile', 'page_id': '12:1', 'tokens': [], 'components': []})
        self.result(self.claim(), readback_json=raw)
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.enqueue(key='mutation', operation='apply', revision=changed['revision'])
        self.enqueue()
        self.result(self.claim(), readback_json=self.discovery_readback())
        self.assertEqual(control.status(self.root)['reconciles'], [original['id']])
        self.enqueue(key='mutation', operation='apply', revision=changed['revision'])

    def test_same_task_revision_focused_getter_recovers_uncertain_apply(self):
        original = self.uncertain_mutation()
        self.enqueue(key='mutation', revision=self.mutating['revision'])
        raw = json.dumps({'schema': 'figma-flow-graph-token-readback-v1', 'operation': 'inspect',
                          'file_key': 'fixturefile', 'page_id': '12:1', 'tokens': [], 'components': []})
        self.result(self.claim(), readback_json=raw)
        self.assertEqual(control.status(self.root)['reconciles'], [original['id']])
        self.mutation()

    def test_create_only_review_recovers_via_signed_discovery_of_original_scope(self):
        with patch.object(control, 'task', return_value={'kind': 'review'}):
            original = self.enqueue(key='review-create', operation='create', revision='f' * 64, timeout=1)
            self.claim()
        with patch.object(control.time, 'time', return_value=original['deadline'] + 1):
            self.assertEqual(control.status(self.root)['state'], 'uncertain')
        self.enqueue()
        self.result(self.claim(), readback_json=self.discovery_readback())
        self.assertEqual(control.status(self.root)['reconciles'], [original['id']])
        self.mutation()

    def test_legacy_pointer_bypass_is_recovered_and_pending_mutation_never_claims(self):
        original = self.uncertain_mutation()
        self.enqueue()
        self.result(self.claim(), status='error', readback_json=None)
        (self.root / '.control/uncertainty.json').unlink()
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.mutation()
        self.assertEqual(control.status(self.root)['uncertain_operations'][0]['id'], original['id'])
        # A queued legacy mutation must also be rejected at the claim boundary.
        directory = self.root / '.control'
        forged_pending = dict(original, id='f' * 32, state='pending', deadline=control.time.time() + 120)
        control.save(directory, forged_pending)
        workspace.atomic(directory / 'active.json', workspace.encode({'id': forged_pending['id']}))
        self.assertIsNone(self.claim())
        self.assertEqual(control.status(self.root)['state'], 'error')

    def test_sync_requires_actual_success_payload_and_preserves_preview_error(self):
        with patch.object(control, 'task', return_value={'kind': 'import'}):
            self.enqueue(operation='sync')
            claim = self.claim()
            for raw in (None, '{"status":"error"}', '{"status":"ok"}'):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    self.result(claim, readback_json=raw)
            raw = '{"status":"applied","preview_error":"Synthetic independent preview failure"}'
            self.result(claim, readback_json=raw)
        receipt = control.status(self.root)
        self.assertEqual(receipt['state'], 'ok')
        self.assertIn('preview_error', Path(receipt['readback']).read_text())

    def test_cli_wait_exits_nonzero_on_deadline(self):
        self.start_server()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = control.main(['run', '--workspace', str(self.root), '--key', 'discovery', '--operation', 'read', '--file-key', 'fixturefile', '--page-id', '12:1', '--expected-revision', self.prepared['revision'], '--timeout', '1'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['state'], 'expired')

    def test_changed_signed_task_artifact_is_not_claimed(self):
        self.enqueue()
        row = workspace.current(self.root)['tasks'][0]
        bundle = workspace.task_artifacts(self.root, row)
        (bundle / 'code.js').write_text('changed outside trusted compiler')
        self.assertIsNone(self.claim())
        self.assertEqual(control.status(self.root)['state'], 'error')

    def test_result_after_catalogue_revision_change_becomes_uncertain(self):
        self.enqueue()
        claim = self.claim()
        workspace.prepare(self.root, 'discovery', 'Updated read', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'], replace_expected=self.prepared['revision'])
        with self.assertRaises(ValueError):
            self.result(claim)
        self.assertEqual(control.status(self.root)['state'], 'uncertain')

    def test_http_auth_exact_endpoints_and_no_remote_queue(self):
        config = control.config(self.root)
        server = ThreadingHTTPServer(('127.0.0.1', 0), control.Handler)
        server.workspace, server.token = self.root, config['token']
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def post(path, payload, **headers):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            base = {'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + config['token'], 'Content-Type': 'application/json'}
            base.update(headers)
            connection.request('POST', path, json.dumps(payload), base)
            response = connection.getresponse()
            code, body = response.status, json.loads(response.read())
            connection.close()
            return code, body

        payload = {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1'}
        self.assertEqual(post('/control/poll', payload, Authorization='Bearer wrong')[0], 403)
        self.assertEqual(post('/control/poll', payload, Host='evil.example')[0], 403)
        self.assertEqual(post('/control/poll', payload, Origin='https://evil.example')[0], 403)
        self.assertEqual(post('/control/run', payload)[0], 403)
        self.assertEqual(post('/control/poll', {**payload, 'script': 'eval()'})[0], 409)
        self.enqueue()
        code, response = post('/control/poll', payload)
        self.assertEqual(code, 200)
        claim = response['operation']
        result = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        result.update(status='ok', readback_json='{"scope":"synthetic-http-only"}')
        self.assertEqual(post('/control/result', result)[0], 200)
        self.assertEqual(control.status(self.root)['state'], 'ok')

    def test_cli_no_wait_status_and_invalid_arguments(self):
        self.start_server()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = control.main(['run', '--workspace', str(self.root), '--key', 'discovery', '--operation', 'read', '--file-key', 'fixturefile', '--page-id', '12:1', '--expected-revision', self.prepared['revision'], '--no-wait'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['state'], 'pending')
        pending = control.status(self.root)
        self.assertEqual(pending['state'], 'pending')
        self.assertNotIn('session_id', pending)
        with self.assertRaises(ValueError):
            control.status(self.root, '../escape')

    def test_readiness_is_authenticated_exact_and_read_only(self):
        server = self.start_server()
        settings = control.config(self.root)
        before = self.snapshot()

        def post(body=b'{}', **headers):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            base = {'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + settings['token'],
                    'Content-Type': 'application/json'}
            base.update(headers)
            connection.request('POST', '/control/readiness', body, base)
            response = connection.getresponse()
            code, value = response.status, json.loads(response.read())
            connection.close()
            return code, value

        with patch.object(control, 'state_dir', side_effect=AssertionError('Readiness touched queue')), \
                patch.object(control, 'active', side_effect=AssertionError('Readiness checked deadline')), \
                patch.object(control, 'poll', side_effect=AssertionError('Readiness polled')), \
                patch.object(control, 'status', side_effect=AssertionError('Readiness checked status')):
            self.assertEqual(post(Authorization='Bearer wrong')[0], 403)
            self.assertEqual(post(Host='evil.example')[0], 403)
            self.assertEqual(post(Origin='https://evil.example')[0], 403)
            for body in (b'{"unexpected":true}', b'[]', b'null', b'{'):
                self.assertEqual(post(body)[0], 409)
            self.assertEqual(post(**{'Content-Length': str(control.MAX_BODY + 1)})[0], 413)
            code, value = post(Origin='null')
            self.assertEqual(code, 200)
            self.assertEqual(value, control.readiness())
        self.assertEqual(self.snapshot(), before)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Re-read installed files')):
            self.assertEqual(control.readiness(), value)

    def test_readiness_failures_precede_all_cli_queue_mutations(self):
        class ResponseHandler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.server.observed = (self.path, self.headers.get('Host'), self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(self.server.code)
                if self.server.include_length:
                    self.send_header('Content-Length', str(len(self.server.body)))
                self.end_headers()
                self.wfile.write(self.server.body)

        server = self.start_server(ResponseHandler)
        server.include_length = True
        valid = control.readiness()
        cases = [(403, b'{}', 'HTTP 403'), (404, b'{}', 'HTTP 404'),
                 (200, b'{', 'malformed'), (200, b'[]', 'unsupported format'),
                 (200, b'x' * (control.MAX_READINESS + 1), 'oversized')]
        for field in ('schema', 'protocol', 'version', 'implementation'):
            cases.append((200, workspace.encode({**valid, field: 'old'}), 'differs'))
        cases.extend([(200, workspace.encode({**valid, 'operations': {'discover': []}}), 'does not support'),
                      (200, workspace.encode({**valid, 'operations': []}), 'capabilities are malformed')])
        for code, body, message in cases:
            server.code, server.body = code, body
            before = self.snapshot()
            for extra in ((), ('--no-wait',)):
                with self.subTest(code=code, message=message, extra=extra), \
                        contextlib.redirect_stderr(io.StringIO()) as error, \
                        patch.object(control, 'enqueue', side_effect=AssertionError('Enqueued before readiness')):
                    self.assertEqual(control.main(self.run_args(*extra)), 2)
                    self.assertIn(message, error.getvalue())
                    self.assertIn('restart only this workspace', error.getvalue())
                    self.assertNotIn(control.config(self.root)['token'], error.getvalue())
                self.assertEqual(self.snapshot(), before)
            self.assertEqual(server.observed, ('/control/readiness', f'localhost:{server.server_port}', b'{}'))
        server.include_length = False
        server.code, server.body = 200, b'x' * (control.MAX_READINESS + 1)
        before = self.snapshot()
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(control.main(self.run_args('--no-wait')), 2)
        self.assertIn('oversized', error.getvalue())
        self.assertEqual(self.snapshot(), before)

    def test_current_server_admits_native_edit_after_readiness(self):
        plan = self.directory / 'edit.json'
        plan.write_text(json.dumps({'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile', 'page_id': '12:1',
            'edits': [{'node_id': '3:4', 'field': 'paddingLeft', 'before': 12, 'after': 20}]}))
        prepared = workspace.prepare(self.root, 'native-edit', 'Edit scoped values', 'native-edit', ['--plan', str(plan)])
        self.start_server()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = control.main(['run', '--workspace', str(self.root), '--key', 'native-edit', '--operation', 'apply',
                '--file-key', 'fixturefile', '--page-id', '12:1', '--expected-revision', prepared['revision'], '--no-wait'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['state'], 'pending')
        self.assertEqual(self.claim()['key'], 'native-edit')

    def test_missing_server_rejects_before_queue_mutation(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), control.Handler)
        settings = control.config(self.root)
        settings['port'] = server.server_port
        server.server_close()
        workspace.atomic(self.root / 'control.json', workspace.encode(settings))
        before = self.snapshot()
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(control.main(self.run_args('--no-wait')), 2)
        self.assertIn('Control server is not running', error.getvalue())
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
