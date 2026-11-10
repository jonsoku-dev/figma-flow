import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "skills" / "figma-flow" / "scripts" / "graph.py"
SPEC = importlib.util.spec_from_file_location("graph", SCRIPT)
graph = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(graph)


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need | quote \"x\"", "status": "observed", "source": "brief"},
                {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                {"id": "figma", "type": "figma", "title": "Frame", "status": "unverified", "source": "Figma draft"},
                {"id": "test", "type": "test", "title": "Flow", "status": "unverified"},
            ],
            "edges": [{"from": "req", "to": "screen", "type": "covers"}, {"from": "screen", "to": "figma", "type": "represented-by"}],
        }

    def _impact_graph(self):
        return {
            "version": 1,
            "nodes": [
                {"id": node_id, "type": "action", "title": node_id, "status": "planned"}
                for node_id in ("a", "b", "c", "d", "e", "f", "x", "y")
            ],
            "edges": [
                {"from": source, "to": target, "type": "links"}
                for source, target in (
                    ("a", "c"), ("a", "b"), ("b", "d"), ("d", "b"),
                    ("b", "f"), ("c", "e"), ("e", "c"), ("c", "f"),
                    ("x", "y"), ("y", "x"),
                )
            ],
        }

    def _local_graph(self):
        return {
            "version": 1,
            "nodes": [
                {"id": node_type, "type": node_type, "title": node_type,
                 "status": "verified" if node_type in {"code", "acceptance", "test"} else "observed",
                 "source": "local-evidence.txt"}
                for node_type in ("requirement", "screen", "code", "acceptance", "test")
            ],
            "edges": [
                {"from": source, "to": target, "type": label}
                for source, target, label in (
                    ("requirement", "screen", "appears on"),
                    ("screen", "code", "implemented by"),
                    ("requirement", "acceptance", "accepted by"),
                    ("acceptance", "test", "checked by"),
                    ("code", "test", "checked by"),
                )
            ],
        }

    def test_strict_local_accepts_complete_declared_coverage_without_figma(self):
        errors, warnings = graph.validate_graph(self._local_graph(), strict_local=True)
        self.assertEqual(errors, [])
        self.assertFalse(any("figma" in warning for warning in warnings))
        self.assertTrue(any("no linked figma" in warning for warning in graph.validate_graph(self._local_graph())[1]))

    def test_strict_local_rejects_missing_or_mislabeled_trace_edges(self):
        for edge_index in range(5):
            for mutation in ("remove", "wrong-label", "reverse"):
                with self.subTest(edge=edge_index, mutation=mutation):
                    data = self._local_graph()
                    if mutation == "remove":
                        del data["edges"][edge_index]
                    elif mutation == "wrong-label":
                        data["edges"][edge_index]["type"] = "unrelated"
                    else:
                        edge = data["edges"][edge_index]
                        edge["from"], edge["to"] = edge["to"], edge["from"]
                    self.assertEqual(graph.validate_graph(data)[0], [])
                    self.assertTrue(graph.validate_graph(data, strict_local=True)[0])

    def test_strict_local_rejects_planned_and_unverified_evidence(self):
        for node_type in ("code", "acceptance", "test"):
            for status in ("planned", "observed", "blocked", "unverified"):
                with self.subTest(node_type=node_type, status=status):
                    data = self._local_graph()
                    next(node for node in data["nodes"] if node["type"] == node_type)["status"] = status
                    errors, _ = graph.validate_graph(data, strict_local=True)
                    self.assertTrue(any("must be verified" in error for error in errors))

    def test_strict_local_does_not_hide_unverified_evidence_behind_a_verified_sibling(self):
        for node_type, owner, label in (("code", "screen", "implemented by"), ("test", "acceptance", "checked by")):
            with self.subTest(node_type=node_type):
                data = self._local_graph()
                data["nodes"].append({"id": "pending", "type": node_type, "title": "Pending evidence", "status": "unverified"})
                data["edges"].append({"from": owner, "to": "pending", "type": label})
                errors, _ = graph.validate_graph(data, strict_local=True)
                self.assertTrue(any("'pending'" in error and "must be verified" in error for error in errors))

    def test_strict_local_rejects_disconnected_and_cross_requirement_tests(self):
        data = self._local_graph()
        other = self._local_graph()
        for node in other["nodes"]:
            node["id"] += "-other"
        for edge in other["edges"]:
            edge["from"] += "-other"
            edge["to"] += "-other"
        data["nodes"].extend(other["nodes"])
        data["edges"].extend(other["edges"])
        self.assertEqual(graph.validate_graph(data, strict_local=True)[0], [])
        for edge in data["edges"]:
            if edge["from"] == "code":
                edge["to"] = "test-other"
            elif edge["from"] == "code-other":
                edge["to"] = "test"
        self.assertEqual(graph.validate_graph(data)[0], [])
        errors, _ = graph.validate_graph(data, strict_local=True)
        self.assertEqual(sum("must share a verified test" in error for error in errors), 4)

    def test_strict_local_rejects_unready_requirements_and_screens(self):
        for node_type in ("requirement", "screen"):
            for status in ("planned", "blocked", "unverified"):
                with self.subTest(node_type=node_type, status=status):
                    data = self._local_graph()
                    next(node for node in data["nodes"] if node["type"] == node_type)["status"] = status
                    self.assertEqual(graph.validate_graph(data)[0], [])
                    errors, _ = graph.validate_graph(data, strict_local=True)
                    self.assertTrue(any("must be observed or verified" in error for error in errors))

    def test_strict_local_checks_every_requirement_screen_and_acceptance(self):
        for node_type in ("requirement", "screen", "acceptance"):
            data = self._local_graph()
            data["nodes"].append({"id": "orphan", "type": node_type, "title": "Orphan", "status": "planned"})
            errors, _ = graph.validate_graph(data, strict_local=True)
            self.assertTrue(any("orphan" in error for error in errors))
        errors, _ = graph.validate_graph({"version": 1, "nodes": [], "edges": []}, strict_local=True)
        self.assertTrue(any("at least one requirement" in error for error in errors))

    def test_strict_local_rejects_indirect_navigation_as_coverage(self):
        data = self._local_graph()
        data["edges"][0] = {"from": "requirement", "to": "code", "type": "depends-on"}
        data["edges"].append({"from": "code", "to": "screen", "type": "navigates to"})
        self.assertEqual(graph.validate_graph(data)[0], [])
        errors, _ = graph.validate_graph(data, strict_local=True)
        self.assertTrue(any("direct 'appears on'" in error for error in errors))

    def test_strict_local_cli_is_opt_in_and_reports_declared_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "graph.json"
            path.write_text(json.dumps(self._local_graph()), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout), redirect_stderr(StringIO()):
                self.assertEqual(graph.main(["validate", str(path), "--strict-local"]), 0)
            self.assertIn("declared local coverage", stdout.getvalue())
            path.write_text(json.dumps(self.sample), encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(graph.main(["validate", str(path)]), 0)
                self.assertEqual(graph.main(["validate", str(path), "--strict-local"]), 1)

    def test_reachability_handles_long_chains_and_many_actions(self):
        data = {"version": 1, "nodes": [], "edges": []}
        for index in range(1200):
            data["nodes"].extend([
                {"id": f"r{index}", "type": "requirement", "title": "Requirement", "status": "observed"},
                {"id": f"s{index}", "type": "screen", "title": "Screen", "status": "observed"},
                {"id": f"a{index}", "type": "action", "title": "Next", "status": "observed",
                 "source_screen": f"s{index}", "target_ids": [f"s{(index + 1) % 1200}"]},
            ])
            data["edges"].extend([
                {"from": f"r{index}", "to": f"s{index}", "type": "appears on"},
                {"from": f"s{index}", "to": f"a{index}", "type": "triggers"},
                {"from": f"a{index}", "to": f"s{(index + 1) % 1200}", "type": "navigates to"},
            ])
        errors, warnings = graph.validate_graph(data)
        self.assertEqual(errors, [])
        self.assertFalse(any("no path to a screen" in warning for warning in warnings))
        self.assertEqual(sum("no linked code" in warning for warning in warnings), 1200)

    def test_rejects_duplicate_ids(self):
        self.sample["nodes"].append(dict(self.sample["nodes"][0]))
        errors, _ = graph.validate_graph(self.sample)
        self.assertTrue(any("Duplicate node id" in error for error in errors))

    def test_version_requires_integer_one(self):
        self.sample["version"] = 1.0
        errors, _ = graph.validate_graph(self.sample)
        self.assertTrue(any("version must be the integer 1" in error for error in errors))

    def test_rejects_bad_endpoint(self):
        self.sample["edges"].append({"from": "screen", "to": "missing", "type": "links"})
        errors, _ = graph.validate_graph(self.sample)
        self.assertTrue(any("unknown node 'missing'" in error for error in errors))

    def test_rejects_wrong_enum_shape_without_crashing(self):
        self.sample["nodes"][0]["type"] = []
        errors, _ = graph.validate_graph(self.sample)
        self.assertTrue(any("nodes[0].type" in error for error in errors))

    def test_requires_nonempty_labels_and_verified_sources(self):
        self.sample["nodes"][0]["title"] = "  "
        self.sample["nodes"][1]["status"] = "verified"
        self.sample["edges"][0]["type"] = ""
        errors, _ = graph.validate_graph(self.sample)
        self.assertTrue(any("title must not be empty" in error for error in errors))
        self.assertTrue(any("source is required for verified" in error for error in errors))
        self.assertTrue(any("edges[0].type must not be empty" in error for error in errors))

    def test_render_escapes_mermaid_and_markdown_content(self):
        errors, _ = graph.validate_graph(self.sample)
        self.assertEqual(errors, [])
        mermaid = graph.render_mermaid(self.sample)
        markdown = graph.render_markdown(self.sample)
        self.assertIn("#quot;", mermaid)
        self.assertNotIn('"x"', mermaid)
        self.assertIn("\\|", markdown)
        self.assertIn("Figma draft", markdown)

    def test_markdown_filtered_views_use_only_selected_nodes_and_direct_edges(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need", "status": "observed"},
                {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                {"id": "figma", "type": "figma", "title": "Frame", "status": "planned"},
                {"id": "code", "type": "code", "title": "View", "status": "planned"},
                {"id": "action", "type": "action", "title": "Save", "status": "planned"},
                {"id": "state", "type": "state", "title": 'Saved "ok" | yes', "status": "planned"},
                {"id": "test", "type": "test", "title": "Check", "status": "planned"},
            ],
            "edges": [
                {"from": "req", "to": "screen", "type": "appears on"},
                {"from": "screen", "to": "figma", "type": "represented by"},
                {"from": "figma", "to": "code", "type": "implemented as"},
                {"from": "screen", "to": "action", "type": "triggers"},
                {"from": "action", "to": "state", "type": "results in"},
                {"from": "action", "to": "test", "type": "checked by"},
                {"from": "code", "to": "test", "type": "checked by"},
            ],
        }

        markdown = graph.render_markdown(data)
        overview = markdown.split("### Overview", 1)[1].split("### Navigation", 1)[0]
        navigation = markdown.split("### Navigation", 1)[1].split("## Diagram (full graph)", 1)[0]
        full_diagram = graph.render_mermaid(data)
        overview_graph = graph._filtered_graph(data, {"requirement", "screen", "figma", "code"})
        navigation_graph = graph._filtered_graph(data, {"screen", "action", "state"})

        self.assertIn("(filtered to selected node types and direct edges)", markdown)
        self.assertIn("req · Need", overview)
        self.assertIn("code · View", overview)
        self.assertNotIn("action · Save", overview)
        self.assertNotIn("test · Check", overview)
        self.assertIn('n0 -->|"appears on"| n1', overview)
        self.assertNotIn('n0 -->|"represented by"| n2', overview)
        self.assertIn("#quot;ok#quot; #124; yes", navigation)
        self.assertNotIn("req · Need", navigation)
        self.assertNotIn("figma · Frame", navigation)
        self.assertIn('n0 -->|"triggers"| n1', navigation)
        self.assertNotIn('n1 -->|"checked by"|', navigation)
        self.assertEqual(markdown.rsplit("```mermaid\n", 1)[1].split("\n```", 1)[0].rstrip("\n"), full_diagram.rstrip("\n"))
        self.assertEqual(overview_graph["edges"], data["edges"][:3])
        self.assertEqual(navigation_graph["edges"], [data["edges"][3], data["edges"][4]])

    def test_markdown_skips_filtered_views_without_nodes_or_edges(self):
        no_view = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need", "status": "planned"},
                {"id": "test", "type": "test", "title": "Check", "status": "planned"},
            ],
            "edges": [{"from": "req", "to": "test", "type": "checked by"}],
        }
        markdown = graph.render_markdown(no_view)
        self.assertNotIn("## Filtered views", markdown)
        self.assertEqual(markdown.rsplit("```mermaid\n", 1)[1].split("\n```", 1)[0].rstrip("\n"), graph.render_mermaid(no_view).rstrip("\n"))

        navigation_only = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need", "status": "planned"},
                {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                {"id": "action", "type": "action", "title": "Tap", "status": "planned"},
                {"id": "state", "type": "state", "title": "Done", "status": "planned"},
            ],
            "edges": [
                {"from": "screen", "to": "action", "type": "triggers"},
                {"from": "action", "to": "state", "type": "results"},
            ],
        }
        markdown = graph.render_markdown(navigation_only)
        self.assertNotIn("### Overview", markdown)
        self.assertIn("### Navigation", markdown)

    def test_mermaid_labels_use_semantic_ids_and_keep_source_details_in_markdown(self):
        self.sample["nodes"][0]["source"] = "https://www.figma.com/file/Abc123/Design"
        self.sample["nodes"][0]["detail"] = "Acceptance context"

        mermaid = graph.render_mermaid(self.sample)
        markdown = graph.render_markdown(self.sample).split("## Edges", 1)[0]

        self.assertIn('n0["req · Need #124; quote #quot;x#quot; (observed)"]', mermaid)
        self.assertNotIn("Figma draft", mermaid)
        self.assertNotIn("https://", mermaid)
        self.assertIn("`requirement`", markdown)
        self.assertIn("`observed`", markdown)
        self.assertIn("Need", markdown)
        self.assertIn('quote "x"', markdown)
        self.assertIn(r"\|", markdown)
        self.assertIn("[open source](<https://www.figma.com/file/Abc123/Design>)", markdown)
        self.assertIn("`Acceptance context`", markdown)

    def test_markdown_keeps_graph_values_inert_and_displays_backtick_ids(self):
        hostile = "![remote](https://example.test/pixel.png) [click](https://example.test/) *em* **bold** _under_"
        self.sample["nodes"][0]["title"] = hostile
        self.sample["nodes"][0]["source"] = "https://example.test/source"
        self.sample["nodes"][0]["id"] = "req``id"
        self.sample["edges"][0]["from"] = "req``id"

        markdown = graph.render_markdown(self.sample)
        graph_text = markdown.split("## Filtered views", 1)[0]

        self.assertIn(f"`{hostile}`", graph_text)
        self.assertIn("[open source](<https://example.test/source>)", graph_text)
        self.assertIn("```req``id```", graph_text)
        self.assertNotIn("![remote]", graph_text.replace(f"`{hostile}`", ""))
        self.assertNotIn("[click]", graph_text.replace(f"`{hostile}`", ""))

    def test_markdown_links_only_safe_https_source_urls(self):
        self.sample["nodes"][0]["source"] = "https://www.figma.com/file/Abc123/Design_(draft)|node`1"
        self.sample["nodes"][0]["title"] = "![title](https://evil.example/pixel) *bold*"
        self.sample["nodes"][0]["detail"] = "[details](https://evil.example/)"
        self.sample["edges"][0]["type"] = "![edge](https://evil.example/pixel)"

        graph_text = graph.render_markdown(self.sample).split("## Diagram", 1)[0]

        self.assertIn("[open source](<https://www.figma.com/file/Abc123/Design_%28draft%29%7Cnode%601>)", graph_text)
        self.assertEqual(graph_text.count("[open source]"), 1)
        self.assertIn("`![title](https://evil.example/pixel) *bold*`", graph_text)
        self.assertIn("`[details](https://evil.example/)`", graph_text)
        self.assertIn("`![edge](https://evil.example/pixel)`", graph_text)

    def test_markdown_keeps_non_https_and_malicious_sources_inert(self):
        for source in (
            "javascript:alert(1)",
            "data:image/png;base64,AAAA",
            "http://example.com/file",
            "https://user:pass@example.com/file",
            "https://example.com/line\nbreak",
            "https://example.com/bad%escape",
        ):
            with self.subTest(source=source):
                self.sample["nodes"][0]["source"] = source
                graph_text = graph.render_markdown(self.sample).split("## Diagram", 1)[0]
                self.assertNotIn("[open source]", graph_text)
                self.assertIn("`", graph_text)

    def test_pipe_and_html_values_remain_visible_without_markdown_structure(self):
        self.sample["nodes"][0]["title"] = "left | <b>middle</b> | right"
        markdown = graph.render_markdown(self.sample)

        self.assertEqual(markdown.count(r"\|"), 2)
        self.assertIn("`  <b>middle</b>  `", markdown)

    def test_mermaid_escapes_edge_delimiters_and_normalizes_newlines(self):
        self.sample["nodes"][0]["title"] = '한글 "label" | # & ;\nnext line'
        self.sample["edges"][0]["type"] = 'covers | " # & ;\n포함'
        mermaid = graph.render_mermaid(self.sample)
        self.assertIn('n0 -->|"covers #124; #quot; #35; #amp; ; 포함"| n1', mermaid)
        self.assertIn("한글 #quot;label#quot; #124; #35; #amp; ; next line", mermaid)
        self.assertNotIn("<br", mermaid)
        self.assertNotIn("\nnext", mermaid)

    def test_markdown_embeds_same_fenced_mermaid_render(self):
        self.sample["nodes"][0]["title"] = "hostile ```mermaid\nlabel"
        self.sample["edges"][0]["type"] = "edge ``` text"
        mermaid = graph.render_mermaid(self.sample)
        markdown = graph.render_markdown(self.sample)
        self.assertIn(f"```mermaid\n{mermaid}\n```", markdown)
        self.assertNotIn("```mermaid\nlabel", markdown)

    def test_partial_unverified_evidence_is_warning_only(self):
        errors, warnings = graph.validate_graph(self.sample)
        self.assertEqual(errors, [])
        self.assertTrue(any("no linked code" in warning for warning in warnings))
        self.assertTrue(any("not verified" in warning for warning in warnings))
        self.assertTrue(any("Node 'figma' is unverified, not verified" in warning for warning in warnings))
        self.assertEqual(sum(warning.startswith("Test 'test'") for warning in warnings), 1)

    def test_missing_requirement_and_screen_are_coverage_warnings(self):
        graph_data = {"version": 1, "nodes": [{"id": "action", "type": "action", "title": "Tap", "status": "planned"}], "edges": []}
        errors, warnings = graph.validate_graph(graph_data)
        self.assertEqual(errors, [])
        self.assertTrue(any("no requirement nodes" in warning for warning in warnings))
        self.assertTrue(any("no screen nodes" in warning for warning in warnings))

    def test_action_metadata_rejects_disagreeing_source_and_target_edges(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "screen-a", "type": "screen", "title": "A", "status": "planned"},
                {"id": "screen-b", "type": "screen", "title": "B", "status": "planned"},
                {"id": "action", "type": "action", "title": "Open B", "status": "planned", "source_screen": "screen-a", "target_ids": ["screen-b"]},
            ],
            "edges": [{"from": "screen-b", "to": "action", "type": "opens"}, {"from": "action", "to": "screen-a", "type": "opens"}],
        }

        errors, _ = graph.validate_graph(data)

        self.assertEqual(sum("source_screen disagrees" in error for error in errors), 1)
        self.assertEqual(sum("target_ids[0] disagrees" in error for error in errors), 1)

        data["edges"] = [{"from": "screen-a", "to": "action", "type": "opens"}, {"from": "action", "to": "screen-b", "type": "opens"}]
        errors, _ = graph.validate_graph(data)
        self.assertEqual(errors, [])

    def test_action_can_have_multiple_targets_or_no_destination(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                {"id": "state-a", "type": "state", "title": "Saved", "status": "planned"},
                {"id": "state-b", "type": "state", "title": "Closed", "status": "planned"},
                {"id": "save", "type": "action", "title": "Save", "status": "planned", "source_screen": "screen", "target_ids": ["state-a", "state-b"]},
                {"id": "back", "type": "action", "title": "Back", "status": "planned", "source_screen": "screen"},
            ],
            "edges": [
                {"from": "screen", "to": "save", "type": "triggers"},
                {"from": "save", "to": "state-a", "type": "results-in"},
                {"from": "save", "to": "state-b", "type": "results-in"},
                {"from": "screen", "to": "back", "type": "triggers"},
            ],
        }

        errors, _ = graph.validate_graph(data)
        self.assertEqual(errors, [])

    def test_action_metadata_rejects_unlisted_screen_sources_and_destinations(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "screen-a", "type": "screen", "title": "A", "status": "planned"},
                {"id": "screen-b", "type": "screen", "title": "B", "status": "planned"},
                {"id": "state-a", "type": "state", "title": "Expected", "status": "planned"},
                {"id": "state-b", "type": "state", "title": "Unexpected", "status": "planned"},
                {"id": "code", "type": "code", "title": "Implementation", "status": "planned"},
                {"id": "test", "type": "test", "title": "Check", "status": "planned"},
                {"id": "action", "type": "action", "title": "Save", "status": "planned", "source_screen": "screen-a", "target_ids": ["state-a"]},
            ],
            "edges": [
                {"from": "screen-a", "to": "action", "type": "triggers"},
                {"from": "screen-b", "to": "action", "type": "triggers"},
                {"from": "action", "to": "state-a", "type": "results-in"},
                {"from": "action", "to": "state-b", "type": "results-in"},
                {"from": "action", "to": "code", "type": "implemented-by"},
                {"from": "action", "to": "test", "type": "checked-by"},
            ],
        }

        errors, _ = graph.validate_graph(data)

        self.assertTrue(any("source_screen omits incoming screen edge 'screen-b' -> 'action'" in error for error in errors))
        self.assertTrue(any("target_ids omits outgoing destination edge 'action' -> 'state-b'" in error for error in errors))
        self.assertFalse(any("code" in error or "test" in error for error in errors))

        data["edges"] = [edge for edge in data["edges"] if edge["from"] != "screen-b" and edge["to"] != "state-b"]
        errors, _ = graph.validate_graph(data)
        self.assertEqual(errors, [])

    def test_malformed_referenced_node_types_do_not_crash_action_checks(self):
        for label, bad_node, bad_edge in (
            ("missing", {"id": "bad", "title": "Missing type", "status": "planned"}, {"from": "bad", "to": "action", "type": "triggers"}),
            ("malformed", {"id": "bad", "type": [], "title": "Bad type", "status": "planned"}, {"from": "action", "to": "bad", "type": "destination"}),
        ):
            with self.subTest(node_type=label):
                data = {
                    "version": 1,
                    "nodes": [
                        {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                        {"id": "action", "type": "action", "title": "Tap", "status": "planned", "source_screen": "screen", "target_ids": []},
                        bad_node,
                    ],
                    "edges": [{"from": "screen", "to": "action", "type": "triggers"}, bad_edge],
                }
                errors, _ = graph.validate_graph(data)
                self.assertTrue(any("nodes[2]" in error for error in errors))

                with tempfile.TemporaryDirectory() as temp:
                    graph_path = Path(temp) / "graph.json"
                    graph_path.write_text(json.dumps(data), encoding="utf-8")
                    result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(graph_path)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)

    def test_requirement_reachability_warns_per_acceptance_and_handles_cycles(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need", "status": "observed"},
                {"id": "connected", "type": "acceptance", "title": "Connected", "status": "planned"},
                {"id": "disconnected", "type": "acceptance", "title": "Disconnected", "status": "planned"},
                {"id": "test-connected", "type": "test", "title": "Connected flow", "status": "planned"},
                {"id": "test-cycle", "type": "test", "title": "Disconnected flow", "status": "planned"},
            ],
            "edges": [
                {"from": "req", "to": "connected", "type": "covers"},
                {"from": "connected", "to": "test-connected", "type": "verified-by"},
                {"from": "disconnected", "to": "test-cycle", "type": "verified-by"},
                {"from": "test-cycle", "to": "disconnected", "type": "retries"},
            ],
        }

        errors, warnings = graph.validate_graph(data)

        self.assertEqual(errors, [])
        self.assertFalse(any("Acceptance 'connected' has no inbound path" in warning for warning in warnings))
        self.assertTrue(any("Acceptance 'disconnected' has no inbound path" in warning for warning in warnings))

        data["nodes"].remove(data["nodes"][0])
        data["edges"] = [{"from": "disconnected", "to": "test-cycle", "type": "verified-by"}, {"from": "test-cycle", "to": "disconnected", "type": "retries"}]
        errors, warnings = graph.validate_graph(data)
        self.assertEqual(errors, [])
        self.assertTrue(any("Graph has no requirement nodes" in warning for warning in warnings))
        self.assertTrue(any("Acceptance 'disconnected' has no inbound path from a requirement" in warning for warning in warnings))

    def test_action_metadata_type_and_reference_errors_do_not_crash(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need", "status": "observed"},
                {"id": "action", "type": "action", "title": "Tap", "status": "planned", "source_screen": [], "target_ids": ["missing", 4]},
            ],
            "edges": [],
        }

        errors, _ = graph.validate_graph(data)

        self.assertTrue(any("source_screen must be a string" in error for error in errors))
        self.assertTrue(any("target_ids[1] must be a string" in error for error in errors))
        self.assertTrue(any("target_ids[0] references unknown node 'missing'" in error for error in errors))

    def test_malformed_action_ids_report_errors_without_traceback(self):
        for bad_id in ([], {}):
            with self.subTest(action_id=bad_id):
                data = {
                    "version": 1,
                    "nodes": [
                        {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                        {"id": "destination", "type": "state", "title": "Done", "status": "planned"},
                        {"id": bad_id, "type": "action", "title": "Open", "status": "planned", "source_screen": "screen", "target_ids": ["destination"]},
                    ],
                    "edges": [],
                }
                errors, _ = graph.validate_graph(data)
                self.assertTrue(any("nodes[2].id must be a string" in error for error in errors))

                with tempfile.TemporaryDirectory() as temp:
                    graph_path = Path(temp) / "graph.json"
                    graph_path.write_text(json.dumps(data), encoding="utf-8")
                    result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(graph_path)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("nodes[2].id must be a string", result.stderr)

    def test_old_action_nodes_remain_valid_with_nonfatal_warning(self):
        data = {"version": 1, "nodes": [{"id": "old-action", "type": "action", "title": "Tap", "status": "planned"}], "edges": []}

        errors, warnings = graph.validate_graph(data)

        self.assertEqual(errors, [])
        self.assertTrue(any("Action 'old-action' has no source_screen field" in warning for warning in warnings))
        self.assertTrue(any("Action 'old-action' has no target_ids field" in warning for warning in warnings))

    def test_action_without_target_ids_warns_but_empty_list_is_explicit(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "screen", "type": "screen", "title": "Main", "status": "planned"},
                {"id": "action", "type": "action", "title": "Back", "status": "planned", "source_screen": "screen"},
            ],
            "edges": [{"from": "screen", "to": "action", "type": "triggers"}],
        }

        errors, warnings = graph.validate_graph(data)

        self.assertEqual(errors, [])
        self.assertTrue(any("Action 'action' has no target_ids field" in warning for warning in warnings))

        data["nodes"][1]["target_ids"] = []
        errors, warnings = graph.validate_graph(data)
        self.assertEqual(errors, [])
        self.assertFalse(any("Action 'action' has no target_ids field" in warning for warning in warnings))

    def test_acceptance_without_requirement_inbound_path_is_warning_only(self):
        data = {
            "version": 1,
            "nodes": [
                {"id": "req", "type": "requirement", "title": "Need", "status": "observed"},
                {"id": "acceptance", "type": "acceptance", "title": "Partial", "status": "planned"},
            ],
            "edges": [],
        }

        errors, warnings = graph.validate_graph(data)

        self.assertEqual(errors, [])
        self.assertTrue(any("Acceptance 'acceptance' has no inbound path from a requirement" in warning for warning in warnings))

        data["edges"].append({"from": "req", "to": "acceptance", "type": "covers"})
        errors, warnings = graph.validate_graph(data)
        self.assertEqual(errors, [])
        self.assertFalse(any("inbound path from a requirement" in warning for warning in warnings))

    def test_acceptance_nodes_warn_for_missing_test_path_and_partial_evidence(self):
        graph_data = {
            "version": 1,
            "nodes": [
                {"id": "acceptance", "type": "acceptance", "title": "Must work", "status": "blocked"},
                {"id": "test", "type": "test", "title": "Flow", "status": "planned"},
            ],
            "edges": [],
        }
        errors, warnings = graph.validate_graph(graph_data)
        self.assertEqual(errors, [])
        self.assertTrue(any("Acceptance 'acceptance' has no path to a test" in warning for warning in warnings))
        self.assertTrue(any("Node 'acceptance' is blocked, not verified" in warning for warning in warnings))

        graph_data["edges"].append({"from": "acceptance", "to": "test", "type": "verified-by"})
        errors, warnings = graph.validate_graph(graph_data)
        self.assertEqual(errors, [])
        self.assertFalse(any("Acceptance 'acceptance' has no path to a test" in warning for warning in warnings))

    def test_impact_requires_an_existing_start_before_loading_networkx(self):
        with mock.patch.object(graph.importlib, "import_module") as import_module:
            with self.assertRaisesRegex(ValueError, "Unknown start node: 'missing'"):
                graph.impact_report(self._impact_graph(), "missing")
            import_module.assert_not_called()

        stdout, stderr = StringIO(), StringIO()
        with mock.patch.object(graph.importlib, "import_module") as import_module, redirect_stdout(stdout), redirect_stderr(stderr):
            with tempfile.TemporaryDirectory() as temp:
                graph_path = Path(temp) / "graph.json"
                graph_path.write_text(json.dumps(self._impact_graph()), encoding="utf-8")
                result = graph.main(["impact", str(graph_path), "--from", "missing"])
        self.assertEqual(result, 1)
        self.assertIn("Unknown start node: 'missing'", stderr.getvalue())
        import_module.assert_not_called()

    def test_impact_cli_rejects_malformed_graph_before_loading_networkx(self):
        data = self._impact_graph()
        data["nodes"][0]["status"] = "invalid"
        stdout, stderr = StringIO(), StringIO()
        with mock.patch.object(graph.importlib, "import_module") as import_module, redirect_stdout(stdout), redirect_stderr(stderr):
            with tempfile.TemporaryDirectory() as temp:
                graph_path = Path(temp) / "graph.json"
                graph_path.write_text(json.dumps(data), encoding="utf-8")
                result = graph.main(["impact", str(graph_path), "--from", "a"])
        self.assertEqual(result, 1)
        self.assertIn("nodes[0].status", stderr.getvalue())
        import_module.assert_not_called()

    def test_impact_reports_sorted_shortest_paths_and_reachable_cyclic_components(self):
        if importlib.util.find_spec("networkx") is None:
            self.skipTest("NetworkX is not installed")
        data = self._impact_graph()

        report = graph.impact_report(data, "a")

        self.assertIn("Candidate impacts", report["classification"])
        self.assertIn("directed edges only", report["classification"])
        self.assertIn("no reverse or semantic dependency is inferred", report["classification"])
        self.assertIn("changes are not verified", report["classification"])
        self.assertEqual(report["start"], "a")
        self.assertEqual([item["id"] for item in report["impacted"]], ["b", "c", "d", "e", "f"])
        paths = {item["id"]: item["path"] for item in report["impacted"]}
        self.assertEqual(paths["b"], ["a", "b"])
        self.assertEqual(paths["d"], ["a", "b", "d"])
        self.assertEqual(next(item["path"] for item in report["impacted"] if item["id"] == "f"), ["a", "b", "f"])
        self.assertEqual(report["cyclic_components"], [["b", "d"], ["c", "e"]])

    def test_impact_cli_emits_json_and_missing_networkx_has_install_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            graph_path.write_text(json.dumps(self._impact_graph()), encoding="utf-8")

            stdout, stderr = StringIO(), StringIO()
            with mock.patch.object(graph.importlib, "import_module", side_effect=ImportError("missing")), redirect_stdout(stdout), redirect_stderr(stderr):
                result = graph.main(["impact", str(graph_path), "--from", "a"])
            self.assertEqual(result, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("NetworkX is required for impact analysis", stderr.getvalue())
            self.assertIn("virtual environment in the task workspace", stderr.getvalue())
            self.assertIn("python -m pip install -r", stderr.getvalue())
            requirements = SCRIPT.resolve().parents[3] / "requirements-optional.txt"
            self.assertIn(f'"{requirements}"', stderr.getvalue())
            self.assertIn("managed plugin cache remains unchanged", stderr.getvalue())

            if importlib.util.find_spec("networkx") is None:
                self.skipTest("NetworkX is not installed; missing-library behavior was verified")
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = graph.main(["impact", str(graph_path), "--from", "a"])
            self.assertEqual(result, 0, stderr.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["cyclic_components"], [["b", "d"], ["c", "e"]])

    def test_render_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            out_dir = Path(temp) / "out"
            out_dir.mkdir()
            (out_dir / "screen-graph.md").write_text("preserve", encoding="utf-8")
            graph_path.write_text(json.dumps(self.sample), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(graph_path), "--out-dir", str(out_dir)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertEqual((out_dir / "screen-graph.md").read_text(encoding="utf-8"), "preserve")

    def test_rejects_unpaired_surrogates_in_graph_string_fields(self):
        node = {"id": "node", "type": "action", "title": "Title", "status": "planned", "source": "source", "detail": "detail"}
        for field in ("id", "title", "source", "detail", "type", "status"):
            with self.subTest(node_field=field):
                data = {"version": 1, "nodes": [dict(node)], "edges": []}
                data["nodes"][0][field] = "\ud800"
                errors, _ = graph.validate_graph(data)
                self.assertTrue(any(f"nodes[0].{field}" in error and "unpaired Unicode surrogate" in error for error in errors))
                self.assertTrue(all(error.isascii() for error in errors))

        edge = {"from": "node", "to": "node", "type": "links"}
        for field in ("from", "to", "type"):
            with self.subTest(edge_field=field):
                data = {"version": 1, "nodes": [dict(node)], "edges": [dict(edge)]}
                data["edges"][0][field] = "\ud800"
                errors, _ = graph.validate_graph(data)
                self.assertTrue(any(f"edges[0].{field}" in error and "unpaired Unicode surrogate" in error for error in errors))
                self.assertTrue(all(error.isascii() for error in errors))

        for field, value in (("source_screen", "\ud800"), ("target_ids", ["\ud800"])):
            with self.subTest(action_field=field):
                action = {"id": "action", "type": "action", "title": "Tap", "status": "planned", field: value}
                errors, _ = graph.validate_graph({"version": 1, "nodes": [action], "edges": []})
                self.assertTrue(any(f"nodes[0].{field}" in error and "unpaired Unicode surrogate" in error for error in errors))
                self.assertTrue(all(error.isascii() for error in errors))

    def test_cli_rejects_surrogate_json_without_traceback_or_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            out_dir = Path(temp) / "out"
            graph_data = {
                "version": 1,
                "nodes": [{"id": "r", "type": "requirement", "title": "\ud800", "status": "observed"}],
                "edges": [],
            }
            graph_path.write_text(json.dumps(graph_data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(graph_path), "--out-dir", str(out_dir)], capture_output=True, text=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("unpaired Unicode surrogate", result.stderr)
            self.assertTrue(result.stderr.isascii())
            self.assertFalse((out_dir / "screen-graph.md").exists())
            self.assertFalse((out_dir / "screen-graph.mmd").exists())

    def test_cli_renders_korean_and_emoji(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            out_dir = Path(temp) / "out"
            graph_data = {
                "version": 1,
                "nodes": [{"id": "r", "type": "requirement", "title": "한글 😀", "status": "observed"}],
                "edges": [],
            }
            graph_path.write_text(json.dumps(graph_data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(graph_path), "--out-dir", str(out_dir)], capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("한글 😀", (out_dir / "screen-graph.md").read_text(encoding="utf-8"))
            self.assertIn("한글 😀", (out_dir / "screen-graph.mmd").read_text(encoding="utf-8"))

    def test_unicode_write_error_cleans_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            out_dir = Path(temp) / "out"
            graph_path.write_text(json.dumps(self.sample), encoding="utf-8")
            stderr = StringIO()
            with mock.patch.object(graph, "render_mermaid", return_value="\ud800"), redirect_stderr(stderr):
                result = graph.main(["render", str(graph_path), "--out-dir", str(out_dir)])

            self.assertEqual(result, 1)
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertIn("invalid text encoding", stderr.getvalue())
            self.assertFalse((out_dir / "screen-graph.md").exists())
            self.assertFalse((out_dir / "screen-graph.mmd").exists())

    def test_render_refuses_dangling_symlink_without_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            out_dir = Path(temp) / "out"
            out_dir.mkdir()
            dangling = out_dir / "screen-graph.mmd"
            dangling.symlink_to(Path(temp) / "missing-target")
            graph_path.write_text(json.dumps(self.sample), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(graph_path), "--out-dir", str(out_dir)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(dangling.is_symlink())
            self.assertFalse((out_dir / "screen-graph.md").exists())

    def test_second_write_failure_cleans_owned_output_and_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            out_dir = Path(temp) / "out"
            graph_path.write_text(json.dumps(self.sample), encoding="utf-8")
            original = graph._write_exclusive
            calls = 0

            def fail_second(path, content):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated write failure")
                return original(path, content)

            with mock.patch.object(graph, "_write_exclusive", side_effect=fail_second), redirect_stderr(StringIO()):
                self.assertEqual(graph.main(["render", str(graph_path), "--out-dir", str(out_dir)]), 1)
            self.assertFalse((out_dir / "screen-graph.md").exists())
            self.assertFalse((out_dir / "screen-graph.mmd").exists())
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(graph_path), "--out-dir", str(out_dir)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out_dir / "screen-graph.md").exists())
            self.assertTrue((out_dir / "screen-graph.mmd").exists())

    def test_cli_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "graph.json"
            graph_path.write_text("{", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(graph_path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Cannot read graph JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
