"""RC1 retained 64 pointer entries after admitting 65 requests."""
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_figma_control as fixtures

c, ws = fixtures.control, fixtures.workspace


class LegacySlotRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ControlTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.q = c.state_dir(self.f.root)

    def old_queue(self, *, claimed=False, complete=False):
        # Original request and (when applicable) claim come from the public queue.
        original = self.f.enqueue()
        if claimed:
            self.f.claim()
            original = c.active_for_file(self.q, 'fixturefile')
        mapping = {}
        for i in range(64):
            oid = f'{i + 1:032x}'
            key = f'F{i:02}'
            row = dict(original, id=oid, key='other', operation='read', file_key=key, state='pending',
                       created_at=time.time(), deadline=time.time()+3600)
            for name in (*c.LIFECYCLE_FIELDS, 'claimed_at', 'claim_id', 'session_id'):
                row.pop(name, None)
            if complete and i == 63:
                row['state'] = 'ok'
            c.save(self.q, row)
            mapping[key] = oid
        # This is the RC1 writer's persisted 64-entry map, not a 65-entry pointer.
        ws.atomic(self.q/'active.json', ws.encode({'id':oid,'by_file':mapping}))
        return original, mapping

    def test_status_restores_exact_pending_id_then_poll_claims_once(self):
        old, _ = self.old_queue(complete=True)
        self.assertEqual(c.status(self.f.root,file_key='fixturefile').get('id'), old['id'],
                         'status must recover the previously admitted request')
        with self.assertRaisesRegex(ValueError, 'already active'):
            self.f.enqueue()
        claim = self.f.claim()
        self.assertEqual(claim['id'], old['id'])
        self.assertIsNone(self.f.claim())
        self.assertTrue(self.f.result(claim)['accepted'])
        with patch.object(Path,'glob',side_effect=AssertionError('second historical scan')):
            self.assertEqual(c.status(self.f.root,file_key='fixturefile')['state'],'ok')

    def test_overcommitted_queue_holds_original_until_a_slot_drains(self):
        old, slots = self.old_queue()
        count = len(list((self.q/'requests').iterdir()))
        value = c.status(self.f.root,file_key='fixturefile')
        self.assertEqual(value.get('id'), old['id'])
        self.assertIn('status',value['legacy_recovery'])
        self.assertEqual(len(value['active_operations']),65)
        with self.assertRaisesRegex(ValueError,'status'):
            self.f.enqueue()
        self.assertEqual(len(list((self.q/'requests').iterdir())),count)
        with patch.object(Path,'glob',side_effect=AssertionError('poll scanned history')):
            self.assertIsNone(self.f.claim())
        other = c.active_for_file(self.q,'F11')
        c.save(self.q,dict(other,state='ok'))
        self.assertEqual(c.status(self.f.root,file_key='fixturefile')['id'],old['id'])
        self.assertEqual(self.f.claim()['id'],old['id'])

    def test_displaced_claim_remains_claimed_and_cannot_be_replayed(self):
        old, _ = self.old_queue(claimed=True,complete=True)
        restored = c.status(self.f.root,file_key='fixturefile')
        self.assertEqual(restored.get('claim_id'),old['claim_id'])
        self.assertIsNone(self.f.claim())
        wrong = dict(old,claim_id='f'*32)
        with self.assertRaises(ValueError):
            self.f.result(wrong)
        self.assertTrue(self.f.result(old)['accepted'])

    def test_expired_displaced_write_requires_scoped_recovery(self):
        old, _ = self.old_queue(claimed=True,complete=True)
        c.save(self.q,dict(old,operation='apply',deadline=time.time()-1))
        status=c.status(self.f.root,old['id'])
        self.assertEqual(status['state'],'uncertain')
        self.assertIn(old['id'],[r['id'] for r in status['uncertain_operations']])
        with self.assertRaisesRegex(ValueError,'uncertain'):
            self.f.enqueue(operation='apply')


if __name__ == '__main__':
    unittest.main()
