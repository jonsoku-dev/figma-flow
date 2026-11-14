"""Regression tests for NF-01 owned component families and Little Hands mapping."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / 'examples' / 'owned-component-families'
LH_DESIGN_DIR = ROOT / 'apps' / 'little-hands' / 'design'

sys.path.insert(0, str(ROOT / 'tools'))
import design_system  # noqa: E402


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prepare = _load_module('nf01_prepare', EXAMPLE_DIR / 'prepare.py')
lh_source = _load_module('lh_source', LH_DESIGN_DIR / 'source.py')


class OwnedComponentFamiliesTests(unittest.TestCase):
    def test_owned_example_provenance_ssot_and_no_external_or_private_leaks(self):
        manifest = json.loads((EXAMPLE_DIR / 'manifest.json').read_text(encoding='utf-8'))
        design = json.loads((EXAMPLE_DIR / 'design.json').read_text(encoding='utf-8'))
        graph = json.loads((EXAMPLE_DIR / 'graph.json').read_text(encoding='utf-8'))

        self.assertEqual(manifest['license'], 'MIT')
        self.assertEqual(manifest['ssot'], 'design.json')
        self.assertEqual(manifest['graph'], 'graph.json')
        self.assertEqual(graph['design_source'], 'design.json')

        owned_layer = next(layer for layer in manifest['layers'] if layer['id'] == 'owned-public-baseline')
        for rel in owned_layer['files']:
            self.assertTrue((EXAMPLE_DIR / rel).is_file(), f'Missing owned file: {rel}')
            content = (EXAMPLE_DIR / rel).read_text(encoding='utf-8')
            self.assertNotIn('/Users/', content)
            self.assertFalse(re.search(r'https?://', content), f'Unexpected external URL in {rel}')

        renderer_js = (EXAMPLE_DIR / 'renderer.js').read_text(encoding='utf-8')
        self.assertIn("fetch('./design.json')", renderer_js)
        self.assertIn("fetch('./graph.json')", renderer_js)
        self.assertNotIn('Participant name', renderer_js)
        self.assertNotIn('Morning session', renderer_js)
        self.assertNotIn('Mina Park', renderer_js)

        provenance = prepare.check_example_provenance(design)
        self.assertEqual(provenance, {'example_id': 'owned-component-families', 'license': 'MIT', 'ssot': 'design.json'})

    def test_owned_example_provenance_rejects_secrets_and_urls(self):
        design = json.loads((EXAMPLE_DIR / 'design.json').read_text(encoding='utf-8'))
        bad_secret = json.loads(json.dumps(design))
        bad_secret['screens'][0]['elements'][0]['dom_source']['control_selector'] = '#id_password'
        with self.assertRaisesRegex(ValueError, 'forbidden'):
            prepare.check_example_provenance(bad_secret)

        bad_url = json.loads(json.dumps(design))
        bad_url['screens'][0]['elements'][0]['dom_source']['selector'] = 'https://example.invalid/form'
        with self.assertRaisesRegex(ValueError, 'forbidden'):
            prepare.check_example_provenance(bad_url)

    def test_core_compiler_and_prepare_delegate_positively_with_nf01_families(self):
        design = json.loads((EXAMPLE_DIR / 'design.json').read_text(encoding='utf-8'))
        resolved = design_system.compile_design(design)
        self.assertEqual(resolved.get('status'), 'ready')
        self.assertEqual(
            sorted(fam['id'] for fam in resolved['componentFamilies']),
            ['checkbox', 'field', 'input', 'radio', 'table-cell', 'table-row'],
        )
        self.assertIn('action-button', resolved['components'])

        elements = {el['id']: el for scr in resolved['screens'] for el in scr['elements']}
        self.assertEqual(elements['radio-session-morning']['variant'], 'selected')
        self.assertEqual(elements['radio-session-afternoon']['variant'], 'unselected')
        self.assertTrue(elements['roster-row-1']['property_values']['showSecondCell'])
        self.assertFalse(elements['roster-row-2']['property_values']['showSecondCell'])

        contract = design_system.compile_graph_component_families(resolved)
        self.assertEqual(contract['schema'], 'figma-flow-semantic-family-contract-v1')
        self.assertEqual(len(contract['componentSets']), 6)

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / 'nf01-out'
            compiled = prepare.prepare_bundle(EXAMPLE_DIR / 'design.json', out_dir, draft_only=True)
            self.assertEqual(compiled['status'], 'ready')
            self.assertEqual(compiled['plugin']['status'], 'draft-only-no-native-authoring')
            self.assertTrue((out_dir / 'preview' / 'resolved.json').is_file())
            self.assertTrue((out_dir / 'preview' / 'styled.html').is_file())
            self.assertTrue((out_dir / 'plugin' / 'draft-preview.json').is_file())

    def test_core_compiler_rejects_invalid_nf01_family_and_disallowed_swap(self):
        design = json.loads((EXAMPLE_DIR / 'design.json').read_text(encoding='utf-8'))

        bad_family = json.loads(json.dumps(design))
        bad_family['componentFamilies'][0]['id'] = 'button'
        with self.assertRaisesRegex(ValueError, 'unsupported component family'):
            design_system.compile_design(bad_family)

        bad_swap = json.loads(json.dumps(design))
        bad_swap['screens'][0]['elements'][0]['property_values']['control'] = {'component': 'table-row', 'variant': 'default'}
        with self.assertRaises(ValueError):
            design_system.compile_design(bad_swap)

    def test_little_hands_nf01_family_design_compiles_with_core_and_preserves_reuse_ids(self):
        design = lh_source.build_family_design(LH_DESIGN_DIR)
        resolved = design_system.compile_design(design)
        self.assertEqual(resolved.get('status'), 'ready')
        self.assertEqual(
            sorted(fam['id'] for fam in resolved['componentFamilies']),
            ['checkbox', 'field', 'input', 'radio', 'table-cell', 'table-row'],
        )
        self.assertEqual(len(resolved['screens']), 4)

        baseline_graph = json.loads((LH_DESIGN_DIR / 'graph.json').read_text(encoding='utf-8'))
        action_cids = {n.get('component_id') for n in baseline_graph['nodes'] if n.get('type') == 'action'}
        self.assertTrue(action_cids)
        self.assertTrue(all(
            cid and cid.startswith(('component-Solid-', 'component-Outline-', 'component-Text-'))
            for cid in action_cids
        ))


if __name__ == '__main__':
    unittest.main()
