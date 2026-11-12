"""Conflict detail keeps observed values and the original plan hash.

Synthetic plugin responses are not live Figma evidence.
"""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_control as control


ROOT = Path(__file__).resolve().parents[1]
PLAN = 'a' * 64


def receipt():
    return {
        'schema': 'figma-flow-native-edit-receipt-v1',
        'status': 'rollback-conflict',
        'native_edit': {
            'plan_sha256': PLAN,
            'applied': False,
            'operation': 'apply',
            'operations': [{'node_id': '12:3', 'field': 'fontSize', 'before': 16, 'after': 18, 'observed': 20}],
        },
        'rollback_conflicts': [{'node_id': '12:3', 'field': 'fontSize', 'reason': 'Changed externally; not overwritten'}],
    }


class ConflictDetailTests(unittest.TestCase):
    def test_conflict_detail_keeps_observed_value_and_plan_hash(self):
        detail = getattr(control, 'conflict_detail', None)
        self.assertTrue(callable(detail), 'conflict detail must keep the observed value and plan hash')
        native = (ROOT / 'figma-bridge' / 'native_edit.js').read_text(encoding='utf-8')
        panel = (ROOT / 'panel-ui' / 'src' / 'GraphPanel.jsx').read_text(encoding='utf-8')
        self.assertIn('before:job.edit.before', native)
        self.assertNotIn('conflict-rerun', panel)
        self.assertNotIn('graph.rerun', panel)

        original = receipt()
        view = detail(original)
        self.assertEqual(view['plan_sha256'], PLAN)
        self.assertEqual(view['actions'], ['save-evidence', 'read-scope'])
        self.assertNotIn('rerun', view['actions'])
        self.assertNotIn('apply', view['actions'])
        row = view['conflicts'][0]
        self.assertEqual(row['target'], '12:3')
        self.assertEqual(row['field'], 'fontSize')
        self.assertEqual(row['before'], 16)
        self.assertEqual(row['after'], 18)
        self.assertEqual(row['observed'], 20)
        self.assertNotEqual(row['observed'], row['after'])
        self.assertEqual(row['rollback'], 'Changed externally; not overwritten')
        self.assertEqual(row['plan_sha256'], PLAN)
        self.assertEqual(original['native_edit']['operations'][0]['observed'], 20)
        self.assertNotIn('private failure text', json.dumps(view))

        missing = receipt()
        del missing['native_edit']['plan_sha256']
        with self.assertRaises(ValueError):
            detail(missing)
        unmatched = receipt()
        unmatched['rollback_conflicts'][0]['node_id'] = '99:9'
        with self.assertRaises(ValueError):
            detail(unmatched)
