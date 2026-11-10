from contextlib import closing
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workspace_chat import ChatServer
import figma_workspace


class WorkspaceChatTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / 'workspace'
        identity = Path(self.temp.name) / 'assigned.json'
        identity.write_text(json.dumps({'id': '123456789'}))
        figma_workspace.init(self.workspace, identity, chat_port=49152)
        self.thread = str(uuid.uuid4())
        figma_workspace.prepare(self.workspace, 'project-task', 'Test chat', 'discover',
                                ['--file-key', 'fixturefile', '--page-id', '0:1'], thread_id=self.thread)
        with figma_workspace.locked(self.workspace):
            self.task = figma_workspace.current(self.workspace)['tasks'][0]
        self.write('chat.json', {'schema': 'figma-flow-workspace-chat-v1', 'port': 49152, 'token': 'b' * 64})
        self.publish_tasks([self.task])
        self.cli = self.workspace / 'fake-codex'
        self.cli.write_text('#!' + sys.executable + '\nimport json, pathlib, sys\npathlib.Path(__file__).with_suffix(".args").write_text(json.dumps(sys.argv[1:]))\n')
        self.cli.chmod(0o700)
        self.start()
        self.body = dict({key: self.task[key] for key in ('key', 'threadId', 'revision')}, requestId=str(uuid.uuid4()), text='Reviewed prompt\n$(touch hacked); `whoami`\n--thread other')

    def write(self, name, value):
        path = self.workspace / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def publish_tasks(self, tasks):
        with figma_workspace.locked(self.workspace):
            catalogue = figma_workspace.current(self.workspace)
            figma_workspace.publish(self.workspace, dict(catalogue, tasks=tasks))

    def start(self):
        self.server = ChatServer(self.workspace, cli=str(self.cli), timeout=5, port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def send(self, body=None, path='/chat/queue', headers=None, method='POST', raw=None):
        with closing(http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)) as client:
            defaults = {'Host': self.server.host, 'Authorization': 'Bearer ' + 'b' * 64, 'Content-Type': 'application/json'}
            defaults.update(headers or {})
            client.request(method, path, raw if raw is not None else json.dumps(self.body if body is None else body), defaults)
            response = client.getresponse()
            return response.status, json.loads(response.read())

    def test_literal_queue_with_real_fake_cli_and_persistent_replay(self):
        status, result = self.send()
        self.assertEqual((status, result), (200, {'status': 'queued', 'consumed': False}))
        self.assertEqual(json.loads(self.cli.with_suffix('.args').read_text()),
                         ['queue', '--thread', self.thread, '--message=' + self.body['text']])
        self.assertEqual(self.send()[0], 409)
        self.server.shutdown()
        self.server.server_close()
        self.start()
        self.assertEqual(self.send()[1], {'status': 'queued', 'consumed': False, 'replayed': True})
        self.assertNotIn(self.body['text'], (self.workspace / 'chat-requests.json').read_text())

    @patch('workspace_chat.subprocess.run')
    def test_authorization_scope_current_registry_and_strict_transport(self, run):
        for headers in ({'Authorization': ''}, {'Host': 'evil.example'}, {'Origin': 'https://evil.example'},
                        {'Content-Type': 'text/plain'}, {'Content-Length': '100001'}, {'Transfer-Encoding': 'chunked'}):
            with self.subTest(headers=headers):
                self.assertGreaterEqual(self.send(headers=headers)[0], 400)
        for update in ({'key': 'another-task'}, {'threadId': str(uuid.uuid4())}, {'revision': 'c' * 64},
                       {'extra': 'no'}, {'requestId': '../../path'}, {'text': '\x00'}, {'text': ' '}):
            with self.subTest(update=update):
                self.assertGreaterEqual(self.send(body=dict(self.body, **update))[0], 400)
        self.assertGreaterEqual(self.send(raw='{"key":"one","key":"two"}')[0], 400)
        self.publish_tasks([dict(self.task, threadId=str(uuid.uuid4()))])
        self.assertEqual(self.send()[0], 409)
        run.assert_not_called()
        self.assertFalse((self.workspace / 'chat-requests.json').exists())

    @patch('workspace_chat.subprocess.run', side_effect=subprocess.TimeoutExpired('codex', 0.1))
    def test_uncertain_timeout_is_not_retried(self, run):
        self.assertEqual(self.send()[0], 504)
        status, result = self.send()
        self.assertEqual((status, result['status'], result['replayed']), (409, 'uncertain', True))
        self.assertEqual(self.send(body=dict(self.body, text='changed'))[0], 409)
        run.assert_called_once()

    def test_real_slow_cli_timeout_stays_uncertain_after_restart(self):
        self.cli.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(3)\n')
        self.server.action_timeout = 0.2
        self.assertEqual(self.send()[0], 504)
        self.server.shutdown()
        self.server.server_close()
        self.start()
        with patch('workspace_chat.subprocess.run') as run:
            self.assertEqual(self.send()[1]['status'], 'uncertain')
            run.assert_not_called()

    @patch('workspace_chat.subprocess.run')
    def test_preflight_and_pinned_mac_opener(self, run):
        self.assertEqual(self.send(method='OPTIONS', headers={'Origin': 'null'})[0], 200)
        run.assert_not_called()
        with patch('workspace_chat.sys.platform', 'darwin'):
            body = {key: value for key, value in self.body.items() if key != 'text'}
            self.assertEqual(self.send(body=body, path='/chat/open'), (200, {'status': 'opened'}))
        self.assertEqual(run.call_args.args[0], ['/usr/bin/open', 'codex://threads/' + self.thread])
        self.assertFalse(run.call_args.kwargs['shell'])

    @patch('workspace_chat.subprocess.run')
    def test_windows_uses_only_registered_uri(self, run):
        body = {key: value for key, value in self.body.items() if key != 'text'}
        with patch('workspace_chat.sys.platform', 'win32'), patch('workspace_chat.os.startfile', create=True) as opener:
            self.assertEqual(self.send(body=body, path='/chat/open')[0], 200)
            opener.assert_called_once_with('codex://threads/' + self.thread)
        run.assert_not_called()

    @patch('workspace_chat.subprocess.run')
    def test_windows_batch_wrapper_is_never_executed(self, run):
        self.server.cli = 'codex.cmd'
        with patch('workspace_chat.sys.platform', 'win32'):
            self.assertEqual(self.send()[0], 503)
        run.assert_not_called()
        self.assertFalse((self.workspace / 'chat-requests.json').exists())

    @patch('workspace_chat.subprocess.run')
    def test_unpublished_mirror_cannot_change_destination(self, run):
        other_thread = str(uuid.uuid4())
        self.write('catalogue.json', {'schema': 'figma-flow-workspace-v1',
                                     'tasks': [dict(self.task, threadId=other_thread)]})
        self.assertEqual(self.send(body=dict(self.body, threadId=other_thread))[0], 409)
        run.assert_not_called()
        self.assertEqual(self.send()[0], 200)

    @patch('workspace_chat.subprocess.run')
    def test_stale_temporary_receipts_do_not_block_actions(self, run):
        legacy = self.workspace / 'chat-requests.tmp'
        orphan = self.workspace / '.chat-requests.json-crashed'
        for path in (legacy, orphan):
            path.write_text('incomplete prior receipt')
            path.chmod(0o600)
        self.assertEqual(self.send()[0], 200)
        run.assert_called_once()
        receipt = self.workspace / 'chat-requests.json'
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(receipt.read_text())[self.body['requestId']]['result']['status'], 'queued')
        self.assertEqual(set(self.workspace.glob('.chat-requests.json-*')), {orphan})
        self.assertEqual(self.send()[1]['replayed'], True)
        run.assert_called_once()

    @patch('workspace_chat.subprocess.run')
    def test_preclaim_receipt_failures_report_definitely_not_started(self, run):
        receipt = self.workspace / 'chat-requests.json'
        receipt.write_text('invalid json')
        receipt.chmod(0o600)
        status, result = self.send()
        self.assertEqual(status, 409)
        self.assertIn('no action was started', result['error'])
        self.assertNotIn('status', result)
        run.assert_not_called()
        receipt.unlink()
        with patch.object(self.server, 'save_ledger', side_effect=OSError('initial claim failed')):
            status, result = self.send()
        self.assertEqual(status, 409)
        self.assertIn('no action was started', result['error'])
        self.assertNotIn('status', result)
        self.assertFalse(receipt.exists())
        run.assert_not_called()

    @patch('workspace_chat.subprocess.run')
    def test_failed_receipt_after_enqueue_stays_uncertain_and_replay_safe(self, run):
        save = self.server.save_ledger
        calls = []
        def fail_final_receipt(path, ledger):
            calls.append(True)
            if len(calls) == 2:
                raise ValueError('receipt failure after command returned')
            save(path, ledger)
        with patch.object(self.server, 'save_ledger', side_effect=fail_final_receipt):
            status, result = self.send()
        self.assertEqual((status, result['status']), (504, 'uncertain'))
        self.assertNotIn('no action was started', result['error'])
        self.assertEqual(self.send()[1]['status'], 'uncertain')
        run.assert_called_once()

    def test_task_replacement_waits_until_queue_finishes(self):
        started, finish, replaced = threading.Event(), threading.Event(), threading.Event()
        responses = []
        def command(*args, **kwargs):
            started.set()
            if not finish.wait(3):
                raise RuntimeError('test command release timed out')
        def replace():
            self.publish_tasks([dict(self.task, threadId=str(uuid.uuid4()))])
            replaced.set()
        with patch('workspace_chat.subprocess.run', side_effect=command):
            sender = threading.Thread(target=lambda: responses.append(self.send()))
            sender.start()
            self.assertTrue(started.wait(3))
            publisher = threading.Thread(target=replace)
            publisher.start()
            try:
                self.assertFalse(replaced.wait(0.1))
            finally:
                finish.set()
                sender.join(3)
                publisher.join(3)
        self.assertEqual(responses[0][0], 200)
        self.assertTrue(replaced.is_set())
        self.assertEqual(self.send(body=dict(self.body, requestId=str(uuid.uuid4())))[0], 409)

    @patch('workspace_chat.subprocess.run')
    def test_rotated_capability_and_duplicate_registry_key_rejected(self, run):
        self.publish_tasks([self.task, self.task])
        self.assertEqual(self.send()[0], 409)
        self.write('chat.json', dict(self.server.config, token='c' * 64))
        self.assertEqual(self.send()[0], 409)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
