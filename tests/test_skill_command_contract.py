"""Exercise the CLI paths published by the Figma Flow skill documents."""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/figma-flow/scripts"


class SkillCommandContractTests(unittest.TestCase):
    def test_generated_workflow_is_exact_and_rejects_a_mutated_projection(self):
        generated = ROOT / "skills/figma-flow/references/workflow.generated.md"
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/sync_workflow.py"), "--check"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["synchronized"])

        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import sync_workflow
            expected = sync_workflow.artifacts()[generated]
        finally:
            sys.path.remove(str(ROOT / "tools"))
        actual = generated.read_text(encoding="utf-8")
        self.assertEqual(actual, expected)
        mutated = actual.replace("Canonical production workflow", "Changed workflow")
        self.assertNotEqual(mutated, expected)

    def test_published_graph_ssot_and_trace_commands_run_and_reject_bad_coverage(self):
        readme = (ROOT / "skills/figma-flow/SKILL.md").read_text(encoding="utf-8")
        contract = (ROOT / "skills/figma-flow/references/graph-contract.md").read_text(encoding="utf-8")
        self.assertIn("graph.py validate GRAPH --strict-local", readme)
        self.assertIn("graph.py render GRAPH --strict-local --out-dir NEW_DIRECTORY", readme)
        self.assertIn("ssot.py snapshot ... --scope local-only", readme)
        self.assertIn("trace_report.py GRAPH --check CHECK_JSON --out NEW_FILE.html", readme)
        self.assertIn('ssot.py" check ./run/manifest-001.json', contract)

        route = subprocess.run(
            [sys.executable, str(ROOT / "tools/figma_feature.py"), "route", "components"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(route.returncode, 0, route.stdout + route.stderr)
        route_result = json.loads(route.stdout)
        self.assertEqual(route_result["status"], "routed")
        self.assertEqual(route_result["reference"], "skills/figma-flow/references/figma-feature-routes.md")
        self.assertEqual(route_result["execution"], "not-executed")

        with tempfile.TemporaryDirectory(prefix="skill-cli-contract-") as temp:
            root = Path(temp)
            for name in ("brief.md", "visual.md", "app.py", "proof.txt"):
                (root / name).write_text(name, encoding="utf-8")
            graph = {
                "version": 1,
                "nodes": [
                    {"id": "R", "type": "requirement", "title": "Requirement", "status": "observed", "source": "proof.txt"},
                    {"id": "S", "type": "screen", "title": "Screen", "status": "observed", "source": "proof.txt"},
                    {"id": "C", "type": "code", "title": "Code", "status": "verified", "source": "proof.txt"},
                    {"id": "A", "type": "acceptance", "title": "Acceptance", "status": "verified", "source": "proof.txt"},
                    {"id": "T", "type": "test", "title": "Test", "status": "verified", "source": "proof.txt"},
                ],
                "edges": [
                    {"from": "R", "to": "S", "type": "appears on"},
                    {"from": "S", "to": "C", "type": "implemented by"},
                    {"from": "R", "to": "A", "type": "accepted by"},
                    {"from": "A", "to": "T", "type": "checked by"},
                    {"from": "C", "to": "T", "type": "checked by"},
                ],
            }
            graph_path = root / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            validate = [sys.executable, str(SCRIPTS / "graph.py"), "validate", str(graph_path), "--strict-local"]
            passed = subprocess.run(validate, cwd=root, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)

            render = subprocess.run(
                [sys.executable, str(SCRIPTS / "graph.py"), "render", str(graph_path),
                 "--strict-local", "--out-dir", str(root / "rendered")],
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(render.returncode, 0, render.stdout + render.stderr)
            self.assertTrue((root / "rendered/screen-graph.md").is_file())
            self.assertTrue((root / "rendered/screen-graph.mmd").is_file())

            bindings = {
                "version": 1,
                "authorities": {"intent": "brief.md", "visual": "visual.md", "implementation": "app.py"},
                "dependency_edge_types": ["depends-on"],
                "evidence": {"S": ["proof.txt"], "A": ["proof.txt"], "C": ["proof.txt"], "T": ["proof.txt"]},
            }
            bindings_path = root / "bindings.json"
            bindings_path.write_text(json.dumps(bindings), encoding="utf-8")
            manifest = root / "manifest-001.json"
            snapshot = subprocess.run(
                [sys.executable, str(SCRIPTS / "ssot.py"), "snapshot", "--brief", str(root / "brief.md"),
                 "--graph", str(graph_path), "--bindings", str(bindings_path), "--scope", "local-only",
                 "--out", str(manifest)], cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(snapshot.returncode, 0, snapshot.stdout + snapshot.stderr)
            check_path = root / "check.json"
            checked = subprocess.run(
                [sys.executable, str(SCRIPTS / "ssot.py"), "check", str(manifest)],
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            check_path.write_text(checked.stdout, encoding="utf-8")

            report_path = root / "trace.html"
            report = subprocess.run(
                [sys.executable, str(SCRIPTS / "trace_report.py"), str(graph_path), "--check", str(check_path),
                 "--out", str(report_path)], cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
            self.assertIn("<!doctype html>", report_path.read_text(encoding="utf-8").lower())

            graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "accepted by"]
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            rejected = subprocess.run(validate, cwd=root, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
            self.assertIn("accepted by", rejected.stderr)

    @unittest.skipUnless(shutil.which("node"), "live example runner requires Node.js")
    def test_published_live_example_first_command_produces_documented_artifacts(self):
        guide = ROOT / "skills/figma-flow/references/live-example.md"
        text = guide.read_text(encoding="utf-8")
        self.assertIn("python3 tools/run_local.py --out /tmp/figma-flow-study-001", text)
        with tempfile.TemporaryDirectory(prefix="figma-flow-live-example-") as temp:
            out = Path(temp) / "study-001"
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/run_local.py"), "--out", str(out)],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((out / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "passed")
            for relative in ("ssot-check.json", "manifest-001.json", "rendered/screen-graph.md",
                             "trace.html", "screen-spec.md", "app", "tests"):
                self.assertTrue((out / relative).exists(), relative)

    def test_unslop_adaptation_credit_matches_pinned_upstream_provenance(self):
        guide = (ROOT / "skills/figma-flow/references/unslop.md").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "vendor/skills/manifest.json").read_text(encoding="utf-8"))
        package = manifest["skills"]["unslop"]
        source = package["source"]
        self.assertEqual(source["repository"], "https://github.com/heydamir/unslop")
        self.assertEqual(source["commit"], "97daa3eb365670ea3f87ed85356cbfcee18105a5")
        self.assertEqual(source["path"], "skills/unslop")
        self.assertEqual(package["license"], "CC-BY-4.0")
        self.assertIn(source["repository"] + "/tree/" + source["commit"] + "/" + source["path"], guide)
        self.assertIn("Damir Sokolovsky", guide)
        self.assertIn("CC BY 4.0", guide)
        pinned_license = package["files"]["LICENSE"]
        actual_license = hashlib.sha256((ROOT / package["directory"] / "LICENSE").read_bytes()).hexdigest()
        self.assertEqual(actual_license, pinned_license)

    def test_draft_build_commands_use_selected_project_paths(self):
        guide = (ROOT / "skills/figma-flow/references/draft-build.md").read_text(encoding="utf-8")
        self.assertNotIn("figma-flow-local-0.4.0", guide)
        self.assertNotIn("figma-flow-cards-work", guide)
        for variable in ("CATALOG_JSON", "IDEA_LABEL", "IDEA_GRAPH", "BRIEF_PATH", "SELECTION_PATH",
                         "BUILD_OUT", "PREPARED_OUT", "PROJECT_ROOT", "MANIFEST_PATH", "PREVIOUS_GRAPH",
                         "TEST_MAPPING", "INSPECTION_OUT", "PLAN_OUT", "TEST_RUN_OUT"):
            self.assertIn("export " + variable + "=", guide)
        self.assertIn('--catalog "$CATALOG_JSON"', guide)
        self.assertIn("Path(os.environ['IDEA_GRAPH'])", guide)
        self.assertIn('check_project.py "$MANIFEST_PATH" --previous-graph "$PREVIOUS_GRAPH"', guide)

        commands = {
            "serve_ideas.py": ("--catalog", "--idea", "--graph", "--brief", "--selection", "--out", "--open-reviewed"),
            "promote_idea.py": ("--catalog", "--idea", "--graph", "--brief", "--selection", "--out", "--prepare-only", "--finish"),
            "check_project.py": ("--previous-graph", "--out"),
            "affected_tests.py": ("--project", "--mapping", "--out", "--run"),
        }
        for command, expected_options in commands.items():
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / command), "--help"],
                    cwd=ROOT, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for option in expected_options:
                    self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
