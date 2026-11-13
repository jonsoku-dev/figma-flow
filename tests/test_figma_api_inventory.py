"""Declaration coverage and context routing are separate from Figma runtime acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_api_inventory as inventory


class FigmaAPIInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = inventory.load()

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/figma_api_inventory.py'), *args],
                                capture_output=True, text=True, cwd=ROOT, check=True)
        return json.loads(result.stdout)

    def test_offline_search_covers_global_namespaces_and_overloads(self):
        rows = inventory.search(self.catalog, 'createRectangle')['rows']
        self.assertTrue(any('figma.createRectangle' in row['routes'] for row in rows))
        rows = inventory.search(self.catalog, owner='VariablesAPI', limit=0)['rows']
        self.assertTrue(any('figma.variables.createVariable' in row['routes'] for row in rows))
        overloads = [row for row in self.catalog['members'] if row['owner'] == 'PluginAPI' and row['name'] == 'on']
        self.assertGreater(len(overloads), 5)
        self.assertEqual(len(overloads), len({row['id'] for row in overloads}))

    def test_inheritance_nodes_aliases_and_source_locations(self):
        rows = inventory.inherited_members(self.catalog, 'RectangleNode')
        self.assertTrue({'fills', 'resize', 'remove', 'type'} <= {row['name'] for row in rows})
        self.assertTrue(any(row['owner'] != 'RectangleNode' for row in rows))
        aliases = {row['name']: row for row in self.catalog['node_aliases']}
        self.assertIn('SceneNode', aliases)
        self.assertIn('RectangleNode', aliases['SceneNode']['references'])
        self.assertIn('NodeType', aliases)
        self.assertTrue(any(node['name'] == 'SlideNode' for node in self.catalog['nodes']))
        lines = (inventory.LIBRARY / 'plugin-api.d.ts').read_text().splitlines()
        for row in self.catalog['members']:
            self.assertIn(row['signature'], '\n'.join(lines[row['line'] - 1:row['end_line']]))
            self.assertIn(self.catalog['source']['ref'], row['source_url'])
            self.assertEqual(row['execution'], 'not-executed')
        names = {row['name'] for row in self.catalog['declarations']}
        for row in self.catalog['declarations']:
            self.assertTrue(set(row['extends']) <= names | {'Omit'}, row['name'])
        extended = inventory.inherited_members(self.catalog, 'ExtendedVariableCollection')
        self.assertIn('name', {row['name'] for row in extended})
        self.assertNotIn('addMode', {row['name'] for row in extended})

    def test_context_blocks_known_incompatible_editors_and_permissions(self):
        sticky = self.cli('route', 'figma.createSticky', '--editor', 'figma')
        self.assertEqual(sticky['routes'][0]['status'], 'blocked')
        user = self.cli('route', 'figma.currentUser', '--editor', 'figma')
        self.assertIn('currentuser', user['routes'][0]['member']['required_permissions'])
        self.assertEqual(user['routes'][0]['status'], 'blocked')
        user = self.cli('route', 'figma.currentUser', '--editor', 'figma', '--permission', 'currentuser')
        self.assertEqual(user['routes'][0]['status'], 'documentation-review-required')
        mode = self.cli('route', 'figma.mode', '--editor', 'figma')
        self.assertEqual(mode['routes'][0]['status'], 'documentation-review-required')
        self.assertFalse(mode['routes'][0]['member']['restricted_access'])
        self.assertTrue(mode['routes'][0]['member']['value_restrictions'])
        private = self.cli('route', 'figma.devResources', '--editor', 'dev')
        self.assertEqual(private['routes'][0]['status'], 'blocked')
        inherited = self.cli('route', 'RectangleNode.resize', '--editor', 'figma')
        self.assertEqual(inherited['routes'][0]['member']['name'], 'resize')
        public = self.cli('route', 'figma.createRectangle', '--editor', 'figma')
        self.assertEqual(public['execution'], 'not-executed')
        self.assertEqual(public['routes'][0]['runtime_support'], 'unverified')

    def test_source_pin_detects_modified_declaration(self):
        real = inventory.hashlib.sha256
        with patch.object(inventory.hashlib, 'sha256') as digest:
            digest.return_value.hexdigest.return_value = '0' * 64
            with self.assertRaisesRegex(ValueError, 'Pinned source hash mismatch'):
                inventory.verify_source()
        self.assertIs(inventory.hashlib.sha256, real)

    def test_static_coverage_separates_qualified_and_ambiguous_references(self):
        compiler = os.environ.get('FIGMA_API_TYPESCRIPT')
        if not compiler:
            self.skipTest('Set FIGMA_API_TYPESCRIPT to run AST source occurrence checks')
        source = """// figma.createEllipse();
        const example = 'figma.createPolygon()';
        figma['createRectangle']();
        figma.variables?.createVariable('sample', collection, 'COLOR');
        unrelated.resize(10, 10);
        figma.currentPage.selection;
        """
        report = inventory.coverage(self.catalog, compiler, [{'path': 'fixture.js', 'text': source}])
        rows = {(row['owner'], row['name']): row for row in report['members']}
        self.assertEqual(rows['PluginAPI', 'createRectangle']['status'], 'qualified-static-reference')
        self.assertEqual(rows['VariablesAPI', 'createVariable']['status'], 'qualified-static-reference')
        self.assertEqual(rows['PluginAPI', 'createEllipse']['status'], 'no-static-reference')
        self.assertEqual(rows['PluginAPI', 'createPolygon']['status'], 'no-static-reference')
        self.assertEqual(rows['LayoutMixin', 'resize']['status'], 'unresolved-receiver-name-reference')
        self.assertEqual(rows['LayoutMixin', 'resize']['qualified_references'], [])
        self.assertEqual(sum(report['counts'].values()), len(self.catalog['members']))
        self.assertTrue(all(row['implementation'] == 'unverified' and row['runtime_acceptance'] == 'unverified'
                            for row in report['members']))
        self.assertNotIn('source text', json.dumps(report['sources']))

    def test_regeneration_is_byte_identical_with_pinned_ast_parser(self):
        compiler = os.environ.get('FIGMA_API_TYPESCRIPT')
        if not compiler:
            self.skipTest('Set FIGMA_API_TYPESCRIPT to TypeScript 5.9.3 module for regeneration check')
        self.assertEqual(inventory.INDEX.read_text(), inventory.canonical(inventory.build(compiler)))
        self.assertGreater(len(self.catalog['declarations']), 350)
        self.assertGreater(len(self.catalog['members']), 1300)


if __name__ == '__main__':
    unittest.main()
