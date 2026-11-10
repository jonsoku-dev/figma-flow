import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/figma-flow/scripts"
sys.path.insert(0, str(SCRIPTS))
import ssot


class SsotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("brief.md", "visual.md", "app.py", "proof.txt"):
            (self.root / name).write_text(name, encoding="utf-8")
        self.data = {"version": 1, "nodes": [
            {"id": key, "type": kind, "title": key, "status": "verified", "source": "proof.txt"}
            for key, kind in (("R", "requirement"), ("S", "screen"), ("C", "code"), ("N", "screen"))],
            "edges": [{"from": "R", "to": "S", "type": "depends-on"},
                      {"from": "S", "to": "C", "type": "depends-on"},
                      {"from": "S", "to": "N", "type": "navigates to"}]}
        self.bindings = {"version": 1, "authorities": {"intent": "brief.md", "visual": "visual.md", "implementation": "app.py"},
                         "dependency_edge_types": ["depends-on"], "evidence": {"S": ["visual.md"]}}
        self.write("graph.json", self.data)
        self.write("bindings.json", self.bindings)

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ssot.main(list(map(str, args)))
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def snapshot(self, name="state.json", previous=None):
        args = ["snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / name]
        if previous:
            args.extend(["--previous", self.root / previous])
        result = self.cli(*args)
        self.assertEqual(result[0], 0, result[2])
        return json.loads((self.root / name).read_text())

    def test_unchanged_is_content_current_only_and_deterministic(self):
        first = self.snapshot()
        second = self.snapshot("same.json")
        self.assertEqual(first, second)
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 0)
        self.assertTrue(all(node["freshness"] == "content-current" for node in result["nodes"].values()))
        self.assertIn("do not verify truth", result["classification"])
        self.assertEqual(json.loads((self.root / "graph.json").read_text()), self.data)

    def test_explanation_unchanged_and_review_digest_compatibility(self):
        baseline = self.snapshot()
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 0)
        explanation = result["change_explanation"]
        self.assertEqual(explanation["baseline_manifest_sha256"], baseline["manifest_sha256"])
        self.assertEqual(explanation["direct_nodes"], {})
        self.assertEqual(explanation["propagation"], {})
        self.assertEqual(explanation["changed_inputs"], [])
        expected = ssot.compare(ssot.build(self.root / "brief.md", self.root / "graph.json",
                                          self.root / "bindings.json", self.root), baseline)
        self.assertEqual(result["review_target_sha256"], ssot.review_target(expected)[0])
        self.assertNotIn("change_explanation", baseline)

    def test_explanation_shortest_chain_cycle_and_navigation(self):
        names = {"R": "REQ-001", "S": "CODE-001", "C": "TEST-001", "N": "NAV-001"}
        for node in self.data["nodes"]:
            node["id"] = names[node["id"]]
        for edge in self.data["edges"]:
            edge["from"], edge["to"] = names[edge["from"]], names[edge["to"]]
        self.data["edges"].append({"from": "TEST-001", "to": "REQ-001", "type": "depends-on"})
        self.bindings["evidence"] = {}
        self.write("graph.json", self.data)
        self.write("bindings.json", self.bindings)
        self.snapshot()
        self.data["nodes"][0]["title"] = "changed requirement"
        self.write("graph.json", self.data)
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        explanation = result["change_explanation"]
        self.assertEqual(list(explanation["direct_nodes"]), ["REQ-001"])
        forest = explanation["propagation"]
        self.assertEqual(forest["TEST-001"]["predecessor_id"], "CODE-001")
        self.assertEqual(forest["CODE-001"]["predecessor_id"], "REQ-001")
        self.assertEqual(forest["TEST-001"]["distance"], 2)
        self.assertNotIn("NAV-001", forest)
        self.assertTrue(all(edge["type"] == "depends-on" for edge in explanation["dependency_edges"]))
        self.assertEqual(result, self.cli("check", self.root / "state.json")[1])
        self.assertNotIn("changed requirement", json.dumps(explanation))

    def test_explanation_chooses_shortest_then_sorted_dependency_route(self):
        self.data["edges"] = [
            {"from": source, "to": target, "type": "depends-on"}
            for source, target in (("R", "S"), ("R", "C"), ("S", "N"), ("C", "N"))]
        self.write("graph.json", self.data)
        self.snapshot()
        self.data["nodes"][0]["title"] = "changed root"
        self.write("graph.json", self.data)
        explanation = self.cli("check", self.root / "state.json")[1]["change_explanation"]
        self.assertEqual(explanation["propagation"]["N"]["predecessor_id"], "C")
        self.assertEqual(explanation["propagation"]["N"]["distance"], 2)
        # The explanation is derived, so removing it reproduces the existing review pin.
        baseline = json.loads((self.root / "state.json").read_text())
        current = ssot.compare(ssot.build(self.root / "brief.md", self.root / "graph.json",
                                         self.root / "bindings.json", self.root), baseline)
        self.assertEqual(self.cli("check", self.root / "state.json")[1]["review_target_sha256"],
                         ssot.review_target(current)[0])

    def test_explanation_evidence_hash_and_availability_deltas(self):
        self.snapshot()
        prior_sha = hashlib.sha256(b"proof.txt").hexdigest()
        (self.root / "proof.txt").write_text("new proof", encoding="utf-8")
        explanation = self.cli("check", self.root / "state.json")[1]["change_explanation"]
        changed = explanation["direct_nodes"]["R"]
        self.assertEqual(changed["categories"], ["evidence-changed"])
        evidence = changed["evidence_changes"][0]
        self.assertEqual(evidence["path"], "proof.txt")
        self.assertEqual(evidence["previous"]["sha256"], prior_sha)
        self.assertEqual(evidence["current"]["sha256"], hashlib.sha256(b"new proof").hexdigest())
        (self.root / "proof.txt").unlink()
        changed = self.cli("check", self.root / "state.json")[1]["change_explanation"]["direct_nodes"]["R"]
        self.assertEqual(changed["evidence_changes"][0]["current"]["availability"], "missing")

    def test_explanation_removed_edges_and_historic_unknown(self):
        self.snapshot()
        self.data["nodes"] = [node for node in self.data["nodes"] if node["id"] != "R"]
        self.data["edges"] = [edge for edge in self.data["edges"] if edge["from"] != "R"]
        self.write("graph.json", self.data)
        explanation = self.cli("check", self.root / "state.json")[1]["change_explanation"]
        self.assertIn({"from": "R", "to": "S", "type": "depends-on", "presence": "previous-only"},
                      explanation["dependency_edges"])
        self.assertIn("removed", explanation["direct_nodes"]["R"]["categories"])
        self.snapshot("second.json", "state.json")
        explanation = self.cli("check", self.root / "second.json")[1]["change_explanation"]
        self.assertTrue(explanation["direct_nodes"]["R"]["historic_only"])
        self.assertEqual(explanation["propagation"]["R"]["root_kind"], "historic-only-unknown")
        self.assertEqual(explanation["direct_nodes"]["C"]["categories"], ["prior-stale-unresolved"])
        self.assertEqual(explanation["propagation"]["C"]["root_kind"], "prior-stale-unresolved")

    def test_explanation_authority_policy_is_not_direct_node_change(self):
        self.snapshot()
        (self.root / "app.py").write_text("new implementation authority", encoding="utf-8")
        result = self.cli("check", self.root / "state.json")[1]
        explanation = result["change_explanation"]
        self.assertEqual(explanation["direct_nodes"], {})
        self.assertEqual(explanation["changed_authorities"][0]["key"], "implementation")
        self.assertEqual(explanation["changed_authorities"][0]["current"]["path"], "app.py")
        self.assertEqual({item["root_kind"] for item in explanation["propagation"].values()},
                         {"authority-or-bindings-changed"})

    def test_evidence_mapping_edit_scopes_staleness_to_node_and_dependents(self):
        baseline = self.snapshot()
        self.bindings["evidence"]["S"] = ["receipt.txt"]
        (self.root / "receipt.txt").write_text("screen receipt", encoding="utf-8")
        self.write("bindings.json", self.bindings)
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        self.assertEqual(result["review_affected_ids"], ["C", "S"])
        self.assertEqual(result["nodes"]["C"]["reasons"], ["upstream-stale"])
        self.assertEqual(result["nodes"]["N"]["freshness"], "content-current")
        self.assertEqual(result["nodes"]["R"]["freshness"], "content-current")
        self.assertEqual(result["changed_inputs"], ["bindings"])
        self.assertEqual(baseline["bindings_policy_sha256"], result["bindings_policy_sha256"])
        self.assertEqual(result["change_explanation"]["bindings_change"], {
            "scope": "scoped-evidence", "policy_hash_matches": True,
            "reason": "binding-policy-unchanged"})
        self.assertEqual(result["change_explanation"]["propagation"]["C"]["root_id"], "S")

    def test_specific_receipt_hash_change_does_not_invalidate_independent_nodes(self):
        (self.root / "receipt.txt").write_text("old receipt", encoding="utf-8")
        self.bindings["evidence"]["S"] = ["receipt.txt"]
        self.write("bindings.json", self.bindings)
        self.snapshot()
        (self.root / "receipt.txt").write_text("new receipt", encoding="utf-8")
        result = self.cli("check", self.root / "state.json")[1]
        self.assertEqual(result["review_affected_ids"], ["C", "S"])
        self.assertEqual(result["changed_inputs"], [])
        self.assertEqual(result["change_explanation"]["bindings_change"]["scope"], "none")

    def test_non_evidence_binding_policy_edit_remains_broad(self):
        baseline = self.snapshot()
        for key, value in (("dependency_edge_types", ["depends-on", "navigates to"]),
                           ("future_policy", {"approval": "required"})):
            with self.subTest(policy=key):
                bindings = dict(self.bindings, **{key: value})
                self.write("bindings.json", bindings)
                result = self.cli("check", self.root / "state.json")[1]
                self.assertNotEqual(baseline["bindings_policy_sha256"], result["bindings_policy_sha256"])
                self.assertEqual(result["review_affected_ids"], ["C", "N", "R", "S"])
                self.assertEqual(result["change_explanation"]["bindings_change"]["scope"], "broad")

    def legacy_baseline(self):
        baseline = self.snapshot()
        del baseline["bindings_policy_sha256"]
        baseline["manifest_sha256"] = ssot.digest({key: value for key, value in baseline.items()
                                                   if key != "manifest_sha256"})
        self.write("state.json", baseline)
        return baseline

    def test_legacy_binding_edit_remains_conservatively_broad(self):
        self.legacy_baseline()
        self.bindings["evidence"]["S"] = ["proof.txt"]
        self.write("bindings.json", self.bindings)
        result = self.cli("check", self.root / "state.json")[1]
        self.assertEqual(result["review_affected_ids"], ["C", "N", "R", "S"])
        self.assertEqual(result["change_explanation"]["bindings_change"], {
            "scope": "broad", "policy_hash_matches": False,
            "reason": "binding-policy-changed-or-unpinned"})

    def test_legacy_review_targets_and_pre_upgrade_reviews_remain_usable(self):
        baseline = self.legacy_baseline()
        for changed in (False, True):
            if changed:
                self.data["nodes"][1]["title"] = "new screen"
                self.write("graph.json", self.data)
            result = self.cli("check", self.root / "state.json")[1]
            legacy_current = ssot.build(self.root / "brief.md", self.root / "graph.json",
                                        self.root / "bindings.json", self.root)
            del legacy_current["bindings_policy_sha256"]
            legacy_current = ssot.compare(legacy_current, baseline)
            self.assertEqual(result["review_target_sha256"], ssot.digest(legacy_current))
        self.write("review.json", {
            "previous_manifest_sha256": baseline["manifest_sha256"],
            "current_state_sha256": ssot.digest(legacy_current),
            "affected_ids": result["review_affected_ids"], "evidence": "proof.txt",
            "evidence_sha256": hashlib.sha256((self.root / "proof.txt").read_bytes()).hexdigest(),
            "review_note": "Reviewed with v0.4 before upgrade."})
        code, _, error = self.cli("snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json",
                                   "--bindings", self.root / "bindings.json", "--previous", self.root / "state.json",
                                   "--review", self.root / "review.json", "--out", self.root / "upgraded.json")
        self.assertEqual(code, 0, error)
        self.assertEqual(self.cli("check", self.root / "upgraded.json")[0], 0)
        self.assertIn("bindings_policy_sha256", json.loads((self.root / "upgraded.json").read_text()))

    def test_brief_change_propagates_only_declared_dependencies(self):
        self.snapshot()
        (self.root / "brief.md").write_text("changed", encoding="utf-8")
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        # Intent authority changes conservatively invalidate every node.
        self.assertTrue(all(node["freshness"] == "stale" for node in result["nodes"].values()))
        self.assertIn("brief-changed", result["nodes"]["R"]["reasons"])

    def test_node_change_propagates_but_navigation_does_not(self):
        self.snapshot()
        self.data["nodes"][1]["title"] = "new screen"
        self.write("graph.json", self.data)
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        self.assertEqual(result["nodes"]["S"]["freshness"], "stale")
        self.assertEqual(result["nodes"]["C"]["reasons"], ["upstream-stale"])
        self.assertEqual(result["nodes"]["N"]["freshness"], "content-current")
        self.assertEqual(result["nodes"]["R"]["freshness"], "content-current")

    def test_changed_missing_evidence_and_resnapshot_remain_stale(self):
        self.snapshot()
        (self.root / "proof.txt").write_text("new evidence", encoding="utf-8")
        self.assertEqual(self.cli("check", self.root / "state.json")[0], 2)
        revision = self.snapshot("state-2.json", "state.json")
        self.assertEqual(revision["revision"], 2)
        self.assertTrue(all(node["freshness"] == "stale" for node in revision["nodes"].values()))
        self.assertEqual(self.cli("check", self.root / "state-2.json")[0], 2)
        (self.root / "proof.txt").unlink()
        result = self.cli("check", self.root / "state-2.json")[1]
        self.assertEqual(result["nodes"]["R"]["evidence"][0]["availability"], "missing")

    def test_remote_authority_and_evidence_never_count_as_checked(self):
        self.bindings["authorities"]["visual"] = "https://www.figma.com/design/file"
        self.bindings["evidence"]["S"] = ["https://www.figma.com/design/file?node-id=1"]
        self.write("bindings.json", self.bindings)
        self.snapshot()
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        self.assertEqual(result["unavailable_authorities"], ["visual"])
        self.assertEqual(result["nodes"]["S"]["freshness"], "unverified")
        self.assertIn("remote-unchecked", [ref["availability"] for ref in result["nodes"]["S"]["evidence"]])

    def test_removed_dependencies_and_nodes_invalidate_former_dependents(self):
        self.snapshot()
        self.data["nodes"] = [node for node in self.data["nodes"] if node["id"] != "R"]
        self.data["edges"] = [edge for edge in self.data["edges"] if edge["from"] != "R"]
        self.write("graph.json", self.data)
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        self.assertEqual(result["removed_nodes"], ["R"])
        self.assertEqual(result["nodes"]["C"]["freshness"], "stale")

    def test_unresolved_isolated_removal_survives_checks_and_revisions(self):
        self.data["edges"] = []
        self.write("graph.json", self.data)
        self.snapshot()
        self.data["nodes"] = [node for node in self.data["nodes"] if node["id"] != "N"]
        self.write("graph.json", self.data)
        second = self.snapshot("state-2.json", "state.json")
        self.assertEqual(second["removed_nodes"], ["N"])
        code, checked, _ = self.cli("check", self.root / "state-2.json")
        self.assertEqual(code, 2)
        self.assertEqual(checked["removed_nodes"], ["N"])
        self.assertTrue(all(node["freshness"] == "content-current" for node in checked["nodes"].values()))
        third = self.snapshot("state-3.json", "state-2.json")
        self.assertEqual(third["removed_nodes"], ["N"])
        self.assertEqual(self.cli("check", self.root / "state-3.json")[0], 2)

    def test_no_overwrite_or_integrity_bypass(self):
        first = self.snapshot()
        args = ["snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / "state.json"]
        self.assertEqual(self.cli(*args)[0], 1)
        self.assertEqual(json.loads((self.root / "state.json").read_text()), first)
        first["nodes"]["R"]["content_sha256"] = "tampered"
        self.write("state.json", first)
        code, _, error = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 1)
        self.assertIn("integrity mismatch", error)

    def test_graph_sources_and_binding_evidence_have_separate_bases(self):
        graph_dir = self.root / "design"
        graph_dir.mkdir()
        (graph_dir / "proof.txt").write_text("graph evidence", encoding="utf-8")
        self.write("design/graph.json", self.data)
        code, _, error = self.cli("snapshot", "--brief", self.root / "brief.md", "--graph", graph_dir / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / "state.json")
        self.assertEqual(code, 0, error)
        state = json.loads((self.root / "state.json").read_text())
        self.assertEqual([ref["path"] for ref in state["nodes"]["S"]["evidence"]], ["design/proof.txt", "visual.md"])
        self.assertEqual(self.cli("check", self.root / "state.json")[0], 0)

    def test_cycles_terminate_and_metadata_changes_are_tracked(self):
        self.data["edges"].append({"from": "C", "to": "S", "type": "depends-on"})
        self.write("graph.json", self.data)
        self.snapshot()
        self.data["release"] = "new"
        self.write("graph.json", self.data)
        code, result, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        self.assertTrue(all(node["freshness"] == "stale" for node in result["nodes"].values()))

    def test_retargeted_symlinks_are_read_through_original_locators(self):
        for name in ("graph.json", "bindings.json", "brief.md", "visual.md", "proof.txt"):
            with self.subTest(locator=name):
                locator = self.root / name
                original = self.root / ("old-" + name)
                replacement = self.root / ("new-" + name)
                locator.rename(original)
                locator.symlink_to(original.name)
                if name == "graph.json":
                    changed = json.loads(original.read_text())
                    changed["nodes"][1]["title"] = "changed through graph link"
                    replacement.write_text(json.dumps(changed), encoding="utf-8")
                elif name == "bindings.json":
                    changed = json.loads(original.read_text())
                    changed["evidence"]["C"] = ["visual.md"]
                    replacement.write_text(json.dumps(changed), encoding="utf-8")
                else:
                    replacement.write_text("changed through symlink", encoding="utf-8")
                state_name = name + ".state.json"
                state = self.snapshot(state_name)
                if name in ("graph.json", "bindings.json", "brief.md"):
                    key = {"graph.json": "graph", "bindings.json": "bindings", "brief.md": "brief"}[name]
                    self.assertEqual(state["inputs"][key]["path"], name)
                locator.unlink()
                locator.symlink_to(replacement.name)
                code, result, error = self.cli("check", self.root / state_name)
                self.assertEqual(code, 2, error)
                self.assertTrue(any(node["freshness"] == "stale" for node in result["nodes"].values()))
                locator.unlink()
                locator.symlink_to("missing-target")
                code, result, _ = self.cli("check", self.root / state_name)
                self.assertEqual(code, 1 if name in ("graph.json", "bindings.json", "brief.md") else 2)
                if result:
                    refs = list(result["authorities"].values()) + [ref for node in result["nodes"].values() for ref in node["evidence"]]
                    self.assertTrue(any(ref["path"] == name and ref["availability"] == "missing" for ref in refs))
                locator.unlink()
                original.rename(locator)

    def test_intent_authority_accepts_same_file_alias_without_losing_locator(self):
        alias = self.root / "brief-alias.md"
        alias.symlink_to("brief.md")
        code, _, error = self.cli("snapshot", "--brief", alias, "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / "state.json")
        self.assertEqual(code, 0, error)
        state = json.loads((self.root / "state.json").read_text())
        self.assertEqual(state["inputs"]["brief"]["path"], "brief-alias.md")
        self.assertEqual(state["authorities"]["intent"]["path"], "brief.md")
        self.assertEqual(self.cli("check", self.root / "state.json")[0], 0)
        (self.root / "other-brief.md").write_text("other", encoding="utf-8")
        alias.unlink()
        alias.symlink_to("other-brief.md")
        code, _, error = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 1)
        self.assertIn("intent authority", error)

    def test_explicit_local_scope_does_not_hide_local_or_remote_evidence_failures(self):
        del self.bindings["authorities"]["visual"]
        self.write("bindings.json", self.bindings)
        args = ["snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / "local.json"]
        self.assertEqual(self.cli(*args)[0], 1)
        self.assertEqual(self.cli(*args, "--scope", "local-only")[0], 0)
        self.assertEqual(self.cli("check", self.root / "local.json")[0], 0)
        self.bindings["authorities"]["visual"] = "missing.md"
        self.write("bindings.json", self.bindings)
        self.assertEqual(self.cli("check", self.root / "local.json")[0], 2)
        self.bindings["authorities"]["visual"] = "https://example.com/design"
        self.bindings["evidence"]["S"] = ["https://example.com/evidence"]
        self.write("bindings.json", self.bindings)
        self.assertEqual(self.cli("check", self.root / "local.json")[0], 2)
        self.assertEqual(self.cli(*args[:-1], self.root / "next.json", "--previous", self.root / "local.json", "--scope", "full")[0], 1)

    def test_local_scope_remote_visual_is_unchecked_but_missing_local_visual_blocks(self):
        self.bindings["authorities"]["visual"] = "https://example.com/design"
        self.write("bindings.json", self.bindings)
        args = ["snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / "remote.json", "--scope", "local-only"]
        self.assertEqual(self.cli(*args)[0], 0)
        code, result, _ = self.cli("check", self.root / "remote.json")
        self.assertEqual(code, 0)
        self.assertEqual(result["authorities"]["visual"]["availability"], "remote-unchecked")
        self.bindings["authorities"]["visual"] = "missing.md"
        self.write("bindings.json", self.bindings)
        args[args.index(self.root / "remote.json")] = self.root / "missing.json"
        self.assertEqual(self.cli(*args)[0], 0)
        code, result, _ = self.cli("check", self.root / "missing.json")
        self.assertEqual(code, 2)
        self.assertEqual(result["unavailable_authorities"], ["visual"])

    def test_review_pins_exact_state_removals_and_evidence(self):
        first = self.snapshot()
        self.data["nodes"] = [n for n in self.data["nodes"] if n["id"] != "R"]
        self.data["edges"] = [e for e in self.data["edges"] if e["from"] != "R"]
        self.write("graph.json", self.data)
        _, result, _ = self.cli("check", self.root / "state.json")
        review = {"previous_manifest_sha256": first["manifest_sha256"],
                  "current_state_sha256": result["review_target_sha256"],
                  "affected_ids": result["review_affected_ids"], "evidence": "proof.txt",
                  "evidence_sha256": hashlib.sha256((self.root / "proof.txt").read_bytes()).hexdigest(),
                  "review_note": "Reviewed changes and removal."}
        self.assertIn("R", review["affected_ids"])
        self.write("review.json", review)
        args = ["snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--previous", self.root / "state.json", "--review", self.root / "review.json", "--out", self.root / "reviewed.json"]
        self.data["nodes"][0]["title"] = "drift"
        self.write("graph.json", self.data)
        self.assertEqual(self.cli(*args)[0], 1)
        self.data["nodes"][0]["title"] = self.data["nodes"][0]["id"]
        self.write("graph.json", self.data)
        (self.root / "proof.txt").write_text("different evidence")
        self.assertEqual(self.cli(*args)[0], 1)
        (self.root / "proof.txt").write_text("proof.txt")
        self.assertEqual(self.cli(*args)[0], 0)
        self.assertEqual(self.cli("check", self.root / "reviewed.json")[0], 0)
        self.snapshot("descendant.json", "reviewed.json")
        self.assertEqual(self.cli("check", self.root / "descendant.json")[0], 0)
        replay = args.copy()
        replay[replay.index("--previous") + 1] = self.root / "reviewed.json"
        replay[-1] = self.root / "replay.json"
        self.assertEqual(self.cli(*replay)[0], 1)
        (self.root / "proof.txt").write_text("changed review evidence")
        code, checked, _ = self.cli("check", self.root / "reviewed.json")
        self.assertEqual(code, 2)
        self.assertIn("proof.txt", checked["changed_review_pins"])
        code, checked, _ = self.cli("check", self.root / "descendant.json")
        self.assertEqual(code, 2)
        self.assertIn("proof.txt", checked["changed_review_pins"])
        self.assertEqual(self.cli("snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--previous", self.root / "descendant.json", "--out", self.root / "blocked.json")[0], 1)

    def test_falsey_previous_manifest_is_rejected(self):
        for value in ({}, [], None, False):
            self.write("invalid.json", value)
            code, _, _ = self.cli("snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--previous", self.root / "invalid.json", "--out", self.root / "not-created.json")
            self.assertEqual(code, 1)
            self.assertFalse((self.root / "not-created.json").exists())

    def test_non_regular_evidence_is_unavailable_without_blocking(self):
        import os
        os.mkfifo(self.root / "pipe")
        self.bindings["evidence"]["S"] = ["pipe"]
        self.write("bindings.json", self.bindings)
        self.snapshot()
        code, checked, _ = self.cli("check", self.root / "state.json")
        self.assertEqual(code, 2)
        self.assertEqual(checked["nodes"]["S"]["freshness"], "unverified")

    def test_invalid_input_and_missing_brief_fail_without_output(self):
        self.data["version"] = 2
        self.write("graph.json", self.data)
        args = ["snapshot", "--brief", self.root / "brief.md", "--graph", self.root / "graph.json", "--bindings", self.root / "bindings.json", "--out", self.root / "state.json"]
        self.assertEqual(self.cli(*args)[0], 1)
        self.assertFalse((self.root / "state.json").exists())
        self.data["version"] = 1
        self.write("graph.json", self.data)
        (self.root / "brief.md").unlink()
        self.assertEqual(self.cli(*args)[0], 1)


if __name__ == "__main__":
    unittest.main()
