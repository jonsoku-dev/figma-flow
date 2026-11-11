import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from graph_design_system import load_graph, update_graph_values, emit_web_module, resolve_design_system, _atomic_write
from graph_sync import build_plan, normalize, receipt, export_bundle, import_values, merge_roots, verify_readback, main, verify_web_proof, recover_projection, bind_adopted_plan, discovery_bundle, graph_panel


def fixture():
    graph = {'design_system': {'version': 1, 'tokens': {
        'b/size/button': {'type': 'FLOAT', 'value': 18},
        'b/type/button': {'type': 'FLOAT', 'alias': 'b/size/button'},
        'b/space/padding-16': {'type': 'FLOAT', 'value': 18}},
        'components': {'button': {'properties': {'fontSize': 'b/type/button',
            'paddingLeft': 'b/space/padding-16', 'paddingRight': 'b/space/padding-16'},
            'native': {'mainKeys': ['main'], 'instanceKeys': ['instance']},
            'web': {'selector': '#invite-submit'}}}}}
    variables = [
        {'id': 'root', 'name': 'b/size/button', 'resolvedType': 'FLOAT', 'valuesByMode': {'mode': 18}, 'variableCollectionId': 'collection'},
        {'id': 'alias', 'name': 'b/type/button', 'resolvedType': 'FLOAT', 'valuesByMode': {'mode': {'type': 'VARIABLE_ALIAS', 'id': 'root'}}, 'variableCollectionId': 'collection'},
        {'id': 'padding', 'name': 'b/space/padding-16', 'resolvedType': 'FLOAT', 'valuesByMode': {'mode': 18}, 'variableCollectionId': 'collection'}]
    nodes = []
    for key, kind in [('main', 'COMPONENT'), ('instance', 'INSTANCE')]:
        nodes.append({'id': key, 'semanticKey': key, 'type': kind, 'parentId': 'page', 'mainComponentId': 'main',
            'paddingLeft': 18, 'paddingRight': 18, 'boundVariables': {
                'paddingLeft': {'type': 'VARIABLE_ALIAS', 'id': 'padding'},
                'paddingRight': {'type': 'VARIABLE_ALIAS', 'id': 'padding'}}})
        nodes.append({'id': key + '.text', 'type': 'TEXT', 'parentId': key, 'fontSize': 18,
            'boundVariables': {'fontSize': [{'type': 'VARIABLE_ALIAS', 'id': 'alias'}]}})
    native = {'fileKey': 'file', 'pageId': 'page', 'collections': [{'id': 'collection', 'modes': [{'modeId': 'mode'}], 'defaultModeId': 'mode'}],
              'variables': variables, 'nodes': nodes}
    return graph, native


class GraphSyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.graph, self.native = fixture()
        self.path = self.directory / 'graph.json'
        self.path.write_text(json.dumps(self.graph))
        self.plan = build_plan(load_graph(self.path), self.native)
        self.focused = normalize(self.native, self.plan)
        self.focused['schema'] = 'figma-flow-graph-token-readback-v1'
        self.focused['baseline'] = {'page_id': 'page', 'collection_id': 'collection', 'graph_sha256': self.plan['graph_sha256']}
        self.pairing = receipt(load_graph(self.path), self.plan, self.focused)
        self.web = self.directory / 'tokens.mjs'

    def changed(self, token, value):
        data = copy.deepcopy(self.focused)
        for item in data['tokens']:
            if item['key'] == token or item['key'] == 'b/type/button' and token == 'b/size/button':
                item['resolved'] = value
        for component in data['components']:
            for consumer in component['consumers']:
                if token == 'b/size/button' and consumer['field'] == 'fontSize' or token == 'b/space/padding-16' and consumer['field'].startswith('padding'):
                    consumer['value'] = value
        return data

    def web_proof(self):
        resolved = resolve_design_system(load_graph(self.path))
        return {'schema': 'figma-flow-graph-web-readback-v1', 'graph_sha256': resolved['graphSha256'],
                'observed_at': '2026-11-10T00:00:00Z', 'url': 'http://localhost:3000/',
                'components': [{'id': 'button', 'selector': '#invite-submit',
                    'graph_sha256': resolved['graphSha256'], 'properties': resolved['components']['button']}]}

    def test_web_proof_rejects_bad_units_stale_missing_and_selector_mismatch(self):
        proof = self.web_proof()
        self.assertTrue(verify_web_proof(load_graph(self.path), proof))
        mutations = [lambda d: d['components'][0]['properties'].update(fontSize='18px'),
                     lambda d: d.update(graph_sha256='0' * 64), lambda d: d.update(components=[]),
                     lambda d: d['components'][0].update(selector='#elsewhere')]
        for mutation in mutations:
            bad = copy.deepcopy(proof)
            mutation(bad)
            with self.assertRaises(ValueError):
                verify_web_proof(load_graph(self.path), bad)
        with self.assertRaises(ValueError):
            verify_web_proof(load_graph(self.path), {})

    def test_web_write_failure_is_recoverable_twice_without_graph_rollback(self):
        def fail_web(path, raw):
            if Path(path) == self.web:
                raise OSError('injected web failure')
            return _atomic_write(path, raw)
        output = self.directory / 'failed'
        with patch('graph_design_system._atomic_write', side_effect=fail_web), self.assertRaisesRegex(RuntimeError, 'recover'):
            import_values(self.path, self.pairing, self.changed('b/size/button', 24), self.web, output, True)
        self.assertEqual(load_graph(self.path)['design_system']['tokens']['b/size/button']['value'], 24)
        self.assertEqual(json.loads((output / 'recovery.json').read_text())['state'], 'prepared')
        for _ in range(2):
            self.assertTrue(recover_projection(output / 'recovery.json')['recovered'])
            self.assertIn('24px', self.web.read_text())
        update_graph_values(self.path, {'b/size/button': 30}, load_graph(self.path).source_sha256)
        with self.assertRaisesRegex(ValueError, 'drifted'):
            recover_projection(output / 'recovery.json')

    def test_export_actual_identities_plugin_and_exact_web(self):
        result = export_bundle(self.path, self.directory / 'export', self.web, baseline=self.native, plugin_id='12345')
        plan = json.loads((self.directory / 'export/native-plan.json').read_text())
        self.assertEqual(plan['tokens'][1]['alias_chain'], ['alias', 'root'])
        self.assertEqual(plan['components'][0]['instance_keys'], ['instance'])
        manifest = json.loads((self.directory / 'export/manifest.json').read_text())
        self.assertEqual(manifest['id'], '12345')
        self.assertEqual(manifest['ui'], 'ui.html')
        self.assertTrue(manifest['enablePrivatePluginApi'])
        html = (self.directory / 'export' / manifest['ui']).read_text()
        config = json.loads(re.search(r'<script id="graph-panel-config" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(config['mode'], 'sync')
        self.assertGreaterEqual(len(config['session']), 32)
        self.assertIn('const GRAPH_PANEL_SESSION = ' + json.dumps(config['session']), (self.directory / 'export/code.js').read_text())
        self.assertEqual(config['stats'], {'tokens': 3, 'components': 1, 'mains': 1, 'instances': 1, 'updates': 0, 'creates': 0, 'bindings': 0})
        self.assertEqual(config['main_ids'], ['main'])
        self.assertNotIn('FIGMA_FLOW_PANEL_CSS', html)
        self.assertNotIn('__GRAPH_PANEL_CONFIG__', html)
        self.assertEqual(result['graph_sha256'], load_graph(self.path).source_sha256)
        self.assertIn('18px', self.web.read_text())

    def test_native_18_to_24_import_keeps_alias_and_generates_web(self):
        report = import_values(self.path, self.pairing, self.changed('b/size/button', 24), self.web, self.directory / 'import', True)
        graph = load_graph(self.path)
        self.assertEqual(graph['design_system']['tokens']['b/size/button']['value'], 24)
        self.assertEqual(graph['design_system']['tokens']['b/type/button'], {'type': 'FLOAT', 'alias': 'b/size/button'})
        self.assertIn('24px', self.web.read_text())
        self.assertTrue(report['applied'])
        self.assertFalse(report['pairing_advanced'])
        self.assertEqual(report['graph_sha256_after'], graph.source_sha256)

    def discovery_edit(self):
        data = copy.deepcopy(self.native)
        data['schema'] = 'figma-flow-graph-native-discovery-v1'
        data['graphSSOT'] = copy.deepcopy(self.focused['baseline'])
        data['variables'][0]['valuesByMode']['mode'] = 24
        for node in data['nodes']:
            if node['type'] == 'TEXT':
                node['fontSize'] = 24
        return data

    def test_import_rejects_invalid_discovery_markers_without_any_writes(self):
        self.web.write_text('existing web module')
        before = {path.relative_to(self.directory): path.read_bytes()
                  for path in self.directory.rglob('*') if path.is_file()}
        for case in ('stale', 'missing', 'conflicting'):
            data = self.discovery_edit()
            if case == 'stale':
                data['graphSSOT']['graph_sha256'] = '0' * 64
            elif case == 'missing':
                del data['graphSSOT']
            else:
                data['baseline'] = {'graph_sha256': '0' * 64}
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, 'native graph marker'):
                import_values(self.path, self.pairing, data, self.web, self.directory / case, True)
            self.assertEqual({path.relative_to(self.directory): path.read_bytes()
                              for path in self.directory.rglob('*') if path.is_file()}, before)
            self.assertFalse((self.directory / case).exists())

    def test_import_accepts_matching_discovery_marker(self):
        for shape in ('graphSSOT', 'baseline', 'both'):
            data = self.discovery_edit()
            if shape == 'baseline':
                data['baseline'] = data.pop('graphSSOT')
            elif shape == 'both':
                data['baseline'] = copy.deepcopy(data['graphSSOT'])
            with self.subTest(shape=shape):
                report = import_values(self.path, self.pairing, data, self.web, self.directory / shape, True)
                self.assertTrue(report['applied'])
        self.assertEqual(load_graph(self.path)['design_system']['tokens']['b/size/button']['value'], 24)
        self.assertIn('24px', self.web.read_text())

    def test_import_rejects_conflicting_focused_markers(self):
        data = self.changed('b/size/button', 24)
        data['graphSSOT'] = {'graph_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'conflicting native graph markers'):
            import_values(self.path, self.pairing, data, self.web, self.directory / 'conflicting', True)

    def test_import_preserves_untyped_native_compatibility(self):
        data = self.discovery_edit()
        del data['schema'], data['graphSSOT']
        report = import_values(self.path, self.pairing, data, self.web, self.directory / 'legacy', True)
        self.assertTrue(report['applied'])
        self.assertEqual(load_graph(self.path)['design_system']['tokens']['b/size/button']['value'], 24)

    def test_reverse_import_can_export_actual_before_for_marker_reconciliation(self):
        actual = self.changed('b/size/button', 24)
        import_values(self.path, self.pairing, actual, self.web, self.directory / 'import', True)
        export_bundle(self.path, self.directory / 'reconcile', self.web, baseline=actual, pairing=self.pairing)
        discovery_marker = copy.deepcopy(actual)
        discovery_marker['graphSSOT'] = discovery_marker.pop('baseline')
        export_bundle(self.path, self.directory / 'reconcile-discovery-marker', self.web, baseline=discovery_marker, pairing=self.pairing)
        discovery_marker['baseline'] = {'graph_sha256':'wrong'}
        with self.assertRaisesRegex(ValueError, 'conflicting native graph markers'):
            export_bundle(self.path, self.directory / 'reconcile-conflicting-markers', self.web, baseline=discovery_marker, pairing=self.pairing)

        plan = json.loads((self.directory / 'reconcile/native-plan.json').read_text())
        self.assertEqual(plan['previous_graph_sha256'], self.pairing['graph_sha256'])
        self.assertEqual(plan['graph_sha256'], load_graph(self.path).source_sha256)
        self.assertEqual(plan['tokens'][0]['before'], 24)
        self.assertEqual(plan['tokens'][0]['value'], 24)

    def test_three_way_disjoint_and_convergent_accept_divergent_reject(self):
        update_graph_values(self.path, {'b/space/padding-16': 30}, load_graph(self.path).source_sha256)
        observed, _ = verify_readback(self.plan, self.changed('b/size/button', 24))
        self.assertEqual(merge_roots(load_graph(self.path), self.pairing, observed), {'b/size/button': 24})
        update_graph_values(self.path, {'b/size/button': 24}, load_graph(self.path).source_sha256)
        self.assertEqual(merge_roots(load_graph(self.path), self.pairing, observed), {})
        update_graph_values(self.path, {'b/size/button': 30}, load_graph(self.path).source_sha256)
        with self.assertRaisesRegex(ValueError, 'divergent'):
            merge_roots(load_graph(self.path), self.pairing, observed)

    def test_wrong_scope_alias_binding_identity_rejected_without_graph_write(self):
        mutations = [lambda d: d.update(status='rolled-back'), lambda d: d.update(status='rollback-conflict'),
                     lambda d: d.update(migration_pending=True), lambda d: d.update(file_key='wrong'), lambda d: d.update(page_id='wrong'),
                     lambda d: d.update(collection_id='wrong'),
                     lambda d: d['tokens'][1].update(alias_chain=['alias', 'elsewhere']),
                     lambda d: d['components'][0]['consumers'][0].update(binding=None),
                     lambda d: d['components'][1].update(main_component_id='other'),
                     lambda d: d['components'][0]['consumers'][0].update(node_id='replaced')]
        before = self.path.read_bytes()
        for index, mutate in enumerate(mutations):
            data = self.changed('b/size/button', 24)
            mutate(data)
            with self.subTest(index=index), self.assertRaises(ValueError):
                import_values(self.path, self.pairing, data, self.web, self.directory / f'bad{index}', True)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertFalse(self.web.exists())

    def test_initial_getter_rejects_graph_alias_and_declared_scope_drift(self):
        native = copy.deepcopy(self.native)
        native['variables'][1]['valuesByMode']['mode'] = 18
        with self.assertRaisesRegex(ValueError, 'alias'):
            build_plan(load_graph(self.path), native)
        self.graph['design_system']['native'] = {'file_key': 'wrong'}
        with self.assertRaisesRegex(ValueError, 'file_key'):
            build_plan(self.graph, self.native)

    def test_graph_panel_lists_primitive_root_when_alias_precedes_it(self):
        plan = copy.deepcopy(self.plan)
        root, alias, padding = plan['tokens']
        root.update(key='spacing/base', variable_name='spacing/base', before=12, value=16)
        alias.update(key='button/gap', variable_name='button/gap', before=12, value=16)
        plan['tokens'] = [alias, root, padding]
        plan['components'][0]['properties'] = {'gap': 'button/gap'}
        html = graph_panel('sync', plan, plan)
        config = json.loads(re.search(r'<script id="graph-panel-config" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(config['changes'], [{'name': 'spacing/base', 'before': '12', 'after': '16'}])
        self.assertEqual(config['stats']['updates'], 1)

    def test_graph_panel_escapes_untrusted_scope_without_losing_actual_values(self):
        value = '</script><img src=x onerror=alert(1)>&'
        html = graph_panel('discovery', {'file_key': value, 'page_id': 'page', 'allowed_page_ids': ['page']})
        config = json.loads(re.search(r'<script id="graph-panel-config" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(config['file_key'], value)
        self.assertNotIn(value, html)
        self.assertIn('<body class="panel">', html)
        self.assertIn('Figma Flow', html)
        self.assertNotIn('innerHTML', html)

    def test_discovery_emits_scoped_read_only_installable_plugin(self):
        output = self.directory / 'discover'
        result = discovery_bundle('file', 'page', ['other-page'], output, '12345')
        self.assertEqual(result['allowed_page_ids'], ['page', 'other-page'])
        source = (output / 'code.js').read_text()
        self.assertIn('figma-flow-graph-native-discovery-v1', source)
        self.assertIn('readNativeSemantics(figma, page)', source)
        self.assertIn("page.getPluginData('graphSSOT')", source)
        self.assertNotIn('setValueForMode', source)
        self.assertNotIn('setBoundVariable', source)
        manifest = json.loads((output / 'manifest.json').read_text())
        self.assertEqual(manifest['id'], '12345')
        self.assertEqual(manifest['ui'], 'ui.html')
        self.assertTrue(manifest['enablePrivatePluginApi'])
        html = (output / manifest['ui']).read_text()
        config = json.loads(re.search(r'<script id="graph-panel-config" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(config['mode'], 'discovery')
        self.assertIn('const GRAPH_PANEL_SESSION = ' + json.dumps(config['session']), source)
        self.assertEqual(config['pages'], ['page', 'other-page'])
        self.assertIn('figma.showUI(__html__', source)
        self.assertIn('themeColors: true', source)
        if shutil.which('node'):
            subprocess.run(['node', '--check', str(output / 'code.js')], check=True, capture_output=True)

    def adoption_graph(self):
        graph = copy.deepcopy(self.graph)
        design = graph['design_system']
        design['id'] = 'test-invite'
        rename = {key: key.removeprefix('b/') for key in design['tokens']}
        design['tokens'] = {rename[key]: {**value, **({'alias': rename[value['alias']]} if 'alias' in value else {})}
                            for key, value in design['tokens'].items()}
        for component in design['components'].values():
            component['properties'] = {field: rename[key] for field, key in component['properties'].items()}
        return graph

    def test_adoption_creates_independent_tokens_and_pins_only_declared_consumers(self):
        graph = self.adoption_graph()
        native = copy.deepcopy(self.native)
        native['nodes'].append({'id': 'reset.text', 'type': 'TEXT', 'parentId': 'page', 'fontSize': 18,
                                'boundVariables': {'fontSize': [{'type': 'VARIABLE_ALIAS', 'id': 'alias'}]}})
        before = copy.deepcopy(native)
        plan = build_plan(graph, native, adopt=True)
        self.assertEqual(native, before)
        self.assertEqual(plan['namespace'], 'ssot/test-invite')
        self.assertTrue(all(token['create'] for token in plan['tokens']))
        self.assertTrue(all(token['variable_name'].startswith('ssot/test-invite/') for token in plan['tokens']))
        self.assertFalse(any(item['node_id'] == 'reset.text' for item in plan['migrations']))
        self.assertEqual({item['before_variable_id'] for item in plan['migrations']}, {'alias', 'padding'})
        self.assertEqual({item['before_value'] for item in plan['migrations']}, {18})
        with self.assertRaisesRegex(ValueError, 'undeclared consumer'):
            build_plan(load_graph(self.path), native)

    def test_adoption_ignores_unrelated_collections_but_rejects_mixed_scoped_bindings(self):
        graph, native = self.adoption_graph(), copy.deepcopy(self.native)
        native['collections'].append({'id': 'unrelated-collection', 'modes': [{'modeId': 'other-mode'}], 'defaultModeId': 'other-mode'})
        native['variables'].append({'id': 'unrelated', 'name': 'other/font', 'resolvedType': 'FLOAT',
            'variableCollectionId': 'unrelated-collection', 'valuesByMode': {'other-mode': 22}})
        native['nodes'].append({'id': 'other-system.text', 'parentId': 'page', 'type': 'TEXT', 'fontSize': 22,
            'boundVariables': {'fontSize': {'type': 'VARIABLE_ALIAS', 'id': 'unrelated'}}})
        before = copy.deepcopy(native)
        plan = build_plan(graph, native, adopt=True)
        self.assertEqual(plan['collection_id'], 'collection')
        self.assertEqual(native, before)
        next(node for node in native['nodes'] if node['id'] == 'instance.text')['boundVariables']['fontSize'] = {'type': 'VARIABLE_ALIAS', 'id': 'unrelated'}
        with self.assertRaisesRegex(ValueError, 'one exact native collection'):
            build_plan(graph, native, adopt=True)

    def test_adoption_pairs_actual_new_ids_and_preserves_strict_future_ids(self):
        graph = self.adoption_graph()
        plan = build_plan(graph, self.native, adopt=True)
        focused = copy.deepcopy(self.focused)
        ids = {token['variable_name']: 'created-' + str(index) for index, token in enumerate(plan['tokens'])}
        focused['tokens'] = [{
            'key': token['key'], 'type': token['type'], 'variable_name': token['variable_name'],
            'variable_id': ids[token['variable_name']], 'root_variable_id': ids[token['root_variable_name']],
            'alias_chain': [ids[name] for name in token['alias_chain_names']], 'resolved': token['value']}
            for token in plan['tokens']]
        for component in focused['components']:
            for consumer in component['consumers']:
                key = graph['design_system']['components']['button']['properties'][consumer['field']]
                consumer['binding'] = {'type': 'VARIABLE_ALIAS', 'id': ids['ssot/test-invite/' + key]}
        paired = receipt(graph, plan, focused)
        self.assertTrue(all(not token.get('create') for token in paired['plan']['tokens']))
        self.assertNotIn('migrations', paired['plan'])
        self.assertTrue(all(token['variable_id'].startswith('created-') for token in paired['plan']['tokens']))
        broken = copy.deepcopy(focused)
        broken['tokens'][0]['variable_name'] = 'shared/old'
        with self.assertRaisesRegex(ValueError, 'name/type'):
            receipt(graph, plan, broken)
        broken = copy.deepcopy(focused)
        broken['tokens'][1]['alias_chain'] = [broken['tokens'][1]['variable_id']]
        with self.assertRaisesRegex(ValueError, 'topology'):
            receipt(graph, plan, broken)

    def test_adoption_requires_namespace_absent_names_and_allowed_page_scope(self):
        graph = self.adoption_graph()
        del graph['design_system']['id']
        with self.assertRaisesRegex(ValueError, 'requires design_system'):
            build_plan(graph, self.native, adopt=True)
        graph = self.adoption_graph()
        native = copy.deepcopy(self.native)
        native['variables'].append({**native['variables'][0], 'id': 'collision', 'name': 'ssot/test-invite/size/button'})
        with self.assertRaisesRegex(ValueError, 'already exist'):
            build_plan(graph, native, adopt=True)
        native = copy.deepcopy(self.native)
        next(node for node in native['nodes'] if node['id'] == 'instance')['parentId'] = 'other-page'
        with self.assertRaisesRegex(ValueError, 'outside allowed'):
            build_plan(graph, native, adopt=True)
        graph['design_system']['native'] = {'allowed_page_ids': ['page', 'other-page']}
        plan = build_plan(graph, native, adopt=True)
        self.assertEqual(plan['node_page_ids']['instance'], 'other-page')

    def test_direct_main_padding_and_instance_font_promote_shared_component_and_guard_repairs(self):
        edited = copy.deepcopy(self.focused)
        for group in edited['components']:
            for consumer in group['consumers']:
                if group['node_id'] == 'main' and consumer['field'] == 'paddingLeft':
                    consumer.update(value=24, binding=None)
                if group['node_id'] == 'instance' and consumer['field'] == 'fontSize':
                    consumer.update(value=20, binding=None)
        before_native = copy.deepcopy(edited)
        report = import_values(self.path, self.pairing, edited, self.web, self.directory / 'direct', True, 'component')
        self.assertEqual(edited, before_native)
        self.assertEqual(report['updates'], {'b/size/button': 20, 'b/space/padding-16': 24})
        self.assertEqual(len(report['repair_bindings']), 2)
        self.assertEqual(report['affected_components'][0]['instance_ids'], ['instance'])
        self.assertEqual(report['affected_components'][0]['web_selector'], '#invite-submit')
        self.assertIn('20px', self.web.read_text())
        self.assertIn('24px', self.web.read_text())
        export_bundle(self.path, self.directory / 'repair-export', self.web, baseline=edited, pairing=self.pairing, import_report=report)
        plan = json.loads((self.directory / 'repair-export/native-plan.json').read_text())
        self.assertEqual(plan['repair_bindings'], report['repair_bindings'])
        self.assertEqual(plan['tokens'][0]['before'], 18)
        self.assertEqual(plan['tokens'][0]['value'], 20)
        with self.assertRaisesRegex(ValueError, 'native value mismatch|binding/getter'):
            receipt(load_graph(self.path), plan, edited)
        changed_again = copy.deepcopy(edited)
        changed_again['components'][0]['consumers'][1]['value'] = 26
        with self.assertRaisesRegex(ValueError, 'unaccepted'):
            export_bundle(self.path, self.directory / 'changed-again', self.web, baseline=changed_again, pairing=self.pairing, import_report=report)

    def test_direct_edits_require_explicit_scope_and_reject_competing_values(self):
        edited = copy.deepcopy(self.focused)
        padding = edited['components'][0]['consumers'][1]
        padding.update(value=24, binding=None)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'binding/getter'):
            import_values(self.path, self.pairing, edited, self.web, self.directory / 'implicit', True)
        conflicting = copy.deepcopy(edited)
        conflicting['components'][1]['consumers'][2].update(value=30, binding=None)
        with self.assertRaisesRegex(ValueError, 'conflicting direct'):
            import_values(self.path, self.pairing, conflicting, self.web, self.directory / 'conflict', True, 'component')
        variable_edit = self.changed('b/space/padding-16', 22)
        variable_edit['components'][0]['consumers'][1].update(value=24, binding=None)
        with self.assertRaisesRegex(ValueError, 'variable and direct'):
            import_values(self.path, self.pairing, variable_edit, self.web, self.directory / 'variable-conflict', True, 'component')
        self.assertEqual(self.path.read_bytes(), before)
        update_graph_values(self.path, {'b/space/padding-16': 22}, load_graph(self.path).source_sha256)
        with self.assertRaisesRegex(ValueError, 'divergent same-token'):
            import_values(self.path, self.pairing, edited, self.web, self.directory / 'graph-conflict', True, 'component')

    def test_unmapped_direct_property_is_reported_without_promotion(self):
        edited = copy.deepcopy(self.focused)
        edited['components'][0]['consumers'].append({'node_id': 'main', 'field': 'opacity', 'value': 0.5, 'binding': None})
        report = import_values(self.path, self.pairing, edited, self.web, self.directory / 'unmapped', False, 'component')
        self.assertEqual(report['updates'], {})
        self.assertEqual(report['unsupported_changes'][0]['field'], 'opacity')
        self.assertEqual(report['repair_bindings'], [])

    def test_style_adoption_reads_unbound_paints_radius_and_rejects_lossy_sources(self):
        graph, native = self.adoption_graph(), copy.deepcopy(self.native)
        graph['design_system']['tokens'].update({'surface': {'type': 'COLOR', 'value': {'r': 0, 'g': 0, 'b': 1, 'a': 1}},
                                                'radius': {'type': 'FLOAT', 'value': 8}})
        graph['design_system']['components']['button']['properties'].update(backgroundColor='surface', borderRadius='radius')
        for node in native['nodes']:
            if node['type'] in {'COMPONENT', 'INSTANCE'}:
                node.update(fills=[{'type': 'SOLID', 'color': {'r': 0, 'g': 0, 'b': 1}}], cornerRadius=8)
        plan = build_plan(graph, native, adopt=True)
        styles = [repair for repair in plan['migrations'] if repair['field'] in {'backgroundColor', 'borderRadius'}]
        self.assertEqual(len(styles), 4)
        self.assertTrue(all(repair['before_variable_id'] is None for repair in styles))
        native['nodes'][0]['fills'].append({'type': 'SOLID', 'color': {'r': 0, 'g': 1, 'b': 0}})
        with self.assertRaisesRegex(ValueError, 'mixed native paint'):
            build_plan(graph, native, adopt=True)

    def test_direct_color_blue_to_green_and_radius_8_to_12_update_graph_and_web(self):
        blue, green = {'r': 0, 'g': 0, 'b': 1, 'a': 1}, {'r': 0, 'g': 1, 'b': 0, 'a': 1}
        graph, native = copy.deepcopy(self.graph), copy.deepcopy(self.native)
        graph['design_system']['tokens'].update({'surface': {'type': 'COLOR', 'value': blue}, 'radius': {'type': 'FLOAT', 'value': 8}})
        graph['design_system']['components']['button']['properties'].update(backgroundColor='surface', borderRadius='radius')
        for name, kind, value in [('surface', 'COLOR', blue), ('radius', 'FLOAT', 8)]:
            native['variables'].append({'id': name, 'name': name, 'resolvedType': kind, 'variableCollectionId': 'collection', 'valuesByMode': {'mode': value}})
        for node in native['nodes']:
            if node['type'] in {'COMPONENT', 'INSTANCE'}:
                node.update(fills=[{'type': 'SOLID', 'color': {'r': 0, 'g': 0, 'b': 1}, 'boundVariables': {'color': {'type': 'VARIABLE_ALIAS', 'id': 'surface'}}}], cornerRadius=8)
                node['boundVariables']['cornerRadius'] = {'type': 'VARIABLE_ALIAS', 'id': 'radius'}
        self.path.write_text(json.dumps(graph))
        plan = build_plan(load_graph(self.path), native)
        actual = normalize(native, plan)
        paired = receipt(load_graph(self.path), plan, actual)
        actual.update(schema='figma-flow-graph-token-readback-v1', baseline={'graph_sha256': paired['graph_sha256']})
        for group in actual['components']:
            for consumer in group['consumers']:
                if group['node_id'] == 'main' and consumer['field'] == 'backgroundColor':
                    consumer.update(value=green, binding=None)
                if group['node_id'] == 'instance' and consumer['field'] == 'borderRadius':
                    consumer.update(value=12, binding=None)
        report = import_values(self.path, paired, actual, self.web, self.directory / 'design-edit', True, 'component')
        self.assertEqual(report['updates'], {'surface': green, 'radius': 12})
        after = load_graph(self.path)
        self.assertEqual(after['design_system']['tokens']['surface']['value'], green)
        self.assertEqual(after['design_system']['tokens']['radius']['value'], 12)
        self.assertIn('rgba(0, 255, 0, 1)', self.web.read_text())
        self.assertIn('12px', self.web.read_text())
        proof = self.web_proof()
        self.assertTrue(verify_web_proof(after, proof))

    def test_incremental_adoption_preserves_existing_tokens_and_allows_new_disjoint_surface_component(self):
        graph = self.adoption_graph()
        native = copy.deepcopy(self.native)
        prefix = 'ssot/test-invite/'
        for variable in native['variables']:
            variable['name'] = prefix + variable['name'].removeprefix('b/')
        old_plan = build_plan(graph, native)
        paired = receipt(graph, old_plan, normalize(native, old_plan))
        native['graphSSOT'] = {'page_id': 'page', 'collection_id': 'collection', 'graph_sha256': paired['graph_sha256']}
        graph['design_system']['tokens'].update({'surface': {'type': 'COLOR', 'value': {'r': 0, 'g': 0, 'b': 1, 'a': 1}},
                                                'radius': {'type': 'FLOAT', 'value': 8}})
        graph['design_system']['components']['button']['properties']['borderRadius'] = 'radius'
        graph['design_system']['components']['surface'] = {'properties': {'backgroundColor': 'surface'},
            'native': copy.deepcopy(graph['design_system']['components']['button']['native']), 'web': {'selector': '#invite-submit:not(:disabled)'}}
        for node in native['nodes']:
            if node['type'] in {'COMPONENT', 'INSTANCE'}:
                node.update(fills=[{'type': 'SOLID', 'color': {'r': 0, 'g': 0, 'b': 1}}], cornerRadius=8)
        self.path.write_text(json.dumps(graph))
        before = copy.deepcopy(native)
        export_bundle(self.path, self.directory / 'extension', self.web, native, paired, adopt=True)
        plan = json.loads((self.directory / 'extension/native-plan.json').read_text())
        self.assertEqual(native, before)
        self.assertEqual(plan['previous_graph_sha256'], paired['graph_sha256'])
        self.assertEqual(len([token for token in plan['tokens'] if token.get('create')]), 2)
        self.assertEqual([token['variable_id'] for token in plan['tokens'] if not token.get('create')], ['root', 'alias', 'padding'])
        self.assertEqual({repair['field'] for repair in plan['migrations']}, {'backgroundColor', 'borderRadius'})
        graph['design_system']['tokens']['size/button']['value'] = 30
        self.path.write_text(json.dumps(graph))
        with self.assertRaisesRegex(ValueError, 'existing owned token'):
            export_bundle(self.path, self.directory / 'bad-extension', self.web, native, paired, adopt=True)

    def test_web_path_cannot_overwrite_canonical_graph(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'overwrite graph'):
            import_values(self.path, self.pairing, self.changed('b/size/button', 24), self.path, self.directory / 'bad-path', True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_preview_does_not_change_canonical_graph_or_web(self):
        before = self.path.read_bytes()
        report = import_values(self.path, self.pairing, self.changed('b/size/button', 24), self.web, self.directory / 'preview')
        self.assertFalse(report['applied'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.web.exists())

    def test_stale_graph_during_cas_does_not_overwrite(self):
        before = self.path.read_bytes()
        original = update_graph_values
        def race(path, updates, sha, **kwargs):
            if Path(path) == self.path:
                self.path.write_bytes(before + b' ')
            return original(path, updates, sha, **kwargs)
        with patch('graph_sync.update_graph_values', side_effect=race), self.assertRaisesRegex(ValueError, 'stale'):
            import_values(self.path, self.pairing, self.changed('b/size/button', 24), self.web, self.directory / 'race', True)
        self.assertEqual(self.path.read_bytes(), before + b' ')
        self.assertFalse(self.web.exists())

    def test_pair_cli_requires_current_applied_marker_and_plan(self):
        plan = self.directory / 'native-plan.json'
        plan.write_text(json.dumps(self.plan))
        readback = self.directory / 'readback.json'
        readback.write_text(json.dumps(self.focused))
        out = self.directory / 'pairing.json'
        emit_web_module(self.path, self.web)
        proof_path = self.directory / 'web-proof.json'
        proof_path.write_text(json.dumps(self.web_proof()))
        args = ['pair', '--graph', str(self.path), '--readback', str(readback), '--out', str(out),
                '--web-module', str(self.web), '--web-proof', str(proof_path)]
        self.assertEqual(main(args[:-2]), 2)
        self.assertFalse(out.exists())
        self.assertEqual(main(args), 0)
        self.focused['baseline']['graph_sha256'] = '0' * 64
        readback.write_text(json.dumps(self.focused))
        self.assertEqual(main(args), 2)


if __name__ == '__main__':
    unittest.main()
