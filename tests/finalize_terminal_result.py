"""Terminal result delivery oracle using real private workspace storage.

Synthetic plugin payloads do not establish live native Figma acceptance.
"""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_figma_control as fixtures

control = fixtures.control
workspace = fixtures.workspace


class TerminalResultDelivery(unittest.TestCase):
    setUp = fixtures.ControlTests.setUp
    enqueue = fixtures.ControlTests.enqueue
    claim = fixtures.ControlTests.claim
    mutation = fixtures.ControlTests.mutation
    uncertain_mutation = fixtures.ControlTests.uncertain_mutation
    discovery_readback = fixtures.ControlTests.discovery_readback

    def payload(self, status='ok', **changes):
        self.enqueue()
        claim = self.claim()
        value = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        value.update(status=status, readback_json=' {"value": 1, "text": "한글"}\n')
        if status == 'error':
            value['error'] = 'native getter failed'
        value.update(changes)
        return value

    def snapshot(self):
        return ({str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                 for path in self.root.rglob('*') if path.is_file()}, copy.deepcopy(control.NATIVE_CLIENTS))

    def duplicate(self, payload, expected):
        before = self.snapshot()
        try:
            actual = control.result(self.root, payload)
        except ValueError as error:
            self.fail('Exact accepted terminal result must return its original receipt: ' + str(error))
        self.assertEqual(actual, expected)
        self.assertEqual(self.snapshot(), before, 'Duplicate delivery must not rewrite storage or refresh native state')

    def reject(self, payload):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            control.result(self.root, payload)
        self.assertEqual(self.snapshot(), before, 'Rejected delivery must leave all stored state unchanged')

    def test_identical_success_and_error_return_original_receipt_without_side_effects(self):
        for status in ('ok', 'error'):
            with self.subTest(status=status):
                payload = self.payload(status)
                accepted = control.result(self.root, payload)
                self.assertEqual(accepted, {'accepted': True, 'id': payload['id'], 'state': status})
                raw = self.root / '.control/readbacks' / (payload['id'] + '.json')
                self.assertEqual(raw.read_bytes(), payload['readback_json'].encode('utf-8'))
                self.duplicate(dict(reversed(list(payload.items()))), accepted)
                self.duplicate(payload, accepted)

    def test_error_without_readback_is_idempotent_but_absent_and_null_are_distinct(self):
        payload = self.payload('error')
        del payload['readback_json']
        accepted = control.result(self.root, payload)
        self.duplicate(payload, accepted)
        self.reject({**payload, 'readback_json': None})

    def test_conflicting_bytes_status_error_claim_and_scope_reject(self):
        payload = self.payload()
        control.result(self.root, payload)
        changes = ({'readback_json': '{"value":1,"text":"한글"}'}, {'status': 'error'}, {'error': ''},
                   {'claim_id': '0' * 32}, {'session_id': 'other-session'}, {'file_key': 'otherfile'},
                   {'page_id': '12:9'}, {'revision': '0' * 64}, {'extra': True}, {'readback_json': None})
        for change in changes:
            with self.subTest(change=change):
                self.reject({**payload, **change})
        failed = self.payload('error')
        control.result(self.root, failed)
        self.reject({**failed, 'error': 'different failure'})

    def test_old_receipt_does_not_touch_unrelated_expired_active_claim(self):
        payload = self.payload()
        accepted = control.result(self.root, payload)
        other = self.enqueue(timeout=1)
        self.claim(session_id='other-session')
        with patch.object(control.time, 'time', return_value=other['deadline'] + 1):
            self.duplicate(payload, accepted)
            self.reject({**payload, 'error': 'conflict'})
        request = workspace.read(self.root / '.control/requests' / (other['id'] + '.json'), private=True)
        self.assertEqual(request['state'], 'claimed')

    def test_duplicate_recovery_does_not_reconcile_later_uncertainty(self):
        self.uncertain_mutation()
        payload = self.payload(readback_json=self.discovery_readback())
        accepted = control.result(self.root, payload)
        later = self.uncertain_mutation()
        self.duplicate(payload, accepted)
        pending = workspace.read(self.root / '.control/uncertainty.json', private=True)
        self.assertEqual(set(pending['operations']), {later['id']})
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.mutation()

    def test_server_terminal_and_legacy_receipts_fail_closed(self):
        payload = self.payload()
        directory = self.root / '.control'
        claimed = workspace.read(directory / 'requests' / (payload['id'] + '.json'), private=True)
        for state in ('ok', 'error', 'uncertain', 'expired'):
            with self.subTest(state=state):
                legacy = {**claimed, 'state': state, 'completed_at': claimed['deadline']}
                control.save(directory, legacy)
                self.reject(payload)

    def test_malformed_operation_ids_never_reach_path_lookup(self):
        payload = self.payload()
        control.result(self.root, payload)
        for operation_id in ('../active', '/tmp/outside', 'a' * 31, 'A' * 32, None, [], {}):
            with self.subTest(operation_id=operation_id):
                self.reject({**payload, 'id': operation_id})


if __name__ == '__main__':
    unittest.main()
