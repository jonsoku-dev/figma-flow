"""One Design review source can produce separately pinned API selections."""
import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_type_review_graph
import figma_sdk_project as sdk
from review_graph import project_graph, selection_sha256


class DesignReviewSelectionIdentityTest(unittest.TestCase):
    def test_same_design_source_has_distinct_selection_pins_and_builds(self):
        private = ROOT / '.figma-flow'
        private.mkdir(exist_ok=True)
        graph = design_type_review_graph.build_graph('FILE_KEY', '1:1')
        member_ids = [node['id'] for node in graph['nodes']
                      if node['type'] == 'figma' and node['id'].startswith('figma:member:')]
        self.assertGreaterEqual(len(member_ids), 1)
        subsets = [
            ['scope:lab', *member_ids, 'component:typography', 'requirement:designer'],
            ['scope:lab', *member_ids, 'component:typography', 'requirement:developer'],
        ]

        with tempfile.TemporaryDirectory(dir=private) as temporary:
            folder = Path(temporary)
            graph_path = folder / 'typography.json'
            graph_path.write_text(json.dumps(graph, ensure_ascii=False))
            source_digests = []
            selection_digests = []
            projections = []
            for index, selected_ids in enumerate(subsets):
                projection, source_sha = project_graph(graph_path, selected_ids)
                source_digests.append(source_sha)
                selection_digests.append(selection_sha256(projection))
                projections.append(projection)
                project = folder / f'design-review-{index}'
                sdk.initialize(project, 'figma', recipe='design-type-review',
                               review_graph=graph_path, selected_ids=selected_ids)
                generated = (project / 'src/review-graph.ts').read_text()
                self.assertIn(json.dumps(selection_digests[-1]), generated)
                self.assertIn(json.dumps(source_sha), generated)
                metadata = json.loads((project / 'sdk-project.json').read_text())
                self.assertEqual(metadata['editor'], 'figma')
                self.assertEqual(metadata['mode'], 'default')
                self.assertEqual(metadata['reviewGraph']['graphSha256'], source_sha)
                self.assertEqual(metadata['reviewGraph']['projectionSha256'], hashlib.sha256(generated.encode()).hexdigest())
                if os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'):
                    sdk.compile_project(project, build=True,
                                        typescript=os.environ['FIGMA_SDK_TEST_TYPESCRIPT'])
                    code = (project / 'dist/code.js').read_text()
                    self.assertIn(selection_digests[-1], code)
                    self.assertIn('FLOW_REVIEW_SELECTION_SHA256', code)

            self.assertEqual(source_digests[0], source_digests[1])
            self.assertNotEqual(selection_digests[0], selection_digests[1])
            self.assertNotEqual(projections[0], projections[1])


if __name__ == '__main__':
    unittest.main()
