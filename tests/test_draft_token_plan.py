from pathlib import Path
import copy
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from draft_token_plan import foundation_bindings


class TokenPlanTests(unittest.TestCase):
    def setUp(self):
        project = ROOT / 'examples/native-direction-review'
        self.candidate = json.loads((project / 'native-layout.json').read_text())['candidates'][0]
        self.graph = json.loads((project / self.candidate['graph']['path']).read_text())
        self.graph['design_foundations']['roles'] = []

    def role(self, token, field, value, target):
        field_type = 'STRING' if field == 'fontFamily' else 'FLOAT'
        kind = 'typography' if field.startswith('font') else 'spacing' if field.startswith('padding') else 'radius'
        return {'kind': kind, 'token': token, 'alias': 'base/' + token, 'value': str(value),
                'native': {'type': field_type, 'value': value, 'bindings': [{'key': target, 'field': field}]}}

    def plan(self, *roles):
        self.graph['design_foundations']['roles'] = list(roles)
        return foundation_bindings(self.candidate, self.graph)

    def test_displayed_plan_must_show_the_written_value(self):
        from draft_token_plan import check_display_value
        ok = [({'token': 't', 'value': 'Inter'}, 'STRING', 'Inter'), ({'token': 't', 'value': 'Inter Regular · 16px'}, 'STRING', 'Inter'),
              ({'token': 't', 'value': 'Inter, sans-serif'}, 'STRING', 'Inter'), ({'token': 't', 'value': '16px'}, 'FLOAT', 16)]
        for role, kind, value in ok:
            check_display_value(role, kind, value)
        bad = [({'token': 't', 'value': 'Arial', 'source_values': ['Inter']}, 'STRING', 'Inter', 'absent from the displayed plan'),
               ({'token': 't', 'value': '1rem'}, 'FLOAT', 16, 'show px'), ({'token': 't', 'value': '12pt'}, 'FLOAT', 16, 'show px'),
               ({'token': 't', 'value': '18px'}, 'FLOAT', 16, 'conflicts')]
        for role, kind, value, message in bad:
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, message):
                check_display_value(role, kind, value)

    def test_importer_fallback_names_are_reserved(self):
        state = self.graph['draft_prototype']['entry_state']
        key = f"{self.candidate['id']}.desktop.{state}.summary"
        for token in ('type/body/16', 'radius/observed/6'):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'reserved for importer fallback'):
                self.plan(self.role(token, 'fontSize', 16, key))
        roles = self.plan(self.role('type/size/16', 'fontSize', 16, key))  # Not a fallback shape: allowed.
        self.assertEqual(roles[0]['token'], 'type/size/16')

    def test_family_and_size_bind_separately_without_changing_text(self):
        state = self.graph['draft_prototype']['entry_state']
        key = f"{self.candidate['id']}.desktop.{state}.summary"
        roles = self.plan(self.role('type/body', 'fontFamily', 'Inter', key), self.role('size/body', 'fontSize', 16, key))
        self.assertEqual([(r['token'], r['type'], r['value']) for r in roles],
                         [('type/body','STRING','Inter'), ('size/body','FLOAT',16)])

    def test_conflicting_values_and_duplicate_target_are_refused(self):
        key = f"{self.candidate['id']}.desktop.component.Primary"
        x = self.role('space/control','paddingLeft',24,key)
        y = self.role('space/control-y','paddingTop',14,key)
        self.assertEqual(len(self.plan(x,y)), 2)
        bad = copy.deepcopy(x)
        bad['native']['bindings'][0]['field'] = 'paddingTop'
        with self.assertRaisesRegex(ValueError,'authored as 14'):
            self.plan(bad)
        same = copy.deepcopy(x)
        same['token'] = 'space/other'
        with self.assertRaisesRegex(ValueError,'already declared'):
            self.plan(x,same)
        y['alias'] = x['alias']
        with self.assertRaisesRegex(ValueError,'conflicting type or value'):
            self.plan(x,y)

    def test_missing_target_and_ambiguous_legacy_spacing_do_not_get_auxiliary_substitutes(self):
        role = self.role('space/control','paddingLeft',24,'missing')
        with self.assertRaisesRegex(ValueError,'incompatible authored property'):
            self.plan(role)
        role.pop('native')
        role['value'] = '24px horizontal, 14px vertical'
        with self.assertRaisesRegex(ValueError,'declare native'):
            self.plan(role)

    def test_displayed_scalar_and_namespaced_collisions_are_rejected(self):
        key = f"{self.candidate['id']}.desktop.component.Primary"
        x = self.role('space/control','paddingLeft',24,key)
        x['value'] = 999
        with self.assertRaisesRegex(ValueError,'displayed value'):
            self.plan(x)
        x['value'] = '24px'
        y = self.role(f"{self.candidate['id']}/space/control",'paddingTop',14,key)
        with self.assertRaisesRegex(ValueError,'Duplicate semantic'):
            self.plan(x,y)

    def test_explicit_zero_is_a_native_target_not_an_empty_value(self):
        self.candidate['control_styles']['mobile']['Return']['radius'] = 0
        key = f"{self.candidate['id']}.mobile.component.Return"
        role = self.role('radius/control','cornerRadius',0,key)
        self.assertEqual(self.plan(role)[0]['value'],0)


class ProductButtonTokenTests(unittest.TestCase):
    setUp = TokenPlanTests.setUp
    role = TokenPlanTests.role
    plan = TokenPlanTests.plan
    def test_passive_buttons_bind_font_and_spacing_through_their_shared_main(self):
        from draft_token_plan import authored_fields
        state = self.graph['draft_prototype']['entry_state']
        self.candidate['control_styles']['desktop']['Primary']['font'] = 'display'
        self.candidate['state_layouts']['desktop'][state]['product_buttons'] = {
            'product': {'box': [20, 20, 150, 60], 'variant': 'Primary', 'label': 'Actual product'}}
        main = f"{self.candidate['id']}.desktop.component.Primary"
        button = f"{self.candidate['id']}.desktop.{state}.product"
        family = self.candidate['fonts']['display']['family']
        self.assertEqual(authored_fields(self.candidate, self.graph)[button + '.label']['fontFamily'], family)
        role = self.role('type/product', 'fontFamily', family, button + '.label')
        with self.assertRaisesRegex(ValueError, 'same role on its main'):
            self.plan(role)
        role['native']['bindings'].append({'key': main + '.label', 'field': 'fontFamily'})
        self.assertEqual(len(self.plan(role)[0]['bindings']), 2)

    def test_legacy_font_roles_follow_style_role_even_when_families_match(self):
        state = self.graph['draft_prototype']['entry_state']
        self.candidate['fonts']['display']['family'] = self.candidate['fonts']['body']['family']
        self.candidate['control_styles']['desktop']['Primary']['font'] = 'display'
        self.candidate['state_layouts']['desktop'][state]['product_buttons'] = {
            'product': {'box': [20, 20, 150, 60], 'variant': 'Primary', 'label': 'Actual product'}}
        role = {'kind': 'typography', 'token': 'type/body', 'alias': 'font/body',
                'value': self.candidate['fonts']['body']['family']}
        bindings = self.plan(role)[0]['bindings']
        self.assertNotIn(f"{self.candidate['id']}.desktop.{state}.product.label", [binding['key'] for binding in bindings])

    def test_product_only_colors_and_strokes_are_real_named_consumers(self):
        from test_draft_color_consumers import source_fixture, extra_color
        from draft_token_plan import authored_color_consumers
        source, graph = source_fixture()
        extra_color(source, graph)
        source['control_styles']['desktop']['Product'] = dict(source['control_styles']['desktop']['Primary'], stroke='tint')
        layout = source['state_layouts']['desktop']['COVER']
        layout['product_buttons'] = {'product': {'box': [24, 20, 200, 60], 'variant': 'Product', 'label': 'Buy item'}}
        role = graph['design_foundations']['roles'][-1]
        role['native'] = {'type': 'COLOR', 'value': {'r': 216 / 255, 'g': 229 / 255, 'b': 208 / 255},
                          'bindings': [{'key': 'x.desktop.COVER.product', 'field': 'strokes'}]}
        self.assertEqual(authored_color_consumers(source, graph)[-1]['consumers'],
                         [{'key': 'x.desktop.COVER.product', 'field': 'strokes'}])
        self.assertEqual(foundation_bindings(source, graph)[0]['bindings'][0]['field'], 'strokes')
        layout['product_buttons']['product']['box'][0] = 500
        with self.assertRaisesRegex(ValueError, 'no visible authored'):
            foundation_bindings(source, graph)

    def test_invalid_product_button_cannot_claim_a_color_consumer(self):
        from test_draft_color_consumers import source_fixture
        for change in ('label', 'variant', 'box'):
            source, graph = source_fixture()
            button = {'box': [24, 20, 200, 60], 'variant': 'Primary', 'label': 'Buy item'}
            button[change] = {'label': ' ', 'variant': 'missing', 'box': [0, 0, 0, 60]}[change]
            source['state_layouts']['desktop']['COVER']['product_buttons'] = {'product': button}
            with self.subTest(change=change), self.assertRaises(ValueError):
                foundation_bindings(source, graph)
