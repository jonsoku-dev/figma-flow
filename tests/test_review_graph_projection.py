"""The same canonical revision may have several independently reproducible review selections."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from review_graph import project_graph, selection_sha256


class ProjectionTests(unittest.TestCase):
    def test_only_selected_nodes_and_their_direct_edges_are_projected(self):
        path = ROOT / 'specs/graph-review/graph.json'
        ids = ['REQ-plan', 'SCR-plan', 'AC-plan', 'TEST-plan']
        result, source_sha = project_graph(path, ids)
        self.assertEqual([r['id'] for r in result['nodes']], ids)
        self.assertEqual(len(result['edges']), 3)
        self.assertEqual(result['nodes'][0]['type'], 'requirement')
        selected, same_sha = project_graph(path, ids[:2])
        self.assertEqual(source_sha, same_sha)
        self.assertNotEqual(selection_sha256(result), selection_sha256(selected))

    def test_rejects_unknown_duplicate_and_missing_ownership(self):
        path = ROOT / 'specs/graph-review/graph.json'
        for ids in (['not-a-node'], ['REQ-plan', 'REQ-plan'], []):
            with self.assertRaises(ValueError):
                project_graph(path, ids)
        with tempfile.TemporaryDirectory() as tmp:
            source = json.loads(path.read_bytes())
            del source['id']
            old = Path(tmp) / 'graph.json'
            old.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, 'stable id'):
                project_graph(old, ['REQ-plan'])
