import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_sdk_project as sdk
from review_graph import project_graph, selection_sha256


class SlidesFlowReviewRecipeTest(unittest.TestCase):
    def test_recipe_registers_graph_projection_and_native_grid_apis(self):
        manifest = json.loads((ROOT / 'library/figma-recipes/manifest.json').read_text())
        rows = [row for row in manifest['recipes'] if row['id'] == 'slides-flow-review']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['editorType'], 'slides')
        self.assertTrue(rows[0]['reviewGraph'])
        for api in ['figma.createSlideRow', 'figma.createSlide', 'figma.getCanvasGrid', 'figma.setCanvasGrid']:
            self.assertIn(api, rows[0]['api'])
        self.assertNotIn('figma.getSlideGrid', rows[0]['api'])
        self.assertNotIn('figma.setSlideGrid', rows[0]['api'])
        source = (ROOT / 'library/figma-recipes/slides-flow-review.ts').read_text()
        for call in ['figma.createSlideRow(', 'figma.createSlide(', 'figma.getCanvasGrid()', 'figma.setCanvasGrid(']:
            self.assertIn(call, source)
        self.assertNotIn('figma.getSlideGrid(', source)
        self.assertNotIn('figma.setSlideGrid(', source)
        self.assertIn('FLOW_REVIEW_GRAPH_SHA256', source)
        self.assertIn('FLOW_REVIEW_SELECTION_SHA256', source)
        self.assertNotIn('createPage(', source)

    @unittest.skipUnless(os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'), 'Set FIGMA_SDK_TEST_TYPESCRIPT to pinned lib/tsc.js for real compilation')
    def test_scaffold_build_and_native_grid_workflow_regression(self):
        private = ROOT / '.figma-flow'
        private.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as temporary:
            folder = Path(temporary)
            graph_path = folder / 'agenda.json'
            graph_data = json.loads((ROOT / 'examples/native-direction-review/agenda/graph.json').read_text())
            graph_data['id'] = 'agenda-recipe-regression'
            graph_data['title'] = 'Agenda recipe regression'
            graph_path.write_text(json.dumps(graph_data))
            projected, digest = project_graph(graph_path, None)
            expected = {**projected, 'sha256': digest, 'selectionSha256': selection_sha256(projected)}
            expected_path = folder / 'expected.json'
            expected_path.write_text(json.dumps(expected))

            project = folder / 'plugin'
            sdk.initialize(project, 'slides', recipe='slides-flow-review', review_graph=graph_path)
            sdk.compile_project(project, build=True, typescript=os.environ['FIGMA_SDK_TEST_TYPESCRIPT'])
            result = subprocess.run(
                ['node', str(ROOT / 'tests/figma_slides_review_harness.cjs'),
                 str(project / 'dist/code.js'), str(expected_path)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
