"""Regression tests for scope-pinned NF-01 component families native-edit provisioning."""
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

import family_provision  # noqa: E402
import native_edit  # noqa: E402


def sample_six_family_design():
    return {
        'version': 1,
        'tokens': {
            'color': {
                'ink': {'$type': 'color', '$value': '#1f242b'},
                'muted': {'$type': 'color', '$value': '#59616b'},
                'surface': {'$type': 'color', '$value': '#ffffff'},
                'border': {'$type': 'color', '$value': '#c7cdd4'},
                'accent': {'$type': 'color', '$value': '#1849a5'},
                'danger': {'$type': 'color', '$value': '#b42318'},
            },
            'space': {
                'xs': {'$type': 'dimension', '$value': '4px'},
                'sm': {'$type': 'dimension', '$value': '8px'},
            },
            'radius': {
                'sm': {'$type': 'dimension', '$value': '4px'},
            },
            'font': {
                'body': {'$type': 'fontFamily', '$value': 'Inter'},
                'size': {'$type': 'dimension', '$value': '14px'},
            },
        },
        'componentFamilies': [
            {
                'id': 'input',
                'version': 1,
                'component': 'input',
                'layout': 'HORIZONTAL',
                'axes': {'state': ['default', 'focus', 'error', 'disabled']},
                'properties': [
                    {'id': 'value', 'name': 'Value', 'type': 'TEXT', 'targetKey': 'label', 'default_value': 'Sample input'},
                ],
            },
            {
                'id': 'checkbox',
                'version': 1,
                'component': 'checkbox',
                'layout': 'HORIZONTAL',
                'axes': {'state': ['unchecked', 'checked', 'disabled']},
                'properties': [
                    {'id': 'optionLabel', 'name': 'Label', 'type': 'TEXT', 'targetKey': 'label', 'default_value': 'Confirm guide'},
                ],
            },
            {
                'id': 'radio',
                'version': 1,
                'component': 'radio',
                'layout': 'HORIZONTAL',
                'axes': {'state': ['unselected', 'selected', 'disabled']},
                'properties': [
                    {'id': 'choiceLabel', 'name': 'Label', 'type': 'TEXT', 'targetKey': 'label', 'default_value': 'Morning slot'},
                ],
            },
            {
                'id': 'field',
                'version': 1,
                'component': 'field',
                'layout': 'VERTICAL',
                'axes': {'state': ['default', 'error', 'disabled']},
                'properties': [
                    {'id': 'label', 'name': 'Label', 'type': 'TEXT', 'targetKey': 'field-label', 'default_value': 'Participant'},
                    {'id': 'helpText', 'name': 'Help', 'type': 'TEXT', 'targetKey': 'field-help', 'default_value': 'Sample helper text'},
                    {'id': 'showHelp', 'name': 'Show help', 'type': 'BOOLEAN', 'targetKey': 'field-help', 'default_value': True},
                    {
                        'id': 'control',
                        'name': 'Control',
                        'type': 'INSTANCE_SWAP',
                        'targetKey': 'field-control',
                        'allowedFamilyIds': ['input', 'checkbox', 'radio'],
                        'default_value': {'component': 'input', 'variant': 'default'},
                        'preferred_values': [
                            {'component': 'input', 'variant': 'default'},
                            {'component': 'checkbox', 'variant': 'unchecked'},
                            {'component': 'radio', 'variant': 'unselected'},
                        ],
                    },
                ],
            },
            {
                'id': 'table-cell',
                'version': 1,
                'component': 'table-cell',
                'layout': 'HORIZONTAL',
                'axes': {'state': ['default', 'header']},
                'properties': [
                    {'id': 'cellText', 'name': 'Cell text', 'type': 'TEXT', 'targetKey': 'label', 'default_value': 'Sample cell'},
                ],
            },
            {
                'id': 'table-row',
                'version': 1,
                'component': 'table-row',
                'layout': 'HORIZONTAL',
                'axes': {'state': ['default', 'selected']},
                'properties': [
                    {
                        'id': 'firstCell',
                        'name': 'Cell',
                        'type': 'INSTANCE_SWAP',
                        'targetKey': 'cell-0',
                        'allowedFamilyIds': ['table-cell'],
                        'default_value': {'component': 'table-cell', 'variant': 'default'},
                    },
                    {
                        'id': 'secondCell',
                        'name': 'Cell',
                        'type': 'INSTANCE_SWAP',
                        'targetKey': 'cell-1',
                        'allowedFamilyIds': ['table-cell'],
                        'default_value': {'component': 'table-cell', 'variant': 'default'},
                    },
                    {'id': 'showSecondCell', 'name': 'Show optional column', 'type': 'BOOLEAN', 'targetKey': 'cell-1', 'default_value': True},
                ],
            },
        ],
        'components': {
            'input': {
                'usage': 'Sample input states',
                'variants': {
                    'default': {'color': 'color.ink', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.sm', 'border-radius': 'radius.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'focus': {'color': 'color.ink', 'background': 'color.surface', 'border-color': 'color.accent', 'padding': 'space.sm', 'border-radius': 'radius.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'error': {'color': 'color.danger', 'background': 'color.surface', 'border-color': 'color.danger', 'padding': 'space.sm', 'border-radius': 'radius.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'disabled': {'color': 'color.muted', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.sm', 'border-radius': 'radius.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
            'checkbox': {
                'usage': 'Sample checkbox states',
                'variants': {
                    'unchecked': {'color': 'color.ink', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.xs', 'gap': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'checked': {'color': 'color.accent', 'background': 'color.surface', 'border-color': 'color.accent', 'padding': 'space.xs', 'gap': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'disabled': {'color': 'color.muted', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.xs', 'gap': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
            'radio': {
                'usage': 'Sample radio states',
                'variants': {
                    'unselected': {'color': 'color.ink', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.xs', 'gap': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'selected': {'color': 'color.accent', 'background': 'color.surface', 'border-color': 'color.accent', 'padding': 'space.xs', 'gap': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'disabled': {'color': 'color.muted', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.xs', 'gap': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
            'field': {
                'usage': 'Sample field states',
                'variants': {
                    'default': {'color': 'color.ink', 'background': 'color.surface', 'padding': 'space.sm', 'gap': 'space.xs', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'error': {'color': 'color.danger', 'background': 'color.surface', 'padding': 'space.sm', 'gap': 'space.xs', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'disabled': {'color': 'color.muted', 'background': 'color.surface', 'padding': 'space.sm', 'gap': 'space.xs', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
            'table-cell': {
                'usage': 'Sample table cell states',
                'variants': {
                    'default': {'color': 'color.ink', 'background': 'color.surface', 'padding': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'header': {'color': 'color.ink', 'background': 'color.surface', 'border-color': 'color.border', 'padding': 'space.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
            'table-row': {
                'usage': 'Sample table row states',
                'variants': {
                    'default': {'color': 'color.ink', 'background': 'color.surface', 'border-color': 'color.border', 'gap': 'space.sm', 'padding': 'space.xs', 'font-family': 'font.body', 'font-size': 'font.size'},
                    'selected': {'color': 'color.accent', 'background': 'color.surface', 'border-color': 'color.accent', 'gap': 'space.sm', 'padding': 'space.xs', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
            'action-button': {
                'usage': 'Undeclared control stays outside NF-01 family sets',
                'variants': {
                    'primary': {'color': 'color.surface', 'background': 'color.accent', 'padding': 'space.sm', 'border-radius': 'radius.sm', 'font-family': 'font.body', 'font-size': 'font.size'},
                },
            },
        },
        'screens': [
            {
                'id': 'sample-screen',
                'title': 'Sample Form and Roster',
                'trace': ['REQ-SAMPLE-1'],
                'elements': [
                    {
                        'id': 'field-primary',
                        'kind': 'component',
                        'component': 'field',
                        'variant': 'default',
                        'text': 'Participant',
                        'property_values': {
                            'label': 'Participant',
                            'helpText': 'Sample helper text',
                            'showHelp': True,
                            'control': {'component': 'input', 'variant': 'default'},
                        },
                    },
                    {
                        'id': 'field-secondary',
                        'kind': 'component',
                        'component': 'field',
                        'variant': 'error',
                        'text': 'Safety check',
                        'property_values': {
                            'label': 'Safety check',
                            'helpText': 'Confirm notice',
                            'showHelp': True,
                            'control': {'component': 'checkbox', 'variant': 'checked'},
                        },
                    },
                    {
                        'id': 'radio-choice-a',
                        'kind': 'component',
                        'component': 'radio',
                        'variant': 'selected',
                        'text': 'Morning slot',
                        'property_values': {'choiceLabel': 'Morning slot'},
                    },
                    {
                        'id': 'row-1',
                        'kind': 'component',
                        'component': 'table-row',
                        'variant': 'default',
                        'text': 'Row 1',
                        'property_values': {
                            'firstCell': {'component': 'table-cell', 'variant': 'header'},
                            'secondCell': {'component': 'table-cell', 'variant': 'default'},
                            'showSecondCell': True,
                        },
                    },
                    {
                        'id': 'submit-btn',
                        'kind': 'component',
                        'component': 'action-button',
                        'variant': 'primary',
                        'text': 'Save',
                    },
                ],
            }
        ],
    }


def sample_discovery(*, file_key='sample_file_01', page_id='10:1', include_sibling=True, extra_nodes=()):
    nodes = [
        {
            'id': page_id,
            'parentId': '0:0',
            'type': 'PAGE',
            'name': 'Test Page',
            'semanticKey': None,
        },
    ]
    if include_sibling:
        nodes.append({
            'id': '10:2',
            'parentId': page_id,
            'type': 'FRAME',
            'name': 'Existing Screen',
            'semanticKey': None,
            'x': 0,
            'y': 0,
            'width': 1200,
            'height': 800,
            'absoluteBoundingBox': {'x': 0, 'y': 0, 'width': 1200, 'height': 800},
        })
    nodes.extend(extra_nodes)
    return {
        'schema': 'figma-flow-graph-native-discovery-v1',
        'fileKey': file_key,
        'pageId': page_id,
        'allowed_page_ids': [page_id],
        'nodes': nodes,
        'collections': [],
        'variables': [],
    }


class FamilyProvisionPlanTests(unittest.TestCase):
    def test_cli_compiles_linked_graph_and_workspace_bundle_with_pinned_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            design_path = base / 'design.json'
            graph_path = base / 'graph.json'
            readback_path = base / 'readback.json'
            plan_path = base / 'plan.json'
            ws_dir = base / 'workspace'
            assigned_path = base / 'assigned.json'
            assigned_path.write_text('{"id": "987654321"}\n', encoding='utf-8')

            design_bytes = (json.dumps(sample_six_family_design(), indent=2) + '\n').encode('utf-8')
            design_path.write_bytes(design_bytes)
            graph_bytes = (json.dumps({
                'version': 1,
                'id': 'sample-owned-families',
                'title': 'Sample Owned Families',
                'design_source': 'design.json',
                'nodes': [],
                'edges': [],
            }, indent=2) + '\n').encode('utf-8')
            graph_path.write_bytes(graph_bytes)
            rb_bytes = (json.dumps(sample_discovery(), indent=2) + '\n').encode('utf-8')
            readback_path.write_bytes(rb_bytes)

            proc = subprocess.run(
                [
                    sys.executable, '-B', str(ROOT / 'tools' / 'native_edit.py'),
                    'component-families',
                    '--graph', str(graph_path),
                    '--readback', str(readback_path),
                    '--file-key', 'sample_file_01',
                    '--page-id', '10:1',
                    '--out', str(plan_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            receipt = json.loads(proc.stdout)
            self.assertEqual(receipt['status'], 'prepared-not-executed')
            self.assertEqual(receipt['position'], {'x': 1296, 'y': 0})
            self.assertEqual(sorted(receipt['families']), ['checkbox', 'field', 'input', 'radio', 'table-cell', 'table-row'])
            self.assertEqual(receipt['instance_count'], 4)
            self.assertFalse(receipt['existing_workbench'])

            init_proc = subprocess.run(
                [
                    sys.executable, '-B', str(ROOT / 'tools' / 'figma_workspace.py'),
                    'init', '--workspace', str(ws_dir), '--id-from', str(assigned_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn('987654321', init_proc.stdout)

            ws_proc = subprocess.run(
                [
                    sys.executable, '-B', str(ROOT / 'tools' / 'figma_workspace.py'),
                    'prepare',
                    '--workspace', str(ws_dir),
                    '--key', 'nf01-family-proof',
                    '--title', 'NF-01 Family Proof',
                    '--project', 'sample',
                    '--kind', 'native-edit',
                    '--',
                    '--plan', str(plan_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            ws_receipt = json.loads(ws_proc.stdout)
            import figma_workspace
            catalogue = figma_workspace.current(ws_dir)
            task = next(row for row in catalogue['tasks'] if row['key'] == 'nf01-family-proof')
            self.assertEqual(task['kind'], 'native-edit')
            self.assertEqual(task['fileKey'], 'sample_file_01')
            self.assertEqual(task['pageId'], '10:1')
            self.assertEqual(task['revision'], ws_receipt['revision'])
            task_bundle = figma_workspace.task_artifacts(ws_dir, task)
            code_js = (task_bundle / 'code.js').read_text(encoding='utf-8')
            self.assertEqual(subprocess.run(['node', '--check', str(task_bundle / 'code.js')], capture_output=True).returncode, 0)
            self.assertIn('ensureSemanticComponents', code_js)
            self.assertIn('nativeFamilyProvisionRun', code_js)
            self.assertNotIn(str(base), code_js)
            plan_line = next(line for line in code_js.splitlines() if line.startswith('const NATIVE_EDIT_PLAN = '))
            embedded_plan = json.loads(plan_line[len('const NATIVE_EDIT_PLAN = '):-1])
            self.assertNotIn('source_graph_path', embedded_plan['provision'])
            self.assertNotIn('design_source_path', embedded_plan['provision'])
            self.assertNotIn('readback_path', embedded_plan['provision'])

            pins_doc = json.loads((task_bundle / 'source-inputs.json').read_text(encoding='utf-8'))
            self.assertEqual(pins_doc['schema'], 'figma-flow-source-pins-v1')
            pins_by_path = {entry['path']: entry['sha256'] for entry in pins_doc['pins']}
            self.assertEqual(pins_by_path[str(plan_path.resolve())], hashlib.sha256(plan_path.read_bytes()).hexdigest())
            self.assertEqual(pins_by_path[str(graph_path.resolve())], hashlib.sha256(graph_bytes).hexdigest())
            self.assertEqual(pins_by_path[str(design_path.resolve())], hashlib.sha256(design_bytes).hexdigest())
            self.assertEqual(pins_by_path[str(readback_path.resolve())], hashlib.sha256(rb_bytes).hexdigest())

    def test_repeat_prepare_preserves_existing_workbench_position_and_allows_owned_subtree_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            design_path = base / 'design.json'
            readback_path = base / 'readback.json'
            plan_path = base / 'plan.json'
            design_path.write_text(json.dumps(sample_six_family_design(), indent=2) + '\n', encoding='utf-8')

            existing_nodes = [
                {
                    'id': '20:1',
                    'parentId': '10:1',
                    'type': 'FRAME',
                    'name': 'NF-01 · Component families workbench',
                    'semanticKey': 'nf01.component-families/workbench',
                    'x': 1500,
                    'y': 48,
                    'width': 960,
                    'height': 1400,
                    'absoluteBoundingBox': {'x': 1500, 'y': 48, 'width': 960, 'height': 1400},
                },
                {
                    'id': '20:2',
                    'parentId': '20:1',
                    'type': 'COMPONENT_SET',
                    'name': 'Field',
                    'semanticKey': 'nf01.component-families/set:field',
                    'x': 24,
                    'y': 24,
                    'width': 320,
                    'height': 180,
                    'absoluteBoundingBox': {'x': 1524, 'y': 72, 'width': 320, 'height': 180},
                },
                {
                    'id': '20:3',
                    'parentId': '20:1',
                    'type': 'INSTANCE',
                    'name': 'Participant',
                    'semanticKey': 'nf01.component-families/instance:field-primary',
                    'x': 24,
                    'y': 300,
                    'width': 320,
                    'height': 80,
                    'absoluteBoundingBox': {'x': 1524, 'y': 348, 'width': 320, 'height': 80},
                },
            ]
            readback_path.write_text(
                json.dumps(sample_discovery(extra_nodes=existing_nodes), indent=2) + '\n',
                encoding='utf-8',
            )
            receipt = family_provision.prepare(design_path, readback_path, 'sample_file_01', '10:1', plan_path)
            self.assertTrue(receipt['existing_workbench'])
            self.assertEqual(receipt['position'], {'x': 1500, 'y': 48})
            plan = json.loads(plan_path.read_text(encoding='utf-8'))
            self.assertEqual([row['id'] for row in plan['provision']['page_roots']], ['10:2'])

    def test_rejects_scope_mismatch_collision_tampering_stale_pins_and_invalid_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            design_path = base / 'design.json'
            readback_path = base / 'readback.json'
            design_path.write_text(json.dumps(sample_six_family_design(), indent=2) + '\n', encoding='utf-8')
            readback_path.write_text(json.dumps(sample_discovery(), indent=2) + '\n', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'exact file and existing page'):
                family_provision.prepare(design_path, readback_path, 'wrong_file', '10:1', base / 'bad-file.json')
            with self.assertRaisesRegex(ValueError, 'exact file and existing page'):
                family_provision.prepare(design_path, readback_path, 'sample_file_01', '99:9', base / 'bad-page.json')
            self.assertFalse((base / 'bad-file.json').exists())
            self.assertFalse((base / 'bad-page.json').exists())

            colliding_rb = base / 'collision-readback.json'
            colliding_rb.write_text(
                json.dumps(sample_discovery(extra_nodes=[{
                    'id': '10:9',
                    'parentId': '10:1',
                    'type': 'FRAME',
                    'name': 'Colliding node',
                    'semanticKey': 'nf01.component-families/set:field',
                    'x': 0,
                    'y': 900,
                    'width': 100,
                    'height': 100,
                    'absoluteBoundingBox': {'x': 0, 'y': 900, 'width': 100, 'height': 100},
                }]), indent=2) + '\n',
                encoding='utf-8',
            )
            with self.assertRaisesRegex(ValueError, 'outside the owned workbench'):
                family_provision.prepare(design_path, colliding_rb, 'sample_file_01', '10:1', base / 'collision.json')

            bad_family_doc = sample_six_family_design()
            bad_family_doc['componentFamilies'][0]['id'] = 'button'
            bad_family_path = base / 'bad-family.json'
            bad_family_path.write_text(json.dumps(bad_family_doc, indent=2) + '\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                family_provision.prepare(bad_family_path, readback_path, 'sample_file_01', '10:1', base / 'bad-fam-plan.json')

            traversal_graph = base / 'traversal-graph.json'
            traversal_graph.write_text(json.dumps({'version': 1, 'id': 'bad', 'design_source': '../outside.json'}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'within the graph directory'):
                family_provision.prepare(traversal_graph, readback_path, 'sample_file_01', '10:1', base / 'trav-plan.json')

            valid_plan_path = base / 'valid-plan.json'
            family_provision.prepare(design_path, readback_path, 'sample_file_01', '10:1', valid_plan_path)
            valid_plan = json.loads(valid_plan_path.read_text(encoding='utf-8'))

            tampered = copy.deepcopy(valid_plan)
            tampered['provision']['contract']['instances'][0]['propertyValues']['label'] = 'Tampered after compile'
            with self.assertRaisesRegex(ValueError, 'differs from its pinned canonical sources'):
                native_edit.validate_plan(tampered)

            design_path.write_text(json.dumps(sample_six_family_design(), indent=4) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed or is unavailable'):
                native_edit.prepare(valid_plan_path, base / 'stale-bundle')

    def test_empty_dedicated_page_places_workbench_at_origin_for_owned_example(self):
        owned_design = ROOT / 'examples' / 'owned-component-families' / 'design.json'
        owned_graph = ROOT / 'examples' / 'owned-component-families' / 'graph.json'
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            readback_path = base / 'empty-page-discovery.json'
            readback_path.write_text(
                json.dumps(sample_discovery(include_sibling=False), indent=2) + '\n',
                encoding='utf-8',
            )
            plan_from_design = base / 'plan-from-design.json'
            r_design = family_provision.prepare(owned_design, readback_path, 'sample_file_01', '10:1', plan_from_design)
            self.assertEqual(r_design['position'], {'x': 0, 'y': 0})
            self.assertEqual(sorted(r_design['families']), ['checkbox', 'field', 'input', 'radio', 'table-cell', 'table-row'])
            self.assertGreaterEqual(r_design['instance_count'], 2)

            plan_from_graph = base / 'plan-from-graph.json'
            r_graph = family_provision.prepare(owned_graph, readback_path, 'sample_file_01', '10:1', plan_from_graph)
            self.assertEqual(r_graph['graph_id'], 'owned-component-families')
            self.assertIn('design_source_sha256', r_graph)
            self.assertEqual(r_graph['position'], {'x': 0, 'y': 0})


if __name__ == '__main__':
    unittest.main()
