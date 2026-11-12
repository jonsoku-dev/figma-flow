"""Frozen normal quality-entrypoint oracle; authored admission is separate from native proof."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import design_quality


def fixture(scroll='horizontal', x=800, y=30):
    state = {'width': 390, 'height': 800, 'bg': 'paper', 'control_boxes': {},
             'layers': [{'id': 'cell', 'kind': 'rect', 'x': x, 'y': y, 'w': 80, 'h': 20,
                         'fill': 'ink', 'role': 'surface'}],
             'containers': [{'key': 'table', 'kind': 'frame', 'parent': None, 'children': ['cell'],
                             'box': [10, 10, 370, 300], 'clip': True, 'scroll': scroll}]}
    return {'schema': 'figma-flow-authored-native-production-v1', 'assets': {},
            'candidates': [{'id': 'a', 'title': 'Table', 'colors': {'paper': '#FFFFFF', 'ink': '#111111'},
                            'fonts': {'body': {'family': 'No Such Family', 'style': 'Regular'}},
                            'control_styles': {'mobile': {}}, 'state_layouts': {'mobile': {'idle': state}}}]}


def state_of(layout):
    return layout['candidates'][0]['state_layouts']['mobile']['idle']


def audit(layout):
    # quality and prepare-native-review both call this real file-based entrypoint.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'native-layout.json'
        path.write_text(json.dumps(layout))
        before = path.read_bytes()
        report = design_quality.run(path)
        if path.read_bytes() != before:
            raise AssertionError('quality audit rewrote raw authored geometry')
        return report


def codes(report):
    return {finding['code'] for finding in report['errors']}


def text(layer_id, x=800, y=60, size=16):
    return {'id': layer_id, 'kind': 'text', 'value': 'Cell', 'x': x, 'y': y, 'w': 120, 'h': 40,
            'size': size, 'leading': 24, 'font': 'body', 'ink': 'ink'}


class ScrollQualityTests(unittest.TestCase):
    def test_normal_quality_entrypoint_accepts_only_declared_scroll_axes_without_clamping(self):
        for schema in ('figma-flow-authored-native-layout-v1', 'figma-flow-authored-native-production-v1'):
            for scroll, x, y in [('horizontal', 800, 30), ('vertical', 30, 900), ('both', 800, 900)]:
                layout = fixture(scroll, x, y)
                layout['schema'] = schema
                before = copy.deepcopy(layout)
                with self.subTest(schema=schema, scroll=scroll):
                    report = audit(layout)
                    self.assertTrue(report['passed'], report['errors'])
                    self.assertEqual(layout, before)
                    self.assertEqual(state_of(layout)['layers'][0]['x'], x)
                    self.assertEqual(state_of(layout)['layers'][0]['y'], y)

    def test_legitimate_scroll_text_is_admitted_and_an_in_frame_fixture_is_clean(self):
        self.assertTrue(audit(fixture(x=30))['passed'])
        layout = fixture()
        state = state_of(layout)
        state['layers'].append(text('label'))
        state['containers'][0]['children'].append('label')
        before = copy.deepcopy(layout)
        report = audit(layout)
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(layout, before)

    def test_root_clip_ordinary_clip_wrong_axis_and_unowned_content_remain_blocking(self):
        for mode in ('root-clip', 'ordinary-clip', 'none', 'wrong-axis', 'unowned', 'clip-false'):
            layout = fixture()
            state = state_of(layout)
            if mode == 'root-clip':
                state['containers'] = []
                state.update(clip=True, scroll='horizontal')
            elif mode == 'ordinary-clip':
                state['containers'][0].pop('scroll')
            elif mode == 'none':
                state['containers'][0]['scroll'] = 'none'
            elif mode == 'wrong-axis':
                state['containers'][0]['scroll'] = 'vertical'
            elif mode == 'clip-false':
                state['containers'][0]['clip'] = False
            else:
                state['containers'][0]['children'] = ['other']
                state['layers'].append({'id': 'other', 'kind': 'rect', 'x': 30, 'y': 30,
                                        'w': 20, 'h': 20, 'fill': 'ink', 'role': 'surface'})
            with self.subTest(mode=mode):
                self.assertIn('off-canvas', codes(audit(layout)))

    def test_nested_scroll_axes_compose_in_order_and_intervening_clip_cannot_be_bypassed(self):
        layout = fixture('vertical', 800, 900)
        state = state_of(layout)
        state['containers'][0]['children'] = ['inner']
        state['containers'].append({'key': 'inner', 'kind': 'frame', 'parent': 'table', 'children': ['cell'],
                                    'box': [0, 0, 370, 1000], 'clip': True, 'scroll': 'horizontal'})
        self.assertTrue(audit(layout)['passed'], 'horizontal inner plus vertical outer is legitimate scroll content')
        for mode in ('ordinary-inner', 'wrong-inner-axis'):
            changed = copy.deepcopy(layout)
            outer, inner = state_of(changed)['containers']
            if mode == 'ordinary-inner':
                inner.pop('scroll')
            else:
                outer['scroll'], inner['scroll'] = 'horizontal', 'vertical'
            with self.subTest(mode=mode):
                self.assertIn('off-canvas', codes(audit(changed)))

    def test_scroll_keeps_text_overlap_tiny_text_contrast_and_control_checks(self):
        for defect, expected in [('text-overlap', 'text-overlap'), ('tiny-text', 'tiny-text'),
                                 ('contrast', 'contrast'), ('control-size', 'control-size'),
                                 ('control-overlap', 'control-text-overlap')]:
            layout = fixture()
            state = state_of(layout)
            state['layers'].append(text('label'))
            state['containers'][0]['children'].append('label')
            if defect == 'text-overlap':
                state['layers'].append(text('duplicate'))
                state['containers'][0]['children'].append('duplicate')
            elif defect == 'tiny-text':
                state['layers'][-1]['size'] = 8
            elif defect == 'contrast':
                state['layers'][-1]['ink'] = 'paper'
            else:
                state['control_boxes']['action'] = [800, 60 if defect == 'control-overlap' else 130,
                                                     120 if defect == 'control-overlap' else 20, 44 if defect == 'control-overlap' else 20]
                state['containers'][0]['children'].append('action')
            with self.subTest(defect=defect):
                self.assertIn(expected, codes(audit(layout)))


if __name__ == '__main__':
    unittest.main()
