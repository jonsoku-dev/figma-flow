import copy
import unittest

import test_graph

graph = test_graph.graph


class ReferenceGraphTests(unittest.TestCase):
    def sample(self):
        data = test_graph.GraphTests()._local_graph()
        data["nodes"].append({"id": "ref", "type": "reference", "title": "Official source", "status": "observed", "source": "https://example.org/campaign", "detail": "Short excerpt; in-game observation, adopted principle only."})
        data["edges"].append({"from": "ref", "to": "requirement", "type": "informs"})
        return data

    def test_reference_trace_preserves_complete_strict_coverage(self):
        data = self.sample()
        self.assertEqual(graph.validate_graph(data, strict_local=True)[0], [])
        self.assertIn("informs", graph.render_mermaid(data))
        self.assertIn("https://example.org/campaign", graph.render_markdown(data))

    def test_informs_direction_and_endpoints_are_strict(self):
        for source, target in (("requirement", "ref"), ("ref", "screen")):
            data = self.sample()
            data["edges"][-1].update({"from": source, "to": target})
            self.assertTrue(any("invalid endpoint types" in e for e in graph.validate_graph(data, strict_local=True)[0]))

    def test_reference_cannot_substitute_for_implementation_or_verification(self):
        for label in ("implemented by", "checked by"):
            data = self.sample()
            edge = next(e for e in data["edges"] if e["type"] == label)
            edge["to"] = "ref"
            self.assertTrue(graph.validate_graph(data, strict_local=True)[0])

    def test_reference_keeps_existing_verified_source_rule(self):
        data = self.sample()
        data["nodes"][-1].update(status="verified", source="")
        self.assertTrue(any("source is required" in e for e in graph.validate_graph(data)[0]))

    def test_legacy_graph_needs_no_reference_or_new_fields(self):
        data = test_graph.GraphTests()._local_graph()
        self.assertEqual(graph.validate_graph(copy.deepcopy(data), strict_local=True)[0], [])


if __name__ == "__main__":
    unittest.main()
