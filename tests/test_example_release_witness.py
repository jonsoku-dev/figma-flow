"""Concrete offline witnesses for the packaged examples surface."""
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExampleReleaseWitnessTests(unittest.TestCase):
    def test_graph_ssot_tutorial_describes_a_single_data_owner_and_separate_native_acceptance(self):
        readme = (ROOT / "examples/graph-ssot/README.md").read_text(encoding="utf-8")
        self.assertIn("The graph owns token values once.", readme)
        self.assertIn("Figma variables and generated web styles are projections.", readme)
        self.assertIn("An `ok` receipt is not design approval or independent origin authentication.", readme)
        self.assertIn("Native mutation alone does not update the canonical graph or web.", readme)
        self.assertIn("This route is an explicit export/read/import workflow.", readme)
        self.assertTrue((ROOT / "examples/owned-component-families/graph.json").is_file())

    def test_native_direction_example_regenerates_same_local_files_and_keeps_demo_limits(self):
        source = ROOT / "examples/native-direction-review"
        with tempfile.TemporaryDirectory(prefix="figma-flow-direction-fixture-") as temporary:
            copied = Path(temporary) / "examples/native-direction-review"
            copied.parent.mkdir(parents=True)
            shutil.copytree(source, copied)
            result = subprocess.run([sys.executable, str(copied / "demo.py"), "--regenerate-fixture"],
                                    cwd=Path(temporary), capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            unit = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(copied), "-p", "test_demo.py"],
                                  cwd=Path(temporary), capture_output=True, text=True, timeout=60)
            self.assertEqual(unit.returncode, 0, unit.stdout + unit.stderr)
            source_files = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            output_files = {p.relative_to(copied).as_posix(): p.read_bytes() for p in copied.rglob("*") if p.is_file()}
            self.assertEqual(source_files, output_files)
        layout = json.loads((source / "native-layout.json").read_text(encoding="utf-8"))
        spec = json.loads((source / "candidate-spec.json").read_text(encoding="utf-8"))
        self.assertEqual(layout["scope"], "exploratory-only")
        self.assertFalse(layout["production_admitted"])
        self.assertEqual(spec["content"]["path"], "content.json")
        self.assertEqual(layout["content"]["sha256"],
                         hashlib.sha256((source / "content.json").read_bytes()).hexdigest())
        readme = (source / "README.md").read_text(encoding="utf-8")
        self.assertIn("Pillow previews", readme)
        self.assertIn("not Figma rendering", readme)

    def test_review_design_preview_files_are_exact_generated_projections(self):
        design = ROOT / "examples/review-design/design.json"
        with tempfile.TemporaryDirectory(prefix="figma-flow-review-design-") as temporary:
            out = Path(temporary) / "output"
            command = [sys.executable, str(ROOT / "tools/design_system.py"), "--input", str(design), "--out", str(out)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            preview = ROOT / "examples/review-design/preview"
            generated = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
            packaged = {p.relative_to(preview).as_posix(): p.read_bytes() for p in preview.rglob("*") if p.is_file()}
            self.assertEqual(packaged, generated)
        product_graph = json.loads((ROOT / "examples/review-design/product-graph.json").read_text(encoding="utf-8"))
        self.assertIn("nodes", product_graph)
        self.assertIn("edges", product_graph)
        validation = subprocess.run([sys.executable, "-B", str(ROOT / "skills/figma-flow/scripts/graph.py"),
                                     "validate", str(ROOT / "examples/review-design/product-graph.json")],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(validation.returncode, 0, validation.stderr)
        cards = (ROOT / "examples/review-design/cards.md").read_text(encoding="utf-8")
        self.assertIn("오늘의 복습 카드", cards)
        self.assertIn("질문과 ‘정답 보기’ 버튼", cards)
        self.assertIn("이번에는 화면 기획 초안까지만 만든다", cards)
        self.assertEqual(product_graph["nodes"][0]["source"], "cards.md#L2")
        self.assertEqual([screen["id"] for screen in json.loads(design.read_text(encoding="utf-8"))["screens"]],
                         ["SCR-CARDS-LIST", "SCR-CARDS-REVIEW"])
        docs = (ROOT / "examples/review-design/README.md").read_text(encoding="utf-8")
        self.assertIn("화면 배치와 예시 문구는 디자인 제안입니다.", docs)
        self.assertIn("--draft-only", docs)

    def test_component_family_css_has_no_copied_token_fallbacks(self):
        root = ROOT / "examples/owned-component-families"
        design = json.loads((root / "design.json").read_text(encoding="utf-8"))
        styles = (root / "styles.css").read_text(encoding="utf-8")
        renderer = (root / "renderer.js").read_text(encoding="utf-8")
        tokens = {f"--{group}-{name}" for group, values in design["tokens"].items() for name in values}
        references = set(re.findall(r"var\((--[a-z-]+)\)", styles))
        self.assertTrue(references)
        self.assertEqual(references - tokens, set())
        self.assertNotRegex(styles, r"var\(--[a-z-]+\s*,")
        self.assertNotRegex(styles, r"#[0-9a-fA-F]{3,8}\b")
        self.assertIn("applyDesignTokensAndVariants(design)", renderer)
        self.assertIn("rootStyle.setProperty", renderer)

    def test_regression_program_runtime_and_catalog_cases_match_the_shipped_scenarios(self):
        fixture = ROOT / "examples/regression-program"
        node = subprocess.run(["node", "--test", "--test-reporter=tap", str(ROOT / "tests/test_regression_program_apps.cjs")],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(node.returncode, 0, node.stdout + node.stderr)
        self.assertRegex(node.stdout, r"# pass 14\b")
        self.assertRegex(node.stdout, r"# fail 0\b")
        catalog = json.loads((fixture / "catalog.json").read_text(encoding="utf-8"))
        generator = load_module("release_regression_catalog", fixture / "catalog.py")
        self.assertEqual(catalog, generator.catalog_document())
        self.assertEqual({row["name"] for row in json.loads((fixture / "server/vectors.json").read_text(encoding="utf-8"))},
                         {"atlas-save-fail", "atlas-save-ok", "morrow-stock", "morrow-price", "morrow-duplicate",
                          "morrow-return-fail", "paper-autosave-fail", "paper-publish-virtual", "paper-publish-forbidden"})

    def test_review_cards_test_map_covers_graph_tests_and_current_tests_pass(self):
        root = ROOT / "examples/review-cards"
        graph = json.loads((root / "graph.json").read_text(encoding="utf-8"))
        mapping = json.loads((root / "test-mapping.json").read_text(encoding="utf-8"))
        bindings = json.loads((root / "bindings.json").read_text(encoding="utf-8"))
        graph_test_ids = {node["id"] for node in graph["nodes"] if node.get("type") == "test"}
        self.assertEqual(graph_test_ids, set(mapping["tests"]))
        bindings = json.loads((root / "bindings.json").read_text(encoding="utf-8"))
        for test_id, paths in mapping["tests"].items():
            with self.subTest(test_id=test_id):
                self.assertTrue(paths)
                for relative in paths:
                    self.assertTrue((root / relative).is_file(), relative)
                evidence = bindings["evidence"].get(test_id)
                self.assertTrue(evidence)
                logs = [path for path in evidence if path.endswith(".tap")]
                self.assertEqual(len(logs), 1)
                result = subprocess.run(["node", "--test", "--test-reporter=tap", *[str(root / path) for path in paths]],
                                        cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                current_cases = re.findall(r"^ok \d+ - (.+)$", result.stdout, re.M)
                stored_cases = [case.strip('"') for case in re.findall(
                    r"^ok \d+ - (.+)$", (root / logs[0]).read_text(encoding="utf-8"), re.M)]
                self.assertTrue(current_cases)
                self.assertEqual(stored_cases, current_cases)
        test_paths = sorted(str(path) for path in (root / "tests").glob("*.test.cjs"))
        result = subprocess.run(["node", "--test", "--test-reporter=tap", *test_paths],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"# pass 21\b")
        self.assertRegex(result.stdout, r"# fail 0\b")

    def test_idea_notes_snapshot_remains_historical_and_current_app_tests_cover_visual_graph(self):
        root = ROOT / "examples/idea-notes"
        graph = json.loads((root / "graph.json").read_text(encoding="utf-8"))
        bindings = json.loads((root / "bindings.json").read_text(encoding="utf-8"))
        code = next(node for node in graph["nodes"] if node["id"] == "CODE-001")
        self.assertEqual(bindings["authorities"]["intent"], "brief.md")
        self.assertEqual(bindings["authorities"]["visual"], "app/visual-tokens.json")
        self.assertIn("app/visual-tokens.json", bindings["evidence"]["CODE-001"])
        self.assertIn("evidence/browser-current.json", bindings["evidence"]["CODE-001"])
        self.assertIn("visual-tokens.json", code["detail"])
        self.assertTrue((root / "brief.md").read_text(encoding="utf-8").strip())
        self.assertIn("현재 코드 인수로 보지 않는다", (root / "screen-spec.md").read_text(encoding="utf-8"))
        self.assertIn("Figma 인수는 주장하지 않는다", (root / "README.md").read_text(encoding="utf-8"))
        snapshot = json.loads((root / "evidence/browser.json").read_text(encoding="utf-8"))
        self.assertEqual(set(snapshot["app_sha256"]), {"app/app.js", "app/index.html", "app/style.css"})
        self.assertTrue(snapshot["date"].startswith("2026-11-07"))
        self.assertNotEqual(snapshot["app_sha256"]["app/app.js"],
                            hashlib.sha256((root / "app/app.js").read_bytes()).hexdigest())
        self.assertIn("not a Figma or cross-browser audit", snapshot["scope"])
        self.assertTrue(all(row["passed"] for row in snapshot["checks"]))
        self.assertTrue(snapshot["limitations"])
        current = json.loads((root / "evidence/browser-current.json").read_text(encoding="utf-8"))
        self.assertEqual(set(current["app_sha256"]), {"app/app.js", "app/index.html", "app/style.css", "app/visual-tokens.json"})
        for relative, expected in current["app_sha256"].items():
            self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), expected)
        self.assertEqual({check["id"] for check in current["checks"]},
                         {"visual-token-mutation", "desktop", "mobile", "keyboard", "persist",
                          "write-retry", "two-tabs", "search", "console", "favicon"})
        self.assertTrue(all(check["passed"] for check in current["checks"]))
        for name, expected in current["screenshots"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)
        self.assertIn("No Figma import", current["scope"])
        result = subprocess.run(["node", "--test", "--test-reporter=tap", str(root / "tests/app.test.cjs")],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# fail 0", result.stdout)
        run_ids = {node["id"] for node in graph["nodes"] if node["type"] == "test" and node.get("source") == "evidence/node-tests.tap"}
        passed_ids = set(re.findall(r"^ok \d+ - (TEST-\d+)\b", result.stdout, re.M))
        self.assertEqual(run_ids, passed_ids)
        self.assertEqual(int(re.search(r"^# pass (\d+)$", result.stdout, re.M).group(1)), len(run_ids))

    def test_web_css_effect_fixture_exercises_the_documented_mask_and_filter_scope(self):
        html = (ROOT / "examples/web-design-css-effects/index.html").read_text(encoding="utf-8")
        self.assertIn("mask-composite: intersect", html)
        self.assertIn("filter: blur(2px) drop-shadow(0 5px 7px", html)
        self.assertIn("brightness(120%) saturate(150%)", html)
        docs = (ROOT / "docs/design-runtime-verification.md").read_text(encoding="utf-8")
        section = docs.split("## 복합 마스크와 필터", 1)[1].split("## Canvas", 1)[0]
        self.assertIn("examples/web-design-css-effects/index.html", section)
        self.assertIn("같은 영역에서 6개 표본을 비교했다.", section)
        self.assertIn("지원되지 않는 복합 필터는 캡처 제한에 남긴다.", section)


if __name__ == "__main__":
    unittest.main()
