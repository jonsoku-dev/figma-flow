import contextlib
import io
import json
from pathlib import Path
import shlex
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_feature as feature


class FeatureRoutesTests(unittest.TestCase):
    def test_flow_english_and_korean(self):
        for query, expected in [('discover', 'discover'), ('문서 읽기 하고 싶어', 'discover'),
                                ('컴포넌트 속성 만들기', 'components'), ('component properties', 'components')]:
            result = feature.route(query)
            self.assertEqual(result['status'], 'routed')
            self.assertEqual(result['routes'][0]['id'], expected)
            self.assertTrue(result['routes'][0]['next_steps'])
            self.assertTrue(result['routes'][0]['prerequisites'])
            self.assertEqual(result['execution'], 'not-executed')

    def test_sdk_recipe_commands_match_manifest(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / 'library/figma-recipes/manifest.json').read_text())
        recipes = {row['id']: row for row in manifest['recipes']}
        for row in feature.ROUTES:
            if row['kind'] not in ('sdk-recipe', 'flow-recipe'):
                continue
            recipe = recipes[row['recipe']]
            self.assertEqual(recipe['editorType'], row['editor'])
            steps = row['sdk_fallback']['next_steps'] if row['kind'] == 'flow-recipe' else row['next_steps']
            recipe_command = next(step for step in steps if '--recipe ' + row['recipe'] in step)
            if recipe.get('workspaceMenu'):
                self.assertEqual(row['kind'], 'flow-recipe')
                self.assertIn('flow-recipe:' + row['recipe'], ' '.join(row['next_steps']))
            else:
                self.assertEqual(row['kind'], 'sdk-recipe')
                if recipe.get('reviewGraph'):
                    self.assertIn('--review-graph', recipe_command)
                if recipe.get('requiresFileKey'):
                    self.assertIn('design_type_review_graph.py --file-key FILE_KEY --page-id PAGE_ID', steps[0])
                    self.assertIn('.figma-flow/type-review-graph.json', recipe_command)
                    self.assertNotIn('--node', recipe_command)
        for query, expected in [('그리드', 'design-grid'),
                                ('smart animate', 'design-motion'), ('motion', 'motion-timeline')]:
            self.assertEqual(feature.route(query)['routes'][0]['id'], expected)
        for query in ('figjam', '피그잼', 'slides', '슬라이드', 'buzz', 'codegen'):
            result = feature.route(query)
            self.assertFalse([row for row in result.get('routes', [])
                              if row['kind'] in ('sdk-recipe', 'flow-recipe', 'widget-project')])
        self.assertTrue(all(row['editorType'] == 'figma' and row.get('mode', 'default') == 'default'
                            for row in recipes.values()))

    def test_registered_design_menu_and_component_demo_are_explicit(self):
        rows = [row for row in feature.ROUTES if row['kind'] == 'flow-recipe']
        self.assertEqual({row['id'] for row in rows},
                         {'design-shapes', 'design-grid', 'design-motion', 'design-component-properties'})
        for row in rows:
            self.assertEqual(row['next_steps'][0], 'python3 tools/figma_workspace.py refresh --workspace WORKSPACE')
            self.assertIn('Examples · add to current page', row['next_steps'][1])
            self.assertNotIn('new page', ' '.join(row['next_steps']))
            self.assertIn('current page', ' '.join(row['prerequisites']))
        for query in ('속성', '불리언', '인스턴스 교체', 'visibility', 'component property demo'):
            result = feature.route(query)
            self.assertEqual(result['status'], 'routed')
            self.assertEqual(result['routes'][0]['id'], 'design-component-properties')
        source = feature.route('components')['routes'][0]
        self.assertIn('Source authoring:', ' '.join(source['prerequisites']))
        self.assertIn('figma_bridge.py --input SOURCE_JSON', ' '.join(source['next_steps']))

    def test_rest_export_steps_are_inert_real_cli(self):
        from figma_rest_inventory import load, request_export
        result = request_export(load(), 'getComments', path_values={'file_key': 'file-key'})
        self.assertIn('api.figma.com', json.dumps(result))
        self.assertEqual(feature.route('comments')['routes'][0]['next_steps'][-1],
                         'python3 tools/figma_rest_inventory.py curl getComments --path file_key=FILE_KEY')
        self.assertIn('figma_rest_inventory.py', ' '.join(feature.route('rest')['routes'][0]['next_steps']))

    def test_ambiguous_does_not_choose_a_write(self):
        result = feature.route('discover and native edit')
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual({row['id'] for row in result['routes']}, {'discover', 'native-edit'})
        self.assertEqual(result['execution'], 'not-executed')

    def test_api_fallback_and_unknown(self):
        result = feature.route('figma.createFrame')
        self.assertEqual(result['status'], 'api-catalog')
        self.assertTrue(any(row['name'] == 'createFrame' for row in result['catalog']['rows']))
        self.assertIn('declarations only', result['prerequisites'][0])
        unknown = feature.route('no_such_figma_feature_12345')
        self.assertEqual(unknown['status'], 'unknown')
        self.assertEqual(unknown['catalog']['rows'], [])
        self.assertEqual(unknown['catalog']['declarations'], [])

    def test_shell_query_is_only_quoted_data(self):
        query = 'missing; $(touch /tmp/should-not-exist)'
        result = feature.route(query, {'members': [], 'declarations': [], 'evidence': 'fixture', 'source': {}})
        self.assertEqual(shlex.split(result['next_steps'][0])[-1], query)

    def test_local_and_native_product_routes(self):
        for query, kind in [('코드 커넥트', 'official-api'), ('라이브러리 발행', 'interactive')]:
            result = feature.route(query)
            self.assertEqual(result['routes'][0]['kind'], kind)
            self.assertEqual(result['runtime_acceptance'], 'unverified')
            self.assertTrue(result['routes'][0]['prerequisites'])

    def test_widget_route_exposes_local_generator_commands(self):
        result = feature.route('widget')
        self.assertEqual(result['status'], 'routed')
        route = result['routes'][0]
        self.assertEqual(route['id'], 'widget')
        self.assertEqual(route['kind'], 'widget-project')
        self.assertIn('Figma Design', ' '.join(route['prerequisites']))
        self.assertEqual(route['next_steps'], [
            'python3 tools/figma_widget_project.py init NEW_WIDGET_DIR',
            'npm --prefix NEW_WIDGET_DIR install --ignore-scripts --no-audit --no-fund',
            'python3 tools/figma_widget_project.py check NEW_WIDGET_DIR',
            'python3 tools/figma_widget_project.py build NEW_WIDGET_DIR',
        ])
        self.assertIn('docs/figma-widget.md', ' '.join(route['prerequisites']))

    def test_every_output_uses_local_or_native_routes(self):
        forbidden = ('mcp', 'get_design_context', 'use_figma', 'send_code_to_figma',
                     'upload_assets', 'weave_list_tools', 'weave_run_tool')
        outputs = [feature.route(row['id']) for row in feature.ROUTES]
        outputs.extend(feature.route(query) for query in ['figma.createFrame', 'no_such_figma_feature_12345',
                                                       'discover and native edit'])
        for argv in (['list'], ['route', 'make'], ['route', 'figma.createFrame'],
                     ['route', 'no_such_figma_feature_12345']):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                feature.main(argv)
            outputs.append(json.loads(output.getvalue()))
        for result in outputs:
            text = json.dumps(result).lower()
            for term in forbidden:
                self.assertNotIn(term, text)
            self.assertEqual(result['execution'], 'not-executed')
        for identity in ['make', 'sites', 'weave']:
            self.assertFalse(feature.route(identity)['routes'])
        self.assertIn('credential', ' '.join(feature.route('comments')['routes'][0]['prerequisites']))

    def test_cli_prints_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(feature, 'load', side_effect=AssertionError('No catalog needed')):
            feature.main(['route', 'native', 'edit'])
        self.assertEqual(json.loads(output.getvalue())['routes'][0]['id'], 'native-edit')
        with self.assertRaises(ValueError):
            feature.route('  ')


if __name__ == '__main__':
    unittest.main()
