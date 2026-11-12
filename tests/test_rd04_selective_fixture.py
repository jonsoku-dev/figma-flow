"""Pin partial application for two independent tokens and one alias bundle.

The fixture is not a live Figma readback.
"""
import inspect
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import graph_sync


ROOT = Path(__file__).resolve().parents[1]


class SelectiveSyncFixtureTests(unittest.TestCase):
    def test_two_independent_tokens_leave_the_third_and_keep_the_alias_bundle_whole(self):
        load = getattr(graph_sync, 'load_selective_sync_fixture', None)
        condition = getattr(graph_sync, 'selective_sync_condition', None)
        self.assertTrue(callable(load) and callable(condition), 'partial token selection must keep the unselected value and the alias bundle')
        for fn in (load, condition):
            text = inspect.getsource(fn)
            self.assertNotIn('import_values', text)
            self.assertNotIn('_atomic_write', text)

        raw = json.loads((ROOT / 'tests/fixtures/rd04/partial-apply.json').read_text(encoding='utf-8'))
        before = json.dumps(raw)
        loaded = load(ROOT)
        self.assertEqual(json.dumps(raw), before)
        self.assertEqual(raw['schema'], 'figma-flow-selective-sync-v1')
        self.assertEqual([item['key'] for item in raw['independent']], ['color/action', 'color/quiet', 'space/gap'])
        self.assertEqual(raw['selection'], ['color/action', 'color/quiet'])
        self.assertEqual(loaded['condition']['applied'], [
            {'key': 'color/action', 'value': '#0055ff'},
            {'key': 'color/quiet', 'value': '#8899aa'},
        ])
        self.assertEqual(loaded['condition']['preserved'], [{'key': 'space/gap', 'value': 8}])
        self.assertEqual(loaded['condition']['preserved'][0]['value'], raw['independent'][2]['before'])
        self.assertNotEqual(loaded['condition']['preserved'][0]['value'], raw['independent'][2]['after'])
        self.assertEqual(loaded['condition']['alias_bundle'], {
            'partial_allowed': False,
            'keys': ['type/body', 'type/size'],
            'targets': ['button.font', 'text.font'],
        })
        self.assertNotIn('space/gap', [item['key'] for item in loaded['condition']['applied']])
        with self.assertRaisesRegex(ValueError, 'partial alias bundle'):
            condition(raw, ['type/body'])
        with self.assertRaisesRegex(ValueError, 'empty selection'):
            condition(raw, [])
        whole = condition(raw, ['type/body', 'type/size'])
        self.assertEqual([item['key'] for item in whole['applied']], ['type/body', 'type/size'])
        self.assertFalse(whole['alias_bundle']['partial_allowed'])
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-04-selective-sync/tasks.md').read_text(encoding='utf-8')
        self.assertIn('load_selective_sync_fixture', tasks_doc)
        self.assertIn('space/gap', tasks_doc)
