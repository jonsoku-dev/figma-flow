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


class ReviewSelectionIdentityTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'), 'Set FIGMA_SDK_TEST_TYPESCRIPT to pinned TypeScript 5.9.3')
    def test_distinct_selections_same_source_reuse_exact_boards_and_reject_conflicts(self):
        private = ROOT / '.figma-flow'
        private.mkdir(exist_ok=True)
        compiler = os.environ['FIGMA_SDK_TEST_TYPESCRIPT']
        subsets = [
            ['screen-agenda-overview', 'action-agenda-open', 'state-agenda-details'],
            ['screen-agenda-details', 'action-agenda-back', 'state-agenda-overview'],
        ]

        with tempfile.TemporaryDirectory(dir=private) as temporary:
            folder = Path(temporary)
            graph_path = folder / 'agenda.json'
            graph = json.loads((ROOT / 'examples/native-direction-review/agenda/graph.json').read_text())
            graph['id'] = 'agenda-selection-regression'
            graph['title'] = 'Agenda selection regression'
            graph_path.write_text(json.dumps(graph))

            compiled = {}
            expected = {}
            for editor, recipe, harness in [
                ('figjam', 'figjam-review-planner', ROOT / 'tests/helpers/figma_figjam_review_harness.cjs'),
                ('slides', 'slides-flow-review', ROOT / 'tests/helpers/figma_slides_review_harness.cjs'),
            ]:
                compiled[editor] = []
                expected[editor] = []
                for index, selected_ids in enumerate(subsets):
                    projection, source_sha256 = project_graph(graph_path, selected_ids)
                    selection_sha = selection_sha256(projection)
                    expected_data = {
                        **projection,
                        'graph': projection,
                        'sha256': source_sha256,
                        'sourceSha256': source_sha256,
                        'selectionSha256': selection_sha,
                    }
                    expected_path = folder / f'{editor}-{index}.json'
                    expected_path.write_text(json.dumps(expected_data))
                    project = folder / f'{editor}-{index}'
                    sdk.initialize(project, editor, recipe=recipe, review_graph=graph_path, selected_ids=selected_ids)
                    sdk.compile_project(project, build=True, typescript=compiler)
                    compiled[editor].append(project / 'dist/code.js')
                    expected[editor].append(expected_path)

                first_projection, first_source_sha = project_graph(graph_path, subsets[0])
                second_projection, second_source_sha = project_graph(graph_path, subsets[1])
                self.assertEqual(first_source_sha, second_source_sha)
                self.assertNotEqual(selection_sha256(first_projection), selection_sha256(second_projection))
                command = [
                    'node', str(harness), str(compiled[editor][0]), str(expected[editor][0]),
                    str(compiled[editor][1]), str(expected[editor][1]),
                ]
                result = subprocess.run(command, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
