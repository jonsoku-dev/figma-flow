"""Offline witnesses for library pins, projections, and maintained catalogs."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import campaign_forms
import campaign_library
import figma_api_inventory
import figma_rest_inventory
import figma_widget_project
import route_design
import sync_workflow
import workflow


def pinned_compiler(env_names, expected_name):
    value = next((os.environ.get(name) for name in env_names if os.environ.get(name)), None)
    if not value:
        raise unittest.SkipTest(f"Set one of {', '.join(env_names)} to the pinned TypeScript 5.9.3 compiler")
    compiler = Path(value).resolve()
    package = json.loads((compiler.parent.parent / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "typescript" or package.get("version") != "5.9.3" or compiler.name != expected_name:
        raise AssertionError("The supplied compiler must be the pinned TypeScript 5.9.3 package")
    return compiler


class LibraryReleaseWitnessTests(unittest.TestCase):
    def test_upstream_api_pins_and_rest_projection_are_offline_and_deterministic(self):
        try:
            import yaml
        except ImportError as exc:
            raise unittest.SkipTest("Install the pinned PyYAML 6.0.2 toolchain to regenerate REST inventory") from exc
        self.assertEqual(yaml.__version__, "6.0.2")
        plugin = figma_api_inventory.verify_source()
        widget = figma_widget_project.verify_source()
        rest_source, raw_rest = figma_rest_inventory.verify_source()
        self.assertEqual((plugin["version"], plugin["ref"]),
                         ("1.142.0", "dff4874ca083e18cd74835fd5afc5079d46866b7"))
        self.assertEqual((widget["version"], widget["ref"]),
                         ("1.13.0", "8815555bab1cf358ee9958fe2fa2cf46f77f3fb6"))
        self.assertEqual((rest_source["version"], rest_source["ref"]),
                         ("0.47.0", "af027cd20aca8326a41115e4d15bbdf875158e81"))
        self.assertEqual(hashlib.sha256(raw_rest).hexdigest(), rest_source["source_sha256"])
        self.assertEqual(figma_rest_inventory.canonical(figma_rest_inventory.build()),
                         figma_rest_inventory.INDEX.read_text(encoding="utf-8"))
        rest_requirements = (ROOT / "library/figma-rest/requirements.txt").read_text(encoding="utf-8")
        self.assertEqual("PyYAML==6.0.2\n", rest_requirements)
        self.assertEqual(gzip.decompress((ROOT / "library/figma-rest/openapi.yaml.gz").read_bytes()), raw_rest)

    def test_plugin_api_index_and_static_status_snapshot_rebuild_from_pinned_typescript(self):
        typescript = pinned_compiler(("FIGMA_API_TYPESCRIPT", "FIGMA_SDK_TEST_TYPESCRIPT"), "typescript.js")
        catalog = figma_api_inventory.build(str(typescript))
        self.assertEqual(figma_api_inventory.canonical(catalog),
                         figma_api_inventory.INDEX.read_text(encoding="utf-8"))
        result = figma_api_inventory.coverage(catalog, str(typescript))
        compact = {key: value for key, value in result.items() if key != "members"}
        compact["members"] = [{key: row[key] for key in ("id", "status", "implementation", "runtime_acceptance")}
                              for row in result["members"]]
        baseline = json.loads((ROOT / "library/figma-api/coverage-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(compact, baseline)
        self.assertTrue(all(row["implementation"] == "unverified" and row["runtime_acceptance"] == "unverified"
                            for row in result["members"]))

    def test_recipe_manifest_and_bundle_inventory_have_closed_pinned_entries(self):
        recipes = ROOT / "library/figma-recipes"
        manifest = json.loads((recipes / "manifest.json").read_text(encoding="utf-8"))
        bundle = json.loads((recipes / "bundle.json").read_text(encoding="utf-8"))
        entries = {row["id"]: row for row in manifest["recipes"]}
        compiled = {row["id"]: row for row in bundle["recipes"]}
        self.assertEqual(set(entries), set(compiled) | {row["id"] for row in bundle["sdkGraphRecipes"]})
        for identifier, row in compiled.items():
            with self.subTest(recipe=identifier):
                source = recipes / row["source"]
                target = recipes / row["entry"]
                self.assertEqual(row["sourceSha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(row["jsSha256"], hashlib.sha256(target.read_bytes()).hexdigest())
                self.assertEqual(entries[identifier]["entry"], row["source"])
        helper = next(row for row in compiled.values() if row["id"] == "design-component-properties")
        helper_path = recipes / helper["helpers"]
        self.assertEqual(helper["helpersSha256"], hashlib.sha256(helper_path.read_bytes()).hexdigest())
        self.assertEqual(bundle["typescriptVersion"], "5.9.3")
        graph_bundle = bundle["sdkGraphRecipes"]
        self.assertEqual([row["id"] for row in graph_bundle], ["design-type-review"])
        graph_row = graph_bundle[0]
        self.assertEqual(graph_row["graphTemplateSha256"],
                         hashlib.sha256((recipes / graph_row["graphTemplate"]).read_bytes()).hexdigest())
        self.assertEqual(graph_row["sourceSha256"],
                         hashlib.sha256((recipes / graph_row["source"]).read_bytes()).hexdigest())
        rollback = subprocess.run(["node", str(recipes / "test-rollback.cjs")],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)

    def test_library_readmes_preserve_upstream_and_example_evidence_limits(self):
        api_readme = (ROOT / "library/figma-api/README.md").read_text(encoding="utf-8")
        rest_readme = (ROOT / "library/figma-rest/README.md").read_text(encoding="utf-8")
        widget_readme = (ROOT / "library/figma-widget/README.md").read_text(encoding="utf-8")
        widget_guide = (ROOT / "docs/figma-widget.md").read_text(encoding="utf-8")
        recipes_readme = (ROOT / "docs/figma-recipes.md").read_text(encoding="utf-8")
        self.assertIn("offline declaration catalog, not an executor or a runtime support claim", api_readme)
        self.assertIn("No network request is made by the CLI.", api_readme)
        self.assertIn("Every row retains `implementation: unverified` and `runtime_acceptance: unverified`.", api_readme)
        self.assertIn("never read credentials or send HTTP requests.", rest_readme)
        self.assertIn("Nothing evaluates or runs the returned command automatically.", rest_readme)
        self.assertIn("Neither file is an implementation", widget_readme)
        self.assertIn("예제는 Figma 공식 샘플이 아니다.", recipes_readme)
        self.assertIn("실제 에디터 삽입·협업 동기화는 별도 인수 검증이 필요하다.", widget_guide)
        self.assertIn("정적 번들 생성은 Figma 문서에 접근하지 않는다.", recipes_readme)

    def test_historical_api_audit_pins_all_stored_evidence_without_claiming_currentness(self):
        source = figma_api_inventory.verify_source()
        audit_path = ROOT / "library/figma-api/audit/members.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        candidate = audit["comparison"]["candidate"]
        self.assertEqual((candidate["api_source_ref"], candidate["api_source_version"], candidate["api_source_files"]),
                         (source["ref"], source["version"], source["files"]))
        self.assertRegex(candidate["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(candidate["tree"], r"^[0-9a-f]{40}$")
        evidence_docs = audit["curated_evidence_sources"]
        self.assertEqual({row["path"] for row in evidence_docs}, {
            "library/figma-api/audit/evidence/curated.json",
            "library/figma-api/audit/evidence/design-recipes.json",
            "library/figma-api/audit/evidence/editor-gaps.json",
            "library/figma-api/audit/evidence/editor-recipes.json",
            "library/figma-api/audit/evidence/native-read.json",
        })
        for row in evidence_docs:
            evidence_path = ROOT / row["path"]
            self.assertEqual(hashlib.sha256(evidence_path.read_bytes()).hexdigest(), row["sha256"])
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["candidate"], {
                "ref": candidate["ref"], "commit": candidate["commit"], "tree": candidate["tree"]})
            self.assertTrue(evidence["members"] or evidence.get("scope_findings"))
        report = (ROOT / "library/figma-api/audit/report.md").read_text(encoding="utf-8")
        evidence_readme = (ROOT / "library/figma-api/audit/evidence/README.md").read_text(encoding="utf-8")
        self.assertIn("Candidate runtime", report)
        self.assertIn("The catalog is a declaration inventory, not an implementation inventory.", report)
        self.assertIn("Those references do not prove support.", report)
        self.assertIn("They are not a sample from which to estimate support across the full SDK.", evidence_readme)
        self.assertIn("The tests alone are not treated as a runtime observation.", evidence_readme)

    def test_recipe_outputs_rebuild_byte_identically_in_a_disposable_tree(self):
        compiler = pinned_compiler(("FIGMA_SDK_TEST_TYPESCRIPT", "FIGMA_API_TYPESCRIPT"), "tsc.js")
        with tempfile.TemporaryDirectory(prefix="figma-flow-recipe-build-") as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "tools", root / "tools", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            shutil.copytree(ROOT / "library", root / "library",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "node_modules"))
            (root / "figma-bridge").mkdir()
            shutil.copyfile(ROOT / "figma-bridge/code.js", root / "figma-bridge/code.js")
            shutil.copytree(ROOT / "figma-bridge/locales", root / "figma-bridge/locales")
            shutil.copytree(ROOT / "panel-ui/src", root / "panel-ui/src")
            shutil.copytree(ROOT / "skills/figma-flow/scripts", root / "skills/figma-flow/scripts")
            shutil.copytree(ROOT / "specs", root / "specs",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            (root / "tests/fixtures").mkdir(parents=True)
            shutil.copyfile(ROOT / "tests/fixtures/declared-component-properties.json",
                            root / "tests/fixtures/declared-component-properties.json")
            build = root / "library/figma-recipes/build.py"
            result = subprocess.run([sys.executable, str(build), "--typescript", str(compiler)],
                                    cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected_paths = [
                "bundle.json", "component-properties.helpers.js",
                "bundled/design-component-properties.js", "bundled/design-grid.js",
                "bundled/design-motion.js", "bundled/design-shapes.js",
            ]
            for relative in expected_paths:
                with self.subTest(path=relative):
                    self.assertEqual((root / "library/figma-recipes" / relative).read_bytes(),
                                     (ROOT / "library/figma-recipes" / relative).read_bytes())

    def test_maintained_campaign_catalogs_keep_source_links_and_unverified_plan_status(self):
        campaigns = campaign_library.load_library(campaign_library.DEFAULT_DATA)
        self.assertTrue(campaigns["sources"])
        self.assertTrue(campaigns["patterns"])
        self.assertRegex(campaigns["captured_on"], r"^\d{4}-\d\d-\d\d$")
        source_ids = {source["id"] for source in campaigns["sources"]}
        self.assertTrue(all(set(pattern["source_ids"]) <= source_ids for pattern in campaigns["patterns"]))
        for source in campaigns["sources"]:
            self.assertEqual("https", source["url"].split(":", 1)[0])
            self.assertTrue(source["evidence"].strip())
            self.assertTrue(source["observed"].strip())
        plan = campaign_library.plan(campaigns, campaigns["categories"][0]["id"])
        self.assertEqual((plan["status"], plan["verification"]), ("untested", "manual"))
        self.assertTrue(all(check["status"] == "untested" for pattern in plan["patterns"] for check in pattern["checks"]))

        registry = route_design.load_registry()
        self.assertEqual({"direction", "logo", "icons", "images", "typography", "motion", "figma", "verification"},
                         {lane["id"] for lane in registry["lanes"]})
        forms = campaign_forms.load()
        self.assertEqual({"commemorative-event", "launch-reveal", "participation-promotion"},
                         {form["id"] for form in forms["forms"]})
        all_forms = campaign_forms.select("1,2,3 모두", data=forms)
        self.assertEqual({form["id"] for form in all_forms}, {form["id"] for form in forms["forms"]})
        self.assertTrue(all(row["status"] == "planned" and "unverified" in row["evidence"] for row in all_forms))

        self.assertEqual(workflow.load_graph(), workflow.public_graph()["graph"])
        self.assertEqual([], sync_workflow.check())


if __name__ == "__main__":
    unittest.main()
