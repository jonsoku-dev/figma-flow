import copy
import fcntl
import hashlib
import json
import multiprocessing
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import graph_design_system
from graph_design_system import emit_web_module, load_graph, resolve_design_system, update_graph_values


def fixture():
    return {'design_system': {'version': 1, 'tokens': {
        'size/button': {'type': 'FLOAT', 'value': 14},
        'type/button': {'type': 'FLOAT', 'alias': 'size/button'},
        'font/source': {'type': 'STRING', 'value': 'Noto Sans KR'},
        'font/family': {'type': 'STRING', 'alias': 'font/source'},
        'space/x': {'type': 'FLOAT', 'value': 18},
        'space/y': {'type': 'FLOAT', 'value': 8}},
        'components': {'invite-primary': {'properties': {
            'fontSize': 'type/button', 'fontFamily': 'font/family',
            'paddingLeft': 'space/x', 'paddingRight': 'space/x',
            'paddingTop': 'space/y', 'paddingBottom': 'space/y'},
            'native': {'mainKeys': ['main'], 'instanceKeys': ['instance']},
            'web': {'selector': '#invite-submit'}}}},
        'design_foundations': {'version': 1, 'roles': [
            {'token': 'type/button', 'alias': 'old', 'value': '14px', 'source_values': ['14px'],
             'native': {'type': 'FLOAT', 'value': 14, 'bindings': [{'key': 'main', 'field': 'fontSize'}]}}]}}


def race_update(path, sha, value, queue):
    try:
        update_graph_values(path, {'space/x': value}, sha)
        queue.put('ok')
    except ValueError as error:
        queue.put(str(error))


class GraphDesignSystemTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'graph.json'
        self.graph = fixture()
        self.path.write_text(json.dumps(self.graph), encoding='utf-8')

    def sha(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_resolves_primitive_roots_without_mutating_source(self):
        before = copy.deepcopy(self.graph)
        result = resolve_design_system(load_graph(self.path))
        self.assertEqual(result['graphSha256'], self.sha())
        self.assertEqual(result['primitiveRoots']['type/button'], 'size/button')
        self.assertEqual(result['tokens']['font/family'], 'Noto Sans KR')
        self.assertEqual(result['components']['invite-primary']['paddingRight'], 18)
        self.assertEqual(self.graph, before)

    def test_roundtrip_18_to_24_and_font_alias_updates(self):
        result = update_graph_values(self.path, {'space/x': 24, 'type/button': 18,
                                                'font/family': 'Gowun Dodum'}, self.sha())
        graph = load_graph(self.path)
        self.assertEqual(graph['design_system']['tokens']['type/button'], {'type': 'FLOAT', 'alias': 'size/button'})
        self.assertEqual(graph['design_system']['tokens']['size/button']['value'], 18)
        self.assertEqual(result['components']['invite-primary']['paddingLeft'], 24)
        self.assertEqual(result['components']['invite-primary']['paddingRight'], 24)
        self.assertEqual(result['components']['invite-primary']['fontFamily'], 'Gowun Dodum')
        role = graph['design_foundations']['roles'][0]
        self.assertEqual((role['value'], role['native']['value'], role['source_values']), ('18px', 18, ['18px']))
        self.assertEqual(role['alias'], 'size/button')
        self.assertEqual(role['native']['bindings'], [{'key': 'main', 'field': 'fontSize'}])
        self.assertEqual(result['graphSha256'], self.sha())

    def test_invalid_or_stale_updates_never_modify_graph(self):
        raw = self.path.read_bytes()
        for updates, sha in [({'space/x': 24}, 'stale'),
                             ({'size/button': 18, 'type/button': 24}, self.sha()),
                             ({'space/x': -1}, self.sha()),
                             ({'font/family': 'Arial; color:red'}, self.sha()),
                             ({'space/x': True}, self.sha()),
                             ({'space/x': float('nan')}, self.sha())]:
            with self.subTest(updates=updates):
                with self.assertRaises(ValueError):
                    update_graph_values(self.path, updates, sha)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_cycle_wrong_type_unknown_and_literal_property_fail(self):
        mutations = [
            lambda g: g['tokens']['size/button'].update(alias='type/button'),
            lambda g: g['tokens']['font/family'].update(type='FLOAT'),
            lambda g: g['tokens']['font/family'].update(alias='unknown'),
            lambda g: g['components']['invite-primary']['properties'].update(paddingLeft=18),
            lambda g: g['tokens']['type/button'].update(value=14)]
        for mutate in mutations:
            graph = copy.deepcopy(self.graph)
            mutate(graph['design_system'])
            with self.assertRaises(ValueError):
                resolve_design_system(graph)
        graph = copy.deepcopy(self.graph)
        graph['design_system']['tokens']['size/button'] = {'type': 'FLOAT', 'alias': 'type/button'}
        with self.assertRaisesRegex(ValueError, 'cycle'):
            resolve_design_system(graph)

    def test_property_ranges_are_validated_after_alias_resolution(self):
        for prop, value in [('fontSize', 0), ('paddingLeft', -1), ('opacity', 2), ('fontWeight', 1001)]:
            graph = fixture()
            graph['design_system']['tokens']['size/button']['value'] = value
            graph['design_system']['components']['invite-primary']['properties'] = {prop: 'type/button'}
            with self.assertRaises(ValueError):
                resolve_design_system(graph)
        graph = fixture()
        graph['design_system']['tokens']['space/y']['value'] = 0
        self.assertEqual(resolve_design_system(graph)['components']['invite-primary']['paddingTop'], 0)

    @unittest.skipUnless(shutil.which('node'), 'Node required to exercise ESM exports')
    def test_generated_esm_exposes_exact_graph_values(self):
        update_graph_values(self.path, {'space/x': 24}, self.sha())
        out = self.path.with_suffix('.mjs')
        expected = emit_web_module(self.path, out)
        completed = subprocess.run(['node', '--input-type=module', '-e',
            'import * as values from ' + json.dumps(out.as_uri()) + '; console.log(JSON.stringify(values));'],
            check=True, text=True, capture_output=True)
        exported = json.loads(completed.stdout)
        self.assertEqual(exported, {key: expected[key] for key in ('graphSha256', 'tokens', 'components', 'muiComponents', 'primitiveRoots', 'graphStylesheet')})
        self.assertEqual(exported['components']['invite-primary']['paddingLeft'], 24)
        self.assertEqual(exported['muiComponents']['invite-primary']['paddingLeft'], '24px')
        self.assertEqual(exported['muiComponents']['invite-primary']['fontSize'], '14px')
        with self.assertRaises(ValueError):
            emit_web_module(self.path, self.path)

    def test_namespace_foundations_are_derived_from_prefixed_canonical_tokens(self):
        design = self.graph['design_system']
        design['foundationNamespace'] = 'b'
        design['tokens'] = {'b/' + key: {**token, **({'alias': 'b/' + token['alias']} if 'alias' in token else {})}
                            for key, token in design['tokens'].items()}
        for component in design['components'].values():
            component['properties'] = {prop: 'b/' + ref for prop, ref in component['properties'].items()}
        self.path.write_text(json.dumps(self.graph), encoding='utf-8')
        update_graph_values(self.path, {'b/type/button': 24}, self.sha())
        role = load_graph(self.path)['design_foundations']['roles'][0]
        self.assertEqual(role['token'], 'type/button')
        self.assertEqual(role['native']['value'], 24)
        self.assertEqual(role['value'], '24px')
        self.assertEqual(role['alias'], 'b/size/button')

    def test_component_visual_design_updates_preserve_raw_values_and_emit_css(self):
        design = self.graph['design_system']
        design['tokens'].update({
            'color/action': {'type': 'COLOR', 'value': {'r': 0, 'g': 0, 'b': 1}},
            'radius/action': {'type': 'FLOAT', 'value': 8},
            'border/action': {'type': 'FLOAT', 'value': 0},
            'size/action': {'type': 'FLOAT', 'value': 44}})
        design['components']['invite-primary']['properties'].update({
            'backgroundColor': 'color/action', 'color': 'color/action', 'borderColor': 'color/action',
            'borderRadius': 'radius/action', 'borderWidth': 'border/action', 'minHeight': 'size/action'})
        self.path.write_text(json.dumps(self.graph), encoding='utf-8')
        initial = resolve_design_system(load_graph(self.path))
        self.assertEqual(initial['muiComponents']['invite-primary']['backgroundColor'], 'rgba(0, 0, 255, 1)')
        self.assertEqual(initial['muiComponents']['invite-primary']['borderWidth'], '0px')
        out = self.path.with_suffix('.mjs')
        green = {'r': 0, 'g': 1, 'b': 0}
        result = update_graph_values(self.path, {'color/action': green, 'radius/action': 12,
                                               'border/action': 2, 'size/action': 48},
                                     self.sha(), web_module=out)
        raw, mui = result['components']['invite-primary'], result['muiComponents']['invite-primary']
        self.assertEqual(raw['backgroundColor'], green)
        self.assertEqual((raw['borderRadius'], raw['borderWidth'], raw['minHeight']), (12, 2, 48))
        self.assertEqual({key: mui[key] for key in ('backgroundColor', 'color', 'borderColor')},
                         dict.fromkeys(('backgroundColor', 'color', 'borderColor'), 'rgba(0, 255, 0, 1)'))
        self.assertEqual((mui['borderRadius'], mui['borderWidth'], mui['minHeight'], mui['borderStyle']),
                         ('12px', '2px', '48px', 'solid'))
        self.assertIn('rgba(0, 255, 0, 1)', out.read_text())
        precise = update_graph_values(self.path, {'size/action': 48.123456789}, self.sha())
        self.assertEqual(precise['muiComponents']['invite-primary']['minHeight'], '48.123456789px')
        design['components']['invite-primary']['properties']['boxShadow'] = 'color/action'
        with self.assertRaisesRegex(ValueError, 'unsupported component property'):
            resolve_design_system(self.graph)

    def test_stylesheet_projects_graph_selectors_and_variant_scope(self):
        design = self.graph['design_system']
        design['tokens']['color/action'] = {'type': 'COLOR', 'value': {'r': 0, 'g': 0, 'b': 1}}
        design['components']['invite-primary-surface'] = {
            'properties': {'backgroundColor': 'color/action'},
            'web': {'selector': '#invite-submit:not(:disabled)'}}
        css = resolve_design_system(self.graph)['graphStylesheet']
        self.assertIn('#invite-submit { font-size: 14px; font-family: Noto Sans KR;', css)
        self.assertIn('padding-left: 18px;', css)
        self.assertIn('#invite-submit:not(:disabled) { background-color: rgba(0, 0, 255, 1); }', css)
        self.assertNotIn('background-color', css.split('\n')[0])
        for malicious in ('#x { color:red }', '#x; body', '@import url(x)', '</style>',
                          '#x\nbody', '#x:not(:disabled', '#x)'):
            design['components']['invite-primary-surface']['web']['selector'] = malicious
            with self.assertRaisesRegex(ValueError, 'invalid web selector'):
                resolve_design_system(self.graph)

    def test_component_colors_reject_alpha_and_invalid_rgb(self):
        for color in ({'r': 2, 'g': 0, 'b': 0}, {'r': True, 'g': 0, 'b': 0},
                      {'r': 0, 'g': 0, 'b': 0, 'a': .5}, {'r': 0, 'g': 0, 'b': 0, 'a': True}):
            graph = fixture()
            graph['design_system']['tokens']['color/action'] = {'type': 'COLOR', 'value': color}
            graph['design_system']['components']['invite-primary']['properties']['backgroundColor'] = 'color/action'
            with self.assertRaises(ValueError):
                resolve_design_system(graph)

    def test_graph_lock_is_held_through_update_and_export_publication(self):
        out = self.path.with_suffix('.mjs')
        real_write = graph_design_system._atomic_write
        checked = []

        def check_and_write(path, raw):
            if Path(path) == out:
                with self.path.with_name('graph.json.lock').open('a+b') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                checked.append(True)
            real_write(path, raw)

        with patch.object(graph_design_system, '_atomic_write', side_effect=check_and_write):
            update_graph_values(self.path, {'space/x': 24}, self.sha(), web_module=out)
            before = self.path.read_bytes()
            update_graph_values(self.path, {}, self.sha(), web_module=out)
            self.assertEqual(self.path.read_bytes(), before)
            emit_web_module(self.path, out, expected_sha256=self.sha())
        self.assertEqual(len(checked), 3)
        self.assertIn(self.sha(), out.read_text())
        module_before = out.read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale graph'):
            emit_web_module(self.path, out, expected_sha256='stale')
        self.assertEqual(out.read_bytes(), module_before)

    def test_failed_web_publication_preserves_canonical_graph_and_old_module(self):
        out = self.path.with_suffix('.mjs')
        emit_web_module(self.path, out)
        module_before = out.read_bytes()
        real_write = graph_design_system._atomic_write

        def fail_web(path, raw):
            if Path(path) == out:
                raise OSError('injected publication failure')
            real_write(path, raw)

        with patch.object(graph_design_system, '_atomic_write', side_effect=fail_web):
            with self.assertRaisesRegex(OSError, 'publication failure'):
                update_graph_values(self.path, {'space/x': 24}, self.sha(), web_module=out)
        self.assertEqual(load_graph(self.path)['design_system']['tokens']['space/x']['value'], 24)
        self.assertEqual(out.read_bytes(), module_before)
        emit_web_module(self.path, out, expected_sha256=self.sha())
        self.assertIn(self.sha(), out.read_text())

    def test_concurrent_cas_writers_only_one_can_succeed(self):
        context = multiprocessing.get_context('fork')
        queue = context.Queue()
        sha = self.sha()
        processes = [context.Process(target=race_update, args=(self.path, sha, value, queue)) for value in (24, 32)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
        outcomes = [queue.get(timeout=2) for _ in processes]
        self.assertEqual(outcomes.count('ok'), 1)
        self.assertEqual(sum('stale graph' in item for item in outcomes), 1)
        self.assertIn(load_graph(self.path)['design_system']['tokens']['space/x']['value'], (24, 32))
        queue.close()


if __name__ == '__main__':
    unittest.main()
