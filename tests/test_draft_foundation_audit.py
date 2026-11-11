"""Portable modeled observations; never represented as an actual Figma capture."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from draft_foundation_audit import audit_draft_foundations


def modeled_fixture():
    color = {'r': 16 / 255, 'g': 32 / 255, 'b': 48 / 255}
    alias = lambda identifier: {'type': 'VARIABLE_ALIAS', 'id': identifier}
    sample = {'label': 'Read note', 'component': 'CMP', 'variant': 'Primary', 'action': 'ACT', 'state': 'ST', 'useCases': ['Read a selected message']}
    candidate = {'id': 'a', 'fonts': {'body': {'family': 'Inter', 'style': 'Regular'}},
                 'graph': {'design_foundations': {'roles': [
                     {'token': 'color/ink', 'kind': 'color', 'alias': 'palette/ink', 'value': '#102030'},
                     {'token': 'type/body', 'kind': 'typography', 'alias': 'font/body', 'value': 'Inter 16px / mobile 14px'},
                     {'token': 'space/page', 'kind': 'spacing', 'alias': 'scale/page', 'value': '24px'}],
                     'palette': {'samples': [sample]}}},
                 'state_layouts': {'desktop': {'ST': {'layers': [{'id': 'headline', 'kind': 'text', 'font': 'body', 'size': 14}]}}}}
    variables = []
    for identifier, name, kind, value in [('primitive-color', 'a/palette/ink', 'COLOR', color),
                                          ('color', 'a/color/ink', 'COLOR', alias('primitive-color')),
                                          ('primitive14', 'review/primitive/14', 'FLOAT', 14),
                                          ('type14', 'a/type/body/14', 'FLOAT', alias('primitive14')),
                                          ('primitive17', 'review/primitive/17', 'FLOAT', 17),
                                          ('type17', 'review/type/palette', 'FLOAT', alias('primitive17'))]:
        variables.append({'id': identifier, 'name': name, 'resolvedType': kind, 'variableCollectionId': 'collection', 'valuesByMode': {'mode': value}})
    def node(identifier, kind, parent, box, semantic=None):
        value = {'id': identifier, 'type': kind, 'parentId': parent, 'absoluteBoundingBox': dict(zip(('x', 'y', 'width', 'height'), box)), 'visible': True, 'fills': [], 'strokes': []}
        if semantic:
            value['semanticKey'] = semantic
        return value
    def ink(value):
        value['fills'] = [{'type': 'SOLID', 'color': color, 'boundVariables': {'color': alias('color')}}]
        return value
    def text(identifier, parent, box, value, size, semantic=None):
        result = ink(node(identifier, 'TEXT', parent, box, semantic))
        result.update(characters=value, fontSize=size, fontName=candidate['fonts']['body'], boundVariables={'fontSize': [alias('type' + str(size))]})
        if size == 14:
            result['textStyleId'] = 'style14'
        return result
    nodes = [node('page', 'PAGE', None, (0, 0, 1000, 1000)),
             ink(node('scene', 'FRAME', 'page', (0, 0, 250, 200), 'a.desktop.ST')),
             text('headline', 'scene', (10, 10, 120, 40), 'A native title', 14, 'a.desktop.ST.headline'),
             node('source-library', 'FRAME', 'page', (-420, -20, 260, 160), 'review.component-library'),
             node('set', 'COMPONENT_SET', 'source-library', (-400, 0, 220, 120), 'a.desktop.component-set'),
             ink(node('main', 'COMPONENT', 'set', (-380, 20, 160, 50), 'a.desktop.component.Primary')),
             text('main-label', 'main', (-370, 25, 130, 30), 'Read note', 14, 'a.desktop.component.Primary.label'),
             node('palette', 'FRAME', 'page', (300, 0, 300, 250)),
             node('card', 'FRAME', 'palette', (310, 10, 280, 220)),
             ink(node('sample', 'INSTANCE', 'card', (320, 65, 160, 50))),
             text('label', 'card', (320, 20, 200, 30), sample['label'], 17),
             text('documentation', 'card', (320, 130, 250, 70), 'ACT / ST / Read a selected message', 17)]
    nodes[4].update(cornerRadius=5, topLeftRadius=5, topRightRadius=5, bottomLeftRadius=5, bottomRightRadius=5)
    nodes[5]['variantProperties'] = {'Visual': 'Primary'}
    nodes[9]['mainComponentId'] = 'main'
    native = {'scope': 'exploratory-only', 'pageId': 'page', 'production_admitted': False, 'nodes': nodes, 'variables': variables,
              'collections': [{'id': 'collection', 'defaultModeId': 'mode', 'modes': [{'modeId': 'mode'}]}],
              'palettes': {'a': {'libraryId': 'palette', 'samples': [dict(sample, instanceId='sample', mainComponentId='main', componentSetId='set', labelNodeId='label', documentationNodeId='documentation')]}},
              'textStyles': [{'id': 'style14', 'fontName': candidate['fonts']['body'], 'fontSize': 14}]}
    # Typed intended semantic declarations, independent of incidental numeric adapters.
    extra = [('font-primitive', 'a/font/body', 'STRING', 'Inter'),
             ('font-semantic', 'a/type/body', 'STRING', alias('font-primitive')),
             ('space-primitive', 'a/scale/page', 'FLOAT', 24),
             ('space-semantic', 'a/space/page', 'FLOAT', alias('space-primitive')),
             ('radius-primitive', 'a/radius/base', 'FLOAT', 0),
             ('radius-semantic', 'a/radius/control', 'FLOAT', alias('radius-primitive'))]
    for identifier, name, kind, value in extra:
        native['variables'].append({'id': identifier, 'name': name, 'resolvedType': kind, 'variableCollectionId': 'collection', 'valuesByMode': {'mode': value}})
    for item in (nodes[2], nodes[6]):
        item['boundVariables']['fontFamily'] = alias('font-semantic')
    nodes[9]['semanticKey'] = 'a.desktop.ST.sample'
    main_key, instance_key = nodes[5]['semanticKey'], nodes[9]['semanticKey']
    for item in (nodes[5], nodes[9]):
        item['layoutMode'] = 'HORIZONTAL'
        for field in ('paddingLeft', 'paddingRight'):
            item[field] = 24
            item.setdefault('boundVariables', {})[field] = alias('space-semantic')
        item['cornerRadius'] = 0
        for field in ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'):
            item[field] = 0
            item['boundVariables'][field] = alias('radius-semantic')
    roles = candidate['graph']['design_foundations']['roles']
    roles[1]['native'] = {'type': 'STRING', 'value': 'Inter', 'bindings': [{'key': nodes[index]['semanticKey'], 'field': 'fontFamily'} for index in (2, 6)]}
    roles[2]['native'] = {'type': 'FLOAT', 'value': 24, 'bindings': [{'key': key, 'field': field} for key in (main_key, instance_key) for field in ('paddingLeft', 'paddingRight')]}
    roles.append({'token': 'radius/control', 'kind': 'radius', 'value': '0px', 'alias': 'radius/base',
                  'native': {'type': 'FLOAT', 'value': 0, 'bindings': [{'key': key, 'field': 'cornerRadius'} for key in (main_key, instance_key)]}})
    candidate['foundationBindings'] = [{'token': role['token'], 'alias': role.get('alias'), **role['native']} for role in roles if 'native' in role]
    return native, candidate


class DraftFoundationAuditTests(unittest.TestCase):
    def test_selected_production_audit_requires_matching_validated_context(self):
        native, candidate = modeled_fixture()
        native.update(schema='figma-flow-native-selected-production-readback-v1',
                      scope='selected-production', production_admitted=True,
                      sourceSelection={'sha256':'selection'}, production_graph={'sha256':'graph'},
                      change_request={'sha256':'request'})
        packet = {key:native[key] for key in ('scope','production_admitted','sourceSelection','production_graph','change_request')}
        packet['schema'] = 'figma-flow-native-selected-production-v1'
        self.assertFalse(audit_draft_foundations(native, candidate)['passed'])
        self.assertTrue(audit_draft_foundations(native, candidate, production_packet=packet)['passed'])
        native['sourceSelection'] = {'sha256':'wrong'}
        self.assertFalse(audit_draft_foundations(native, candidate, production_packet=packet)['passed'])


    def codes(self, report):
        return {item['code'] for item in report['failures']}

    def test_exact_declared_scope_has_actual_counts_and_never_production_admission(self):
        native, candidate = modeled_fixture()
        before = copy.deepcopy((native, candidate))
        native['counts'] = {'visible_bound_fields': 999, 'real_palette_instances': 100}
        result = audit_draft_foundations(native, candidate)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['status'], 'observed-declared-scope')
        self.assertEqual(result['counts']['visible_bound_fields'], 15)
        self.assertEqual(result['counts']['real_palette_instances'], 1)
        self.assertEqual(result['counts']['observed_canonical_roles'], 4)
        self.assertEqual(result['counts']['unobserved_planned_roles'], 0)
        self.assertEqual(result['counts']['required_semantic_bindings'], result['counts']['covered_semantic_bindings'])
        self.assertFalse(result['production_admitted'])
        self.assertTrue(any('Raster' in limit for limit in result['limits']))
        native.pop('counts')
        self.assertEqual((native, candidate), before)

    def test_exploratory_scope_does_not_force_production_role_categories(self):
        native, candidate = modeled_fixture()
        candidate['graph']['design_foundations']['roles'] = candidate['graph']['design_foundations']['roles'][:1]
        candidate['foundationBindings'] = []
        self.assertTrue(audit_draft_foundations(native, candidate)['passed'])

    def test_native_value_cannot_disagree_with_graph_even_if_consumers_match(self):
        native, candidate = modeled_fixture()
        candidate['graph']['design_foundations']['roles'][0]['value'] = '#ffffff'
        self.assertIn('canonical-role-value-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_wrong_missing_and_cyclic_aliases_fail(self):
        for target in ('missing', 'color', 'primitive14'):
            native, candidate = modeled_fixture()
            native['variables'][1]['valuesByMode']['mode']['id'] = target
            self.assertFalse(audit_draft_foundations(native, candidate)['passed'])
        native, candidate = modeled_fixture()
        native['variables'][1]['valuesByMode']['mode'] = native['variables'][0]['valuesByMode']['mode']
        self.assertIn('canonical-role-alias-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_concrete_float_names_aliases_and_observed_fields_must_agree(self):
        native, candidate = modeled_fixture()
        native['variables'][3]['name'] = 'a/type/body/99'
        self.assertIn('numeric-token-name-value-mismatch', self.codes(audit_draft_foundations(native, candidate)))
        native, candidate = modeled_fixture()
        native['variables'][2]['name'] = 'review/primitive/99'
        self.assertIn('scalar-alias-name-value-mismatch', self.codes(audit_draft_foundations(native, candidate)))
        native, candidate = modeled_fixture()
        native['nodes'][2]['fontSize'] = 18
        self.assertIn('observed-field-value-mismatch', self.codes(audit_draft_foundations(native, candidate)))
        self.assertIn('projected-font-size-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_hidden_owner_and_unbound_fields_do_not_become_observed_samples(self):
        native, candidate = modeled_fixture()
        native['nodes'][7]['visible'] = False
        self.assertIn('missing-real-palette-owner', self.codes(audit_draft_foundations(native, candidate)))
        native, candidate = modeled_fixture()
        native['nodes'][2]['boundVariables'] = {}
        self.assertIn('missing-actual-variable-binding', self.codes(audit_draft_foundations(native, candidate)))

    def test_canonical_style_is_real_and_auxiliary_palette_style_limit_is_explicit(self):
        native, candidate = modeled_fixture()
        good = audit_draft_foundations(native, candidate)
        self.assertTrue(any('Auxiliary palette labels' in limit for limit in good['limits']))
        native['textStyles'] = []
        self.assertIn('missing-real-typography-style', self.codes(audit_draft_foundations(native, candidate)))

    def test_platform_font_defaults_are_allowed_but_explicit_variations_are_checked(self):
        native, candidate = modeled_fixture()
        for node in native['nodes']:
            if 'fontName' in node:
                node['fontName'] = dict(node['fontName'], variationSettings={'wght': 400})
        native['textStyles'][0]['fontName'] = dict(native['textStyles'][0]['fontName'], variationSettings={'wght': 400})
        self.assertTrue(audit_draft_foundations(native, candidate)['passed'])
        candidate['fonts']['body']['variationSettings'] = {'wght': 700}
        self.assertIn('projected-font-family-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_palette_documentation_and_main_set_links_cannot_be_json_only(self):
        for field in ('labelNodeId', 'documentationNodeId', 'mainComponentId', 'componentSetId'):
            native, candidate = modeled_fixture()
            native['palettes']['a']['samples'][0][field] = 'missing'
            self.assertFalse(audit_draft_foundations(native, candidate)['passed'])
        native, candidate = modeled_fixture()
        native['nodes'][-1]['characters'] = 'Unrelated text'
        self.assertIn('missing-real-palette-documentation', self.codes(audit_draft_foundations(native, candidate)))

    def test_overlapping_owner_frames_and_collapsed_variants_fail(self):
        native, candidate = modeled_fixture()
        native['nodes'][3]['absoluteBoundingBox'].update(x=0, y=0)
        self.assertIn('overlapping-owner-frames', self.codes(audit_draft_foundations(native, candidate)))
        native, candidate = modeled_fixture()
        native['nodes'].append(dict(native['nodes'][5], id='main2'))
        self.assertIn('overlapping-main-variants', self.codes(audit_draft_foundations(native, candidate)))

    def test_unpainted_component_set_radius_is_not_falsely_a_rendered_role(self):
        native, candidate = modeled_fixture()
        self.assertTrue(audit_draft_foundations(native, candidate)['passed'])
        native['nodes'][4]['fills'] = copy.deepcopy(native['nodes'][5]['fills'])
        self.assertIn('missing-actual-variable-binding', self.codes(audit_draft_foundations(native, candidate)))

    def test_equal_zero_radius_through_wrong_alias_cannot_pass_as_projection(self):
        native, candidate = modeled_fixture()
        native['variables'].append(dict(native['variables'][2], id='wrong-zero', name='review/primitive/0', valuesByMode={'mode': 0}))
        next(v for v in native['variables'] if v['id'] == 'radius-semantic')['valuesByMode']['mode'] = {'type': 'VARIABLE_ALIAS', 'id': 'wrong-zero'}
        result = audit_draft_foundations(native, candidate)
        self.assertFalse(result['passed'])
        self.assertIn('canonical-role-alias-mismatch', self.codes(result))
        self.assertEqual(result['role_projections'], [])

    def test_missing_actual_bounds_and_cross_candidate_bindings_fail(self):
        native, candidate = modeled_fixture()
        native['nodes'][9].pop('absoluteBoundingBox')
        self.assertIn('missing-real-visible-bounds', self.codes(audit_draft_foundations(native, candidate)))
        native, candidate = modeled_fixture()
        native['variables'][1]['name'] = 'b/color/ink'
        self.assertIn('wrong-candidate-variable', self.codes(audit_draft_foundations(native, candidate)))

    def test_missing_or_stale_typed_plan_cannot_pass_by_auxiliary_uses(self):
        native, candidate = modeled_fixture()
        candidate.pop('foundationBindings')
        result = audit_draft_foundations(native, candidate)
        self.assertFalse(result['passed'])
        self.assertIn('compiled-foundation-plan-differs-from-graph', self.codes(result))
        native, candidate = modeled_fixture()
        candidate['graph']['design_foundations']['roles'][2].pop('native')
        result = audit_draft_foundations(native, candidate)
        self.assertFalse(result['passed'])
        self.assertIn('unresolvable-canonical-native-plan', self.codes(result))
        self.assertIn('missing-exact-native-role-declaration', self.codes(result))
        self.assertNotEqual(result['status'], 'observed-subset')

    def test_missing_zero_binding_fails_even_when_radius_looks_identical(self):
        native, candidate = modeled_fixture()
        for node in (native['nodes'][5], native['nodes'][9]):
            for field in ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'):
                node['boundVariables'].pop(field)
        result = audit_draft_foundations(native, candidate)
        self.assertIn('intended-canonical-binding-mismatch', self.codes(result))
        self.assertLess(result['counts']['covered_declared_native_bindings'], result['counts']['declared_native_bindings'])

    def test_same_font_family_value_with_wrong_variable_name_or_getter_fails(self):
        native, candidate = modeled_fixture()
        next(v for v in native['variables'] if v['id'] == 'font-semantic')['name'] = 'a/type/other'
        self.assertIn('missing-or-ambiguous-canonical-role-variable', self.codes(audit_draft_foundations(native, candidate)))
        native, candidate = modeled_fixture()
        native['nodes'][2]['boundVariables']['fontFamily'] = {'type': 'VARIABLE_ALIAS', 'id': 'font-primitive'}
        self.assertIn('intended-canonical-binding-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_literal_typed_role_requires_literal_native_value_not_an_alias(self):
        native, candidate = modeled_fixture()
        role = candidate['graph']['design_foundations']['roles'][1]
        role['alias'] = None
        candidate['foundationBindings'][0]['alias'] = None
        semantic = next(v for v in native['variables'] if v['id'] == 'font-semantic')
        self.assertIn('canonical-role-alias-mismatch', self.codes(audit_draft_foundations(native, candidate)))
        semantic['valuesByMode']['mode'] = 'Inter'
        self.assertTrue(audit_draft_foundations(native, candidate)['passed'])

    def test_matching_alias_name_must_point_to_exact_literal_primitive(self):
        native, candidate = modeled_fixture()
        primitive = next(v for v in native['variables'] if v['id'] == 'font-primitive')
        native['variables'].append(dict(primitive, id='nested-literal', name='a/font/another'))
        primitive['valuesByMode'] = {'mode': {'type': 'VARIABLE_ALIAS', 'id': 'nested-literal'}}
        self.assertIn('canonical-role-alias-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_range_font_getters_cover_utf16_text_and_actual_segment_values(self):
        native, candidate = modeled_fixture()
        node = native['nodes'][2]
        node['characters'] = 'A😀'
        node['boundVariables'].pop('fontFamily')
        node['fontFamilyBinding'] = None
        node['fontSegments'] = [{'start': 0, 'end': 3, 'fontName': node['fontName'],
                                 'boundVariables': {'fontFamily': {'type': 'VARIABLE_ALIAS', 'id': 'font-semantic'}}}]
        result = audit_draft_foundations(native, candidate)
        self.assertTrue(result['passed'], result)
        self.assertTrue(any(use['nodeId'] == node['id'] and use['proof'] == 'segments' for use in result['canonical_bindings']))
        node['fontSegments'][0]['end'] = 2
        self.assertIn('intended-canonical-binding-mismatch', self.codes(audit_draft_foundations(native, candidate)))
        node['fontSegments'][0]['end'] = 3
        node['fontSegments'][0]['fontName'] = {'family': 'Other', 'style': 'Regular'}
        self.assertIn('intended-canonical-binding-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_actual_referenced_style_binding_is_verified_without_fabricated_node_alias(self):
        native, candidate = modeled_fixture()
        node = native['nodes'][2]
        node['boundVariables'].pop('fontFamily')
        node['boundVariables'].pop('fontSize')
        node['fontFamilyBinding'] = None
        node['fontSegments'] = [{'start': 0, 'end': len(node['characters']), 'fontName': node['fontName'], 'boundVariables': {}}]
        native['styles'] = [dict(native['textStyles'][0], type='TEXT', boundVariables={
            'fontFamily': {'type': 'VARIABLE_ALIAS', 'id': 'font-semantic'},
            'fontSize': {'type': 'VARIABLE_ALIAS', 'id': 'type14'}})]
        result = audit_draft_foundations(native, candidate)
        self.assertTrue(result['passed'], result)
        self.assertTrue(any(use['nodeId'] == node['id'] and use['proof'] == 'style' for use in result['canonical_bindings']))
        native['styles'][0]['boundVariables']['fontFamily']['id'] = 'font-primitive'
        self.assertIn('intended-canonical-binding-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_equal_instance_values_require_actual_inheritance_proof(self):
        native, candidate = modeled_fixture()
        instance = native['nodes'][9]
        instance['boundVariables'].pop('paddingLeft')
        self.assertIn('intended-canonical-binding-mismatch', self.codes(audit_draft_foundations(native, candidate)))
        instance['overrides'] = []  # Observed Instance.overrides getter, not a claimed inherited flag.
        result = audit_draft_foundations(native, candidate)
        self.assertTrue(result['passed'], result)
        proof = next(use for use in result['canonical_bindings'] if use['nodeId'] == instance['id'] and use['field'] == 'paddingLeft')
        self.assertEqual(proof['proof'], 'proven-main-inheritance/node')
        self.assertEqual(proof['mainNodeId'], 'main')
        instance['overrides'] = [{'id': instance['id'], 'overriddenFields': ['paddingLeft']}]
        self.assertIn('intended-canonical-binding-mismatch', self.codes(audit_draft_foundations(native, candidate)))

    def test_padding_alias_on_non_layout_node_does_not_satisfy_spacing_role(self):
        native, candidate = modeled_fixture()
        native['nodes'][5]['layoutMode'] = 'NONE'
        self.assertIn('intended-spacing-not-used-by-layout', self.codes(audit_draft_foundations(native, candidate)))

    def test_native_name_is_qualified_once_and_duplicate_normalized_roles_fail(self):
        native, candidate = modeled_fixture()
        role = candidate['graph']['design_foundations']['roles'][2]
        role['token'], role['alias'] = 'a/space/page', 'a/scale/page'
        candidate['foundationBindings'][1]['token'] = role['token']
        candidate['foundationBindings'][1]['alias'] = role['alias']
        self.assertTrue(audit_draft_foundations(native, candidate)['passed'])
        duplicate = copy.deepcopy(role)
        duplicate['token'], duplicate['alias'] = 'space/page', 'scale/page'
        candidate['graph']['design_foundations']['roles'].append(duplicate)
        candidate['foundationBindings'].append({'token': duplicate['token'], 'alias': duplicate['alias'], **duplicate['native']})
        self.assertIn('duplicate-canonical-role-token', self.codes(audit_draft_foundations(native, candidate)))

    def test_declared_target_cannot_be_relocated_into_palette_with_same_key(self):
        native, candidate = modeled_fixture()
        native['nodes'][2]['parentId'] = 'palette'
        self.assertIn('intended-target-outside-authored-owner', self.codes(audit_draft_foundations(native, candidate)))

    def test_shared_legacy_resolver_only_accepts_unambiguous_authored_roles(self):
        from draft_token_plan import foundation_bindings
        native, candidate = modeled_fixture()
        graph = candidate['graph']
        graph['nodes'] = []
        graph['draft_prototype'] = {'states': [{'id': 'ST'}], 'bindings': []}
        candidate['colors'] = {'ink': '#102030'}
        candidate['control_styles'] = {'desktop': {'Primary': {'radius': 0, 'paddingX': 24,
            'paddingY': 0, 'fontSize': 14, 'fill': 'ink', 'ink': 'ink'}}, 'mobile': {}}
        screen = candidate['state_layouts']['desktop']['ST']
        screen.update(bg='ink', width=250, height=200)
        screen['layers'][0].update(value='A native title', x=10, y=10, w=120, h=40, ink='ink')
        candidate['state_layouts']['mobile'] = {'ST': {'bg': 'ink', 'width': 200, 'height': 200, 'layers': []}}
        graph['design_foundations']['roles'] = [role for role in graph['design_foundations']['roles'] if role['kind'] != 'spacing']
        for role in graph['design_foundations']['roles']:
            role.pop('native', None)
        candidate['foundationBindings'] = foundation_bindings(candidate, graph)
        result = audit_draft_foundations(native, candidate)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['counts']['declared_native_bindings'], 3)
        candidate['foundationBindings'][0]['value'] = 'Unreviewed family'
        self.assertIn('compiled-foundation-plan-differs-from-graph', self.codes(audit_draft_foundations(native, candidate)))
        graph['design_foundations']['roles'].append({'token': 'space/control', 'kind': 'spacing', 'alias': 'scale/control', 'value': '24px horizontal / 14px vertical'})
        result = audit_draft_foundations(native, candidate)
        self.assertIn('unresolvable-canonical-native-plan', self.codes(result))
        self.assertTrue(any('space/control' in error for error in result['errors']))

    def test_created_style_records_do_not_replace_real_style_consumers(self):
        native, candidate = modeled_fixture()
        native['nodes'][2]['textStyleId'] = ''
        result = audit_draft_foundations(native, candidate)
        self.assertIn('missing-real-typography-style', self.codes(result))
        self.assertFalse(result['passed'])
        self.assertTrue(native['textStyles'])  # Created styles alone are insufficient.

    def test_duplicate_exact_role_consumers_are_rejected(self):
        native, candidate = modeled_fixture()
        role = candidate['graph']['design_foundations']['roles'][1]
        role['native']['bindings'].append(dict(role['native']['bindings'][0]))
        candidate['foundationBindings'][0]['bindings'] = copy.deepcopy(role['native']['bindings'])
        self.assertIn('duplicate-intended-native-binding', self.codes(audit_draft_foundations(native, candidate)))

    def test_malformed_or_production_claiming_input_fails(self):
        native, candidate = modeled_fixture()
        native['nodes'].append(native['nodes'][0])
        self.assertFalse(audit_draft_foundations(native, candidate)['passed'])
        native, candidate = modeled_fixture()
        native['production_admitted'] = True
        self.assertIn('invalid-draft-scope', self.codes(audit_draft_foundations(native, candidate)))


if __name__ == '__main__':
    unittest.main()


class ProductButtonAuditTests(unittest.TestCase):
    def fixture(self):
        native, candidate = modeled_fixture()
        candidate['control_styles'] = {'desktop': {'Primary': {'fontSize': 14}}}
        candidate['state_layouts']['desktop']['ST']['product_buttons'] = {
            'product': {'variant': 'Primary', 'box': [10, 70, 160, 50], 'label': 'Actual product'}}
        instance = copy.deepcopy(native['nodes'][9])
        instance.update(id='product', parentId='scene', semanticKey='a.desktop.ST.product', reactions=[])
        instance['absoluteBoundingBox'] = {'x': 10, 'y': 70, 'width': 160, 'height': 50}
        label = copy.deepcopy(native['nodes'][6])
        label.update(id='product-label', parentId='product', semanticKey='a.desktop.ST.product.label', characters='Actual product')
        label['absoluteBoundingBox'] = {'x': 34, 'y': 80, 'width': 110, 'height': 30}
        native['nodes'].extend([instance, label])
        return native, candidate

    def test_product_button_is_an_observed_instance_with_actual_text(self):
        native, candidate = self.fixture()
        result = audit_draft_foundations(native, candidate)
        self.assertTrue(result['passed'], result)

    def test_missing_detached_hidden_or_interactive_product_button_fails(self):
        for mutation in ('missing', 'type', 'main', 'hidden', 'reactions', 'missing-reactions', 'label'):
            with self.subTest(mutation=mutation):
                native, candidate = self.fixture()
                instance, label = native['nodes'][-2:]
                if mutation == 'missing': native['nodes'].remove(instance)
                elif mutation == 'type': instance['type'] = 'FRAME'
                elif mutation == 'main': instance['mainComponentId'] = 'missing'
                elif mutation == 'hidden': instance['visible'] = False
                elif mutation == 'reactions': instance['reactions'] = [{'trigger': {'type': 'ON_CLICK'}}]
                elif mutation == 'missing-reactions': instance.pop('reactions')
                else: label['characters'] = 'False label'
                self.assertFalse(audit_draft_foundations(native, candidate)['passed'])
