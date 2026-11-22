"""Keep published guide screenshots tied to their selected frame and caption."""
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/guide.md"
TRIALS = ROOT / "docs/design-system-trials.md"


def image_links(path):
    text = path.read_text(encoding="utf-8")
    return {target: alt for alt, target in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)}


def image_link_rows(path):
    text = path.read_text(encoding="utf-8")
    return re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)


def visible_crop(image, box, minimum_stddev=18):
    crop = image.crop(box).convert("L")
    return ImageStat.Stat(crop).stddev[0] > minimum_stddev


class GuideVisualEvidenceTests(unittest.TestCase):
    def test_setup_images_show_the_selected_template_and_manifest_row(self):
        links = image_links(GUIDE)
        expected = {
            "images/development-menu.png": ("개발 메뉴", (324, 85)),
            "images/new-plugin-dialog.png": ("Figma Design", (695, 429)),
            "images/custom-ui-template.png": ("사용자 정의 UI", (695, 429)),
            "images/manifest-picker.png": ("manifest", (716, 448)),
        }
        for target, (phrase, size) in expected.items():
            with self.subTest(target=target):
                self.assertIn(target, links)
                self.assertIn(phrase, links[target])
                with Image.open(ROOT / "docs" / target) as image:
                    self.assertEqual(image.size, size)

        # The selected Custom UI template has a green selection mark in its third card.
        with Image.open(ROOT / "docs/images/custom-ui-template.png") as image:
            selected = image.crop((470, 105, 515, 140)).convert("RGB")
            green = sum(1 for r, g, b in selected.get_flattened_data()
                        if g > 140 and g > r * 1.35 and g > b * 1.15)
            self.assertGreater(green, 40)

        # The manifest picker frames the selected file row across the dialog.
        with Image.open(ROOT / "docs/images/manifest-picker.png") as image:
            row = image.crop((8, 94, 706, 119)).convert("RGB")
            blue = sum(1 for r, g, b in row.get_flattened_data()
                       if b > 160 and b > g * 1.1 and b > r * 1.2)
            self.assertGreater(blue, 5000)

        # The new-plugin dialog presents Figma Design as a choice; it does not show it selected.
        with Image.open(ROOT / "docs/images/new-plugin-dialog.png") as image:
            green = sum(1 for r, g, b in image.convert("RGB").get_flattened_data()
                        if g > 140 and g > r * 1.35 and g > b * 1.15)
            self.assertEqual(green, 0)

    def test_trial_images_keep_each_desktop_mobile_and_before_after_frame(self):
        links = image_links(TRIALS)
        expected = {
            "trials/mui-comparison.jpg": ("MUI A", (1496, 1008)),
            "trials/shadcn-comparison.jpg": ("shadcn/ui A", (1496, 1008)),
            "trials/mui-native-repair.jpg": ("수정 전", (1656, 590)),
            "trials/shadcn-native-repair.jpg": ("수정 후", (1656, 590)),
        }
        for target, (phrase, size) in expected.items():
            with self.subTest(target=target):
                self.assertIn(target, links)
                self.assertIn(phrase, links[target])
                with Image.open(ROOT / "docs" / target) as image:
                    self.assertEqual(image.size, size)
                    if size == (1496, 1008):
                        boxes = ((15, 48, 736, 528), (760, 48, 1476, 528),
                                 (280, 585, 470, 986), (1020, 585, 1210, 986))
                    else:
                        boxes = ((15, 45, 818, 575), (838, 45, 1640, 575))
                    self.assertTrue(all(visible_crop(image, box) for box in boxes),
                                    "Every labeled desktop/mobile or before/after frame must contain visible content")

    def test_guide_references_every_retained_documentation_image(self):
        referenced = set(image_links(GUIDE)) | set(image_links(TRIALS))
        assets = {
            p.relative_to(ROOT / "docs").as_posix()
            for folder in (ROOT / "docs/images", ROOT / "docs/trials")
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        }
        self.assertEqual(assets, referenced)

    def test_previous_panel_images_are_labeled_as_previous_versions(self):
        guide_text = GUIDE.read_text(encoding="utf-8")
        links = image_link_rows(GUIDE)
        for name in ("panel-import.png", "panel-graph-sync.png", "panel-graph-diff.png"):
            with self.subTest(name=name):
                self.assertTrue(any(path.endswith(name) and "이전 버전" in alt for alt, path in links), name)
        self.assertIn("현재 Figma viewer나 본제작의 실제 실행 결과를 보여 주지 않습니다.", guide_text)
        self.assertIn("현재 Figma viewer는 상태만 표시합니다.", guide_text)
        historical = ("이전 버전", "이전 interactive panel", "Historical screenshot", "과거", "過去の", "旧パネル")
        for name in ("panel-workspace.png", "panel-graph-diff.png"):
            with self.subTest(name=name):
                alts = [alt for alt, path in links if path.endswith(name)]
                self.assertGreaterEqual(len(alts), 2, name)
                self.assertTrue(all(any(marker in alt for marker in historical) for alt in alts), (name, alts))

    def test_current_panel_images_frame_candidate_cards_and_history_scroll(self):
        links = image_links(GUIDE)
        self.assertIn("images/panel-review.png", links)
        self.assertIn("두 후보", links["images/panel-review.png"])
        self.assertIn("images/panel-history.png", links)
        self.assertIn("스크롤", links["images/panel-history.png"])

        with Image.open(ROOT / "docs/images/panel-review.png") as image:
            self.assertEqual(image.size, (560, 700))
            self.assertTrue(visible_crop(image, (24, 183, 276, 324)))
            self.assertTrue(visible_crop(image, (286, 183, 536, 324)))
            self.assertTrue(visible_crop(image, (24, 448, 536, 510)))

        with Image.open(ROOT / "docs/images/panel-history.png") as image:
            self.assertEqual(image.size, (569, 721))
            self.assertTrue(visible_crop(image, (24, 278, 530, 715)))
            # The scrollbar is part of the captured frame, so the caption's scroll instruction is grounded.
            rail = image.crop((548, 48, 562, 712)).convert("RGB")
            rail_pixels = list(rail.get_flattened_data())
            self.assertGreater(sum(1 for r, g, b in rail_pixels if r < 235 and g < 235 and b < 235), 100)

    def test_recipe_guide_names_every_manifest_entry_and_visual_graph_projection(self):
        guide = (ROOT / "docs/figma-recipes.md").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "library/figma-recipes/manifest.json").read_text(encoding="utf-8"))
        bundle = json.loads((ROOT / "library/figma-recipes/bundle.json").read_text(encoding="utf-8"))
        graph = json.loads((ROOT / "library/figma-recipes/design-examples.graph.json").read_text(encoding="utf-8"))
        rows = re.findall(r"^\| `([^`]+)` \|", guide, flags=re.MULTILINE)
        recipe_ids = {recipe["id"] for recipe in manifest["recipes"]}
        self.assertEqual(set(rows), recipe_ids)
        self.assertTrue(all(recipe.get("designGraph") == bundle["designGraph"]["source"]
                            for recipe in manifest["recipes"]))
        graph_bundle = bundle["designGraph"]
        self.assertTrue({"sourceSha256", "projectionSha256", "componentPayloadSource", "componentPayloadSha256"}
                        <= set(graph_bundle))
        self.assertTrue(all({"sourceSha256", "jsSha256", "visualProjectionSha256"} <= set(recipe)
                            for recipe in bundle["recipes"]))
        self.assertTrue(all({"graphTemplateSha256", "graphProjectionSha256", "visualProjectionSha256",
                             "selectionSha256", "compiledSha256"} <= set(recipe)
                            for recipe in bundle["sdkGraphRecipes"]))
        self.assertEqual({node.get("recipe") for node in graph["nodes"] if node["type"] == "recipe"}, recipe_ids)
        edges = {(edge["from"], edge["to"], edge["type"]) for edge in graph["edges"]}
        for recipe_id in recipe_ids:
            self.assertIn(("recipe:" + recipe_id, "visual:" + recipe_id, "owns-visual-values"), edges)
        self.assertIn(("recipe:design-component-properties", "payload:declared-component-properties",
                       "owns-design-payload"), edges)
        self.assertIn("design-examples.graph.json", guide)
        self.assertIn("owns-visual-values", guide)
        self.assertIn("owns-design-payload", guide)
        self.assertIn("src/recipe-visuals.ts", guide)
        self.assertIn("sdk-project.json", guide)
        self.assertIn("전체 projection SHA-256", guide)

    def test_distributed_guide_markdown_local_targets_resolve(self):
        markdown = [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
        markdown.extend(p for p in (ROOT / "docs").rglob("*.md")
                        if "llm-wiki" not in p.relative_to(ROOT).parts)
        broken = []
        for source in markdown:
            text = source.read_text(encoding="utf-8", errors="replace")
            for raw in re.findall(r"!??\[[^\]]*\]\(([^)]+)\)", text):
                target = raw.split()[0].strip("<>")
                if not target or target.startswith(("#", "http:", "https:", "mailto:", "data:")):
                    continue
                local = target.split("#", 1)[0]
                if local and not (source.parent / local).resolve().exists():
                    broken.append((source.relative_to(ROOT).as_posix(), target))
        self.assertEqual(broken, [])

    def test_optional_evidence_guide_matches_absent_and_available_cli_paths(self):
        guide = (ROOT / "docs/optional-evidence-tests.md").read_text(encoding="utf-8")
        self.assertIn("With no evidence input the command exits with an error and writes no receipt.", guide)
        self.assertIn("A partial native evidence set is rejected.", guide)
        self.assertIn("receipt is `incomplete`", guide)
        command = ROOT / "tools/replay_optional_tests.py"

        with tempfile.TemporaryDirectory(prefix="guide-optional-evidence-") as temporary:
            root = Path(temporary)
            missing_receipt = root / "missing.json"
            missing = subprocess.run(
                [sys.executable, str(command), "--receipt", str(missing_receipt)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(missing.returncode, 2)
            self.assertIn("Supply at least one original fixture or native evidence set", missing.stderr)
            self.assertFalse(missing_receipt.exists())

            sys.path.insert(0, str(ROOT / "tests"))
            try:
                from test_design_quality import layout, rect, text
                shadow = root / "synthetic-shadow-fixture"
                shadow.mkdir()
                bars = [rect("upper-light", 60, 600, 270, 18, fill="night"),
                        rect("main-light", 60, 650, 270, 18, fill="night"),
                        rect("lower-light", 60, 700, 270, 18, fill="night"),
                        text("heading", 24, 24, 200, 30, value="Disposable synthetic layout")]
                (shadow / "native-layout.json").write_text(
                    json.dumps(layout(bars), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            finally:
                sys.path.remove(str(ROOT / "tests"))

            partial_receipt = root / "partial.json"
            partial = subprocess.run(
                [sys.executable, str(command), "--shadow-root", str(shadow), "--receipt", str(partial_receipt)],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(partial.returncode, 1)
            receipt = json.loads(partial.stdout)
            self.assertEqual(receipt["status"], "incomplete")
            self.assertEqual(receipt["tests"][0]["status"], "passed")
            self.assertEqual(receipt["tests"][1]["status"], "not_run")
            self.assertEqual(receipt["tests"][2]["status"], "not_run")
            self.assertTrue(partial_receipt.is_file())


if __name__ == "__main__":
    unittest.main()
