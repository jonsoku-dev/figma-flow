"""Frozen RD02 input-boundary regressions; no Figma or host state required."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import design_directions
import figma_draft


def fixture():
    return {'layers': [{'id': 'leaf', 'kind': 'rect', 'x': 0, 'y': 0, 'w': 20, 'h': 20, 'fill': 'paper'}],
            'containers': [{'key': 'card', 'kind': 'frame', 'parent': None,
                            'children': ['leaf'], 'box': [0, 0, 100, 80]}]}


def authored(state):
    return {'assets': {}, 'candidates': [{'id': 'a', 'fonts': {'body': {'family': 'Inter', 'style': 'Regular'}},
            'colors': {'paper': '#FFFFFF'}, 'control_styles': {},
            'state_layouts': {'mobile': {'one': {'width': 390, 'height': 844, **state}}}}]}


class NativeLayoutBoundaryTests(unittest.TestCase):
    def test_actual_packet_validation_rejects_invalid_container_tree(self):
        state = fixture()
        self.assertEqual(figma_draft.layout_errors(authored(state)), [])
        cases = []
        for change in ({'children': ['missing']}, {'parent': 'missing'}, {'kind': 'unknown'},
                       {'box': [0, 0, 0, 10]}, {'box': [0, 0, float('nan'), 10]}):
            invalid = copy.deepcopy(state)
            invalid['containers'][0].update(change)
            cases.append(invalid)
        for invalid in cases:
            with self.subTest(container=invalid['containers'][0]):
                self.assertTrue(figma_draft.layout_errors(authored(invalid)),
                                'make_packet calls layout_errors: malformed containers must fail at that actual boundary')

    def test_normalizer_rejects_nonfinite_and_invalid_dimensions(self):
        for box in ([0, 0, 0, 10], [0, 0, -1, 10], [0, 0, 10, 0], [float('inf'), 0, 10, 10], [0, 0, float('nan'), 10]):
            state = fixture()
            state['containers'][0]['box'] = box
            with self.subTest(box=box), self.assertRaises(ValueError):
                design_directions.normalize_layer_containers(state)

    def test_normalizer_rejects_invalid_gap_and_padding(self):
        for field, value in [('gap', float('inf')), ('gap', float('nan')), ('gap', True),
                             ('padding', [-1, 0, 0, 0]), ('padding', [0, '1', 0, 0]),
                             ('padding', [0, float('nan'), 0, 0]), ('padding', [0, True, 0, 0])]:
            state = fixture()
            state['containers'][0] = {'key': 'flow', 'kind': 'auto-layout', 'parent': None, 'children': ['leaf'],
                'layout': {'direction': 'VERTICAL', 'gap': 4, 'padding': [0, 0, 0, 0], 'width': 'fixed', 'height': 'hug'}}
            state['containers'][0]['layout'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                design_directions.normalize_layer_containers(state)

    def test_nested_groups_and_frames_are_valid_and_parent_ordered(self):
        state = fixture()
        state['containers'][0]['parent'] = 'inner'
        state['containers'] += [{'key': 'outer', 'kind': 'group', 'children': ['inner']},
                                {'key': 'inner', 'kind': 'group', 'parent': 'outer', 'children': ['card']}]
        normalized = design_directions.normalize_layer_containers(state)
        self.assertEqual([item['key'] for item in normalized['containers']], ['outer', 'inner', 'card'])
        self.assertEqual(state['containers'][0]['key'], 'card', 'normalization must not mutate source')


if __name__ == '__main__':
    unittest.main()
