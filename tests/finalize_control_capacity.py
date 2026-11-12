"""Real private HTTP result capacity; synthetic JSON is not native acceptance."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_control as control
import figma_workspace as workspace

MiB = 1024 * 1024


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class ControlCapacity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'workspace'
        assigned = self.directory / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.root, assigned)
        prepared = workspace.prepare(self.root, 'discovery', 'Read values', 'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'], infer_thread=False)
        self.server = control.ThreadingHTTPServer(('127.0.0.1', 0), control.Handler)
        self.addCleanup(self.server.server_close)
        control.enable(self.root, self.server.server_port)
        self.server.workspace = self.root
        self.server.token = control.config(self.root)['token']
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        control.enqueue(self.root, 'discovery', 'read', 'fixturefile', '12:1', prepared['revision'], 120)
        claim = control.poll(self.root, {'session_id': 'capacity-session', 'file_key': 'fixturefile',
            'page_id': '12:1', 'runtime': workspace.current(self.root)['runtime']})['operation']
        self.receipt = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        self.receipt['status'] = 'ok'

    def post(self, body=b'{}', route='/control/result', **headers):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        values = {'Host': f'localhost:{self.server.server_port}',
                  'Authorization': 'Bearer ' + self.server.token, 'Content-Type': 'application/json'}
        values.update(headers)
        try:
            connection.request('POST', route, body=body, headers=values)
        except (BrokenPipeError, ConnectionResetError) as error:
            self.fail(f'HTTP service rejected the envelope before body transfer completed: {error}')
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_real_http_result_admits_actual_case_sized_raw_json_and_escaped_envelope(self):
        prefix, suffix, quotes, raw_bytes = '{"text":"', '"}', 1713000, 29991516
        raw = prefix + '\\"' * quotes + 'a' * (raw_bytes - len(prefix) - len(suffix) - 2 * quotes) + suffix
        expected_sha = hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(len(raw.encode()), raw_bytes)
        body = json.dumps({**self.receipt, 'readback_json': raw}, separators=(',', ':')).encode()
        self.assertGreater(len(body), 33000000)
        self.assertLess(len(body), 40 * MiB)
        del raw
        code, result = self.post(body)
        del body
        self.assertEqual(code, 200, 'bounded real native-size envelope must reach control.result')
        self.assertTrue(result['accepted'])
        stored = self.root / '.control/readbacks' / (self.receipt['id'] + '.json')
        self.assertEqual(stored.stat().st_size, raw_bytes)
        with stored.open('rb') as handle:
            self.assertEqual(hashlib.file_digest(handle, 'sha256').hexdigest(), expected_sha)
        self.assertEqual(control.status(self.root)['state'], 'ok')

    def test_direct_result_admits_case_sized_native_json(self):
        raw = '{"text":"' + 'a' * (29991516 - 11) + '"}'
        self.assertEqual(len(raw.encode()), 29991516)
        try:
            result = control.result(self.root, {**self.receipt, 'readback_json': raw})
        except ValueError as error:
            self.fail(f'Legitimate native-size JSON must reach result persistence: {error}')
        self.assertTrue(result['accepted'])
        self.assertEqual(control.status(self.root)['state'], 'ok')
        stored = self.root / '.control/readbacks' / (self.receipt['id'] + '.json')
        self.assertEqual(stored.stat().st_size, 29991516)

    def test_raw_utf8_over_32_mib_is_rejected_without_workspace_mutation(self):
        raw = '{"text":"' + '가' * ((32 * MiB + 2) // 3) + '"}'
        self.assertLess(len(raw), 32 * MiB)
        self.assertGreater(len(raw.encode()), 32 * MiB)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            control.result(self.root, {**self.receipt, 'readback_json': raw})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(control.status(self.root)['state'], 'claimed')

    def test_over_40_mib_declared_envelope_is_rejected_before_body_read(self):
        before = self.snapshot()
        code, _ = self.post(**{'Content-Length': str(40 * MiB + 1)})
        self.assertEqual(code, 413)
        self.assertEqual(self.snapshot(), before)

    def test_http_auth_origin_route_and_exact_claim_guards_remain(self):
        before = self.snapshot()
        for headers in ({'Authorization': 'Bearer wrong'}, {'Origin': 'https://example.com'}, {'Host': 'example.com'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post(**headers)[0], 403)
        self.assertEqual(self.post(route='/control/run')[0], 403)
        for field in ('claim_id', 'session_id', 'file_key', 'page_id', 'revision'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                control.result(self.root, {**self.receipt, field: 'different', 'readback_json': '{}'})
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
