"""Stable change identities serialize apart from selection order.

Synthetic fixture rows are not a live Figma apply.
"""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import graph_sync


ROOT = Path(__file__).resolve().parents[1]


def token_identity(key):
    body = json.dumps({'key': key, 'kind': 'token'}, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(body).hexdigest()


class SelectionIdentityTests(unittest.TestCase):
    def test_stable_identity_serializes_the_same_bundle_for_either_order(self):
        serialize = getattr(graph_sync, 'serialize_selection', None)
        self.assertTrue(callable(serialize), 'stable change identity must serialize with its selection bundle')
        self.assertNotIn('import_values', inspect.getsource(serialize))
        self.assertNotIn('_atomic_write', inspect.getsource(serialize))

        raw = json.loads((ROOT / 'tests/fixtures/rd04/partial-apply.json').read_text(encoding='utf-8'))
        forward = serialize(raw, ['color/action', 'color/quiet'])
        reverse = serialize(raw, ['color/quiet', 'color/action'])
        self.assertEqual(forward['serialized'], reverse['serialized'])
        document = forward['document']
        self.assertEqual(set(document), {'schema', 'plan_sha256', 'changes'})
        self.assertEqual(document['schema'], 'figma-flow-selection-v1')
        self.assertEqual(document['plan_sha256'], hashlib.sha256(json.dumps([
            {'bundle': row['bundle'], 'identity': row['identity'], 'key': row['key'], 'kind': row['kind']}
            for row in document['changes']
        ], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        by_key = {row['key']: row for row in document['changes']}
        self.assertEqual(by_key['color/action']['identity'], token_identity('color/action'))
        self.assertEqual(by_key['color/quiet']['identity'], token_identity('color/quiet'))
        self.assertNotEqual(by_key['color/action']['identity'], by_key['color/quiet']['identity'])
        self.assertTrue(by_key['color/action']['selected'] and by_key['color/quiet']['selected'])
        self.assertFalse(by_key['space/gap']['selected'])
        self.assertIsNone(by_key['space/gap']['bundle'])
        self.assertEqual(by_key['type/body']['bundle'], by_key['type/size']['bundle'])
        self.assertNotEqual(by_key['type/body']['bundle'], by_key['type/body']['identity'])
        self.assertFalse(by_key['type/body']['selected'] or by_key['type/size']['selected'])
        self.assertEqual(forward['serialized'], json.dumps(document, sort_keys=True, separators=(',', ':')))
        bundle = serialize(raw, ['type/size', 'type/body'])
        self.assertEqual(bundle['document']['plan_sha256'], document['plan_sha256'])
        bundled = {row['key']: row for row in bundle['document']['changes']}
        self.assertTrue(bundled['type/body']['selected'] and bundled['type/size']['selected'])
        self.assertFalse(any(bundled[key]['selected'] for key in ('color/action', 'color/quiet', 'space/gap')))
        with self.assertRaisesRegex(ValueError, 'partial alias bundle'):
            serialize(raw, ['type/body'])
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-04-selective-sync/tasks.md').read_text(encoding='utf-8')
        self.assertIn('serialize_selection', tasks_doc)
        self.assertIn('plan_sha256', tasks_doc)
