"""Local fixture/server checks; these do not certify an actual browser or Figma run."""
import copy
import http.client
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_live_preview as preview


def node(eid, color, metadata=None):
    return {'id': 'native-' + eid, 'semantic_id': eid, 'type': 'INSTANCE',
            'declared_metadata': metadata or {},
            'fills': [{'type': 'SOLID', 'color': color}],
            'strokes': [{'type': 'SOLID', 'color': color}],
            'children': [{'id': eid + '-label', 'type': 'TEXT',
                          'fills': [{'type': 'SOLID', 'color': color}]}]}


class LivePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'app').mkdir()
        (self.root / 'app/index.html').write_text('<main><link rel="stylesheet" href="style.css"></main>')
        (self.root / 'app/style.css').write_text('body{color:red}')
        self.design = {'version': 1, 'tokens': {'palette': {'blue': {'$type': 'color', '$value': '#123456'}},
                      'color': {'brand': {'$type': 'color', '$value': '{palette.blue}'}}},
                      'components': {'button': {'variants': {'primary': {'background': 'color.brand'},
                                                             'secondary': {'border-color': 'color.brand'}}}},
                      'screens': [{'id': 'SCR-CARDS-REVIEW', 'title': 'Review', 'trace': ['REQ-REVIEW'], 'elements': [
                          {'id': 'review-reveal', 'kind': 'component', 'component': 'button',
                           'variant': 'primary', 'text': 'Reveal'}]}]}
        (self.root / 'design.json').write_text(json.dumps(self.design))
        self.color = dict(r=0.2, g=0.4, b=0.6)
        self.readback = {'pages': [{'id': 'page', 'children': [
            node('component:button/primary', self.color, {'token_properties': {'background': 'color.brand'}}),
            node('component:button/secondary', self.color, {'token_properties': {'border-color': 'color.brand'}}),
            node('review-reveal', dict(r=1, g=0, b=0))]}]}
        self.server = preview.start_preview(self.root)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, path, method='GET', headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_native_instance_overrides_component_and_alias_scope(self):
        state = preview.update_preview(self.server, self.readback, 'page',
                                       dict(status='applied', changed_tokens=['palette.blue'], screens=['SCR-CARDS-REVIEW']))
        by_element = {check['element']: check for check in state['checks']}
        self.assertEqual(by_element['review-reveal']['expected'], [255, 0, 0, 1])
        self.assertEqual(by_element['review-retry']['expected'], [51, 102, 153, 1])
        self.assertEqual(by_element['review-complete']['source'], 'native-component-paint')
        self.assertEqual(state['revision'], 1)
        self.assertEqual(self.request('/revision.json')[0], 200)

    def test_revision_pins_all_relative_resources_and_no_write_routes(self):
        self.assertEqual(self.request('/app/revision/0/index.html')[0], 200)
        self.assertEqual(self.request('/app/revision/0/style.css')[0], 200)
        (self.root / 'app/style.css').write_text('body{color:blue}')
        preview.update_preview(self.server, self.readback, 'page', dict(status='unchanged'))
        self.assertEqual(self.request('/app/revision/0/style.css')[0], 409)
        self.assertEqual(self.request('/app/revision/1/style.css')[2], b'body{color:blue}')
        self.assertEqual(self.request('/revision.json', 'POST')[0], 501)
        self.assertEqual(self.request('/revision.json', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('/revision.json', headers={'Cookie': 'unrelated=yes'})[0], 200)
        self.assertEqual(self.request('/revision.json', headers={'Host': 'localhost:' + str(self.server.server_port)})[0], 200)
        self.assertEqual(self.server.preview_state['epoch'], self.server.preview_epoch)
        self.assertEqual(self.request('/app/revision/1/%2e%2e/design.json')[0], 404)
        self.assertEqual(self.request('/design.json')[0], 404)
        self.assertNotIn('X-Frame-Options', self.request('/')[1])

    def test_empty_impacts_never_expand_to_all_screens_or_properties(self):
        for result in [dict(status='baseline'), dict(status='unchanged'),
                       dict(status='baseline', changed_tokens=['palette.blue'], screens=['SCR-CARDS-REVIEW']),
                       dict(status='applied', changed_tokens=['palette.blue'], screens=[]),
                       dict(status='applied', changed_tokens=[], screens=['SCR-CARDS-REVIEW'])]:
            with self.subTest(result=result):
                state = preview.update_preview(self.server, self.readback, 'page', result)
                self.assertEqual(state['screens'], [])
                self.assertEqual(state['checks'], [])
                self.assertTrue(state['unknowns'])

    def test_unchanged_after_applied_clears_prior_measurement_scope(self):
        applied = preview.update_preview(self.server, self.readback, 'page',
                                         dict(status='applied', changed_tokens=['palette.blue'], screens=['SCR-CARDS-REVIEW']))
        self.assertTrue(applied['checks'])
        state = preview.update_preview(self.server, self.readback, 'page', dict(status='unchanged'))
        self.assertEqual(state['revision'], applied['revision'] + 1)
        self.assertEqual(state['status'], 'unchanged')
        self.assertEqual(state['screens'], [])
        self.assertEqual(state['checks'], [])

    def metric_fixture(self):
        self.design['tokens']['space'] = {name: {'$type': 'dimension', '$value': value}
                                          for name, value in [('pad', '16px'), ('round', '12px'), ('font', '16px')]}
        props = {'padding': 'space.pad', 'border-radius': 'space.round', 'font-size': 'space.font'}
        self.design['components']['button']['variants']['primary'].update(props)
        (self.root / 'design.json').write_text(json.dumps(self.design))
        data = copy.deepcopy(self.readback)
        data['pages'][0]['children'][0]['declared_metadata']['token_properties'].update(props)
        data['variables'] = [{'id': 'var-' + name, 'semantic_id': 'space.' + name}
                             for name in ('pad', 'round', 'font')]
        for index in (0, 2):
            target = data['pages'][0]['children'][index]
            target.update(paddingTop=19, paddingRight=20, paddingBottom=21, paddingLeft=22,
                          cornerRadius=12, topLeftRadius=3, topRightRadius=4,
                          bottomRightRadius=5, bottomLeftRadius=6)
            target['boundVariables'] = {field: {'type': 'VARIABLE_ALIAS', 'id': 'var-' + token}
                                       for field, token in [('paddingTop', 'pad'), ('paddingRight', 'pad'),
                                                            ('paddingBottom', 'pad'), ('paddingLeft', 'pad'),
                                                            ('topLeftRadius', 'round'), ('topRightRadius', 'round'),
                                                            ('bottomRightRadius', 'round'), ('bottomLeftRadius', 'round')]}
            target['children'][0].update(fontSize=23, boundVariables={
                'fontSize': {'type': 'VARIABLE_ALIAS', 'id': 'var-font'}})
        return data

    def metrics(self, data):
        state = preview.comparison(self.root, data, 'page',
                                   dict(status='applied', changed_tokens=['space.pad', 'space.round', 'space.font'],
                                        screens=['SCR-CARDS-REVIEW']))
        return state, {check['property']: check for check in state['checks'] if check['element'] == 'review-reveal'}

    def test_metrics_use_actual_individual_native_values_and_binding_evidence(self):
        state, checks = self.metrics(self.metric_fixture())
        expected = {'padding-top': 19, 'padding-right': 20, 'padding-bottom': 21, 'padding-left': 22,
                    'border-top-left-radius': 3, 'border-top-right-radius': 4,
                    'border-bottom-right-radius': 5, 'border-bottom-left-radius': 6, 'font-size': 23}
        self.assertEqual({prop: check['expected'] for prop, check in checks.items()}, expected)
        self.assertTrue(all(check['kind'] == 'px' and check['binding']['status'] == 'observed'
                            for check in checks.values()))
        self.assertEqual(checks['font-size']['native_node'], 'review-reveal-label')
        self.assertTrue(any(check['source'] == 'native-component-metric' for check in state['checks']))
        self.assertEqual(state['unknowns'], [])

    def test_radius_fallback_requires_absent_individual_fields_not_mixed_values(self):
        data = self.metric_fixture()
        target = data['pages'][0]['children'][2]
        del target['topLeftRadius']
        target['topRightRadius'] = 'mixed'
        target['bottomLeftRadius'] = None
        _, checks = self.metrics(data)
        self.assertEqual(checks['border-top-left-radius']['expected'], 12)
        self.assertEqual(checks['border-top-left-radius']['native_field'], 'cornerRadius')
        self.assertEqual(checks['border-top-left-radius']['binding']['field'], 'topLeftRadius')
        self.assertNotIn('border-top-right-radius', checks)
        self.assertNotIn('border-bottom-left-radius', checks)
        self.assertEqual(checks['border-bottom-right-radius']['expected'], 5)
        target['unavailable_fields'] = {'topLeftRadius': 'getter unavailable'}
        _, checks = self.metrics(data)
        self.assertNotIn('border-top-left-radius', checks)

    def test_metrics_reject_invalid_hidden_or_ambiguous_native_values(self):
        for value in [True, False, None, 'mixed', float('nan'), float('inf'), -1]:
            with self.subTest(value=value):
                data = self.metric_fixture()
                data['pages'][0]['children'][2]['paddingTop'] = value
                state, checks = self.metrics(data)
                self.assertNotIn('padding-top', checks)
                self.assertTrue(any('padding-top' in item for item in state['unknowns']))
        data = self.metric_fixture()
        data['pages'][0]['children'][2]['visible'] = False
        _, checks = self.metrics(data)
        self.assertEqual(checks, {})
        data = self.metric_fixture()
        target = data['pages'][0]['children'][2]
        target['children'].append(copy.deepcopy(target['children'][0]))
        _, checks = self.metrics(data)
        self.assertNotIn('font-size', checks)
        data = self.metric_fixture()
        data['pages'][0]['children'][2]['children'][0]['visible'] = False
        _, checks = self.metrics(data)
        self.assertNotIn('font-size', checks)

    def test_binding_missing_or_mismatched_is_explicit_unknown_not_equivalence(self):
        data = self.metric_fixture()
        target = data['pages'][0]['children'][2]
        del target['boundVariables']['paddingTop']
        target['boundVariables']['paddingRight']['id'] = 'var-round'
        target['boundVariables']['paddingBottom']['id'] = 'absent'
        state, checks = self.metrics(data)
        self.assertEqual(checks['padding-top']['binding']['status'], 'missing')
        self.assertEqual(checks['padding-right']['binding']['status'], 'mismatch')
        self.assertEqual(checks['padding-bottom']['binding']['status'], 'unresolved')
        self.assertEqual(checks['padding-right']['expected'], 20)
        self.assertEqual(len(state['unknowns']), 3)
        target['boundVariables'] = None
        _, checks = self.metrics(data)
        self.assertEqual(checks['padding-top']['binding']['status'], 'missing')

    def test_text_font_size_single_array_binding_observed_mixed_arrays_unknown(self):
        data = self.metric_fixture()
        label = data['pages'][0]['children'][2]['children'][0]
        reference = label['boundVariables']['fontSize']
        label['boundVariables']['fontSize'] = [reference]
        state, checks = self.metrics(data)
        self.assertEqual(checks['font-size']['expected'], 23)
        self.assertEqual(checks['font-size']['binding']['status'], 'observed')
        self.assertEqual(state['unknowns'], [])
        for mixed in [[], [reference, reference], [reference, {'type': 'VARIABLE_ALIAS', 'id': 'var-round'}]]:
            with self.subTest(mixed=mixed):
                label['boundVariables']['fontSize'] = mixed
                state, checks = self.metrics(data)
                self.assertEqual(checks['font-size']['binding']['status'], 'ambiguous')
                self.assertTrue(any('font-size' in message and 'ambiguous' in message for message in state['unknowns']))

    def test_before_snapshot_uses_native_before_and_frozen_app_bytes(self):
        after = self.metric_fixture()
        before = copy.deepcopy(after)
        before['pages'][0]['children'][2]['paddingTop'] = 8
        captured = preview.snapshot_app(self.root)
        (self.root / 'app/style.css').write_text('body{color:blue}')
        (self.root / 'app/before').mkdir()
        (self.root / 'app/before/only-after.txt').write_text('after-only')
        result = dict(status='applied', changed_tokens=['space.pad'], screens=['SCR-CARDS-REVIEW'])
        state = preview.update_preview(self.server, after, 'page', result, previous=(before, captured))
        self.assertTrue(state['before_available'])
        def top(checks):
            return next(check['expected'] for check in checks if check['element'] == 'review-reveal'
                        and check['property'] == 'padding-top')
        self.assertEqual(top(state['checks']), 19)
        self.assertEqual(top(state['before_checks']), 8)
        captured['/style.css'] = b'tampered'
        self.assertEqual(self.request('/before/revision/1/style.css')[2], b'body{color:red}')
        self.assertEqual(self.request('/app/revision/1/style.css')[2], b'body{color:blue}')
        # A real app file under app/before/ is no longer shadowed by the snapshot route.
        self.assertEqual(self.request('/app/revision/1/before/only-after.txt')[2], b'after-only')
        self.assertEqual(self.request('/before/revision/1/only-after.txt')[0], 404)
        self.assertEqual(self.request('/before/revision/1/%2e%2e/style.css')[0], 404)
        preview.update_preview(self.server, after, 'page', result)
        self.assertEqual(self.request('/before/revision/1/style.css')[0], 409)
        self.assertEqual(self.request('/before/revision/2/style.css')[0], 404)
        self.assertFalse(self.server.preview_state['before_available'])
        self.assertEqual(self.server.preview_state['before_checks'], [])

    def test_missing_invalid_before_is_unknown_without_synthetic_checks(self):
        data = self.metric_fixture()
        result = dict(status='applied', changed_tokens=['space.pad'], screens=['SCR-CARDS-REVIEW'])
        self.assertFalse(self.server.preview_state['before_available'])
        self.assertEqual(self.server.preview_state['before_checks'], [])
        state = preview.update_preview(self.server, data, 'page', result,
                                       previous=({'pages': []}, preview.snapshot_app(self.root)))
        self.assertTrue(state['checks'])
        self.assertFalse(state['before_available'])
        self.assertEqual(state['before_checks'], [])
        self.assertTrue(state['before_unknowns'])
        self.assertEqual(self.request('/app/revision/1/before/index.html')[0], 404)
        for captured in [{}, {'/index.html': b'html', '/../private': b'private'}, {'/index.html': 'not-bytes'}]:
            with self.subTest(captured=captured), self.assertRaises(ValueError):
                preview.update_preview(self.server, data, 'page', result, previous=(data, captured))
        self.assertEqual(self.server.preview_state['revision'], 1)
        before = copy.deepcopy(data)
        before['pages'][0]['children'][2]['paddingTop'] = 'mixed'
        state = preview.update_preview(self.server, data, 'page', result,
                                       previous=(before, preview.snapshot_app(self.root)))
        self.assertFalse(any(check['element'] == 'review-reveal' and check['property'] == 'padding-top'
                             for check in state['before_checks']))
        self.assertTrue(any('padding-top' in message for message in state['before_unknowns']))

    def test_symlinks_are_not_served_and_unsupported_paints_are_unknown(self):
        (self.root / 'outside.txt').write_text('private')
        (self.root / 'app/link.txt').symlink_to(self.root / 'outside.txt')
        data = copy.deepcopy(self.readback)
        data['pages'][0]['children'][2]['fills'] = [{'type': 'GRADIENT_LINEAR'}]
        state = preview.update_preview(self.server, data, 'page', dict(status='applied', changed_tokens=['palette.blue'], screens=['SCR-CARDS-REVIEW']))
        self.assertTrue(any('지원하지 않는 paint' in value for value in state['unknowns']))
        self.assertFalse(any(check['element'] == 'review-reveal' for check in state['checks']))
        self.assertEqual(self.request('/app/revision/1/link.txt')[0], 404)
        with self.assertRaises(ValueError):
            preview.update_preview(self.server, data, 'wrong-page', {})
        self.assertEqual(self.server.preview_state['revision'], 1)


if __name__ == '__main__':
    unittest.main()
