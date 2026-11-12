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


def text_pair_fixture(defect=None):
    candidate, frame, _ = fixture()
    candidate['fonts']['body'] = {'family': 'Hahmlet', 'style': 'Bold'}
    candidate['control_styles']['mobile'] = {}
    state = candidate['state_layouts']['mobile']['idle']
    state['product_buttons'] = {}
    state['layers'] = [
        {'id': 'capacity', 'kind': 'text', 'value': '45', 'x': 884.75, 'y': 448.28125, 'w': 38.125, 'h': 45,
         'size': 30, 'leading': 45, 'max_lines': 1, 'font': 'body', 'ink': 'ink'},
        {'id': 'unit', 'kind': 'text', 'value': ' 명', 'x': 922.875, 'y': 468.53125, 'w': 15.453125, 'h': 19.5,
         'size': 13, 'leading': 19.5, 'max_lines': 1, 'font': 'body', 'ink': 'ink'}]
    nodes = {KEY: frame}
    for layer, (width, height) in zip(state['layers'], [(39, 45), (16, 20)]):
        nodes[KEY + '.' + layer['id']] = {
            'id': layer['id'], 'parentId': 'screen', 'type': 'TEXT', 'x': layer['x'], 'y': layer['y'], 'width': width, 'height': height,
            'characters': layer['value'], 'fontName': candidate['fonts']['body'], 'fontSize': layer['size'],
            'lineHeight': {'unit': 'PIXELS', 'value': layer['leading']}, 'letterSpacing': {'unit': 'PIXELS', 'value': 0},
            'textAutoResize': 'HEIGHT', 'textAlignHorizontal': 'LEFT'}
    if defect:
        index = 0 if defect.startswith('first-') else 1
        source = state['layers'][index]
        node = nodes[KEY + '.' + source['id']]
        if defect.endswith('-x'):
            node['x'] += .25 if index == 0 else -.25
        elif defect.endswith('-y'):
            node['y'] += .25
        elif defect.endswith('-nonceil-width'):
            node['width'] += .125 if index == 0 else .25
        elif defect.endswith('-nonceil-height'):
            node['height'] += .25
        elif defect.endswith('-height-not-leading'):
            source['h'] -= .25
        elif defect.endswith('-multiline'):
            source['max_lines'] = 2
        elif defect.endswith('-unspecified'):
            source.pop('max_lines')
        elif defect == 'authored-overlap':
            state['layers'][0]['w'] += .25
        elif defect == 'wrapped-height':
            nodes[KEY + '.capacity']['height'] = 90
    return candidate, frame, nodes


class TextPairAllocationRoundingTests(unittest.TestCase):
    def test_existing_single_line_width_and_height_ceils_preserve_touching_source_texts(self):
        candidate, frame, nodes = text_pair_fixture()
        before = copy.deepcopy(nodes)
        self.assertEqual(findings(candidate, frame, nodes), [])
        self.assertEqual(nodes, before, 'text-pair admission must retain the raw native allocation ceils')

    def test_non_quantized_text_pair_collisions_still_fail(self):
        for defect in ('first-x', 'second-x', 'first-y', 'second-y', 'authored-overlap', 'wrapped-height',
                       'first-nonceil-width', 'second-nonceil-width', 'first-nonceil-height', 'second-nonceil-height',
                       'first-height-not-leading', 'second-height-not-leading', 'first-multiline', 'second-multiline',
                       'first-unspecified', 'second-unspecified'):
            candidate, frame, nodes = text_pair_fixture(defect)
            with self.subTest(defect=defect):
                self.assertIn('text-overlap', {finding['code'] for finding in findings(candidate, frame, nodes)})

    def test_text_pair_source_quality_remains_strict(self):
        candidate, _, _ = text_pair_fixture()
        layout = {'schema': 'figma-flow-authored-native-layout-v1', 'assets': {}, 'candidates': [candidate]}
        self.assertTrue(design_quality.evaluate(layout)['passed'])
        candidate['state_layouts']['mobile']['idle']['layers'][1]['x'] -= 1
        self.assertIn('text-overlap', {finding['code'] for finding in design_quality.evaluate(layout)['errors']})


if __name__ == '__main__':
    unittest.main()
