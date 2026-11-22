"""Keep public guide entrypoints and historical-document boundaries source-bound."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuideSourceContractTests(unittest.TestCase):
    def test_current_docs_are_version_neutral_and_follow_manifest_pair(self):
        self._assert_version_neutral_install_contract(ROOT)

        # The same instructions remain correct for the real major candidate.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp)
            for relative in ("plugin.json", ".codex-plugin/plugin.json", "README.md", "docs/guide.md"):
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            for relative in ("plugin.json", ".codex-plugin/plugin.json"):
                path = fixture / relative
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["version"] = "1.0.0"
                path.write_text(json.dumps(manifest), encoding="utf-8")
            self._assert_version_neutral_install_contract(fixture)

    def _assert_version_neutral_install_contract(self, root):
        primary = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex["version"], primary["version"])
        self.assertIn("docs/guide.md", (root / "README.md").read_text(encoding="utf-8"))
        guide = (root / "docs/guide.md").read_text(encoding="utf-8")
        self.assertIn("RELEASE_TAG=vX.Y.Z", guide)
        self.assertIn("both plugin manifests", guide)
        self.assertNotRegex(guide, r"git clone --branch v\d+\.\d+\.\d+")
        self.assertNotIn("0.36.0을 설치", guide)
        self.assertIn("Historical 0.36.0 verification snapshot", guide)
        self.assertIn("過去の0.36.0検証スナップショット", guide)

    def test_readme_current_product_summary_and_historical_release_label_match_authorities(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        constitution = (ROOT / "CONSTITUTION.md").read_text(encoding="utf-8")
        api = json.loads((ROOT / "library/figma-api/index.json").read_text(encoding="utf-8"))
        self.assertIn("Figma에는 **Figma Flow 하나**를 등록합니다", readme)
        self.assertIn("대화·승인·프로필 선언·결과 해석은 Codex에서 합니다", readme)
        self.assertIn("수동 뷰어", readme)
        self.assertIn("현재 검증된 릴리스 태그", readme)
        self.assertNotRegex(readme, r"git clone --branch v\d+\.\d+\.\d+")
        self.assertIn("API 1,382개 멤버 대조", readme)
        self.assertEqual(len(api["members"]), 1382)
        self.assertIn("Historical 0.36.0 verification snapshot", readme)
        self.assertIn("과거 0.27 구현 계획", readme)
        self.assertIn("Figma Flow의 제품 범위는 Figma Design이다", constitution)

    def test_api_priority_snapshot_numbers_match_the_pinned_inventory_report(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import api_priority
        import review_api_coverage

        guide = (ROOT / "docs/api-priority.md").read_text(encoding="utf-8")
        baseline_path = review_api_coverage.PUBLIC_OBSERVATION_OVERLAYS[0]
        baseline = api_priority.build(overlays=[json.loads(baseline_path.read_text(encoding="utf-8"))])
        current = json.loads(subprocess.check_output(
            [sys.executable, "-B", str(ROOT / "tools/review_api_coverage.py")],
            cwd=ROOT, text=True))
        total = len(json.loads(api_priority.AUDIT.read_text(encoding="utf-8"))["members"])
        observed_030 = total - baseline["source"]["unobserved_members"]
        observed_031 = current["baseline_observed"]
        added_031 = observed_031 - observed_030

        self.assertEqual(baseline["source"]["unobserved_members"], 1232)
        self.assertIn(f"0.30 baseline had {observed_030} observed keys and 1,232 unobserved rows", guide)
        self.assertIn(f"Four 0.31 responsive-web batches added {added_031} distinct keys", guide)
        self.assertIn(f"bringing the count to {observed_031:,} and the remaining queue to {current['before_032_unobserved']:,}", guide)
        self.assertIn(f"The 0.32 Design overlays add {current['newly_observed']:,} distinct keys", guide)
        self.assertIn(f"The current queue has {current['remaining_without_live_member_evidence']:,} unobserved rows", guide)

    def test_design_type_review_claims_match_its_pinned_graph_and_historical_receipt_node(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import design_type_review_graph

        template = json.loads((ROOT / "library/figma-recipes/design-type-review.graph.json").read_text(encoding="utf-8"))
        observation = json.loads((ROOT / "specs/editable-web/api-observations.json").read_text(encoding="utf-8"))
        doc = (ROOT / "docs/design-type-review.md").read_text(encoding="utf-8")
        generated = design_type_review_graph.build_graph("FILE_KEY", "1:1")
        self.assertEqual((len(generated["nodes"]), len(generated["edges"])), (24, 23))
        self.assertIn("default graph selected 24 nodes and 23 edges", doc)
        self.assertEqual(len(template["priority_members"]), 19)

        nodes = {node["id"]: node for node in observation["nodes"]}
        receipt = nodes["OBS-030-type-creation"]
        self.assertEqual(receipt["source"], "../../docs/design-type-review.md")
        self.assertEqual(receipt["getter_counts"]["success"], 19)
        self.assertRegex(receipt["receipt_sha256"], r"^[0-9a-f]{64}$")
        member_edges = [edge for edge in observation["edges"]
                        if edge["from"] == receipt["id"] and edge["type"] == "observed member"]
        self.assertEqual(len(member_edges), 19)
        self.assertTrue(all(edge["to"].startswith("member:") and edge["to"] in nodes
                            for edge in member_edges))
        self.assertIn("The metadata contains the 19 exact API member IDs", doc)

    def test_component_property_authoring_example_matches_the_canonical_recipe_payload(self):
        doc = (ROOT / "docs/component-property-authoring.md").read_text(encoding="utf-8")
        graph = json.loads((ROOT / "library/figma-recipes/design-examples.graph.json").read_text(encoding="utf-8"))
        payload = next(node["values"] for node in graph["nodes"]
                       if node["id"] == "payload:declared-component-properties")
        button = payload["components"]["button"]
        self.assertEqual(button["properties"]["ShowLabel"]["type"], "BOOLEAN")
        self.assertEqual(button["properties"]["Symbol"]["type"], "INSTANCE_SWAP")
        self.assertEqual(button["properties"]["Symbol"]["preferred_values"], [
            {"component": "symbol", "variant": "circle"},
            {"component": "symbol", "variant": "square"},
        ])
        for token in ("BOOLEAN", "INSTANCE_SWAP", "property_values", "preferred_values", "512 component nodes"):
            self.assertIn(token, doc)
        self.assertTrue((ROOT / "tests/fixtures/declared-component-properties.json").is_file())

    def test_historical_design_reports_match_their_sanitized_observation_graph_counts(self):
        service = json.loads((ROOT / "specs/design-inspection/service-observations.json").read_text(encoding="utf-8"))
        values = json.loads((ROOT / "specs/design-inspection/value-observations.json").read_text(encoding="utf-8"))
        editable = json.loads((ROOT / "specs/editable-web/api-observations.json").read_text(encoding="utf-8"))
        responsive = json.loads((ROOT / "specs/responsive-web/api-observations.json").read_text(encoding="utf-8"))
        editable_graph = json.loads((ROOT / "specs/editable-web/graph.json").read_text(encoding="utf-8"))
        responsive_graph = json.loads((ROOT / "specs/responsive-web/graph.json").read_text(encoding="utf-8"))
        runtime_doc = (ROOT / "docs/design-runtime-verification.md").read_text(encoding="utf-8")
        editable_doc = (ROOT / "docs/editable-web-verification.md").read_text(encoding="utf-8")
        responsive_doc = (ROOT / "docs/responsive-web-verification.md").read_text(encoding="utf-8")

        service_row = next(node for node in service["nodes"] if node["id"] == "OBS-SERVICES-032")
        service_counts = service_row["getter_counts"]
        self.assertEqual(service_counts, {"success": 241, "unavailable": 15, "runtime-error": 13})
        self.assertIn("269개 고유 항목 중 241개가 성공했다. 15개는 값 미제공, 13개는 런타임 오류였다.", runtime_doc)
        value_row = next(node for node in values["nodes"] if node["id"] == "OBS-native-value-61015a9cc0ad5b7a")
        self.assertEqual(value_row["getter_counts"]["success"], 62)
        self.assertIn("네이티브 필드 62개를 확인", runtime_doc)

        editable_obs = [node for node in editable["nodes"] if node["id"].startswith("OBS-030-")]
        bulk_calls = sum(node.get("getter_counts", {}).get("success", 0) for node in editable_obs
                         if node["id"] != "OBS-030-type-creation")
        type_calls = next(node["getter_counts"]["success"] for node in editable_obs
                          if node["id"] == "OBS-030-type-creation")
        self.assertEqual((bulk_calls, type_calls), (253, 19))
        self.assertEqual(sum(node["type"] == "screen" for node in editable_graph["nodes"]), 4)
        self.assertIn("253 actual typed-probe calls", editable_doc)
        self.assertIn("0.30.0 candidate", editable_doc)

        responsive_obs = [node for node in responsive["nodes"] if node["id"].startswith("OBS-responsive-api-batch-")]
        totals = {key: sum(node["getter_counts"].get(key, 0) for node in responsive_obs)
                  for key in ("success", "unavailable", "unsupported", "blocked")}
        self.assertEqual(totals, {"success": 473, "unavailable": 10, "unsupported": 5, "blocked": 0})
        self.assertEqual(sum(node["type"] == "figma" for node in responsive_graph["nodes"]), 54)
        self.assertIn("54개 모두 같은 프레임 ID", responsive_doc)
        self.assertIn("473회 성공, 10회 값 미제공, 5회 수신 객체에서 미지원", responsive_doc)
        self.assertIn("이 파일에서 미검증이다", responsive_doc)

    def test_web_observation_and_capture_commands_match_public_cli_help(self):
        native = ROOT / "tools/native_edit.py"
        for kind, doc_name in (("web-carousel", "web-carousel-input.md"),
                               ("web-tabs", "web-tabs-input.md"),
                               ("web-disclosure", "web-disclosure-input.md")):
            with self.subTest(kind=kind):
                doc = (ROOT / "docs" / doc_name).read_text(encoding="utf-8")
                self.assertIn(f"tools/native_edit.py {kind}", doc)
                result = subprocess.run([sys.executable, "-B", str(native), kind, "--help"],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for option in ("--graph", "--observations", "--out"):
                    self.assertIn(option, result.stdout)

        capture_doc = (ROOT / "docs/web-design-capture.md").read_text(encoding="utf-8")
        source_help = subprocess.run([sys.executable, "-B", str(ROOT / "tools/web_design_source.py"), "--help"],
                                     cwd=ROOT, capture_output=True, text=True)
        edit_help = subprocess.run([sys.executable, "-B", str(native), "web-design", "--help"],
                                   cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(source_help.returncode, 0, source_help.stdout + source_help.stderr)
        self.assertEqual(edit_help.returncode, 0, edit_help.stdout + edit_help.stderr)
        for option in ("--capture", "--assets", "--id", "--title", "--out"):
            self.assertIn(option, source_help.stdout)
            self.assertIn(option, capture_doc)
        for option in ("--graph", "--file-key", "--page-id", "--preview-width", "--out"):
            self.assertIn(option, edit_help.stdout)
            self.assertIn(option, capture_doc)

    def test_html_asset_map_guide_matches_the_consumed_contract_and_schema_versions(self):
        doc = (ROOT / "docs/html-asset-map.md").read_text(encoding="utf-8")
        contract = json.loads((ROOT / "tools/input-effect-contract.json").read_text(encoding="utf-8"))
        for field in contract["assetMap"]["manifestFields"] + contract["assetMap"]["pageCaptureFields"] + contract["assetMap"]["entryFields"]:
            self.assertIn(f'"{field}"', doc)
        self.assertIn(contract["assetMap"]["schema"], doc)
        self.assertIn(contract["records"]["output"], doc)
        for version in contract["records"]["previousReadable"]:
            self.assertIn(version, doc)
        self.assertIn("It never performs HTTP requests", doc)

    def test_next_roadmap_docs_match_proposed_and_historical_scope_labels(self):
        folder = ROOT / "docs/next-roadmap"
        index = (folder / "README.md").read_text(encoding="utf-8")
        graph = json.loads((folder / "backlog.graph.json").read_text(encoding="utf-8"))
        self.assertEqual(graph["entry_document"], "README.md")
        self.assertEqual(graph["planning_document"], "capability-review.md")
        self.assertIn("backlog.graph.json", index)
        self.assertIn("Historical Proposals", index)
        for index in range(1, 7):
            path = next(folder.glob(f"NF-{index:02d}-*.md"))
            self.assertIn("PROPOSED", path.read_text(encoding="utf-8"), str(path))
        nf08 = (folder / "NF-08-optional-plugin-routing.md").read_text(encoding="utf-8")
        self.assertIn("PROPOSED", nf08)
        nf07 = (folder / "NF-07-web-import-editor-capabilities.md").read_text(encoding="utf-8")
        self.assertIn("0.30.0에서 웹 캡처", nf07)
        self.assertIn("후속 범위다", nf07)
        nf09 = (folder / "NF-09-interactive-web-design.md").read_text(encoding="utf-8")
        self.assertIn("0.33.0은 모바일 CSS", nf09)
        self.assertIn("설치 및 발행은 아직 대기 중이다", nf09)
        for report in ("p0-reference-acceptance.md", "p1-acceptance.md", "p2-wave1-acceptance.md"):
            self.assertTrue((folder / report).is_file())

    def test_web_fidelity_reports_match_the_sanitized_historical_visual_observations(self):
        record = json.loads((ROOT / "specs/editable-web/historical-visual-observations.json").read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in record["observations"]}
        web_0321 = (ROOT / "docs/web-fidelity-0321.md").read_text(encoding="utf-8")
        web_0322 = (ROOT / "docs/web-svg-fidelity-0322.md").read_text(encoding="utf-8")
        self.assertEqual(record["schema"], "figma-flow-historical-visual-observations-v1")
        self.assertFalse(record["rawScreenshotsIncluded"])
        self.assertFalse(record["sourceArtifactsIncluded"])
        self.assertIn("original browser and Figma screenshots are unavailable", record["sourceScreenshotsNote"])

        old = by_id["web-fidelity-0321"]
        self.assertFalse(old["sourceScreenshotsIncluded"])
        self.assertIn("historical-visual-observations.json", web_0321)
        self.assertIn("원본 스크린샷은 배포본에 포함하지 않는다", web_0321)
        labels = {
            ("portfolio-home-desktop", "hero line 1"): "Portfolio · Hero 제목 1행",
            ("codeforge-desktop", "hero line 1"): "CodeForge · Hero 제목 1행",
            ("codeforge-desktop", "hero line 2"): "CodeForge · Hero 제목 2행",
        }
        for screen in old["screens"]:
            for measure in screen["textMeasurements"]:
                label = labels[(screen["id"], measure["label"])]
                spacing = measure["nativeLetterSpacing"]["value"]
                formatted_spacing = f"−{abs(spacing):g}" if spacing < 0 else f"{spacing:g}"
                row = (f"| {label} | {measure['browserWidthCssPx']:.2f} | "
                       f"{measure['baselineNativeWidthPx']} | {measure['measuredNativeWidthPx']} | "
                       f"{formatted_spacing} px |")
                self.assertIn(row, web_0321)
            self.assertTrue(screen["applyReusedFrame"])
            self.assertTrue(screen["applyReuseGraphSha256Matches"])

        new = by_id["web-svg-fidelity-0322"]
        self.assertFalse(new["sourceScreenshotsIncluded"])
        self.assertIn("historical-visual-observations.json", web_0322)
        for logo in new["logos"]:
            row = (f"| {logo['name']} | {logo['vectors']} | {logo['browser']['chromatic']:,} | "
                   f"{logo['previous']['chromatic']:,} | {logo['candidate']['chromatic']:,} |")
            self.assertIn(row, web_0322)
        totals = new["totals"]
        self.assertIn(f"| 합계 | {totals['vectorCount']} | {totals['browserChromaticPixels']:,} | "
                      f"{totals['priorChromaticPixels']:,} | {totals['currentChromaticPixels']:,} |", web_0322)
        self.assertEqual(totals["originalSvgBytes"], 32140)
        self.assertEqual(totals["normalizedSvgBytes"], 31922)
        self.assertEqual(new["nativeReadback"]["preview"]["bytes"], 73070)
        self.assertTrue(new["nativeReadback"]["applyReusedFrame"])
        self.assertTrue(new["nativeReadback"]["applyReuseGraphSha256Matches"])
        self.assertIn("원본 browser/Figma 스크린샷은 private ignored evidence에만 남고 portable package에는 포함하지 않는다", web_0322)

    def test_historical_visual_nodes_are_summaries_not_live_render_witnesses(self):
        graph = json.loads((ROOT / "specs/editable-web/graph.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        summaries = {
            "OBS-HISTORICAL-WEB-FIDELITY-0321": "historical-visual-observations.json#/observations/0",
            "OBS-HISTORICAL-WEB-SVG-FIDELITY-0322": "historical-visual-observations.json#/observations/1",
        }
        for identity, source in summaries.items():
            self.assertEqual(nodes[identity]["type"], "reference")
            self.assertEqual(nodes[identity]["status"], "observed")
            self.assertEqual(nodes[identity]["source"], source)
            self.assertFalse(any(edge["to"] == identity and edge["type"] in {"rendered as", "observed in"}
                                 for edge in graph["edges"]))
        actual = {(edge["from"], edge["to"], edge["type"]) for edge in graph["edges"]}
        self.assertIn(("AC-WEB-TRACKING-NATIVE", "OBS-HISTORICAL-WEB-FIDELITY-0321", "summarized in"), actual)
        self.assertIn(("AC-WEB-SVG-FILTER", "OBS-HISTORICAL-WEB-SVG-FIDELITY-0322", "summarized in"), actual)
        self.assertTrue(any(edge["from"] == "AC-WEB-TRACKING-NATIVE" and edge["type"] == "checked by"
                            for edge in graph["edges"]))
        self.assertTrue(any(edge["from"] == "AC-WEB-SVG-FILTER" and edge["type"] == "checked by"
                            for edge in graph["edges"]))

    def test_development_roadmap_and_starter_spec_label_their_historical_scope(self):
        roadmap = (ROOT / "docs/development-roadmap/README.md").read_text(encoding="utf-8")
        current = (ROOT / "docs/development-roadmap/CURRENT_STATE.md").read_text(encoding="utf-8")
        acceptance = (ROOT / "docs/development-roadmap/FINAL_ACCEPTANCE.md").read_text(encoding="utf-8")
        starter = (ROOT / "docs/STARTER_ROLE_FEATURE_SPEC.md").read_text(encoding="utf-8")

        self.assertIn("제품 버전은 0.26.2다", roadmap)
        self.assertIn("아래 항목은 모두 제안이며 구현 완료나 출시 약속을 뜻하지 않는다.", roadmap)
        for identity in ("RD-01", "RD-02", "RD-03", "RD-04", "RD-05", "RD-06", "RD-07", "RD-08", "RD-09"):
            self.assertIn(identity, roadmap)
        self.assertIn("2026-11-13 검증 스냅샷", current)
        self.assertIn("후보 push·설치 후 검증은 대기", current)
        self.assertIn("이 문서는 조건별 검증 스냅샷이며 최종 출시·설치 영수증이 아니다.", acceptance)
        self.assertIn("조사 기준일은 2026-11-13이다.", starter)
        self.assertIn("배포 기준은 **v0.27.1**", starter)
        self.assertIn("개발 중 기능은 이날 작업 트리에서 확인한 스냅샷이다.", starter)

    def test_roadmap_ids_boundaries_and_task_test_controls_match_acceptance_matrix(self):
        roadmap = ROOT / "docs/development-roadmap"
        matrix = (roadmap / "FINAL_ACCEPTANCE.md").read_text(encoding="utf-8")
        all_matrix_ids = set(re.findall(r"\*\*(RD-\d{2}-AC-\d{2})\*\*", matrix))
        expected_all_ids = {f"RD-{rd:02d}-AC-{ac:02d}" for rd in range(1, 10) for ac in range(1, 6)}
        self.assertEqual(all_matrix_ids, expected_all_ids)

        for rd in range(1, 10):
            prefix = f"RD-{rd:02d}"
            feature = next(roadmap.glob(f"{prefix}-*/feature.md"))
            feature_text = feature.read_text(encoding="utf-8")
            self.assertEqual(set(re.findall(prefix + r"-REQ-\d{2}", feature_text)),
                             {f"{prefix}-REQ-{i:02d}" for i in range(1, 6)}, str(feature))
            self.assertEqual(set(re.findall(prefix + r"-AC-\d{2}", feature_text)),
                             {f"{prefix}-AC-{i:02d}" for i in range(1, 6)}, str(feature))
            self.assertEqual(set(re.findall(r"\*\*(" + prefix + r"-AC-\d{2})\*\*", matrix)),
                             {f"{prefix}-AC-{i:02d}" for i in range(1, 6)}, prefix)

            for kind in ("design", "feature", "tasks"):
                path = next(roadmap.glob(f"{prefix}-*/{kind}.md"))
                text = path.read_text(encoding="utf-8")
                self.assertIn("FINAL_ACCEPTANCE.md", text, str(path))
                self.assertIn("CURRENT_STATE.md", text, str(path))
                self.assertIn("CURSOR_HANDOFF.md", text, str(path))
                intro = " ".join(text.splitlines()[:5])
                self.assertRegex(intro, r"0\.27|snapshot|스냅샷|후보", str(path))

            tasks = next(roadmap.glob(f"{prefix}-*/tasks.md"))
            task_text = tasks.read_text(encoding="utf-8")
            refs = set(re.findall(r"(?:(?:\.\./)+)?(?:tests|examples)/[A-Za-z0-9_./-]+", task_text))
            for relative in refs:
                relative = relative.rstrip(".,;:)")
                resolved = (tasks.parent / relative).resolve() if relative.startswith("../") else ROOT / relative
                self.assertTrue(resolved.is_file(), f"{tasks}: {relative}")

    def test_roadmap_plan_and_handoffs_keep_historical_and_user_authority_boundaries(self):
        roadmap = ROOT / "docs/development-roadmap"
        plan = (roadmap / "README.md").read_text(encoding="utf-8")
        self.assertIn("아래 항목은 모두 제안이며 구현 완료나 출시 약속을 뜻하지 않는다.", plan)
        self.assertIn("제품 버전은 0.26.2다", plan)
        self.assertIn("0.26.3에서 추가한 이력 시각화", plan)
        for rd in range(1, 10):
            prefix = f"RD-{rd:02d}"
            directory = next(roadmap.glob(f"{prefix}-*"))
            for kind in ("feature", "design", "tasks"):
                self.assertIn(f"{prefix}-", plan)
                relative = f"{directory.name}/{kind}.md"
                self.assertIn(relative, plan, f"{prefix} {kind}")
                self.assertTrue(next(roadmap.glob(f"{prefix}-*/{kind}.md")).is_file())

        codex = (roadmap / "CODEX_FINAL_HANDOFF.md").read_text(encoding="utf-8")
        cursor = (roadmap / "CURSOR_HANDOFF.md").read_text(encoding="utf-8")
        current = (roadmap / "CURRENT_STATE.md").read_text(encoding="utf-8")
        self.assertIn("사용자가 직접 푸시한다", codex)
        self.assertIn("태그, 배포, 버전 bump를 하지 않는다", codex)
        self.assertIn("현재 사용자의 요청과 적용되는 `AGENTS.md`를 따른다", cursor)
        self.assertIn("문서 자체는 설치·외부 게시·실제 Figma 파일 변경 권한이 아니다", cursor)
        self.assertIn("2026-11-13 검증 스냅샷", current)
        self.assertIn("이 문서 갱신 자체는 새 설치나 실행의 증거가 아니다", current)

    def test_contribution_release_commands_match_the_current_cli(self):
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("tools/major_release.py --ref HEAD --candidate 1.0.0", text)
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tools/major_release.py"), "--help"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for option in ("--ref", "--candidate", "--base-ref", "--if-major", "--archive"):
            self.assertIn(option, result.stdout)

    def test_guide_procedure_assets_and_historical_import_labels_resolve(self):
        guide = ROOT / "docs/guide.md"
        text = guide.read_text(encoding="utf-8")
        self.assertIn("images/panel-history.png", text)
        self.assertIn("images/panel-review.png", text)
        for retired_panel in ("images/panel-import.png", "images/panel-graph-sync.png",
                              "images/panel-graph-diff.png"):
            self.assertIn("![", text)
            self.assertIn(retired_panel, text)
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
            if target.startswith(("http:", "https:")):
                continue
            self.assertTrue((guide.parent / target.split("#", 1)[0]).resolve().is_file(), target)

    def test_rd06_documented_native_read_witness_commands_run(self):
        for script in ("rd06_fresh_read.cjs", "rd06_read_comparison.cjs",
                       "rd06_reject_partial.cjs", "rd06_summary_coverage.cjs"):
            with self.subTest(script=script):
                result = subprocess.run(["node", str(ROOT / "tests" / script)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rd07_and_rd09_documented_command_witnesses_run(self):
        for script in ("rd07_transport_move.cjs", "rd09_audit_log.cjs"):
            with self.subTest(script=script):
                result = subprocess.run(["node", str(ROOT / "tests" / script)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
