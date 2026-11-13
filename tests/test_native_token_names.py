import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from graph_sync import token_native_names


class NativeTokenNamesTests(unittest.TestCase):
    def test_grouping_keeps_graph_keys_and_rejects_colliding_native_paths(self):
        design = {'id': 'booking', 'tokens': {'color.action.primary': {}}}
        graph = {'design_system': design}
        self.assertEqual(token_native_names(graph), ('ssot/booking', {
            'color.action.primary': 'ssot/booking/color/action/primary'}))
        design['tokens']['color/action/primary'] = {}
        with self.assertRaisesRegex(ValueError, 'duplicate native token names'):
            token_native_names(graph)
