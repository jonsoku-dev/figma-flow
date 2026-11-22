import json
import tempfile
import unittest
from pathlib import Path

from tools.spec_graph_coverage import check


class SpecGraphCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.feature = self.root / "specs" / "sample"
        self.feature.mkdir(parents=True)
        (self.root / "src.py").write_text("# source\n", encoding="utf-8")
        (self.root / "test.py").write_text("# test\n", encoding="utf-8")
        self.graph_rel = "specs/sample/graph.json"
        self.graph_path = self.root / self.graph_rel
        self.graph = {"version": 1, "nodes": [
            {"id": "REQ-X", "type": "requirement", "title": "Requirement", "status": "observed"},
            {"id": "AC-X", "type": "acceptance", "title": "Criterion", "status": "verified", "source": "../../test.py"},
            {"id": "CODE-X", "type": "code", "title": "Implementation", "status": "verified", "source": "../../src.py"},
            {"id": "TEST-X", "type": "test", "title": "Verification", "status": "verified", "source": "../../test.py"},
        ], "edges": [
            {"from": "REQ-X", "to": "AC-X", "type": "accepted by"},
            {"from": "REQ-X", "to": "CODE-X", "type": "implemented by"},
            {"from": "AC-X", "to": "TEST-X", "type": "checked by"},
            {"from": "CODE-X", "to": "TEST-X", "type": "verified by"},
        ]}
        self.write_graph()
        (self.root / "specs" / "graph-roots.json").write_text(json.dumps({"version": 1, "roots": [{"path": self.graph_rel, "role": "canonical-feature-graph"}]}), encoding="utf-8")
        (self.root / "specs" / "README.md").write_text("[graph-roots.json](graph-roots.json)\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_graph(self):
        self.graph_path.write_text(json.dumps(self.graph), encoding="utf-8")

    def codes(self):
        return {item["code"] for item in check(self.root)}

    def test_accepts_connected_graph_without_requiring_id_duplication_in_prose(self):
        self.assertEqual([], check(self.root))

    def test_detects_missing_registered_graph_and_empty_specs_root(self):
        self.graph_path.unlink()
        self.assertIn("registered-graph-missing", self.codes())
        (self.root / "specs").rename(self.root / "specs.saved")
        self.assertIn("missing-specs-root", self.codes())

    def test_checks_source_path_on_any_node_and_rejects_escape(self):
        self.graph["nodes"][0]["source"] = "../../../../outside.txt"
        self.write_graph()
        self.assertIn("unsafe-source-path", self.codes())

    def test_rejects_typed_endpoint_mismatch_and_accepts_indirect_test_chain(self):
        self.graph["edges"].remove({"from": "AC-X", "to": "TEST-X", "type": "checked by"})
        self.graph["edges"] += [
            {"from": "AC-X", "to": "CODE-X", "type": "evaluated by"},
            {"from": "REQ-X", "to": "TEST-X", "type": "appears on"},
        ]
        self.write_graph()
        codes = self.codes()
        self.assertIn("typed-edge-mismatch", codes)
        # indirect path AC -> code -> test remains a valid evidence chain.
        self.assertNotIn("acceptance-no-test", codes)

    def test_only_explicit_definition_ids_are_required_in_graph(self):
        spec = self.feature / "spec.md"
        spec.write_text("- **REQ-MISSING** — Defined requirement.\n\nRelated to REQ-ALSO-MISSING in prose.\n", encoding="utf-8")
        self.write_graph()
        findings = check(self.root)
        declared = [item for item in findings if item["code"] == "declared-spec-id-unmapped"]
        self.assertEqual([item["identity"] for item in declared], ["REQ-MISSING"])

    def test_legacy_typed_convention_mismatch_is_advisory_not_blocking(self):
        self.graph["edges"].append({"from": "TEST-X", "to": "CODE-X", "type": "verified by"})
        self.write_graph()
        finding = next(item for item in check(self.root) if item["code"] == "typed-edge-mismatch")
        self.assertEqual(finding["severity"], "advisory")

    def test_empty_registry_and_unregistered_graph_are_reported(self):
        registry = self.root / "specs" / "graph-roots.json"
        registry.write_text(json.dumps({"version": 1, "roots": []}), encoding="utf-8")
        findings = check(self.root)
        codes = {item["code"] for item in findings}
        self.assertIn("empty-root-registry", codes)
        self.assertIn("unregistered-graph", codes)


if __name__ == "__main__":
    unittest.main()
