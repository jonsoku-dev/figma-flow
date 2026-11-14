"""NF-03 read-only exact-scope operation detail, causal links, and safe diff tests.

Synthetic plugin responses exercise real signed workspace and control server paths
without claiming live Figma Desktop getter execution.
"""
import copy
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

import figma_control as control
import figma_workspace as workspace
from graph_design_system import load_graph
from graph_sync import build_plan, normalize, receipt
import input_effect
import operation_detail as detail_mod
from test_figma_bridge import design as bridge_design
from test_graph_sync import fixture as graph_fixture

THREAD = '12345678-abcd-4abc-9abc-123456789abc'


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class OperationDetailTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'workspace'
        assigned = self.directory / 'assigned.json'
        assigned.write_text('{"id":"12345"}', encoding='utf-8')
        workspace.init(self.root, assigned)
        control.enable(self.root, 49215)
        self.server = None

    def start_server(self):
        if self.server is not None:
            return self.server
        settings = dict(control.config(self.root))
        server = ThreadingHTTPServer(('127.0.0.1', 0), control.Handler)
        server.workspace, server.token = self.root, settings['token']
        settings['port'] = server.server_port
        workspace.atomic(self.root / 'control.json', workspace.encode(settings))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.server = server
        return server

    def post(self, path, payload, **override_headers):
        server = self.start_server()
        settings = control.config(self.root)
        raw_body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode('utf-8')
        headers = {
            'Host': f'localhost:{server.server_port}',
            'Authorization': 'Bearer ' + settings['token'],
            'Content-Type': 'application/json',
        }
        headers.update(override_headers)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            conn.request('POST', path, raw_body, headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, json.loads(raw), raw
        finally:
            conn.close()

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): path.read_bytes() if path.is_file() else ('symlink' if path.is_symlink() else 'dir')
            for path in sorted(self.root.rglob('*'))
        }

    def current_runtime(self):
        return workspace.current(self.root, repair=False)['runtime']

    def detail_payload(self, operation_id, task_key, revision, *, file_key='fixturefile', page_id='12:1', runtime=None, session_id='plugin-session-1'):
        return {
            'session_id': session_id,
            'file_key': file_key,
            'page_id': page_id,
            'runtime': self.current_runtime() if runtime is None else runtime,
            'operation_id': operation_id,
            'task_key': task_key,
            'revision': revision,
        }

    def execute_run(self, key, operation, file_key, page_id, revision, readback_obj, *, status='ok', error=None, record_native_started=True, session_id='plugin-session-1'):
        req = control.enqueue(self.root, key, operation, file_key, page_id, revision, 120)
        runtime = self.current_runtime()
        polled = control.poll(self.root, {
            'session_id': session_id,
            'file_key': file_key,
            'page_id': page_id,
            'runtime': runtime,
        })
        claim = polled['operation']
        self.assertIsNotNone(claim)
        if record_native_started:
            control.note_native_started(self.root, {
                **{field: claim[field] for field in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')},
                'runtime': runtime,
            })
        res_payload = {
            **{field: claim[field] for field in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')},
            'status': status,
        }
        if readback_obj is not None:
            res_payload['readback_json'] = json.dumps(readback_obj)
        if error is not None:
            res_payload['error'] = error
        control.result(self.root, res_payload)
        return req['id']

    def prepare_task(self, key, title, kind, args, **kwargs):
        kwargs.setdefault('thread_id', THREAD)
        return workspace.prepare(self.root, key, title, kind, args, **kwargs)

    def make_pairing(self, graph_path, native, out_name='pairing.json'):
        loaded = load_graph(graph_path)
        plan = build_plan(loaded, native)
        focused = normalize(native, plan)
        focused['schema'] = 'figma-flow-graph-token-readback-v1'
        focused['baseline'] = {
            'page_id': native['pageId'],
            'collection_id': 'collection',
            'graph_sha256': plan['graph_sha256'],
        }
        pairing_obj = receipt(loaded, plan, focused)
        pairing_path = self.directory / out_name
        pairing_path.write_text(json.dumps(pairing_obj), encoding='utf-8')
        return pairing_path

    def make_input_record(self, folder_name='inputs', heading='Primary Workspace'):
        inp_dir = self.directory / folder_name
        inp_dir.mkdir(exist_ok=True)
        (inp_dir / 'brief.md').write_text(f'# Brief\nHeadline: {heading}\n', encoding='utf-8')
        (inp_dir / 'facts.json').write_text(json.dumps({'headline': heading}), encoding='utf-8')
        (inp_dir / 'authority.json').write_text(json.dumps({'facts': {'headline': {'priority': ['brief', 'html']}}}), encoding='utf-8')
        (inp_dir / 'index.html').write_text(
            f'<!doctype html><html><body><h1>{heading}</h1></body></html>\n',
            encoding='utf-8',
        )
        record = input_effect.project(inp_dir, {
            'schema': input_effect.SCHEMA,
            'brief': 'brief.md',
            'facts': 'facts.json',
            'authority': 'authority.json',
            'inputs': {'html': 'index.html'},
        })
        return record, inp_dir

    def test_exact_scope_404_cross_page_cross_file_runtime_and_binding_rejections(self):
        disc_main = self.prepare_task(
            'disc-main', 'Discover main', 'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'],
        )
        disc_other_page = self.prepare_task(
            'disc-page-b', 'Discover page B', 'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:9'],
        )
        disc_other_file = self.prepare_task(
            'disc-file-b', 'Discover file B', 'discover',
            ['--file-key', 'otherfile99', '--page-id', '12:1'],
        )

        op_main = self.execute_run(
            'disc-main', 'read', 'fixturefile', '12:1', disc_main['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'allowed_page_ids': ['12:1'], 'nodes': [], 'variables': [], 'collections': []},
        )
        op_other_page = self.execute_run(
            'disc-page-b', 'read', 'fixturefile', '12:9', disc_other_page['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:9', 'allowed_page_ids': ['12:9'], 'nodes': [], 'variables': [], 'collections': []},
        )
        op_other_file = self.execute_run(
            'disc-file-b', 'read', 'otherfile99', '12:1', disc_other_file['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'otherfile99', 'pageId': '12:1', 'allowed_page_ids': ['12:1'], 'nodes': [], 'variables': [], 'collections': []},
        )

        self.start_server()
        before_snapshot = self.snapshot()

        # 1. Exact-scope missing operation -> HTTP 404 not-found-in-scope.
        code, body, _ = self.post('/control/history-detail', self.detail_payload('f' * 32, 'disc-main', disc_main['revision']))
        self.assertEqual(code, 404)
        self.assertEqual(body['reason'], 'not-found-in-scope')

        # 2. Cross-page operation ID in same workspace -> HTTP 404 (never leaks foreign page body or binding oracle).
        for tk, rev in (('disc-page-b', disc_other_page['revision']), ('disc-main', disc_main['revision'])):
            code, body, raw = self.post(
                '/control/history-detail',
                self.detail_payload(op_other_page, tk, rev, file_key='fixturefile', page_id='12:1'),
            )
            self.assertEqual(code, 404)
            self.assertEqual(body['reason'], 'not-found-in-scope')
            self.assertNotIn(b'disc-page-b', raw)

        # 3. Cross-file operation ID -> HTTP 404.
        code, body, raw = self.post(
            '/control/history-detail',
            self.detail_payload(op_other_file, 'disc-file-b', disc_other_file['revision'], file_key='fixturefile', page_id='12:1'),
        )
        self.assertEqual(code, 404)
        self.assertEqual(body['reason'], 'not-found-in-scope')
        self.assertNotIn(b'otherfile99', raw)

        # 4. Stale / mismatched runtime -> HTTP 409 runtime-mismatch.
        stale_rt = dict(self.current_runtime(), generation='0' * 32)
        code, body, _ = self.post(
            '/control/history-detail',
            self.detail_payload(op_main, 'disc-main', disc_main['revision'], runtime=stale_rt),
        )
        self.assertEqual(code, 409)
        self.assertEqual(body['reason'], 'runtime-mismatch')

        # 5. Selected summary row task_key / revision mismatch against canonical operation -> HTTP 409 task-revision-mismatch.
        code, body, _ = self.post(
            '/control/history-detail',
            self.detail_payload(op_main, 'disc-page-b', disc_main['revision']),
        )
        self.assertEqual(code, 409)
        self.assertEqual(body['reason'], 'task-revision-mismatch')

        code, body, _ = self.post(
            '/control/history-detail',
            self.detail_payload(op_main, 'disc-main', 'a' * 64),
        )
        self.assertEqual(code, 409)
        self.assertEqual(body['reason'], 'task-revision-mismatch')

        # 6. UI executionId, path traversal, or 64-hex revision passed as operation_id -> HTTP 409 invalid-operation-id.
        for bad_id in ('mabc12-uiexec99', '../requests/' + op_main, disc_main['revision'], ''):
            code, body, _ = self.post(
                '/control/history-detail',
                self.detail_payload(bad_id, 'disc-main', disc_main['revision']),
            )
            self.assertEqual(code, 409)
            self.assertEqual(body['reason'], 'invalid-operation-id')

        # 7. Malformed envelope (missing or extra keys) -> HTTP 409 invalid-envelope.
        missing_rev = self.detail_payload(op_main, 'disc-main', disc_main['revision'])
        missing_rev.pop('revision')
        code, body, _ = self.post('/control/history-detail', missing_rev)
        self.assertEqual(code, 409)
        self.assertEqual(body['reason'], 'invalid-envelope')

        extra_key = {**self.detail_payload(op_main, 'disc-main', disc_main['revision']), 'rerun': True}
        code, body, _ = self.post('/control/history-detail', extra_key)
        self.assertEqual(code, 409)
        self.assertEqual(body['reason'], 'invalid-envelope')

        # 8. Auth, Host, Origin, and non-existent write/retry routes -> HTTP 403.
        valid_env = self.detail_payload(op_main, 'disc-main', disc_main['revision'])
        self.assertEqual(self.post('/control/history-detail', valid_env, Authorization='Bearer wrong')[0], 403)
        self.assertEqual(self.post('/control/history-detail', valid_env, Host='evil.example')[0], 403)
        self.assertEqual(self.post('/control/history-detail', valid_env, Origin='https://evil.example')[0], 403)
        for forbidden_route in ('/control/run', '/control/retry', '/control/recover', '/control/history-detail/../poll'):
            self.assertEqual(self.post(forbidden_route, valid_env)[0], 403)

        # 9. Positive read-only lookup succeeds and leaves workspace byte-identical.
        code, detail, raw = self.post('/control/history-detail', valid_env, Origin='https://www.figma.com')
        self.assertEqual(code, 200)
        self.assertLessEqual(len(raw), 256 * 1024)
        self.assertEqual(detail['schema'], 'figma-flow-operation-detail-v1')
        self.assertTrue(detail['readOnly'])
        self.assertEqual(detail['operationId'], op_main)
        self.assertEqual(detail['task']['key'], 'disc-main')
        self.assertEqual(detail['task']['revision'], disc_main['revision'])
        self.assertEqual(detail['task']['revisionBinding'], 'current')
        self.assertEqual(detail['diff']['status'], 'unavailable')
        self.assertEqual(detail['diff']['reason'], 'read-only-operation')
        self.assertEqual(self.snapshot(), before_snapshot)

    def test_two_scoped_runs_unavailable_then_positive_diff_and_redaction(self):
        # Prepare native-edit revision 1 and execute scoped Run 1.
        plan_path = self.directory / 'screen-edit.json'
        plan_v1 = {
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'edits': [
                {'node_id': '33:44', 'field': 'paddingLeft', 'before': 12, 'after': 20},
                {'node_id': '33:44', 'field': 'paddingRight', 'before': 12, 'after': 16},
                {'node_id': '55:66', 'main_id': '10:20', 'field': 'color', 'before': {'r': 0.1, 'g': 0.2, 'b': 0.3, 'a': 1.0}, 'after': {'r': 0.2, 'g': 0.4, 'b': 0.6, 'a': 1.0}},
            ],
        }
        plan_path.write_text(json.dumps(plan_v1), encoding='utf-8')
        prep_v1 = self.prepare_task('screen-edit', 'Edit Screen A', 'native-edit', ['--plan', str(plan_path)])
        op_run1 = self.execute_run(
            'screen-edit', 'apply', 'fixturefile', '12:1', prep_v1['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'native_edit': {'operation': 'apply', 'applied': True}, 'nodes': []},
        )

        # Run 1 has no prior revision artifact -> diff MUST be unavailable (before-artifact-missing).
        code1, detail1, _ = self.post('/control/history-detail', self.detail_payload(op_run1, 'screen-edit', prep_v1['revision']))
        self.assertEqual(code1, 200)
        self.assertEqual(detail1['classification'], 'recorded')
        self.assertEqual([p['phase'] for p in detail1['phases']], ['queued', 'claimed', 'native-started', 'result-received'])
        self.assertEqual(detail1['diff']['status'], 'unavailable')
        self.assertEqual(detail1['diff']['reason'], 'before-artifact-missing')
        self.assertEqual(detail1['diff']['fields'], [])

        # Prepare revision 2 (--replace-expected) with changed, added, and removed fields, then execute scoped Run 2.
        plan_v2 = {
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'edits': [
                {'node_id': '33:44', 'field': 'paddingLeft', 'before': 20, 'after': 32},
                {'node_id': '33:44', 'field': 'borderRadius', 'before': 8, 'after': 24},
                {'node_id': '55:66', 'main_id': '10:20', 'field': 'color', 'before': {'r': 0.2, 'g': 0.4, 'b': 0.6, 'a': 1.0}, 'after': {'r': 0.9, 'g': 0.1, 'b': 0.2, 'a': 1.0}},
            ],
        }
        plan_path.write_text(json.dumps(plan_v2), encoding='utf-8')
        prep_v2 = self.prepare_task(
            'screen-edit', 'Edit Screen A', 'native-edit',
            ['--plan', str(plan_path)], replace_expected=prep_v1['revision'],
        )
        self.assertNotEqual(prep_v1['revision'], prep_v2['revision'])

        op_run2 = self.execute_run(
            'screen-edit', 'apply', 'fixturefile', '12:1', prep_v2['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'native_edit': {'operation': 'apply', 'applied': True}, 'nodes': []},
        )

        # Run 2 compares exact verified artifacts (rev1 vs rev2) -> positive diff without leaking raw node IDs!
        code2, detail2, raw2 = self.post('/control/history-detail', self.detail_payload(op_run2, 'screen-edit', prep_v2['revision']))
        self.assertEqual(code2, 200)
        self.assertEqual(detail2['task']['revision'], prep_v2['revision'])
        self.assertEqual(detail2['task']['currentRevision'], prep_v2['revision'])
        self.assertEqual(detail2['task']['revisionBinding'], 'current')
        self.assertEqual(detail2['diff']['status'], 'available')
        self.assertEqual(detail2['diff']['basis'], 'revision-pair')
        self.assertEqual(detail2['diff']['beforeRevision'], prep_v1['revision'])
        self.assertEqual(detail2['diff']['afterRevision'], prep_v2['revision'])

        by_field = {(row['key'], row['field']): row for row in detail2['diff']['fields']}
        self.assertEqual(by_field[('target:node#1', 'paddingLeft')], {
            'key': 'target:node#1', 'field': 'paddingLeft', 'kind': 'changed', 'before': 20, 'after': 32,
        })
        self.assertEqual(by_field[('target:node#1', 'borderRadius')], {
            'key': 'target:node#1', 'field': 'borderRadius', 'kind': 'added', 'before': None, 'after': 24,
        })
        self.assertEqual(by_field[('target:node#1', 'paddingRight')], {
            'key': 'target:node#1', 'field': 'paddingRight', 'kind': 'removed', 'before': 16, 'after': None,
        })
        self.assertEqual(by_field[('target:node#2', 'color')]['kind'], 'changed')
        self.assertNotIn(b'33:44', raw2)
        self.assertNotIn(b'55:66', raw2)
        self.assertNotIn(b'10:20', raw2)
        self.assertNotIn(str(self.root).encode('utf-8'), raw2)

        # Re-querying Run 1 after replacement shows revisionBinding == 'pinned-historical' and currentRevision == rev2.
        code1_after, detail1_after, _ = self.post('/control/history-detail', self.detail_payload(op_run1, 'screen-edit', prep_v1['revision']))
        self.assertEqual(code1_after, 200)
        self.assertEqual(detail1_after['task']['revision'], prep_v1['revision'])
        self.assertEqual(detail1_after['task']['currentRevision'], prep_v2['revision'])
        self.assertEqual(detail1_after['task']['revisionBinding'], 'pinned-historical')

    def test_sync_two_revisions_and_missing_or_tampered_before_artifact_and_uncommitted_generation(self):
        graph, native = graph_fixture()
        native['fileKey'] = 'fixturefile'
        native['pageId'] = '12:1'
        for node in native['nodes']:
            if node.get('parentId') == 'page':
                node['parentId'] = '12:1'
        graph_path = self.directory / 'graph.json'
        baseline_path = self.directory / 'baseline.json'
        graph_path.write_text(json.dumps(graph), encoding='utf-8')
        baseline_path.write_text(json.dumps(native), encoding='utf-8')
        pairing_path = self.make_pairing(graph_path, native, 'pairing.json')

        sync_v1 = self.prepare_task(
            'token-sync', 'Sync Tokens', 'sync',
            ['--graph', str(graph_path), '--native-readback', str(baseline_path)],
        )
        op_sync_1 = self.execute_run(
            'token-sync', 'apply', 'fixturefile', '12:1', sync_v1['revision'],
            {'schema': 'figma-flow-graph-token-readback-v1', 'status': 'success', 'file_key': 'fixturefile', 'page_id': '12:1', 'tokens': [], 'components': []},
        )

        # Update graph token value for revision 2 via verified pairing receipt.
        graph_v2 = copy.deepcopy(graph)
        graph_v2['design_system']['tokens']['b/size/button']['value'] = 24
        graph_path.write_text(json.dumps(graph_v2), encoding='utf-8')
        sync_v2 = self.prepare_task(
            'token-sync', 'Sync Tokens', 'sync',
            ['--graph', str(graph_path), '--pairing', str(pairing_path)],
            replace_expected=sync_v1['revision'],
        )
        op_sync_2 = self.execute_run(
            'token-sync', 'apply', 'fixturefile', '12:1', sync_v2['revision'],
            {'schema': 'figma-flow-graph-token-readback-v1', 'status': 'success', 'file_key': 'fixturefile', 'page_id': '12:1', 'tokens': [], 'components': []},
        )

        code, detail, _ = self.post('/control/history-detail', self.detail_payload(op_sync_2, 'token-sync', sync_v2['revision']))
        self.assertEqual(code, 200)
        self.assertEqual(detail['diff']['status'], 'available')
        self.assertEqual(detail['diff']['beforeRevision'], sync_v1['revision'])
        changed_keys = {row['key']: (row['before'], row['after'], row['kind']) for row in detail['diff']['fields']}
        self.assertEqual(changed_keys['b/size/button'], (18, 24, 'changed'))

        # Simulate an uncommitted generation left behind by a failed manifest write: must never be used.
        graph_v3 = copy.deepcopy(graph_v2)
        graph_v3['design_system']['tokens']['b/size/button']['value'] = 40
        graph_path.write_text(json.dumps(graph_v3), encoding='utf-8')
        orig_atomic = workspace.atomic

        def fail_manifest(path, raw):
            if Path(path) == self.root / 'manifest.json':
                raise OSError('simulated manifest failure')
            return orig_atomic(path, raw)

        with patch.object(workspace, 'atomic', side_effect=fail_manifest), self.assertRaises(OSError):
            self.prepare_task(
                'token-sync', 'Sync Tokens', 'sync',
                ['--graph', str(graph_path), '--pairing', str(pairing_path)],
                replace_expected=sync_v2['revision'],
            )
        # Restore graph_v2 on disk.
        graph_path.write_text(json.dumps(graph_v2), encoding='utf-8')
        code_after_fail, detail_after_fail, _ = self.post('/control/history-detail', self.detail_payload(op_sync_2, 'token-sync', sync_v2['revision']))
        self.assertEqual(code_after_fail, 200)
        self.assertEqual(detail_after_fail['task']['currentRevision'], sync_v2['revision'])
        self.assertEqual(detail_after_fail['diff']['afterRevision'], sync_v2['revision'])
        self.assertEqual(
            [(r['key'], r['before'], r['after']) for r in detail_after_fail['diff']['fields']],
            [('b/size/button', 18, 24), ('b/type/button', 18, 24)],
        )

        # Tamper before-artifact code.js digest -> diff degrades safely to unverified-artifact without fabricating diff.
        v1_art_dir = Path(sync_v1['artifacts'])
        orig_code = (v1_art_dir / 'code.js').read_bytes()
        (v1_art_dir / 'code.js').write_bytes(orig_code + b'\n// tampered')
        code_tamp, detail_tamp, _ = self.post('/control/history-detail', self.detail_payload(op_sync_2, 'token-sync', sync_v2['revision']))
        self.assertEqual(code_tamp, 200)
        self.assertEqual(detail_tamp['diff']['status'], 'unavailable')
        self.assertEqual(detail_tamp['diff']['reason'], 'unverified-artifact')
        self.assertEqual(detail_tamp['diff']['fields'], [])

        # Restore code.js, then remove native-plan.json -> diff degrades safely to before-artifact-missing.
        (v1_art_dir / 'code.js').write_bytes(orig_code)
        (v1_art_dir / 'code.js').chmod(0o600)
        (v1_art_dir / 'native-plan.json').unlink()
        code_miss, detail_miss, _ = self.post('/control/history-detail', self.detail_payload(op_sync_2, 'token-sync', sync_v2['revision']))
        self.assertEqual(code_miss, 200)
        self.assertEqual(detail_miss['diff']['status'], 'unavailable')
        self.assertEqual(detail_miss['diff']['reason'], 'before-artifact-missing')
        self.assertEqual(detail_miss['diff']['fields'], [])

    def test_causal_relations_legacy_unknown_recovery_and_no_false_inference(self):
        # 1. Upstream task + unrelated same-project neighbor + downstream consumer with declared depends_on & input_record.
        up_plan = self.directory / 'up.json'
        up_plan.write_text(json.dumps({
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile', 'page_id': '12:1',
            'edits': [{'node_id': '1:2', 'field': 'paddingLeft', 'before': 4, 'after': 8}],
        }), encoding='utf-8')
        up_v1 = self.prepare_task('upstream-tokens', 'Upstream Tokens', 'native-edit', ['--plan', str(up_plan)], project='SharedProj')
        up_op_1 = self.execute_run(
            'upstream-tokens', 'apply', 'fixturefile', '12:1', up_v1['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'native_edit': {'operation': 'apply', 'applied': True}, 'nodes': []},
        )

        # Unrelated task in the exact same project executed immediately before consumer (visual/temporal neighbor).
        neighbor_plan = self.directory / 'neighbor.json'
        neighbor_plan.write_text(json.dumps({
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile', 'page_id': '12:1',
            'edits': [{'node_id': '7:8', 'field': 'paddingRight', 'before': 4, 'after': 12}],
        }), encoding='utf-8')
        neighbor = self.prepare_task('same-project-neighbor', 'Neighbor', 'native-edit', ['--plan', str(neighbor_plan)], project='SharedProj')
        neighbor_op = self.execute_run(
            'same-project-neighbor', 'apply', 'fixturefile', '12:1', neighbor['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'native_edit': {'operation': 'apply', 'applied': True}, 'nodes': []},
        )

        up_row = next(t for t in workspace.current(self.root)['tasks'] if t['key'] == 'upstream-tokens')
        dep_edge = [{
            'task_key': 'upstream-tokens',
            'revision': up_v1['revision'],
            'relation': 'uses-output',
            'artifact': 'code.js',
            'artifact_sha256': up_row['artifact_hashes']['code.js'],
        }]
        record, inp_dir = self.make_input_record('consumer-inputs', 'Initial Heading')
        down_plan = self.directory / 'down.json'
        down_plan.write_text(json.dumps({
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile', 'page_id': '12:1',
            'edits': [{'node_id': '9:10', 'field': 'paddingLeft', 'before': 10, 'after': 18}],
        }), encoding='utf-8')
        down_v1 = self.prepare_task(
            'screen-consumer', 'Screen Consumer', 'native-edit',
            ['--plan', str(down_plan)], project='SharedProj',
            depends_on=dep_edge, input_record=record, input_root=inp_dir,
        )
        down_op = self.execute_run(
            'screen-consumer', 'apply', 'fixturefile', '12:1', down_v1['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'native_edit': {'operation': 'apply', 'applied': True}, 'nodes': []},
        )

        code, detail, raw = self.post('/control/history-detail', self.detail_payload(down_op, 'screen-consumer', down_v1['revision']))
        self.assertEqual(code, 200)
        rel_types = {r['type'] for r in detail['relations']}
        self.assertTrue(rel_types <= {'declared-dependency', 'recovery-of', 'artifact-input'})
        self.assertEqual(rel_types, {'declared-dependency', 'artifact-input'})
        # Neighbor in same project with adjacent timestamp MUST NOT appear in relations!
        self.assertNotIn('same-project-neighbor', json.dumps(detail['relations']))
        self.assertNotIn(neighbor_op, json.dumps(detail['relations']))
        self.assertNotIn(str(inp_dir).encode('utf-8'), raw)

        dep_rel = next(r for r in detail['relations'] if r['type'] == 'declared-dependency')
        self.assertEqual(dep_rel['direction'], 'predecessor')
        self.assertEqual(dep_rel['taskKey'], 'upstream-tokens')
        self.assertEqual(dep_rel['revision'], up_v1['revision'])
        self.assertEqual(dep_rel['revisionBinding'], 'current')
        self.assertEqual(dep_rel['targetOperationId'], up_op_1)

        input_rel = next(r for r in detail['relations'] if r['type'] == 'artifact-input' and r['artifact'] == 'input-record.json')
        self.assertEqual(input_rel['freshness'], 'current')

        # Upstream is replaced with v2 AND consumer's local input file is edited -> dependency becomes pinned-historical & input becomes stale!
        up_plan.write_text(json.dumps({
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile', 'page_id': '12:1',
            'edits': [{'node_id': '1:2', 'field': 'paddingLeft', 'before': 8, 'after': 16}],
        }), encoding='utf-8')
        up_v2 = self.prepare_task(
            'upstream-tokens', 'Upstream Tokens', 'native-edit',
            ['--plan', str(up_plan)], project='SharedProj', replace_expected=up_v1['revision'],
        )
        (inp_dir / 'brief.md').write_text('# Brief\nHeadline: Mutated After Run\n', encoding='utf-8')

        code_stale, detail_stale, raw_stale = self.post('/control/history-detail', self.detail_payload(down_op, 'screen-consumer', down_v1['revision']))
        self.assertEqual(code_stale, 200)
        dep_rel_stale = next(r for r in detail_stale['relations'] if r['type'] == 'declared-dependency')
        self.assertEqual(dep_rel_stale['revision'], up_v1['revision'])
        self.assertEqual(dep_rel_stale['currentRevision'], up_v2['revision'])
        self.assertEqual(dep_rel_stale['revisionBinding'], 'pinned-historical')
        input_rel_stale = next(r for r in detail_stale['relations'] if r['type'] == 'artifact-input' and r['artifact'] == 'input-record.json')
        self.assertEqual(input_rel_stale['freshness'], 'stale')
        self.assertNotIn(b'Mutated After Run', raw_stale)
        self.assertNotIn(str(inp_dir).encode('utf-8'), raw_stale)

        # Upstream op_1 shows screen-consumer as a declared successor!
        _, up_detail, _ = self.post('/control/history-detail', self.detail_payload(up_op_1, 'upstream-tokens', up_v1['revision']))
        succ = [r for r in up_detail['relations'] if r['type'] == 'declared-dependency' and r['direction'] == 'successor']
        self.assertEqual(len(succ), 1)
        self.assertEqual(succ[0]['taskKey'], 'screen-consumer')
        self.assertEqual(succ[0]['targetOperationId'], down_op)

        # 2. Uncertain mutation + canonical recovery read vs adjacent reconciled neighbor without recovery_of.
        # Restore brief.md so workspace prepare for discovery passes input checks.
        (inp_dir / 'brief.md').write_text('# Brief\nHeadline: Initial Heading\n', encoding='utf-8')
        disc = self.prepare_task('scope-disc', 'Scope Discovery', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])
        orig_time = time.time
        try:
            uncertain_req = control.enqueue(self.root, 'upstream-tokens', 'apply', 'fixturefile', '12:1', up_v2['revision'], 1)
            control.poll(self.root, {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': self.current_runtime()})
            time.time = lambda: uncertain_req['deadline'] + 2
            self.assertEqual(control.status(self.root)['state'], 'uncertain')
        finally:
            time.time = orig_time

        rec_op = self.execute_run(
            'scope-disc', 'read', 'fixturefile', '12:1', disc['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'allowed_page_ids': ['12:1'], 'nodes': [], 'variables': [], 'collections': []},
        )
        # Inject a neighbor with phase 'reconciled' but recovery_of=None to prove reconciled phase alone never creates recovery-of!
        fake_reconciled_id = '9' * 32
        fake_reconciled = {
            'schema': control.SCHEMA,
            'id': fake_reconciled_id,
            'operation_id': fake_reconciled_id,
            'lifecycle_version': 1,
            'key': 'scope-disc',
            'operation': 'read',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'revision': disc['revision'],
            'state': 'ok',
            'created_at': time.time(),
            'phase_events': [
                {'phase': 'queued', 'time': '2026-11-14T10:00:00Z', 'source': 'server'},
                {'phase': 'reconciled', 'time': '2026-11-14T10:00:02Z', 'source': 'server'},
            ],
            'recovery_of': None,
        }
        workspace.atomic(self.root / '.control' / 'requests' / (fake_reconciled_id + '.json'), workspace.encode(fake_reconciled))

        _, unc_detail, _ = self.post('/control/history-detail', self.detail_payload(uncertain_req['id'], 'upstream-tokens', up_v2['revision']))
        self.assertEqual(unc_detail['failure'], {'code': 'operation-uncertain', 'action': 'run-native-read'})
        rec_by = [r for r in unc_detail['relations'] if r['type'] == 'recovery-of']
        self.assertEqual(len(rec_by), 1)
        self.assertEqual(rec_by[0]['direction'], 'recovered-by')
        self.assertEqual(rec_by[0]['operationId'], rec_op)

        _, rec_detail, _ = self.post('/control/history-detail', self.detail_payload(rec_op, 'scope-disc', disc['revision']))
        recovers = [r for r in rec_detail['relations'] if r['type'] == 'recovery-of']
        self.assertEqual(len(recovers), 1)
        self.assertEqual(recovers[0]['direction'], 'recovers')
        self.assertEqual(recovers[0]['operationId'], uncertain_req['id'])

        _, fake_rec_detail, _ = self.post('/control/history-detail', self.detail_payload(fake_reconciled_id, 'scope-disc', disc['revision']))
        self.assertEqual([r for r in fake_rec_detail['relations'] if r['type'] == 'recovery-of'], [])

        # 3. Legacy & malformed lifecycle requests never invent phases!
        legacy_id = '7' * 32
        legacy_req = {
            'schema': control.SCHEMA,
            'id': legacy_id,
            'key': 'scope-disc',
            'operation': 'read',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'revision': disc['revision'],
            'state': 'ok',
        }
        workspace.atomic(self.root / '.control' / 'requests' / (legacy_id + '.json'), workspace.encode(legacy_req))
        _, leg_detail, _ = self.post('/control/history-detail', self.detail_payload(legacy_id, 'scope-disc', disc['revision']))
        self.assertEqual(leg_detail['classification'], 'legacy')
        self.assertEqual(leg_detail['phase'], 'unknown')
        self.assertEqual(leg_detail['phases'], [])

        unknown_id = '8' * 32
        unknown_req = {
            **legacy_req,
            'id': unknown_id,
            'lifecycle_version': 99,
            'operation_id': unknown_id,
            'phase_events': [{'phase': 'queued', 'time': '2026-11-14T10:00:00Z', 'source': 'client-ui'}],
            'recovery_of': None,
        }
        workspace.atomic(self.root / '.control' / 'requests' / (unknown_id + '.json'), workspace.encode(unknown_req))
        _, unk_detail, _ = self.post('/control/history-detail', self.detail_payload(unknown_id, 'scope-disc', disc['revision']))
        self.assertEqual(unk_detail['classification'], 'unknown')
        self.assertEqual(unk_detail['phase'], 'unknown')
        self.assertEqual(unk_detail['phases'], [])

    def test_conflict_redaction_200_row_truncation_256kib_cap_and_history_80_summary(self):
        # 1. Conflict redaction: never leaks raw text, raw Figma node IDs, Bearer tokens, or private paths.
        plan_path = self.directory / 'conflict-plan.json'
        plan_path.write_text(json.dumps({
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'edits': [{'node_id': '99:88', 'field': 'paddingLeft', 'before': 10, 'after': 20}],
        }), encoding='utf-8')
        prep = self.prepare_task('conflict-edit', 'Conflict Edit', 'native-edit', ['--plan', str(plan_path)])
        conflict_readback = {
            'schema': 'figma-flow-graph-native-discovery-v1',
            'fileKey': 'fixturefile',
            'pageId': '12:1',
            'native_edit': {
                'plan_sha256': 'b' * 64,
                'operation': 'apply',
                'applied': False,
                'operations': [{
                    'node_id': '99:88',
                    'field': 'characters',
                    'before': 'Private customer copy secret',
                    'after': 'Bearer sk-secret-token /Users/private/secret.txt',
                    'observed': 'External user override text!',
                }],
            },
            'rollback_conflicts': [{
                'node_id': '99:88',
                'field': 'characters',
                'reason': 'external-change-not-overwritten',
                'before': 'Private customer copy secret',
                'after': 'Bearer sk-secret-token /Users/private/secret.txt',
                'observed': 'External user override text!',
            }],
        }
        conflict_op = self.execute_run(
            'conflict-edit', 'apply', 'fixturefile', '12:1', prep['revision'],
            conflict_readback, status='error', error='Rollback conflict at /Users/private/secret.txt with Bearer sk-secret-token',
        )

        code, detail, raw = self.post('/control/history-detail', self.detail_payload(conflict_op, 'conflict-edit', prep['revision']))
        self.assertEqual(code, 200)
        self.assertEqual(detail['failure'], {'code': 'native-conflict', 'action': 'inspect-conflicts'})
        self.assertEqual(len(detail['diff']['conflicts']), 1)
        conflict_row = detail['diff']['conflicts'][0]
        self.assertEqual(conflict_row['key'], 'target:node#1')
        self.assertEqual(conflict_row['field'], 'characters')
        self.assertEqual(conflict_row['reasonCode'], 'external-change-not-overwritten')
        self.assertEqual(conflict_row['expectedBefore']['valueType'], 'text')
        self.assertEqual(conflict_row['plannedAfter']['valueType'], 'text')
        self.assertEqual(conflict_row['observed']['valueType'], 'text')
        for forbidden in (b'Private customer copy', b'Bearer', b'sk-secret-token', b'/Users/private', b'External user override', b'99:88'):
            self.assertNotIn(forbidden, raw)

        # 2. >200 diff rows cap sets truncated=True and caps fields at 200.
        many_before = {(f'token.color.item-{idx:03d}', 'value'): idx for idx in range(245)}
        many_after = {(f'token.color.item-{idx:03d}', 'value'): idx + 1000 for idx in range(245)}
        diff_rows = detail_mod._diff_maps(many_before, many_after)
        self.assertEqual(len(diff_rows), 245)

        graph, native = graph_fixture()
        native['fileKey'] = 'fixturefile'
        native['pageId'] = '12:1'
        for node in native['nodes']:
            if node.get('parentId') == 'page':
                node['parentId'] = '12:1'
        for idx in range(220):
            t_name = f'b/scale/t{idx:03d}'
            graph['design_system']['tokens'][t_name] = {'type': 'FLOAT', 'value': float(idx)}
            native['variables'].append({
                'id': f'v{idx}', 'name': t_name, 'resolvedType': 'FLOAT',
                'valuesByMode': {'mode': float(idx)}, 'variableCollectionId': 'collection',
            })
        g_path = self.directory / 'big-graph.json'
        b_path = self.directory / 'big-base.json'
        g_path.write_text(json.dumps(graph), encoding='utf-8')
        b_path.write_text(json.dumps(native), encoding='utf-8')
        big_pairing = self.make_pairing(g_path, native, 'big-pairing.json')

        big_v1 = self.prepare_task(
            'big-sync', 'Big Sync', 'sync',
            ['--graph', str(g_path), '--native-readback', str(b_path)],
        )
        self.execute_run(
            'big-sync', 'apply', 'fixturefile', '12:1', big_v1['revision'],
            {'schema': 'figma-flow-graph-token-readback-v1', 'status': 'success', 'file_key': 'fixturefile', 'page_id': '12:1', 'tokens': [], 'components': []},
        )
        for idx in range(220):
            graph['design_system']['tokens'][f'b/scale/t{idx:03d}']['value'] = float(idx + 50)
        g_path.write_text(json.dumps(graph), encoding='utf-8')
        big_v2 = self.prepare_task(
            'big-sync', 'Big Sync', 'sync',
            ['--graph', str(g_path), '--pairing', str(big_pairing)],
            replace_expected=big_v1['revision'],
        )
        big_op2 = self.execute_run(
            'big-sync', 'apply', 'fixturefile', '12:1', big_v2['revision'],
            {'schema': 'figma-flow-graph-token-readback-v1', 'status': 'success', 'file_key': 'fixturefile', 'page_id': '12:1', 'tokens': [], 'components': []},
        )

        code_big, detail_big, raw_big = self.post('/control/history-detail', self.detail_payload(big_op2, 'big-sync', big_v2['revision']))
        self.assertEqual(code_big, 200)
        self.assertEqual(len(detail_big['diff']['fields']), 200)
        self.assertEqual(detail_big['diff']['totalFields'], 220)
        self.assertTrue(detail_big['diff']['truncated'])
        self.assertTrue(detail_big['truncated'])
        self.assertEqual(detail_big['scopeNotice'], 'read-only-diff-capped-at-200-fields')
        self.assertLessEqual(len(raw_big), 256 * 1024)

        # Direct 256 KiB byte-cap enforcement check.
        oversized_dto = copy.deepcopy(detail_big)
        oversized_dto['relations'] = [
            {
                'type': 'declared-dependency',
                'direction': 'predecessor',
                'taskKey': f'dep-task-{idx:04d}-' + ('x' * 120),
                'revision': 'c' * 64,
                'currentRevision': 'c' * 64,
                'revisionBinding': 'current',
                'artifact': 'code.js',
                'artifactSha256': 'd' * 64,
                'targetOperationId': None,
            }
            for idx in range(900)
        ]
        capped = detail_mod._enforce_size_cap(oversized_dto)
        self.assertLessEqual(len(workspace.encode(capped)), 256 * 1024)
        self.assertTrue(capped['truncated'])
        self.assertEqual(capped['scopeNotice'], 'read-only-truncated-256kib')

        # 3. /control/history 80-item summary cap remains intact.
        requests_dir = self.root / '.control' / 'requests'
        for idx in range(90):
            op_id = f'{idx:032x}'
            workspace.atomic(requests_dir / f'{op_id}.json', workspace.encode({
                'schema': control.SCHEMA,
                'id': op_id,
                'operation_id': op_id,
                'lifecycle_version': 1,
                'key': 'big-sync',
                'operation': 'apply',
                'file_key': 'fixturefile',
                'page_id': '12:1',
                'revision': big_v2['revision'],
                'state': 'ok',
                'phase_events': [{'phase': 'queued', 'time': '2026-11-14T10:00:00Z', 'source': 'server'}],
                'recovery_of': None,
            }))
        h_code, h_body, _ = self.post('/control/history', {
            'session_id': 'plugin-session-1',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'runtime': self.current_runtime(),
        })
        self.assertEqual(h_code, 200)
        self.assertEqual(len(h_body['journalHistory']), 80)

    def test_retired_binding_paired_import_text_redaction_type_changed_and_symlink_rejection(self):
        # 1. Paired import across two revisions: TEXT copy emits length+changed only, never raw copy; symlinked artifact degrades safely.
        pair_token = 'c' * 64

        class PairHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                _ = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                body = b'{"error":"Expected the paired native snapshot."}'
                self.send_response(409 if self.headers.get('Authorization') == 'Bearer ' + pair_token else 403)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        pair_server = ThreadingHTTPServer(('127.0.0.1', 0), PairHandler)
        pair_thread = threading.Thread(target=pair_server.serve_forever, daemon=True)
        pair_thread.start()
        self.addCleanup(pair_server.server_close)
        self.addCleanup(pair_server.shutdown)

        state_dir = self.directory / 'paired-state'
        project_dir = self.directory / 'paired-app'
        state_dir.mkdir(mode=0o700)
        project_dir.mkdir()

        src_v1 = bridge_design()
        src_v1['screens'][0]['title'] = 'Private Headline Alpha'
        src_path = self.directory / 'resolved.json'
        src_path.write_text(json.dumps(src_v1), encoding='utf-8')
        sha_v1 = hashlib.sha256(src_path.read_bytes()).hexdigest()
        workspace.atomic(state_dir / 'connection.json', workspace.encode({
            'identity': {
                'project': str(project_dir),
                'resolved_sha256': sha_v1,
                'plugin_id': '12345',
                'file_key': 'fixturefile',
                'page_id': '12:1',
            },
            'token': pair_token,
            'sync_port': pair_server.server_port,
            'preview_port': 49186,
        }))
        imp_v1 = self.prepare_task(
            'paired-import', 'Paired Import', 'import',
            ['--input', str(src_path), '--reviewed-sha256', sha_v1, '--paired-state', str(state_dir)],
        )
        op_imp_1 = self.execute_run(
            'paired-import', 'import', 'fixturefile', '12:1', imp_v1['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'nodes': []},
        )

        src_v2 = bridge_design()
        src_v2['screens'][0]['title'] = 'Confidential Updated Headline Beta!'
        src_v2['tokens']['palette.blue']['value'] = '#654321ff'
        src_v2['tokens']['color.brand']['value'] = '#654321ff'
        src_path.write_text(json.dumps(src_v2), encoding='utf-8')
        sha_v2 = hashlib.sha256(src_path.read_bytes()).hexdigest()
        workspace.atomic(state_dir / 'connection.json', workspace.encode({
            'identity': {
                'project': str(project_dir),
                'resolved_sha256': sha_v2,
                'plugin_id': '12345',
                'file_key': 'fixturefile',
                'page_id': '12:1',
            },
            'token': pair_token,
            'sync_port': pair_server.server_port,
            'preview_port': 49186,
        }))
        imp_v2 = self.prepare_task(
            'paired-import', 'Paired Import', 'import',
            ['--input', str(src_path), '--reviewed-sha256', sha_v2, '--paired-state', str(state_dir)],
            replace_expected=imp_v1['revision'],
        )
        op_imp_2 = self.execute_run(
            'paired-import', 'import', 'fixturefile', '12:1', imp_v2['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'nodes': []},
        )

        code_imp, detail_imp, raw_imp = self.post('/control/history-detail', self.detail_payload(op_imp_2, 'paired-import', imp_v2['revision']))
        self.assertEqual(code_imp, 200)
        self.assertEqual(detail_imp['diff']['status'], 'available')
        imp_fields = {(r['key'], r['field']): r for r in detail_imp['diff']['fields']}
        self.assertEqual(imp_fields[('SCR-ONE', 'characters')], {
            'key': 'SCR-ONE',
            'field': 'characters',
            'kind': 'changed',
            'before': {'valueType': 'text', 'changed': True, 'length': len('Private Headline Alpha')},
            'after': {'valueType': 'text', 'changed': True, 'length': len('Confidential Updated Headline Beta!')},
        })
        self.assertEqual(imp_fields[('palette.blue', 'value')]['kind'], 'changed')
        self.assertNotIn(b'Private Headline Alpha', raw_imp)
        self.assertNotIn(b'Confidential Updated Headline Beta!', raw_imp)
        self.assertNotIn(pair_token.encode('utf-8'), raw_imp)

        # Type-changed kind check on safe design maps.
        tc_rows = detail_mod._diff_maps(
            {('token.sample', 'value'): 18},
            {('token.sample', 'value'): {'r': 0.1, 'g': 0.2, 'b': 0.3, 'a': 1.0}},
        )
        self.assertEqual(tc_rows, [{
            'key': 'token.sample',
            'field': 'value',
            'kind': 'type-changed',
            'before': 18,
            'after': {'r': 0.1, 'g': 0.2, 'b': 0.3, 'a': 1.0},
        }])

        # Symlinked nested artifact is rejected without following the symlink.
        outside_secret = self.directory / 'outside-secret.json'
        outside_secret.write_text('{"secret":"never-read"}', encoding='utf-8')
        v1_payload = Path(imp_v1['artifacts']) / 'reviewed-payload.json'
        orig_payload = v1_payload.read_bytes()
        v1_payload.unlink()
        v1_payload.symlink_to(outside_secret)
        code_sym, detail_sym, raw_sym = self.post('/control/history-detail', self.detail_payload(op_imp_2, 'paired-import', imp_v2['revision']))
        self.assertEqual(code_sym, 200)
        self.assertEqual(detail_sym['diff']['status'], 'unavailable')
        self.assertEqual(detail_sym['diff']['reason'], 'unverified-artifact')
        self.assertNotIn(b'never-read', raw_sym)
        v1_payload.unlink()
        v1_payload.write_bytes(orig_payload)
        v1_payload.chmod(0o600)

        # 2. Retired task revision produces revisionBinding == 'retired' on both historical task and declared-dependency!
        imp_row = next(t for t in workspace.current(self.root)['tasks'] if t['key'] == 'paired-import')
        dep_plan = self.directory / 'dep-on-imp.json'
        dep_plan.write_text(json.dumps({
            'schema': 'figma-flow-native-edit-plan-v1',
            'file_key': 'fixturefile', 'page_id': '12:1',
            'edits': [{'node_id': '44:55', 'field': 'paddingLeft', 'before': 8, 'after': 16}],
        }), encoding='utf-8')
        consumer = self.prepare_task(
            'post-import-edit', 'Post Import Edit', 'native-edit',
            ['--plan', str(dep_plan)],
            depends_on=[{
                'task_key': 'paired-import',
                'revision': imp_v2['revision'],
                'relation': 'uses-output',
                'artifact': 'code.js',
                'artifact_sha256': imp_row['artifact_hashes']['code.js'],
            }],
        )
        op_consumer = self.execute_run(
            'post-import-edit', 'apply', 'fixturefile', '12:1', consumer['revision'],
            {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': '12:1', 'native_edit': {'operation': 'apply', 'applied': True}, 'nodes': []},
        )
        retire_file = self.directory / 'retire.json'
        retire_file.write_text(json.dumps({
            'schema': 'figma-flow-workspace-retirement-v1',
            'tasks': [{'key': 'paired-import', 'revision': imp_v2['revision']}],
        }), encoding='utf-8')
        workspace.retire(self.root, retire_file)

        _, retired_op_detail, _ = self.post('/control/history-detail', self.detail_payload(op_imp_2, 'paired-import', imp_v2['revision']))
        self.assertEqual(retired_op_detail['task']['revisionBinding'], 'retired')
        self.assertIsNone(retired_op_detail['task']['currentRevision'])

        _, consumer_detail, _ = self.post('/control/history-detail', self.detail_payload(op_consumer, 'post-import-edit', consumer['revision']))
        dep_retired = next(r for r in consumer_detail['relations'] if r['type'] == 'declared-dependency')
        self.assertEqual(dep_retired['revisionBinding'], 'retired')


if __name__ == '__main__':
    unittest.main()
