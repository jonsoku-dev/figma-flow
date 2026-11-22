"""One malformed graph must be refused by all supported graph readers."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import graph_design_system
import major_release
import review_graph
import spec_graph_coverage


class GraphInputBoundaryTests(unittest.TestCase):
    def test_ambiguous_fields_and_nonfinite_numbers_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            graph = Path(temp) / 'graph.json'
            for token, reason in [
                ('"version":1,"version":1', 'Duplicate JSON key'),
                ('"version":1,"meta":{"source":"first","source":"second"}', 'Duplicate JSON key'),
                ('"version":1,"meta":NaN', 'Non-finite JSON number'),
                ('"version":1,"meta":1e400', 'Non-finite JSON number'),
            ]:
                graph.write_text('{' + token + ',"nodes":[],"edges":[]}', encoding='utf-8')
                cli = subprocess.run(
                    [sys.executable, '-B', str(ROOT/'skills/figma-flow/scripts/graph.py'), 'validate', str(graph)],
                    capture_output=True, text=True, check=False,
                )
                self.assertTrue(cli.returncode != 0 and reason in cli.stderr,
                                'The portable graph CLI must reject ambiguous JSON before validation')
                for load in (graph_design_system.load_graph, major_release.read_json, spec_graph_coverage._load,
                             lambda path: review_graph.project_graph(path, [])):
                    with self.assertRaisesRegex(ValueError, reason):
                        load(graph)


if __name__ == '__main__':
    unittest.main()
