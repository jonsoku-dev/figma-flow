"""Production importer preflight, using compiled source contracts and a no-write VM."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_bridge
from test_figma_bridge import design, selected_graph


RUNTIME = r'''
const fs = require('fs'), vm = require('vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
let creates = 0, fonts = 0;
const figma = {root: {children: []}, currentPage: {}, ui: {postMessage() {}}, showUI() {},
  loadFontAsync: async () => { fonts++; }, setCurrentPageAsync: async () => {},
  createPage() { creates++; throw Error('STOP_BEFORE_NATIVE_WRITE'); }};
const context = {figma, PAYLOAD: payload, __html__: ''};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
vm.runInContext('importDesign(false)', context).then(() => {
  process.stdout.write(JSON.stringify({creates, fonts, error: null}));
}, error => process.stdout.write(JSON.stringify({creates, fonts, error: String(error)})));
'''


class ProductionColorRuntimeTests(unittest.TestCase):
    def setUp(self):
        source = design()
        values = json.loads(json.dumps(figma_bridge.validate(source)))
        graph = selected_graph(source)
        for node in graph['nodes']:
            if node['type'] == 'screen':
                node['annotation'] = {'purpose': 'Read the reviewed content.', 'journey': 'Read and continue to the next screen.'}
                if node['id'] == 'SCR-ONE':
                    node['annotation']['first_action'] = 'ACT-GO'
        foundations = figma_bridge.production_contract(source, graph)
        self.payload = dict(source, variable_values=values, foundations=foundations,
                            selected_direction={'candidate_id': 'selected'}, source_sha256='a' * 64,
                            expected_native_handoff=figma_bridge.expected_handoff(source))

    def run_import(self, payload=None):
        result = subprocess.run(['node', '-e', RUNTIME, str(ROOT / 'figma-bridge/code.js')],
                                input=json.dumps(payload or self.payload), capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def denied(self):
        result = self.run_import()
        self.assertEqual(result['creates'], 0, result)
        self.assertEqual(result['fonts'], 0, result)
        self.assertIn('Invalid production color contract', result['error'])

    def test_compiled_color_and_actual_base_ink_fallback_are_admitted(self):
        role = self.payload['foundations']['roles'][0]
        self.assertIn({'key': 'title', 'field': 'fills'}, role['bindings'])
        result = self.run_import()
        self.assertEqual(result['creates'], 1, result)
        self.assertIn('STOP_BEFORE_NATIVE_WRITE', result['error'])

    def test_malformed_source_and_compiled_color_are_denied_before_any_write(self):
        original = copy.deepcopy(self.payload)
        cases = [('source', 'INVALID'), ('compiled', {'r': 2, 'g': 0, 'b': 0}),
                 ('compiled', {'g': 0, 'b': 0}), ('compiled', {'r': .1, 'g': .2, 'b': .3}),
                 ('compiled', {'r': 0, 'g': 0, 'b': 0, 'a': -1})]
        for kind, value in cases:
            self.payload = copy.deepcopy(original)
            if kind == 'source':
                self.payload['tokens']['color.brand']['value'] = value
            else:
                self.payload['variable_values']['color.brand'][1] = value
            with self.subTest(kind=kind, value=value):
                self.denied()

    def test_injected_unused_planned_color_cannot_claim_palette_or_fake_screen(self):
        self.payload['tokens']['color.unused'] = {'type': 'color', 'value': '#112233'}
        self.payload['variable_values']['color.unused'] = figma_bridge.variable_value(self.payload['tokens']['color.unused'])
        value = self.payload['variable_values']['color.unused'][1]
        role = {'kind': 'color', 'name': 'Unused accent', 'token': 'color/unused',
                'native_type': 'COLOR', 'native_value': value}
        self.payload['foundations']['roles'].append(role)
        for key in ['palette:0:button/primary', 'foundation-palette', 'design-note-board',
                    'component:button/primary', 'missing-screen', 'go']:
            role['bindings'] = [{'key': key, 'field': 'fills'}]
            with self.subTest(key=key):
                self.denied()
        role['bindings'] = []
        self.denied()

    def test_forged_consumer_or_role_value_cannot_replace_source_paints(self):
        role = self.payload['foundations']['roles'][0]
        role['bindings'] = [{'key': 'go', 'field': 'strokes'}]
        self.denied()
        role['bindings'] = [{'key': 'title', 'field': 'fills'}]
        role['native_value'] = {}
        self.denied()

    def test_color_alias_cycle_and_forged_compiled_type_are_denied(self):
        self.payload['tokens']['palette.blue']['alias'] = 'color.brand'
        self.denied()
        self.payload['tokens']['palette.blue'].pop('alias')
        self.payload['variable_values']['color.brand'][0] = 'FLOAT'
        self.denied()

    def test_no_fallback_when_every_actual_label_has_explicit_color(self):
        self.payload['tokens']['color.ink'] = {'type': 'color', 'value': '#000000'}
        self.payload['variable_values']['color.ink'] = figma_bridge.variable_value(self.payload['tokens']['color.ink'])
        ink = {'kind': 'color', 'name': 'Text ink', 'token': 'color/ink', 'native_type': 'COLOR',
               'native_value': self.payload['variable_values']['color.ink'][1],
               'bindings': [{'key': 'go/label', 'field': 'fills'}]}
        self.payload['foundations']['roles'].append(ink)
        self.payload['screens'] = [self.payload['screens'][0]]
        self.payload['screens'][0]['elements'] = [self.payload['screens'][0]['elements'][1]]
        self.payload['components']['button']['variants']['primary']['color'] = 'color.brand'
        self.denied()

    def test_technical_existing_import_stays_sealed(self):
        self.payload['technical_existing_only'] = True
        self.payload['tokens']['color.brand']['value'] = 'INVALID'
        result = self.run_import()
        self.assertEqual(result['creates'], 0)
        self.assertIn('Existing technical sync cannot author new UI', result['error'])


if __name__ == '__main__':
    unittest.main()
