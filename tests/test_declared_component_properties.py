"""Declared native property authoring stays in the ordinary source/bridge path."""
import copy
import json
import os
import tempfile
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from design_system import compile_design, render, render_svg
from figma_bridge import validate, compare_declared_component_properties, compare_import


class DeclaredComponentPropertyTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT / 'tests/fixtures/declared-component-properties.json').read_text())

    def test_source_compile_and_bridge_preserve_declarations_and_overrides(self):
        before = copy.deepcopy(self.source)
        resolved = compile_design(self.source)
        validate(resolved)
        self.assertEqual(resolved['components']['button']['properties'], before['components']['button']['properties'])
        self.assertEqual(resolved['screens'], before['screens'])
        self.assertEqual(self.source, before)

    def test_invalid_contract_is_rejected_in_source_and_resolved_bridge(self):
        for mutation in (
            lambda d: d['components']['button']['properties']['ShowLabel'].update(default_value='false'),
            lambda d: d['components']['button']['properties']['ShowLabel'].update(target='unknown'),
            lambda d: d['components']['button']['properties']['Symbol'].update(default_value={'component': 'missing', 'variant': 'circle'}),
            lambda d: d['components']['button']['properties']['Symbol'].update(preferred_values=[{'component': 'symbol', 'variant': 'missing'}]),
            lambda d: d['components']['button']['properties']['Symbol'].update(default_value={'component': 'button', 'variant': 'default'}),
            lambda d: d['screens'][0]['elements'][1]['property_values'].update(Unknown=True),
            lambda d: d['screens'][0]['elements'][1]['property_values'].update(ShowLabel=1),
            lambda d: d['screens'][0]['elements'][1]['property_values'].update(Symbol={'component': 'button', 'variant': 'default'}),
        ):
            source = copy.deepcopy(self.source)
            mutation(source)
            with self.assertRaises(ValueError):
                compile_design(source)
            resolved = compile_design(copy.deepcopy(self.source))
            mutation(resolved)
            with self.assertRaises(ValueError):
                validate(resolved)

    def test_html_and_svg_previews_apply_defaults_overrides_and_nested_variant_styles(self):
        self.source['tokens']['color']['accent'] = {'$type': 'color', '$value': '#f00f00'}
        self.source['components']['symbol']['variants']['square']['color'] = 'color.accent'
        design = compile_design(self.source)
        page, _css = render(design, True)
        body = page.split('</style>', 1)[1]
        self.assertIn('data-component-root="true"', page)
        self.assertIn('button--default', body)
        self.assertIn('symbol--circle', body)
        self.assertIn('symbol--square', body)
        self.assertIn('.symbol--square { color: var(--color-accent);', page)
        self.assertIn('>Default</span>', body)
        self.assertNotIn('>Swapped</span>', body, 'ShowLabel=false hides the instance label')
        self.assertEqual(body.count('symbol--circle'), 1, 'ShowSymbol=false omits the slot subtree')

        svg = render_svg(design, design['screens'][0], True)
        self.assertIn('fill="#f00f00"', svg, 'the overridden square variant uses its own token style')
        self.assertIn('>Default</text>', svg)
        self.assertNotIn('>Swapped</text>', svg)
        self.assertEqual(svg.count('>symbol</text>'), 2, 'hidden slots do not render; visible slots keep component label semantics')

    def test_component_preview_expansion_is_bounded_for_acyclic_dags(self):
        for index in range(10):
            name = f'layer-{index}'
            next_component = 'leaf' if index == 9 else f'layer-{index + 1}'
            self.source['components'][name] = {
                'variants': {'default': {'color': 'color.ink'}},
                'properties': {
                    'Left': {'type': 'INSTANCE_SWAP', 'target': 'left', 'default_value': {'component': next_component, 'variant': 'default'}},
                    'Right': {'type': 'INSTANCE_SWAP', 'target': 'right', 'default_value': {'component': next_component, 'variant': 'default'}},
                },
            }
        self.source['components']['leaf'] = {'variants': {'default': {'color': 'color.ink'}}}
        self.source['screens'][0]['elements'] = [{
            'id': 'dag', 'kind': 'component', 'component': 'layer-0', 'variant': 'default', 'text': 'Root'
        }]
        design = compile_design(self.source)
        with self.assertRaisesRegex(ValueError, 'preview expansion exceeds its bound'):
            render(design, True)
        with self.assertRaisesRegex(ValueError, 'preview expansion exceeds its bound'):
            render_svg(design, design['screens'][0], True)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.json'
            output = Path(directory) / 'output'
            source.write_text(json.dumps(self.source))
            result = subprocess.run([sys.executable, str(ROOT / 'tools/design_system.py'), '--input', str(source), '--out', str(output)],
                                    cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists(), 'failed preview generation must not create partial output')

    def test_cli_preview_includes_declared_component_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.json'
            output = Path(directory) / 'output'
            source.write_text(json.dumps(self.source))
            result = subprocess.run([sys.executable, str(ROOT / 'tools/design_system.py'), '--input', str(source), '--out', str(output)],
                                    cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            page = (output / 'styled.html').read_text()
            svg = (output / 'properties-demo-styled.svg').read_text()
            self.assertIn('symbol--square', page)
            self.assertIn('"variant": "square"', (output / 'resolved.json').read_text())
            self.assertIn('>Default</text>', svg)

    def test_property_free_components_keep_the_plain_preview_markup(self):
        for component in self.source['components'].values():
            component.pop('properties', None)
        for element in self.source['screens'][0]['elements']:
            element.pop('property_values', None)
        design = compile_design(self.source)
        page, _css = render(design, True)
        self.assertIn('<div class="component button--default">Default</div>', page)
        self.assertNotIn('component-property-node', page)

    def test_actual_importer_component_loop(self):
        result = subprocess.run(['node', '--test', str(ROOT / 'tests/test_declared_component_properties.cjs')], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class DeclaredPropertyReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'observed.json'
            result = subprocess.run(['node', '--test', str(ROOT / 'tests/test_declared_component_properties.cjs')], cwd=ROOT,
                env=dict(os.environ, FIGMA_DECLARED_READBACK_PATH=str(path)), text=True, capture_output=True)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            cls.observed = json.loads(path.read_text())
        cls.expected = compile_design(json.loads((ROOT / 'tests/fixtures/declared-component-properties.json').read_text()))

    def nodes(self, page):
        result = []
        def walk(node):
            result.append(node)
            for child in node.get('children', []):
                walk(child)
        walk(page)
        return result

    def test_complete_snapshot_checks_definitions_references_defaults_and_instances(self):
        checks = compare_declared_component_properties(self.observed, self.expected)
        self.assertTrue(checks)
        self.assertEqual({item['status'] for item in checks}, {'match'})
        self.assertEqual({item['scope'] for item in checks}, {'definition', 'default', 'preferred-values', 'layer-reference', 'actual-target', 'instance-value', 'instance-target'})
        for node in self.nodes(self.observed):
            if '/slot:' in (node.get('semantic_id') or ''):
                self.assertEqual(node['semantic_id'], node['declared_metadata']['semantic_id'])

    def test_drift_and_missing_observed_fields_fail_instead_of_trusting_metadata(self):
        for field in ('componentPropertyDefinitions', 'componentPropertyReferences', 'preferredValues', 'componentProperties', 'main_component_id', 'visible'):
            page = copy.deepcopy(self.observed)
            nodes = self.nodes(page)
            if field == 'componentPropertyDefinitions':
                owner = next(node for node in nodes if node.get('name') == 'button' and node['type'] == 'COMPONENT_SET')
                del owner[field]
            elif field == 'preferredValues':
                owner = next(node for node in nodes if node.get('name') == 'button' and node['type'] == 'COMPONENT_SET')
                definition = next(prop for prop in owner['componentPropertyDefinitions'].values() if prop['type'] == 'INSTANCE_SWAP')
                definition[field][0]['key'] = 'wrong-key'
            elif field == 'componentPropertyReferences':
                child = next(node for node in nodes if node.get('semantic_id') == 'component:button/default/slot:symbol')
                child[field]['mainComponent'] = 'wrong#key'
            elif field == 'componentProperties':
                instance = next(node for node in nodes if node.get('semantic_id') == 'default-button')
                del instance[field]
            else:
                child = next(node for node in nodes if node.get('semantic_id') == 'swapped-button/slot:symbol')
                child[field] = False if field == 'visible' else 'wrong-main'
            checks = compare_declared_component_properties(page, self.expected)
            self.assertIn('changed', {item['status'] for item in checks}, field)

    def test_reused_user_overrides_are_reported_changed_without_mutation(self):
        page = copy.deepcopy(self.observed)
        instance = next(node for node in self.nodes(page) if node.get('semantic_id') == 'default-button')
        key = next(key for key in instance['componentProperties'] if key.startswith('ShowLabel#'))
        instance['componentProperties'][key]['value'] = False
        instance['children'][0]['visible'] = False
        before = copy.deepcopy(page)
        checks = compare_declared_component_properties(page, self.expected)
        self.assertTrue(any(item['scope'] == 'instance-value' and item['status'] == 'changed' for item in checks))
        self.assertEqual(page, before)

    def test_import_comparison_includes_declared_property_checks_and_legacy_is_additive(self):
        page = copy.deepcopy(self.observed)
        page['source_sha256'] = 'digest'
        result = compare_import(page, self.expected, 'digest', {}, {})
        self.assertEqual({item['status'] for item in result['component_property_checks']}, {'match'})
        legacy = copy.deepcopy(self.expected)
        for definition in legacy['components'].values():
            definition.pop('properties', None)
        self.assertEqual(compare_declared_component_properties(page, legacy), [])


if __name__ == '__main__':
    unittest.main()
