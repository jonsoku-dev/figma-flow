"""Frozen native line-box oracle; redacted geometry from the native fractional-leading failure."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import design_quality
import figma_draft

KEY = 'app.mobile.idle'
LEADING = 23.390625


def fixture():
    layer = {'id': 'policy', 'kind': 'text', 'value': 'Policy', 'x': 40, 'y': 153, 'w': 602,
             'h': LEADING, 'size': 13, 'leading': LEADING, 'max_lines': 1, 'font': 'body', 'ink': 'ink'}
    state = {'width': 1200, 'height': 800, 'bg': 'paper', 'layers': [layer], 'control_boxes': {},
             'product_buttons': {'open': {'box': [40, 176.390625, 64.21875, 44], 'variant': 'Primary', 'label': 'Open'}}}
    font = {'family': 'Inter', 'style': 'Regular'}
    style = {'fontSize': 14, 'leading': 20, 'paddingX': 8, 'paddingY': 8, 'radius': 4}
    candidate = {'id': 'app', 'fonts': {'body': font}, 'colors': {'paper': '#FFFFFF', 'ink': '#111111'},
                 'prototype': {'states': [{'id': 'idle'}], 'bindings': []}, 'action_notes': {}, 'action_labels': {},
                 'control_styles': {'mobile': {'Primary': style}}, 'state_layouts': {'mobile': {'idle': state}}}
    frame = {'id': 'screen', 'parentId': 'page', 'type': 'FRAME', 'x': 0, 'y': 0, 'width': 1200, 'height': 800}
    nodes = {KEY: frame, 'app.mobile.component.Primary': {'id': 'main', 'type': 'COMPONENT'},
             KEY + '.policy': {'id': 'policy', 'parentId': 'screen', 'type': 'TEXT', 'x': 40, 'y': 153, 'width': 602, 'height': 24,
                               'characters': 'Policy', 'fontName': font, 'fontSize': 13, 'lineHeight': {'unit': 'PIXELS', 'value': LEADING},
                               'letterSpacing': {'unit': 'PIXELS', 'value': 0}, 'textAutoResize': 'HEIGHT', 'textAlignHorizontal': 'LEFT'},
             KEY + '.open': {'id': 'open', 'parentId': 'screen', 'type': 'INSTANCE', 'mainComponentId': 'main',
                             'x': 40, 'y': 176.390625, 'width': 64.21875, 'height': 44, 'cornerRadius': 4, 'reactions': [],
                             'paddingLeft': 8, 'paddingRight': 8, 'paddingTop': 8, 'paddingBottom': 8},
             KEY + '.open.label': {'id': 'label', 'parentId': 'open', 'type': 'TEXT', 'x': 8, 'y': 12, 'width': 48.21875, 'height': 20,
                                   'characters': 'Open', 'fontName': font, 'fontSize': 14, 'lineHeight': {'unit': 'PIXELS', 'value': 20},
                                   'letterSpacing': {'unit': 'PIXELS', 'value': 0}, 'textAutoResize': 'HEIGHT', 'textAlignHorizontal': 'CENTER'}}
    return candidate, frame, nodes


def findings(candidate, frame, nodes):
    return figma_draft.native_screen_findings(candidate, 'mobile', 'idle', frame, nodes, page_id='page')


def mutate(candidate, nodes, defect):
    state = candidate['state_layouts']['mobile']['idle']
    layer = state['layers'][0]
    text = nodes[KEY + '.policy']
    control = nodes[KEY + '.open']
    if defect in ('control-up', 'control-down'):
        control['y'] += -.25 if defect == 'control-up' else .25
    elif defect == 'authored-overlap':
        state['product_buttons']['open']['box'][1] -= .25
        control['y'] -= .25
    elif defect == 'two-lines':
        text['height'] = 48
    elif defect == 'height-not-leading':
        layer['h'] = 23.5
        state['product_buttons']['open']['box'][1] = control['y'] = layer['y'] + layer['h']
    elif defect in ('text-width', 'text-x', 'text-y'):
        text[{'text-width': 'width', 'text-x': 'x', 'text-y': 'y'}[defect]] += .25
    elif defect == 'not-ceil':
        text['height'] = 24.25
    elif defect == 'multiple-allowed-lines':
        layer['max_lines'] = 2
    elif defect == 'unspecified-lines':
        layer.pop('max_lines')


class LineboxRoundingTests(unittest.TestCase):
    def test_only_single_line_native_height_ceil_may_touch_control_allocation(self):
        candidate, frame, nodes = fixture()
        before = copy.deepcopy(nodes)
        self.assertEqual(findings(candidate, frame, nodes), [])
        self.assertEqual(nodes, before, 'native validation must not clamp or rewrite raw text/control evidence')

    def test_non_rounding_collisions_still_fail_even_when_drift_is_below_one_pixel(self):
        for defect in ('control-up', 'control-down', 'authored-overlap', 'two-lines', 'height-not-leading',
                       'text-width', 'text-x', 'text-y', 'not-ceil', 'multiple-allowed-lines', 'unspecified-lines'):
            candidate, frame, nodes = fixture()
            mutate(candidate, nodes, defect)
            with self.subTest(defect=defect):
                self.assertIn('control-text-overlap', {finding['code'] for finding in findings(candidate, frame, nodes)})

    def test_authoring_quality_still_rejects_source_overlap(self):
        candidate, _, nodes = fixture()
        layout = {'schema': 'figma-flow-authored-native-layout-v1', 'assets': {}, 'candidates': [candidate]}
        self.assertTrue(design_quality.evaluate(layout)['passed'])
        mutate(candidate, nodes, 'authored-overlap')
        self.assertIn('control-text-overlap', {finding['code'] for finding in design_quality.evaluate(layout)['errors']})


if __name__ == '__main__':
    unittest.main()
