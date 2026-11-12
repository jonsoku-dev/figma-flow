"""Frozen scroll admission oracle. Getter-shaped fixtures do not prove live Figma behavior."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import design_directions
import figma_draft


KEY = 'a.mobile.idle'


def fixture(scroll='horizontal', box=(800, 30, 80, 20)):
    layer = dict(id='cell', kind='rect', x=box[0], y=box[1], w=box[2], h=box[3], fill='paper')
    container = dict(key='table', kind='frame', parent=None, children=['cell'],
                     box=[10, 10, 370, 300], clip=True, scroll=scroll)
    state = dict(width=390, height=800, layers=[layer], containers=[container], control_boxes={})
    candidate = dict(id='a', fonts={'body': {'family': 'Inter', 'style': 'Regular'}}, colors={'paper': '#FFFFFF'},
                     prototype={'states': [{'id': 'idle'}], 'bindings': []}, action_notes={}, action_labels={},
                     control_styles={'mobile': {}}, state_layouts={'mobile': {'idle': state}})
    frame = dict(id='screen', type='FRAME', parentId='page', x=0, y=0, width=390, height=800, clipsContent=True)
    nodes = {KEY: frame,
             KEY + '.table': dict(id='table', type='FRAME', parentId='screen', x=10, y=10,
                                  width=370, height=300, clipsContent=True, overflowDirection=scroll.upper()),
             KEY + '.cell': dict(id='cell', type='RECTANGLE', parentId='table', x=box[0]-10, y=box[1]-10,
                                 width=box[2], height=box[3])}
    return candidate, frame, nodes


def findings(candidate, frame, nodes):
    return figma_draft.native_screen_findings(candidate, 'mobile', 'idle', frame, nodes, page_id='page')


class ScrollClipTests(unittest.TestCase):
    def test_only_explicit_enum_on_clipped_frame_is_admitted_at_both_boundaries(self):
        candidate, _, _ = fixture()
        state = candidate['state_layouts']['mobile']['idle']
        for scroll in ('none', 'horizontal', 'vertical', 'both'):
            with self.subTest(scroll=scroll):
                state['containers'][0]['scroll'] = scroll
                normalized = design_directions.normalize_layer_containers(state)
                self.assertEqual(normalized['containers'][0]['scroll'], scroll)
                self.assertEqual(figma_draft.layout_errors({'candidates': [candidate]}), [])
        for change in ({'scroll': 'HORIZONTAL'}, {'scroll': 'diagonal'}, {'scroll': None}, {'scroll': True},
                       {'scroll': 'horizontal', 'clip': False}, {'scroll': 'vertical', 'clip': None},
                       {'kind': 'group', 'scroll': 'horizontal'}, {'kind': 'auto-layout', 'scroll': 'both',
                        'layout': {'direction': 'VERTICAL', 'gap': 0, 'padding': [0, 0, 0, 0], 'width': 'fixed', 'height': 'fixed'}}):
            changed = copy.deepcopy(state)
            changed['containers'][0].update(change)
            if change.get('kind') == 'group':
                changed['containers'][0].pop('clip')
                changed['containers'][0].pop('box')
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    design_directions.normalize_layer_containers(changed)
                invalid = copy.deepcopy(candidate)
                invalid['state_layouts']['mobile']['idle'] = changed
                self.assertTrue(figma_draft.layout_errors({'candidates': [invalid]}))
        changed = copy.deepcopy(state)
        changed['containers'][0].pop('clip')
        changed['containers'][0]['scroll'] = 'horizontal'
        with self.assertRaises(ValueError):
            design_directions.normalize_layer_containers(changed)

    def test_declared_axes_admit_real_overflow_without_rewriting_raw_geometry(self):
        for scroll, box in [('horizontal', (800, 30, 80, 20)), ('vertical', (30, 900, 80, 20)),
                            ('both', (800, 900, 80, 20))]:
            candidate, frame, nodes = fixture(scroll, box)
            before = copy.deepcopy(nodes)
            with self.subTest(scroll=scroll):
                self.assertEqual(findings(candidate, frame, nodes), [])
                self.assertEqual(nodes, before, 'raw native coordinates must never be clamped to the viewport')
                nodes[KEY + '.cell']['x'] += 10
                self.assertIn('geometry-drift', {row['code'] for row in findings(candidate, frame, nodes)})

    def test_root_clip_ordinary_frame_wrong_axis_and_unowned_leaf_still_fail(self):
        for mode in ('root-only', 'ordinary-frame', 'none', 'wrong-axis', 'unowned-leaf'):
            candidate, frame, nodes = fixture()
            state = candidate['state_layouts']['mobile']['idle']
            if mode == 'root-only':
                state['containers'] = []
                nodes.pop(KEY + '.table')
                nodes[KEY + '.cell'].update(parentId='screen', x=800, y=30)
                frame['overflowDirection'] = 'HORIZONTAL'
            elif mode in ('ordinary-frame', 'none'):
                state['containers'][0].pop('scroll')
                nodes[KEY + '.table']['overflowDirection'] = 'NONE'
                if mode == 'none':
                    state['containers'][0]['scroll'] = 'none'
            elif mode == 'wrong-axis':
                state['containers'][0]['scroll'] = 'vertical'
                nodes[KEY + '.table']['overflowDirection'] = 'VERTICAL'
            else:
                state['containers'][0]['children'] = ['other']
                state['layers'].append(dict(id='other', kind='rect', x=20, y=20, w=10, h=10, fill='paper'))
                nodes[KEY + '.other'] = dict(id='other', type='RECTANGLE', parentId='table', x=10, y=10, width=10, height=10)
                nodes[KEY + '.cell'].update(parentId='screen', x=800, y=30)
            with self.subTest(mode=mode):
                self.assertIn('off-canvas', {row['code'] for row in findings(candidate, frame, nodes)})

    def test_native_clip_and_overflow_drift_fail_even_when_leaf_fits_screen(self):
        for field, value in [('clipsContent', False), ('overflowDirection', 'NONE'),
                             ('overflowDirection', 'VERTICAL'), ('overflowDirection', None), ('type', 'GROUP')]:
            candidate, frame, nodes = fixture(box=(30, 30, 80, 20))
            nodes[KEY + '.table'][field] = value
            with self.subTest(field=field, value=value):
                self.assertTrue(findings(candidate, frame, nodes), 'native scroll getters must match declaration')
        candidate, frame, nodes = fixture(box=(30, 30, 80, 20))
        nodes[KEY + '.table'].pop('overflowDirection')
        self.assertTrue(findings(candidate, frame, nodes), 'missing getter must fail closed')

    def test_nested_scrollers_compose_axes_and_non_scroll_clip_cannot_be_bypassed(self):
        candidate, frame, nodes = fixture('vertical', (800, 900, 80, 20))
        state = candidate['state_layouts']['mobile']['idle']
        state['containers'][0]['children'] = ['inner']
        state['containers'].append(dict(key='inner', kind='frame', parent='table', children=['cell'],
                                        box=[0, 0, 370, 1000], clip=True, scroll='horizontal'))
        nodes[KEY + '.inner'] = dict(id='inner', type='FRAME', parentId='table', x=0, y=0,
                                    width=370, height=1000, clipsContent=True, overflowDirection='HORIZONTAL')
        nodes[KEY + '.cell']['parentId'] = 'inner'
        self.assertEqual(findings(candidate, frame, nodes), [])
        original_candidate, original_nodes = copy.deepcopy(candidate), copy.deepcopy(nodes)
        state['containers'][0]['scroll'] = 'horizontal'
        state['containers'][1]['scroll'] = 'vertical'
        nodes[KEY + '.table']['overflowDirection'] = 'HORIZONTAL'
        nodes[KEY + '.inner']['overflowDirection'] = 'VERTICAL'
        self.assertTrue(findings(candidate, frame, nodes), 'axis permissions cannot be unioned across intervening clips')
        candidate, nodes = original_candidate, original_nodes
        candidate['state_layouts']['mobile']['idle']['containers'][1].pop('scroll')
        nodes[KEY + '.inner']['overflowDirection'] = 'NONE'
        self.assertTrue(findings(candidate, frame, nodes), 'outer scroll must not excuse a nested ordinary clip')


if __name__ == '__main__':
    unittest.main()
