"""Bounded, signed large-read relay regression; data is generated, not retained."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

import figma_control as control
import figma_workspace as workspace
import finalize_control_capacity as capacity_fixture

MiB = 1024 * 1024
REFERENCE_RAW_BYTES = 47_447_005
REFERENCE_NODE_COUNT = 20_421


def native_readback_fixture():
    nodes = []
    for index in range(REFERENCE_NODE_COUNT):
        nodes.append(json.dumps({
            'id': f'{index + 1}:1', 'parentId': '12:1', 'type': 'FRAME',
            'name': f'Layer {index + 1}', 'width': 120, 'height': 48,
            'visible': True, 'fills': [], 'boundVariables': {},
        }, separators=(',', ':')))
    prefix = ('{"schema":"figma-flow-graph-native-discovery-v1","status":"applied",'
              '"fileKey":"fixturefile","pageId":"12:1","allowed_page_ids":["12:1"],'
              '"nodes":[' + ','.join(nodes) + '],"variables":[],"collections":[],"fixture":"')
    suffix = '"}'
    escaped_quotes = r'\"' * 2_797_491
    filler_size = REFERENCE_RAW_BYTES - len(prefix.encode()) - len(escaped_quotes.encode()) - len(suffix.encode())
    if filler_size < 0:
        raise AssertionError('generated node fixture unexpectedly exceeds its measured native size')
    raw = prefix + escaped_quotes + ('x' * filler_size) + suffix
    require(len(raw.encode('utf-8')) == REFERENCE_RAW_BYTES,
            'fixture must match the measured compact 20,421-node readback size')
    require(len(json.loads(raw)['nodes']) == REFERENCE_NODE_COUNT, 'fixture must decode as a full native readback object')
    return raw


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_bounded_views(case, receipt, raw_bytes):
    status = control.status(case.root, receipt['id'])
    history = control.history(case.root, {'session_id': receipt['session_id'],
        'file_key': receipt['file_key'], 'page_id': receipt['page_id'],
        'runtime': workspace.current(case.root)['runtime']})
    detail = control.history_detail(case.root, {'session_id': receipt['session_id'],
        'file_key': receipt['file_key'], 'page_id': receipt['page_id'],
        'runtime': workspace.current(case.root)['runtime'], 'operation_id': receipt['id'],
        'task_key': 'discovery', 'revision': receipt['revision']})
    for label, value in (('status', status), ('history', history), ('operation detail', detail)):
        encoded = workspace.encode(value)
        require(b'readback_json' not in encoded, label + ' must not return a raw result field')
        require(raw_bytes not in encoded, label + ' must not return the native readback')
        require(len(encoded) < 256 * 1024, label + ' must remain bounded')
    require(detail.get('operation') == 'read' and detail.get('readOnly') is True,
            'operation detail must remain a scoped read-only projection')


class TestBookingRelayRegression(unittest.TestCase):
    def test_signed_native_size_read_uses_bounded_large_http_route(self):
        raw = native_readback_fixture()
        raw_bytes = raw.encode('utf-8')
        case = capacity_fixture.ControlCapacity(
            'test_real_http_result_admits_actual_case_sized_raw_json_and_escaped_envelope')
        case.setUp()
        try:
            receipt = dict(case.receipt)
            receipt['readback_json'] = raw
            before = case.snapshot()
            with self.assertRaises(ValueError, msg='legacy direct result() must retain its 32 MiB cap'):
                control.result(case.root, receipt)
            self.assertEqual(case.snapshot(), before, 'legacy cap rejection must not mutate the active claim')
            self.assertEqual(control.status(case.root)['state'], 'claimed')

            # Probe the exact authenticated route with a deliberately malformed small envelope.
            code, _ = case.post(b'{}', route='/control/result-large')
            self.assertEqual(code, 409, 'authenticated /control/result-large route must be registered')
            self.assertEqual(control.status(case.root)['state'], 'claimed', 'invalid probe must not consume the claim')

            body = json.dumps(receipt, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.assertGreater(len(raw_bytes), 32 * MiB, 'raw readback must exceed the legacy inner cap')
            self.assertGreater(len(body), 40 * MiB, 'escaped envelope must exceed the legacy HTTP cap')
            self.assertLess(len(raw_bytes), 64 * MiB, 'raw readback must remain inside the hard large-read cap')
            self.assertLess(len(body), 80 * MiB, 'wire envelope must remain inside the hard large-request cap')
            code, value = case.post(body, route='/control/result-large')
            self.assertEqual(code, 200, 'signed read result must cross the authenticated HTTP route')
            self.assertEqual(value, {'accepted': True, 'id': receipt['id'], 'state': 'ok'})
            stored = case.root / '.control/readbacks' / (receipt['id'] + '.json')
            self.assertEqual(stored.stat().st_size, len(raw_bytes), 'server must store exact raw UTF-8 bytes')
            with stored.open('rb') as handle:
                self.assertEqual(hashlib.file_digest(handle, 'sha256').hexdigest(), hashlib.sha256(raw_bytes).hexdigest())
            assert_bounded_views(case, receipt, raw_bytes)

            # A retry of the same accepted result remains idempotent after the operation is terminal.
            code, replay = case.post(body, route='/control/result-large')
            self.assertEqual(code, 200)
            self.assertEqual(replay, value)

            before = case.snapshot()
            code, _ = case.post(b'{}', route='/control/result-large', Authorization='Bearer wrong')
            self.assertEqual(code, 403, 'large-result route must keep the bearer-token boundary')
            self.assertEqual(case.snapshot(), before, 'unauthenticated request must not mutate workspace state')

            code, _ = case.post(b'{}', route='/control/result-large', **{'Content-Length': str(80 * MiB + 1)})
            self.assertEqual(code, 413, 'large-result route must retain its hard 80 MiB wire ceiling')
            self.assertEqual(case.snapshot(), before, 'over-ceiling request must be rejected before mutation')

            code, _ = case.post(b'{}', route='/control/result', **{'Content-Length': str(40 * MiB + 1)})
            self.assertEqual(code, 413, 'ordinary /control/result must retain its 40 MiB request cap')
            self.assertEqual(case.snapshot(), before, 'oversized legacy request must be rejected before mutation')
            print('PASS signed 20,421-node result: raw 47,447,005 bytes; escaped envelope exceeds 40 MiB')
            print('PASS status/history/detail stay bounded and omit readback bytes')
            print('PASS legacy direct and HTTP result limits remain 32 MiB / 40 MiB')
        finally:
            case.doCleanups()

    def test_large_result_route_rejects_a_signed_mutation_claim(self):
        case = capacity_fixture.ControlCapacity(
            'test_real_http_result_admits_actual_case_sized_raw_json_and_escaped_envelope')
        case.setUp()
        try:
            control.result(case.root, {**case.receipt, 'readback_json': '{}'})
            from test_graph_sync import fixture
            graph, native = fixture()
            native.update(fileKey='fixturefile', pageId='12:1')
            for node in native['nodes']:
                if node.get('parentId') == 'page':
                    node['parentId'] = '12:1'
            graph_path, native_path = case.directory / 'large-mutation-graph.json', case.directory / 'large-mutation-native.json'
            graph_path.write_text(json.dumps(graph))
            native_path.write_text(json.dumps(native))
            task = workspace.prepare(case.root, 'large-mutation', 'Apply graph', 'sync',
                ['--graph', str(graph_path), '--native-readback', str(native_path)], infer_thread=False)
            control.enqueue(case.root, 'large-mutation', 'apply', 'fixturefile', '12:1', task['revision'], 120)
            claim = control.poll(case.root, {'session_id': 'capacity-session', 'file_key': 'fixturefile',
                'page_id': '12:1', 'runtime': workspace.current(case.root)['runtime']})['operation']
            raw = '{"status":"applied","payload":"' + ('x' * (33 * MiB)) + '"}'
            payload = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
            payload.update(status='ok', readback_json=raw)
            body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
            self.assertGreater(len(body), 32 * MiB, 'mutation case must cross the legacy raw-result threshold')
            before = case.snapshot()
            code, _ = case.post(body, route='/control/result-large')
            self.assertEqual(code, 409, 'large-result route must reject a claimed sync/apply operation')
            self.assertEqual(case.snapshot(), before, 'rejected large mutation must not change workspace data')
            self.assertEqual(control.status(case.root)['state'], 'claimed')
        finally:
            case.doCleanups()


if __name__ == '__main__':
    if '--gate' in sys.argv:
        sys.argv.remove('--gate')
        TestBookingRelayRegression('test_signed_native_size_read_uses_bounded_large_http_route').test_signed_native_size_read_uses_bounded_large_http_route()
        TestBookingRelayRegression('test_large_result_route_rejects_a_signed_mutation_claim').test_large_result_route_rejects_a_signed_mutation_claim()
    else:
        unittest.main()
