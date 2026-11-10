"""0.17.4: problems found while taking a selected direction into production."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import asset_batch  # noqa: E402
import design_directions  # noqa: E402

EXAMPLE = ROOT / 'examples/native-direction-review'


class ReviewGraphMatchesProductionTests(unittest.TestCase):
    def test_graph_without_status_is_rejected_before_selection(self):
        graph = json.loads((EXAMPLE / 'bulletin/graph.json').read_text())
        for node in graph['nodes']:
            node.pop('status')
        errors = design_directions._product_graph_errors(graph)
        self.assertTrue(errors)
        self.assertIn('status', errors[0])

    def test_shipped_example_graphs_are_production_ready(self):
        for name in ('bulletin', 'agenda'):
            graph = json.loads((EXAMPLE / name / 'graph.json').read_text())
            self.assertEqual(design_directions._product_graph_errors(graph), [], name)


class KeyArtReferenceTextTests(unittest.TestCase):
    def packet(self):
        pins = {'selection_sha256': 's', 'candidate_id': 'a', 'candidate_sha256': 'c',
                'workflow_graph_sha256': 'w', 'product_graph_sha256': 'p'}
        batch = {'batch_id': 'b', 'game_id': 'g', 'references': [], 'design_selection': pins,
                 'concept': {'sha256': 'k'}, 'workflow_state': 'batch-frozen',
                 'roles': [{'id': 'hero', 'kind': 'key_art'}, {'id': 'mark', 'kind': 'logo'}]}
        selection = {'candidate': {'composition': 'x', 'typography': 'y', 'interaction': 'z'}}
        return asset_batch._request_packet(batch, 'h', '{}', selection, ROOT)[1]['requests']

    def test_key_art_request_forbids_copying_ui_text_from_reference_comps(self):
        hero, mark = self.packet()
        self.assertIn('never paint any letters', hero['args']['prompt'])
        self.assertNotIn('never paint any letters', mark['args']['prompt'])


if __name__ == '__main__':
    unittest.main()
