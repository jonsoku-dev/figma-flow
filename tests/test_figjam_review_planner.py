import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'library/figma-recipes/figjam-review-planner.ts'


class FigJamReviewPlannerTest(unittest.TestCase):
    def test_recipe_uses_only_graph_projection_and_local_figjam_apis(self):
        source = SOURCE.read_text()
        self.assertIn("figma.editorType !== 'figjam' || figma.mode !== 'default'", source)
        self.assertIn('FLOW_REVIEW_GRAPH', source)
        self.assertIn('FLOW_REVIEW_GRAPH_SHA256', source)
        self.assertIn('FLOW_REVIEW_SELECTION_SHA256', source)
        self.assertIn('figma.createSticky()', source)
        self.assertIn('figma.createTable(graph.nodes.length + 1, 4)', source)
        self.assertIn('figma.createCodeBlock()', source)
        self.assertIn('figma.createConnector()', source)
        self.assertIn("await figma.loadFontAsync({ family: 'Source Code Pro', style: 'Medium' })", source)
        self.assertIn("'node:' + node.id", source)
        self.assertIn("'edge:' + JSON.stringify([edge.from, edge.to, edge.type])", source)
        self.assertIn('node.getPluginData(GRAPH_HASH_KEY)', source)
        self.assertIn('node.getPluginData(SELECTION_HASH_KEY)', source)
        self.assertIn('node.setPluginData(SEMANTIC_ID_KEY, semanticId)', source)
        self.assertIn('MAX_NODES = 24', source)
        self.assertIn('MAX_EDGES = 48', source)
        self.assertLess(source.index("figma.editorType !== 'figjam'"), source.index('const graph = FLOW_REVIEW_GRAPH;'))
        self.assertLess(source.index('validateReviewGraph(graph, identity)'), source.index('figma.createSticky()'))
        self.assertLess(source.index('findExistingBoard(page, identity, graph)'), source.index('figma.createSticky()'))
        self.assertLess(source.index("await figma.loadFontAsync({ family: 'Source Code Pro', style: 'Medium' })"), source.index('const title = track('))
        self.assertIn('A partial board for this graph revision exists', source)
        self.assertIn('Board evidence readback did not match the graph projection', source)
        self.assertIn('for (const node of [...owned].reverse())', source)
        self.assertIn('originalSelection.filter(node => !node.removed)', source)
        for forbidden in ['fetch(', 'XMLHttpRequest', 'figma.createPage(', 'node.parent.remove()']:
            self.assertNotIn(forbidden, source)

    @unittest.skipUnless(os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'), 'Set FIGMA_SDK_TEST_TYPESCRIPT to pinned TypeScript 5.9.3')
    def test_source_compiles_against_pinned_figma_sdk_and_graph_projection(self):
        compiler = Path(os.environ['FIGMA_SDK_TEST_TYPESCRIPT']).resolve()
        compiler_package = json.loads((compiler.parent.parent / 'package.json').read_text())
        self.assertEqual(compiler_package.get('version'), '5.9.3')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            globals_path = folder / 'globals.d.ts'
            globals_path.write_text('''
type FlowReviewNode = { readonly id: string; readonly kind: 'requirement' | 'screen' | 'component' | 'evidence'; readonly type: string; readonly title: string; readonly detail: string; readonly status: string };
type FlowReviewEdge = { readonly from: string; readonly to: string; readonly type: string };
declare const FLOW_REVIEW_GRAPH: { readonly id: string; readonly title: string; readonly nodes: readonly FlowReviewNode[]; readonly edges: readonly FlowReviewEdge[] };
declare const FLOW_REVIEW_GRAPH_SHA256: string;
declare const FLOW_REVIEW_SELECTION_SHA256: string;
declare const figma: PluginAPI;
''')
            result = subprocess.run(['node', str(compiler), '--strict', '--target', 'ES2020', '--lib', 'ES2020',
                '--module', 'none', '--skipLibCheck', 'false', '--noEmit',
                str(ROOT / 'library/figma-api/plugin-api.d.ts'), str(globals_path), str(SOURCE)],
                cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
