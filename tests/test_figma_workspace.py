"""Private compiler tests use real normal generators; no live Figma evidence is implied."""
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import figma_workspace as workspace
from test_graph_sync import fixture as graph_fixture
from test_figma_bridge import design

THREAD = '12345678-abcd-4abc-9abc-123456789abc'


@unittest.skipUnless(os.name == 'posix', 'Private workspace permissions currently require POSIX')
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'workspace'
        self.identity = self.root / 'assigned.json'
        self.identity.write_text('{"id":"12345"}')
        workspace.init(self.path, self.identity)

    def prepare(self, key='read-test', title='Read Figma', **kwargs):
        return workspace.prepare(self.path, key, title, 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'], thread_id=kwargs.pop('thread_id', THREAD), **kwargs)

    def active(self):
        manifest = json.loads((self.path / 'manifest.json').read_text())
        return manifest, (self.path / manifest['main']).read_text(), (self.path / manifest['ui']).read_text()

    def test_init_preserves_assigned_identity_private_permissions_and_network_none(self):
        manifest, code, html = self.active()
        self.assertEqual(manifest['name'], 'Figma Flow')
        self.assertEqual(manifest['id'], '12345')
        self.assertEqual(manifest['networkAccess'], {'allowedDomains': ['none']})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in self.path.rglob('*')))
        self.assertIn('const FLOW_TASKS = []', code)
        self.assertIn('Figma Flow', html)
        before = (self.path / 'manifest.json').read_bytes()
        workspace.init(self.path, self.identity)
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)
        self.identity.write_text('{"id":"99999"}')
        with self.assertRaisesRegex(ValueError, 'different plugin'):
            workspace.init(self.path, self.identity)
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)

    def test_unrelated_files_and_source_symlinks_are_not_admitted(self):
        other = self.root / 'other'
        other.mkdir(mode=0o700)
        original = other / 'code.js'
        original.write_text('unrelated content')
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            workspace.init(other, self.identity)
        self.assertEqual(original.read_text(), 'unrelated content')
        linked = self.root / 'linked.json'
        linked.symlink_to(self.identity)
        with self.assertRaises(ValueError):
            workspace.init(self.root / 'linked-workspace', linked)

    def test_network_admission_accepts_only_bounded_exact_unprivileged_localhost_origins(self):
        for origin in ('https://example.com', 'http://127.0.0.1:49187', 'http://localhost:80', 'http://localhost:65536', 'http://localhost:49187/path', 'http://user:secret@localhost:49187'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                workspace.network({'networkAccess': {'allowedDomains': ['none'], 'devAllowedDomains': [origin]}})
        self.assertEqual(workspace.network({'networkAccess': {'allowedDomains': ['none'], 'devAllowedDomains': ['http://localhost:49187']}}), ['http://localhost:49187'])

    def test_foreign_generated_manifest_is_rejected_before_publication(self):
        before = (self.path / 'manifest.json').read_bytes()
        def foreign(command, **kwargs):
            out = Path(command[command.index('--out') + 1])
            out.mkdir()
            (out / 'manifest.json').write_text(json.dumps({'id': '99999', 'main': 'code.js', 'ui': 'ui.html'}))
            (out / 'code.js').write_text('throw Error("foreign")')
            (out / 'ui.html').write_text('<p>Foreign</p>')
            return subprocess.CompletedProcess(command, 0, b'', b'')
        with patch.object(workspace.subprocess, 'run', side_effect=foreign), self.assertRaisesRegex(ValueError, 'identity'):
            self.prepare()
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)
        self.assertEqual(workspace.list_tasks(self.path)['tasks'], [])

    def test_real_discovery_is_composed_without_eval_and_identical_retry_is_idempotent(self):
        title = 'Read </script><img src=x> "quoted"'
        result = self.prepare(title=title, project='Project <unsafe>')
        manifest, code, _ = self.active()
        self.assertIn('run":function(){const figma=workspaceTaskFigma();const __html__=workspaceTaskHtml(', code)
        self.assertIn('discoverGraphNative', code)
        self.assertNotIn('new Function(', code)
        self.assertNotIn('eval(', code)
        self.assertEqual(workspace.list_tasks(self.path)['tasks'][0]['title'], title)
        self.assertEqual(workspace.list_tasks(self.path)['tasks'][0]['threadId'], THREAD)
        before = (self.path / 'manifest.json').read_bytes()
        again = self.prepare(title=title, project='Project <unsafe>')
        self.assertTrue(again['unchanged'])
        self.assertEqual(again['revision'], result['revision'])
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)
        if shutil.which('node'):
            subprocess.run(['node', '--check', str(self.path / manifest['main'])], check=True, capture_output=True)

    def test_explicit_replacement_is_cas_and_does_not_reuse_stale_revision(self):
        first = self.prepare()
        before = (self.path / 'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare(title='Changed title')
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)
        second = self.prepare(title='Changed title', replace_expected=first['revision'])
        self.assertNotEqual(first['revision'], second['revision'])
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.prepare(title='Further edit', replace_expected=first['revision'])
        self.assertEqual(workspace.list_tasks(self.path)['tasks'][0]['title'], 'Changed title')

    def test_offline_tasks_allow_missing_thread_but_malformed_thread_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            result = workspace.prepare(self.path, 'offline', 'Offline discovery', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])
        self.assertTrue(result['revision'])
        self.assertIsNone(workspace.list_tasks(self.path)['tasks'][0]['threadId'])
        with self.assertRaisesRegex(ValueError, 'UUID'):
            self.prepare(key='bad-thread', thread_id='not-a-uuid')

    def test_exact_flags_own_output_identity_and_reject_abbreviations_and_code_inputs(self):
        for args in (['--out=/tmp/other'], ['--plugin-id', '999'], ['--plugin=999'], ['--file-k', 'file'], ['--code', 'evil.js'], ['--ui.html', 'evil'], ['python', 'tools/graph_sync.py'], ['--adopt=true']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                workspace.prepare(self.path, 'invalid', 'Invalid task', 'discover', args, thread_id=THREAD)
        self.assertEqual(workspace.list_tasks(self.path)['tasks'], [])
        for key in ('../escape', 'UpperCase', 'space key', 'double--dash', 'a' * 65):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare(key=key)

    def test_normal_sync_preserves_native_plan_and_exposes_compiler_owned_web_artifact(self):
        graph, native = graph_fixture()
        source, baseline = self.root / 'graph.json', self.root / 'native.json'
        source.write_text(json.dumps(graph))
        baseline.write_text(json.dumps(native))
        result = workspace.prepare(self.path, 'sync-button', 'Sync button', 'sync', ['--graph=' + str(source), '--native-readback', str(baseline)], thread_id=THREAD)
        artifact = Path(result['artifacts'])
        plan = json.loads((artifact / 'native-plan.json').read_text())
        self.assertEqual(plan['file_key'], 'file')
        self.assertEqual(plan['components'][0]['main_keys'], ['main'])
        self.assertEqual(plan['tokens'][1]['alias_chain'], ['alias', 'root'])
        self.assertEqual(Path(result['web_module']).parent, artifact)
        self.assertIn('18px', Path(result['web_module']).read_text())
        task = workspace.list_tasks(self.path)['tasks'][0]
        self.assertEqual((task['fileKey'], task['pageId']), ('file', 'page'))

    def test_production_import_cannot_bypass_human_selected_admission(self):
        source = self.root / 'resolved.json'
        source.write_text(json.dumps(design()))
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        before = (self.path / 'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'generator rejected'):
            workspace.prepare(self.path, 'import-design', 'Import', 'import', ['--input', str(source), '--reviewed-sha256', sha], thread_id=THREAD)
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)
        self.assertEqual(workspace.list_tasks(self.path)['tasks'], [])

    def review_inputs(self):
        spec = importlib.util.spec_from_file_location('workspace_review_demo', ROOT / 'examples/native-direction-review/demo.py')
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        result = demo.instantiate(self.root / 'review-project')
        return result['manifest']

    def test_real_review_portable_and_explicit_private_receiver_preserve_normal_packet(self):
        manifest = self.review_inputs()
        pair = self.root / 'review-pair'
        result = workspace.prepare(self.path, 'review-layout', 'Review layouts', 'review', ['--manifest', str(manifest), '--file-key', 'fixturefile', '--pair-dir', str(pair), '--receiver-port', '49185'], thread_id=THREAD)
        artifact = Path(result['artifacts'])
        token = (pair / 'capability').read_text()
        packet = json.loads((artifact / 'packet.json').read_text())
        self.assertFalse(packet['production_admitted'])
        self.assertEqual(packet['fileKey'], 'fixturefile')
        self.assertEqual((pair / 'capability').stat().st_mode & 0o777, 0o600)
        self.assertNotIn(token, (artifact / 'plugin/ui.html').read_text())
        self.assertIn(token, (artifact / 'paired-plugin/ui.html').read_text())
        self.assertEqual(self.active()[0]['networkAccess']['devAllowedDomains'], ['http://localhost:49185'])
        self.assertNotIn(token, (self.path / 'catalogue.json').read_text())
        self.assertNotIn(token, json.dumps(workspace.list_tasks(self.path)))
        with self.assertRaisesRegex(ValueError, 'different file, packet'):
            workspace.prepare(self.path, 'foreign-review', 'Other target', 'review', ['--manifest', str(manifest), '--file-key', 'anotherfile', '--pair-dir', str(pair), '--receiver-port', '49185'], thread_id=THREAD)

    def test_paired_import_authenticates_existing_endpoint_and_preserves_owner_pins(self):
        source = self.root / 'resolved.json'
        source.write_text(json.dumps(design()))
        sha, token = hashlib.sha256(source.read_bytes()).hexdigest(), 'a' * 64
        observations = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                observations.append((self.path, self.headers.get('Authorization'), self.rfile.read(int(self.headers['Content-Length']))))
                body = b'{"error":"Expected the paired native snapshot."}'
                self.send_response(409 if self.headers.get('Authorization') == 'Bearer ' + token else 403)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        state, project = self.root / 'paired', self.root / 'app'
        state.mkdir(mode=0o700)
        project.mkdir()
        connection = {'identity': {'project': str(project), 'resolved_sha256': sha, 'plugin_id': '12345', 'file_key': 'fixturefile', 'page_id': '12:1'}, 'token': token, 'sync_port': server.server_port, 'preview_port': 49186}
        workspace.atomic(state / 'connection.json', workspace.encode(connection))
        args = ['--input', str(source), '--reviewed-sha256', sha, '--paired-state', str(state)]
        result = workspace.prepare(self.path, 'paired-import', 'Paired import', 'import', args, thread_id=THREAD)
        self.assertEqual(observations, [('/sync', 'Bearer ' + token, b'{}')])
        self.assertNotIn(token, json.dumps(result))
        self.assertNotIn(token, json.dumps(workspace.list_tasks(self.path)))
        self.assertNotIn(token, (self.path / 'catalogue.json').read_text())
        payload = json.loads((Path(result['artifacts']) / 'reviewed-payload.json').read_text())
        self.assertTrue(payload['technical_existing_only'])
        connection['identity']['plugin_id'] = '99999'
        workspace.atomic(state / 'connection.json', workspace.encode(connection))
        with self.assertRaisesRegex(ValueError, 'identity'):
            workspace.prepare(self.path, 'foreign-pair', 'Foreign pair', 'import', args, thread_id=THREAD)

    def test_private_chat_explicit_port_and_capability_never_enter_catalogue_or_list(self):
        workspace.init(self.path, self.identity, 49187)
        config = json.loads((self.path / 'chat.json').read_text())
        self.assertEqual(config['port'], 49187)
        self.assertEqual(len(config['token']), 64)
        manifest, code, html = self.active()
        self.assertEqual(manifest['networkAccess']['devAllowedDomains'], ['http://localhost:49187'])
        self.assertIn(config['token'], code)
        self.assertNotIn(config['token'], html)
        self.assertNotIn(config['token'], (self.path / 'catalogue.json').read_text())
        self.assertNotIn(config['token'], json.dumps(workspace.list_tasks(self.path)))
        for port in (0, 80, 1023, 65536):
            with self.subTest(port=port), self.assertRaises(ValueError):
                workspace.init(self.path, self.identity, port)

    def test_symlinked_artifact_and_forged_catalogue_never_become_executable(self):
        result = self.prepare()
        artifact = Path(result['artifacts'])
        code = artifact / 'code.js'
        code.unlink()
        code.symlink_to(self.root / 'untrusted.js')
        (self.root / 'untrusted.js').write_text('throw Error("untrusted")')
        with self.assertRaises(ValueError):
            self.prepare(key='another')
        manifest = self.active()[0]
        generation = self.path / Path(manifest['main']).parent / 'catalogue.json'
        catalogue = json.loads(generation.read_text())
        catalogue['tasks'][0]['artifact_hashes']['code.js'] = '0' * 64
        workspace.atomic(generation, workspace.encode(catalogue))
        with self.assertRaisesRegex(ValueError, 'signature'):
            workspace.list_tasks(self.path)

    def test_failed_manifest_publish_does_not_admit_unpublished_task_revision(self):
        initial = self.prepare()
        before = (self.path / 'manifest.json').read_bytes()
        original = workspace.atomic
        def fail_manifest(path, raw):
            if Path(path) == self.path / 'manifest.json':
                raise OSError('injected publication failure')
            return original(path, raw)
        with patch.object(workspace, 'atomic', side_effect=fail_manifest), self.assertRaises(OSError):
            self.prepare(title='Replacement', replace_expected=initial['revision'])
        self.assertEqual((self.path / 'manifest.json').read_bytes(), before)
        tasks = workspace.list_tasks(self.path)['tasks']
        self.assertEqual(tasks[0]['revision'], initial['revision'])
        self.assertEqual(json.loads((self.path / 'catalogue.json').read_text())['tasks'][0]['revision'], initial['revision'])

    def test_concurrent_prepares_preserve_both_tasks(self):
        failures = []
        def prepare(key):
            try:
                self.prepare(key=key)
            except Exception as error:
                failures.append(error)
        threads = [threading.Thread(target=prepare, args=(key,)) for key in ('read-one', 'read-two')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual({task['key'] for task in workspace.list_tasks(self.path)['tasks']}, {'read-one', 'read-two'})


if __name__ == '__main__':
    unittest.main()
