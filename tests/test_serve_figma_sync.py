from contextlib import closing
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from serve_figma_sync import SyncHandler, run


class SyncHTTPTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), SyncHandler)
        self.server.host = f'127.0.0.1:{self.server.server_port}'
        self.server.auth = b'Bearer private'
        self.server.file_key, self.server.page_id = 'cards', '2:77'
        self.server.session = Mock()
        self.server.session.last_comparison.return_value = None
        self.server.session.sync.return_value = {'status': 'applied'}
        self.server.preview, self.server.preview_url = object(), 'http://127.0.0.1:12345/'
        self.server.apply_lock = threading.Lock()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.body = {'file_key': 'cards', 'page_id': '2:77', 'readback': {'scope': 'paired-active-import-page',
                     'evidence': 'observed-plugin-api-readback', 'pages': [{'id': '2:77'}]}}

    def send(self, method='POST', path='/sync', headers=None, body=None):
        with closing(http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)) as client:
            base = {'Authorization': 'Bearer private', 'Content-Type': 'application/json', 'Origin': 'null'}
            client.request(method, path, json.dumps(self.body if body is None else body), dict(base, **(headers or {})))
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    @patch('serve_figma_sync.update_preview')
    def test_click_and_preflight(self, publish):
        status, headers, _ = self.send('OPTIONS', headers={'Access-Control-Request-Private-Network': 'true'})
        self.assertEqual(status, 200)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'null')
        self.assertEqual(headers['Access-Control-Allow-Private-Network'], 'true')
        status, _, data = self.send()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['preview_url'], self.server.preview_url)
        self.server.session.sync.assert_called_once_with(self.body['readback'])
        publish.assert_called_once()

    @patch('serve_figma_sync.update_preview')
    @patch('serve_figma_sync.snapshot_app')
    def test_captures_previous_render_inputs_before_apply(self, capture, publish):
        prior = {'native': 'before'}
        self.server.session.last_comparison.return_value = (prior, {'status': 'baseline'})
        capture.return_value = {'/index.html': b'original'}
        def apply(data):
            capture.assert_called_once_with(self.server.session.project)
            return {'status': 'applied'}
        self.server.session.sync.side_effect = apply
        self.assertEqual(self.send()[0], 200)
        self.assertEqual(publish.call_args.kwargs['previous'], (prior, capture.return_value))

    def test_only_paired_page_and_capability_can_apply(self):
        for headers in ({'Host': 'other.example'}, {'Authorization': ''}, {'Origin': 'http://evil.invalid'},
                        {'Content-Type': 'text/plain'}, {'Content-Length': '9000000'}):
            with self.subTest(headers=headers):
                self.assertGreaterEqual(self.send(headers=headers)[0], 400)
        self.assertGreaterEqual(self.send(path='/other')[0], 400)
        self.assertGreaterEqual(self.send(body=dict(self.body, file_key='elsewhere'))[0], 400)
        self.assertGreaterEqual(self.send(body=dict(self.body, readback={}))[0], 400)
        self.server.session.sync.assert_not_called()

    @patch('serve_figma_sync.update_preview', side_effect=ValueError('no comparison'))
    def test_applied_and_preview_error_are_distinguished(self, publish):
        status, _, data = self.send()
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result['status'], 'applied')
        self.assertIn('no comparison', result['preview_error'])
        self.assertNotIn('preview_url', result)


class SyncEntryTest(unittest.TestCase):
    def test_wrong_selection_fails_before_state_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'project'
            project.mkdir()
            resolved = root / 'resolved.json'
            resolved.write_text('{}')
            selection = root / 'claim.json'
            selection.write_text('{"approved":true}')
            with patch('serve_figma_sync.compile_plugin') as compile:
                with self.assertRaisesRegex(ValueError, 'WAIT_SELECTION'):
                    run(project, resolved, '2:77', 'cards', '123', root / 'state', selection_path=selection)
                compile.assert_not_called()
            self.assertFalse((root / 'state').exists())

    def test_existing_token_only_session_compiles_sealed_companion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'project'
            project.mkdir()
            resolved = root / 'resolved.json'
            resolved.write_text('{}')
            preview = Mock(server_port=12345)
            with patch('serve_figma_sync.SyncSession', return_value=Mock(last_comparison=Mock(return_value=None))), patch('serve_figma_sync.start_preview', return_value=preview), patch('serve_figma_sync.compile_plugin', side_effect=ValueError('stop after compile')) as compile:
                with self.assertRaisesRegex(ValueError, 'stop after compile'):
                    run(project, resolved, '2:77', 'cards', '123', root / 'state')
            self.assertTrue(compile.call_args.kwargs['technical_existing'])
            self.assertIsNone(compile.call_args.kwargs['selection_path'])
            self.assertEqual(compile.call_args.kwargs['local_sync']['page_id'], '2:77')

    def test_selected_assets_are_admitted_before_state_and_forwarded_to_compiler(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'project'
            project.mkdir()
            resolved = root / 'resolved.json'
            resolved.write_text('{}')
            selection, batch, receipts = (root / name for name in ('selection.json', 'batch.json', 'receipts.json'))
            state = root / 'state'
            with patch('serve_figma_sync.design_directions.require_selected'), patch('serve_figma_sync.require_selection'), patch('serve_figma_sync.design_directions.guard_production') as guard:
                for inputs, reason in (({}, 'missing required generated assets'), ({'batch_path': batch, 'asset_receipts': receipts}, 'stale asset receipt')):
                    with self.subTest(reason=reason):
                        guard.side_effect = ValueError(reason)
                        with patch('serve_figma_sync.secrets.token_hex') as token, patch('serve_figma_sync.compile_plugin') as compile:
                            with self.assertRaisesRegex(ValueError, reason):
                                run(project, resolved, '2:77', 'cards', '123', state, selection_path=selection, **inputs)
                            token.assert_not_called()
                            compile.assert_not_called()
                        self.assertFalse(state.exists())
                guard.side_effect = None
                with patch('serve_figma_sync.SyncSession', return_value=Mock(last_comparison=Mock(return_value=None))), patch('serve_figma_sync.start_preview', return_value=Mock(server_port=12345)), patch('serve_figma_sync.compile_plugin', side_effect=ValueError('stop after compile')) as compile:
                    with self.assertRaisesRegex(ValueError, 'stop after compile'):
                        run(project, resolved, '2:77', 'cards', '123', state, selection_path=selection, batch_path=batch, asset_receipts=receipts)
                self.assertEqual(compile.call_args.kwargs['batch_path'], batch)
                self.assertEqual(compile.call_args.kwargs['asset_receipts'], receipts)
                self.assertFalse(compile.call_args.kwargs['technical_existing'])
                self.assertEqual(guard.call_args.kwargs['event'].value, 'handoff-native')
