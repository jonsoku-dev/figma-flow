import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import sync_figma_tokens as sync
from design_system import compile_design
from figma_bridge import variable_value


def fixture_export(resolved, digest, tag='main'):
    """Simulated data exercises offline planning, never live Figma provenance."""
    variables = []
    for path, token in resolved['tokens'].items():
        kind, value = variable_value(token)
        variables.append({'id': tag + ':variable:' + path, 'semantic_id': path,
                          'name': path.replace('.', '/'), 'resolvedType': kind,
                          'variableCollectionId': tag + ':collection', 'valuesByMode': {'default':
                              {'type': 'VARIABLE_ALIAS', 'id': tag + ':variable:' + token['alias']} if token['alias'] else value}})
    return {'format': 'figma-flow-readback-v1', 'evidence': 'simulated-local-fixture-not-live',
            'pages': [{'id': tag + ':page', 'source_sha256': digest,
                       'declared_metadata': {'collection_id': tag + ':collection'},
                       'children': [{'id': tag + ':screen', 'name': 'Original', 'children': []}]}],
            'variables': variables,
            'collections': [{'id': tag + ':collection', 'defaultModeId': 'default',
                             'modes': [{'modeId': 'default', 'name': 'Mode 1'}]}]}


class SyncFigmaTokenTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.design = {'version': 1, 'tokens': {
            'palette': {'$type': 'color', 'blue': {'$value': '#12345680'}},
            'semantic': {'brand': {'$type': 'color', '$value': '{palette.blue}'},
                         'nested': {'$type': 'color', '$value': '{semantic.brand}'}},
            'space': {'$type': 'dimension', 'card': {'$value': '1rem'}},
            'font': {'$type': 'fontFamily', '$value': 'Arial'},
            'orphan': {'$type': 'number', '$value': 1}},
            'components': {'card': {'variants': {'primary': {'background': 'semantic.nested', 'padding': 'space.card'},
                                                'unused': {'background': 'palette.blue'},
                                                'other': {'font-family': 'font'}}}},
            'screens': [{'id': 'S', 'title': 'Start', 'trace': ['req'], 'elements': [
                {'kind': 'component', 'component': 'card', 'variant': 'primary', 'text': 'Card'}]},
                {'id': 'T', 'title': 'End', 'trace': ['req'], 'elements': [{'kind': 'text', 'text': 'End'}]}]}
        self.graph = {'version': 1, 'nodes': [{'id': name, 'type': kind, 'title': name, 'status': 'observed'}
                                            for name, kind in [('req', 'requirement'), ('S', 'screen'), ('T', 'screen')]],
                      'edges': [{'from': 'req', 'to': screen, 'type': 'appears on'} for screen in ('S', 'T')]}
        self.reset_exports()

    def write(self, name, value):
        path = self.base / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def reset_exports(self):
        self.resolved = compile_design(self.design)
        self.write('resolved.json', self.resolved)
        digest = hashlib.sha256((self.base / 'resolved.json').read_bytes()).hexdigest()
        self.before = fixture_export(self.resolved, digest)
        self.after = copy.deepcopy(self.before)

    def change(self, path, value, export=None):
        export = self.after if export is None else export
        next(variable for variable in export['variables'] if variable['semantic_id'] == path)['valuesByMode']['default'] = value

    def run_sync(self):
        self.write('design.json', self.design)
        self.write('resolved.json', self.resolved)
        self.write('graph.json', self.graph)
        self.write('before.json', self.before)
        self.write('after.json', self.after)
        return sync.sync_tokens(*(self.base / name for name in ('design.json', 'resolved.json', 'before.json', 'after.json')),
                                'main:page', self.base / 'graph.json', self.base / 'out')

    def test_root_edit_keeps_semantic_aliases_and_exact_graph_consumers(self):
        self.change('palette.blue', {'r': 1, 'g': 0, 'b': 0, 'a': 1})
        report = self.run_sync()
        revised = json.loads((self.base / 'out/design.json').read_text())
        self.assertEqual(revised['tokens']['palette']['blue']['$value'], '#ff0000')
        self.assertEqual(revised['tokens']['semantic'], self.design['tokens']['semantic'])
        self.assertEqual(report['changed_roots'], ['palette.blue'])
        self.assertEqual(report['inherited_aliases'], ['semantic.brand', 'semantic.nested'])
        self.assertEqual([(item['variant'], item['declared_screen_ids']) for item in report['variants']], [('primary', ['S']), ('unused', [])])
        self.assertEqual([item['screen_id'] for item in report['screens']], ['S'])
        self.assertEqual(len(report['screens'][0]['paths'][0]['node_ids']), 5)
        self.assertEqual(report['screens'][0]['paths'][0]['root'], 'palette.blue')
        css = (self.base / 'out/assets/tokens.css').read_text()
        self.assertIn('--palette-blue: #ff0000;', css)
        self.assertIn('--semantic-brand: var(--palette-blue);', css)
        self.assertEqual(json.loads((self.base / 'design.json').read_text()), self.design)
        self.assertEqual(report['pins']['resolved']['sha256'], hashlib.sha256((self.base / 'resolved.json').read_bytes()).hexdigest())
        dependencies = self.base / 'out/dependencies.json'
        self.assertEqual(report['dependency_graph']['sha256'], hashlib.sha256(dependencies.read_bytes()).hexdigest())
        graph = json.loads(dependencies.read_text())
        self.assertEqual(graph['design_system']['inputs']['design']['sha256'], report['pins']['design']['sha256'])
        edges = {(edge['from'], edge['to']) for edge in graph['edges']}
        for screen in report['screens']:
            for path in screen['paths']:
                self.assertTrue(all(pair in edges for pair in zip(path['node_ids'], path['node_ids'][1:])))

    def test_real_native_float32_color_exports_round_trip_without_false_edits(self):
        # Exact before/after channels observed in the actual 2:77 readbacks.
        self.design['tokens']['palette']['blue']['$value'] = '#425cc7'
        self.reset_exports()
        self.change('palette.blue', {'r': 0.25882354378700256, 'g': 0.3607843220233917,
                                     'b': 0.7803921699523926, 'a': 1}, self.before)
        self.after = copy.deepcopy(self.before)
        self.assertTrue(sync.same('color', variable_value(self.resolved['tokens']['palette.blue'])[1],
                                  next(item for item in self.before['variables'] if item['semantic_id'] == 'palette.blue')['valuesByMode']['default']))
        self.change('palette.blue', {'r': 0.0784313753247261, 'g': 0.4431372582912445,
                                     'b': 0.3686274588108063, 'a': 1})
        report = self.run_sync()
        self.assertEqual(report['changed_roots'], ['palette.blue'])
        self.assertEqual(report['changes'][0]['after'], '#14715e')
        with self.assertRaisesRegex(ValueError, 'round-trip'):
            sync.same('color', {'r': 0.0784313753247261 + 1e-10, 'g': 0, 'b': 0}, {'r': 0, 'g': 0, 'b': 0})

    def test_no_change_preserves_structured_values_and_rem(self):
        self.design['tokens']['palette']['blue']['$value'] = {'colorSpace': 'srgb', 'components': [18/255, 52/255, 86/255], 'alpha': 128/255}
        self.design['tokens']['space']['card']['$value'] = {'value': 1, 'unit': 'rem'}
        self.reset_exports()
        report = self.run_sync()
        self.assertEqual(report['changed_roots'], [])
        self.assertEqual(report['variants'], [])
        self.assertEqual(json.loads((self.base / 'out/design.json').read_text()), self.design)

    def test_rem_number_font_and_alpha_round_trip(self):
        self.change('space.card', 20)
        self.change('orphan', -2.75)
        self.change('font', 'Inter')
        self.change('palette.blue', {'r': 0, 'g': 1, 'b': 0, 'a': 0})
        report = self.run_sync()
        values = {item['token']: item['after'] for item in report['changes']}
        self.assertEqual(values, {'space.card': '1.25rem', 'orphan': -2.75, 'font': 'Inter', 'palette.blue': '#00ff0000'})
        self.assertNotIn('T', [screen['screen_id'] for screen in report['screens']])

    def test_multi_page_selects_own_collection_and_reports_unrelated_edits(self):
        other = fixture_export(self.resolved, '0' * 64, 'other')
        for key in ('pages', 'variables', 'collections'):
            self.before[key] += copy.deepcopy(other[key])
            self.after[key] += copy.deepcopy(other[key])
        self.after['pages'][0]['children'][0]['name'] = 'Unrelated layout/text edit'
        self.after['variables'][-1]['valuesByMode']['default'] = 999
        self.change('space.card', 24)
        report = self.run_sync()
        self.assertEqual(report['changed_roots'], ['space.card'])
        self.assertTrue(report['ignored_changes']['selected_page_paths'])
        self.assertTrue(report['ignored_changes']['outside_selected_collection_paths'])

    def test_stale_compiled_source_and_stale_baseline_fail_without_outputs(self):
        self.design['tokens']['orphan']['$value'] = 2
        with self.assertRaisesRegex(ValueError, 'does not compile exactly'):
            self.run_sync()
        self.design['tokens']['orphan']['$value'] = 1
        self.change('space.card', 30, self.before)
        with self.assertRaisesRegex(ValueError, 'stale baseline'):
            self.run_sync()
        self.assertFalse((self.base / 'out').exists())

    def test_rejects_stamp_page_alias_modes_identity_and_token_drift(self):
        mutations = [
            ('source', lambda: self.after['pages'][0].update(source_sha256='0' * 64), 'stale/wrong'),
            ('page', lambda: self.after['pages'][0].update(id='wrong'), 'selected page'),
            ('alias', lambda: self.change('semantic.brand', {'r': 1, 'g': 0, 'b': 0}), 'alias topology'),
            ('root alias', lambda: self.change('space.card', {'type': 'VARIABLE_ALIAS', 'id': 'main:variable:orphan'}), 'alias topology'),
            ('mode', lambda: self.after['collections'][0]['modes'].append({'modeId': 'dark', 'name': 'Dark'}), 'single default'),
            ('name', lambda: self.after['variables'][0].update(name='renamed'), 'name/type drift'),
            ('type', lambda: self.after['variables'][0].update(resolvedType='FLOAT'), 'name/type drift'),
            ('native', lambda: self.after['variables'][0].update(id='new-id'), 'native token identity'),
            ('missing', lambda: self.after['variables'].pop(), 'missing semantic'),
            ('ambiguous', lambda: self.after['variables'].append(dict(self.after['variables'][0], id='duplicate')), 'ambiguous'),
            ('orphan', lambda: self.after['variables'].append(dict(self.after['variables'][0], id='extra', semantic_id='unknown')), 'orphan'),
            ('wrong collection', lambda: self.after['pages'][0]['declared_metadata'].update(collection_id='other'), 'collection is missing'),
        ]
        saved = copy.deepcopy(self.after)
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                self.after = copy.deepcopy(saved)
                mutate()
                with self.assertRaisesRegex(ValueError, message):
                    self.run_sync()
                self.assertFalse((self.base / 'out').exists())

    def test_rejects_nonrepresentable_colors_and_edited_structured_values(self):
        self.change('palette.blue', {'r': .123456, 'g': 0, 'b': 0, 'a': 1})
        with self.assertRaisesRegex(ValueError, 'round-trip'):
            self.run_sync()
        self.design['tokens']['space']['card']['$value'] = {'value': 1, 'unit': 'rem'}
        self.reset_exports()
        self.change('space.card', 18)
        with self.assertRaisesRegex(ValueError, 'structured'):
            self.run_sync()

    def test_invalid_graph_no_outputs_and_fresh_directory_boundary(self):
        self.graph['edges'] = []
        with self.assertRaisesRegex(ValueError, 'trace does not belong'):
            self.run_sync()
        self.assertFalse((self.base / 'out').exists())
        (self.base / 'out').mkdir()
        with self.assertRaisesRegex(ValueError, 'fresh directory'):
            self.run_sync()

    def test_cli_and_duplicate_json_boundary(self):
        self.run_sync()
        result = subprocess.run([sys.executable, str(ROOT / 'tools/sync_figma_tokens.py'),
                                 *[item for flag, path in [('design', 'design.json'), ('resolved', 'resolved.json'), ('before', 'before.json'),
                                    ('after', 'after.json'), ('graph', 'graph.json'), ('out', 'cli-out')] for item in ('--' + flag, str(self.base / path))],
                                 '--page-id', 'main:page'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['changed_roots'], [])
        path = self.write('duplicate.json', {})
        path.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            sync.read_json(path)

    def prepare_chain(self):
        self.change('palette.blue', {'r': 1, 'g': 0, 'b': 0, 'a': 1})
        first = self.run_sync()
        self.prior = self.base / 'out'
        # Safe equivalent serialization of the emitted design is accepted.
        self.current_design = self.write('current-design.json', json.loads((self.prior / 'design.json').read_text()))
        self.next_before = self.base / 'next-before.json'
        self.next_before.write_bytes((self.base / 'after.json').read_bytes())
        self.change('palette.blue', {'r': 0, 'g': 1, 'b': 0, 'a': 1})
        self.next_after = self.write('next-after.json', self.after)
        return first

    def run_chain(self, page='main:page', prior=True):
        return sync.sync_tokens(self.current_design, self.base / 'resolved.json', self.next_before, self.next_after,
                                page, self.base / 'graph.json', self.base / 'next-out', prior_sync=self.prior if prior else None)

    def test_consecutive_edits_keep_original_origin_and_chain_receipts(self):
        first = self.prepare_chain()
        second = self.run_chain()
        self.assertEqual(second['changed_roots'], ['palette.blue'])
        self.assertEqual(second['changes'][0]['before'], '#ff0000')
        self.assertEqual(second['changes'][0]['after'], '#00ff00')
        self.assertEqual(second['receipt']['origin'], first['receipt']['origin'])
        self.assertEqual(second['receipt']['prior_report']['sha256'], hashlib.sha256((self.prior / 'impact.json').read_bytes()).hexdigest())
        self.assertEqual(second['pins']['before']['sha256'], first['pins']['after']['sha256'])

    def test_chain_is_explicit_and_rejects_stale_before(self):
        self.prepare_chain()
        with self.assertRaisesRegex(ValueError, 'does not compile exactly'):
            self.run_chain(prior=False)
        self.next_before.write_text(json.dumps(json.loads(self.next_before.read_text()), indent=3))
        with self.assertRaisesRegex(ValueError, 'exact prior after export SHA256'):
            self.run_chain()
        self.assertFalse((self.base / 'next-out').exists())

    def test_chain_rejects_changed_current_design_and_wrong_page(self):
        self.prepare_chain()
        current = json.loads(self.current_design.read_text())
        current['tokens']['space']['card']['$value'] = '2rem'
        self.current_design.write_text(json.dumps(current))
        with self.assertRaisesRegex(ValueError, 'current design does not match'):
            self.run_chain()
        self.current_design.write_bytes((self.prior / 'design.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'origin, source, page or collection'):
            self.run_chain(page='wrong-page')
        self.assertFalse((self.base / 'next-out').exists())

    def test_chain_rejects_corrupt_prior_artifacts_and_origin(self):
        self.prepare_chain()
        for name in ('design.json', 'resolved.json', 'dependencies.json', 'assets/tokens.css', 'assets/components.css', 'report.md'):
            with self.subTest(name=name):
                path = self.prior / name
                raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                with self.assertRaisesRegex(ValueError, 'corrupt prior-sync artifact'):
                    self.run_chain()
                path.write_bytes(raw)
        report_path = self.prior / 'impact.json'
        report = json.loads(report_path.read_text())
        report['receipt']['origin']['resolved_sha256'] = '0' * 64
        report_path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'origin, source, page or collection'):
            self.run_chain()
        self.assertFalse((self.base / 'next-out').exists())

    def test_chain_cli(self):
        self.prepare_chain()
        result = subprocess.run([sys.executable, str(ROOT / 'tools/sync_figma_tokens.py'),
                                 '--design', str(self.current_design), '--resolved', str(self.base / 'resolved.json'),
                                 '--before', str(self.next_before), '--after', str(self.next_after), '--page-id', 'main:page',
                                 '--graph', str(self.base / 'graph.json'), '--out', str(self.base / 'next-out'), '--prior-sync', str(self.prior)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['changed_roots'], ['palette.blue'])


if __name__ == '__main__':
    unittest.main()
