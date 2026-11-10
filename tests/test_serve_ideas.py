import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import test_promote_idea
from direction_fixture import selected_direction
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from serve_ideas import IdeaServer


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.root = root
        graph = root / 'graph.json'
        graph.write_text('{}')
        brief = root / 'brief.md'
        brief.write_text('brief')
        catalog = root / 'catalog.json'
        catalog.write_text(json.dumps({'version': 1, 'projects': [{'label': 'idea', 'status': 'draft',
            'graph_sha256': hashlib.sha256(graph.read_bytes()).hexdigest(), 'nodes': [], 'edges': [], 'trace': None}]}))
        self.server = IdeaServer(catalog, 'idea', graph, brief, root / 'new')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def test_build_without_user_choice_never_starts_process_or_output(self):
        headers = {'Origin': self.server.origin, 'X-Build-Token': self.server.token}
        with patch('serve_ideas.subprocess.run') as execute:
            status, body = self.request('POST', '/api/build', headers)
            self.assertEqual(status, 409)
            self.assertIn(b'WAIT_SELECTION', body)
            self.assertEqual(self.server.state, 'ready')
            self.server.run_build()
            execute.assert_not_called()
        self.assertFalse(self.server.out.exists())

    def test_current_user_selection_executes_and_changed_graph_blocks_again(self):
        with selected_direction(self.root) as chosen:
            self.server.selection_path = chosen.selection_path
            self.server.graph_path = chosen.product_graph
            manifest = json.loads(chosen.manifest.read_text())
            self.server.brief_path.write_bytes(Path(manifest['brief']['path']).read_bytes())
            with patch('serve_ideas.subprocess.run', return_value=subprocess.CompletedProcess([], 1)) as execute:
                self.server.run_build()
                execute.assert_called_once()
            chosen.product_graph.write_text(chosen.product_graph.read_text() + ' ')
            with patch('serve_ideas.subprocess.run') as execute:
                self.server.run_build()
                execute.assert_not_called()
            self.assertEqual(self.server.state, 'failed')
            self.assertFalse(self.server.out.exists())

    def test_changed_figma_brief_blocks_local_selection_before_process(self):
        with selected_direction(self.root) as chosen:
            self.server.selection_path = chosen.selection_path
            self.server.graph_path = chosen.product_graph
            self.server.brief_path.write_text('Create this app in Figma without Dev Mode.')
            with patch('serve_ideas.subprocess.run') as execute:
                self.server.run_build()
                execute.assert_not_called()
            self.assertIn('current brief differs', self.server.message)
            self.assertFalse(self.server.out.exists())

    def test_host_origin_token_and_file_access(self):
        token = self.server.token
        self.assertEqual(self.request('GET', '/', {'Host': 'attacker.test'})[0], 403)
        self.assertEqual(self.request('GET', '/catalog.json')[0], 404)
        self.assertEqual(self.request('GET', '/api/status')[0], 404)
        self.assertEqual(self.request('POST', '/api/build', {'Origin': 'http://evil.test', 'X-Build-Token': token})[0], 403)
        self.assertEqual(self.request('POST', '/api/build', {'Origin': self.server.origin, 'X-Build-Token': 'wrong'})[0], 403)
        self.assertEqual(self.server.state, 'ready')

    def test_symlink_trace_and_nonregular_input_rejected(self):
        root = self.root
        trace_dir = root / 'projects' / '001'
        trace_dir.mkdir(parents=True)
        (trace_dir / 'trace.html').symlink_to(root / 'brief.md')
        catalog = root / 'catalog.json'
        data = json.loads(catalog.read_text())
        data['projects'][0]['trace'] = 'projects/001/trace.html'
        catalog.write_text(json.dumps(data))
        other = IdeaServer(catalog, 'idea', root / 'graph.json', root / 'brief.md', root / 'new')
        try:
            self.assertNotIn('/projects/001/trace.html', other.artifacts)
        finally:
            other.server_close()
        (trace_dir / 'trace.html').unlink()
        os.link(root / 'brief.md', trace_dir / 'trace.html')
        other = IdeaServer(catalog, 'idea', root / 'graph.json', root / 'brief.md', root / 'new')
        try:
            self.assertNotIn('/projects/001/trace.html', other.artifacts)
        finally:
            other.server_close()
        (trace_dir / 'trace.html').unlink()
        trace_dir.rmdir()
        trace_dir.symlink_to(root, target_is_directory=True)
        other = IdeaServer(catalog, 'idea', root / 'graph.json', root / 'brief.md', root / 'new')
        try:
            self.assertNotIn('/projects/001/trace.html', other.artifacts)
        finally:
            other.server_close()
        fifo = root / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            IdeaServer(catalog, 'idea', root / 'graph.json', fifo, root / 'new')

    def test_phase_and_preflight_error_are_reported(self):
        self.server.out.mkdir()
        (self.server.out / 'promotion-status.json').write_text('{"phase":"testing"}')
        self.server.state = 'running'
        self.assertIn('테스트 실행 중', self.server.current_status()['message'])
        def fail(command, **kwargs):
            kwargs['stderr'].write(b'Promotion failed: Brief is empty\n')
            return subprocess.CompletedProcess(command, 1)
        with patch('serve_ideas.require_selection'), patch('serve_ideas.subprocess.run', fail):
            self.server.run_build()
        self.assertEqual(self.server.state, 'failed')
        self.assertIn('Brief is empty', self.server.message)

    def test_preview_is_separate_pinned_and_confined(self):
        app = self.server.out / 'app'
        app.mkdir(parents=True)
        (app / 'index.html').write_text('<h1>App</h1>')
        (app / 'app.js').write_text('ok')
        (app / 'outside').symlink_to(self.root / 'brief.md')
        os.link(self.root / 'brief.md', app / 'hardlink')
        (app / 'folder').mkdir()
        def success(command, **kwargs):
            return subprocess.CompletedProcess(command, 0)
        with patch('serve_ideas.require_selection'), patch('serve_ideas.subprocess.run', success):
            self.assertIsNone(self.server.current_status()['preview_url'])
            self.server.run_build()
        status = self.server.current_status()
        self.assertEqual(status['state'], 'succeeded')
        self.assertNotEqual(self.server.preview.server_port, self.server.server_port)
        self.assertEqual(status['preview_url'], 'http://' + self.server.preview.host + '/')
        def preview(path, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.preview.server_port)
            conn.request('GET', path, headers=headers or {})
            response = conn.getresponse()
            data = response.read()
            result = response.status, response.getheader('Content-Type'), data
            conn.close()
            return result
        self.assertEqual(preview('/')[2], b'<h1>App</h1>')
        self.assertIn('javascript', preview('/app.js')[1])
        (app / 'app.js').write_text('changed')
        self.assertEqual(preview('/app.js')[2], b'ok')
        for path in ['/outside', '/hardlink', '/folder/', '/%2e%2e/brief.md', '/api/status']:
            self.assertEqual(preview(path)[0], 404)
        self.assertEqual(preview('/', {'Host': 'evil.test'})[0], 403)
        page = self.server.page.decode()
        self.assertIn("job.state === 'succeeded'", page)
        self.assertIn('완성된 앱 열기', page)

    def test_reopen_accepted_same_draft_only_and_reject_stale(self):
        fixture = test_promote_idea.PromoteTests('test_complete_job_runs_fixed_cli_real_tests_and_admission')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        result = fixture.run_promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = fixture.out / 'admission/manifest-001.json'
        before = sorted(str(p.relative_to(fixture.out)) for p in fixture.out.rglob('*'))
        reopened = IdeaServer(fixture.catalog, 'Counter', fixture.draft, fixture.brief, fixture.out, manifest)
        try:
            self.assertEqual(reopened.current_status()['state'], 'succeeded')
            self.assertIsNotNone(reopened.current_status()['preview_url'])
            self.assertFalse(reopened.start_build())
            self.assertEqual(before, sorted(str(p.relative_to(fixture.out)) for p in fixture.out.rglob('*')))
        finally:
            reopened.server_close()
        next_manifest = fixture.out / 'admission/manifest-002.json'
        snapshot = subprocess.run([
            sys.executable, str(Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts/ssot.py'),
            'snapshot', '--brief', str(fixture.out / 'brief.md'), '--graph', str(fixture.out / 'graph.json'),
            '--bindings', str(fixture.out / 'bindings.json'), '--out', str(next_manifest), '--previous', str(manifest)],
            capture_output=True, text=True)
        self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
        reopened = IdeaServer(fixture.catalog, 'Counter', fixture.draft, fixture.brief, fixture.out, next_manifest)
        reopened.server_close()
        other = fixture.root / 'other.md'
        other.write_text('different brief')
        with self.assertRaises(ValueError):
            IdeaServer(fixture.catalog, 'Counter', fixture.draft, other, fixture.out, manifest)
        (fixture.out / 'app/index.html').write_text('changed')
        with self.assertRaises(ValueError):
            IdeaServer(fixture.catalog, 'Counter', fixture.draft, fixture.brief, fixture.out, manifest)

    def test_single_job_and_poll(self):
        started, release = threading.Event(), threading.Event()
        def run():
            started.set()
            release.wait(3)
            with self.server.lock:
                self.server.state, self.server.message = 'succeeded', 'done'
        headers = {'Origin': self.server.origin, 'X-Build-Token': self.server.token}
        with patch('serve_ideas.require_selection'), patch.object(self.server, 'run_build', run):
            self.assertEqual(self.request('POST', '/api/build', headers)[0], 202)
            self.assertTrue(started.wait(2))
            self.assertEqual(self.request('POST', '/api/build', headers)[0], 409)
            self.assertEqual(json.loads(self.request('GET', '/api/status', headers)[1])['state'], 'running')
            release.set()
            for _ in range(100):
                if json.loads(self.request('GET', '/api/status', headers)[1])['state'] == 'succeeded':
                    break
            else:
                self.fail('job did not complete')


if __name__ == '__main__':
    unittest.main()
