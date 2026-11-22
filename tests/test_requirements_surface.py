"""Behavioral checks for the shipped requirements and evidence inventories."""
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

from tools.spec_graph_coverage import check as check_spec_graphs


ROOT = Path(__file__).resolve().parents[1]
PARITY_CONTROL_IDS = {
    "nav.tasks", "nav.history", "workspace.history-task-filter", "nav.codex",
    "workspace.task-filters", "profile.declare-plan-seat", "workspace.locale",
    "import.import", "import.fresh-existing-choice", "import.read-export", "import.sync",
    "import.open-source-preview", "review.create", "review.save-readback",
    "review.select-direction", "graph.read", "graph.readback-download", "graph.summary-read",
    "graph.apply", "graph.apply-subset", "graph.diagnostics-download", "workspace.asset-inventory",
    "workspace.carousel-select", "workspace.carousel-open-present", "chat.prepare-send",
    "chat.selection-info", "chat.copy-open", "figma.open-file-select-target",
    "figma.login-authorize", "figma.select-known-node", "figma.launch-plugin-session",
    "figma.present-prototype", "figma.visual-canvas-review", "figma.manual-target-choice",
}
OBSERVATION_ROOT_IDS = {
    "specs/design-inspection/scene-observations.json": {
        "OBS-scene-api-fixtures-stable0", "OBS-scene-owned-writes-v032",
        "OBS-scene-api-extra-after-services-v032", "OBS-scene-instance-main-component-read-v032",
        "OBS-scene-owned-component-reads-v032", "OBS-scene-owned-instance-list-blocked-v032",
        "OBS-scene-final-safe-properties-v032",
    },
    "specs/design-inspection/service-observations.json": {"OBS-SERVICES-032"},
    "specs/design-inspection/value-observations.json": {"OBS-native-value-61015a9cc0ad5b7a"},
    "specs/editable-web/api-observations.json": {
        "OBS-030-api-first", "OBS-030-api-2", "OBS-030-api-3", "OBS-030-vector-first",
        "OBS-030-vector-next", "OBS-030-type-creation",
    },
    "specs/graph-review/api-observations.json": {
        "OBS-DESIGN-first-70", "OBS-DESIGN-next-20", "OBS-DESIGN-all-90",
        "OBS-DESIGN-repeat-70", "OBS-DESIGN-nine-first", "OBS-DESIGN-nine-last",
        "OBS-DESIGN-nine-complete", "OBS-FIGJAM", "OBS-SLIDES",
    },
    "specs/responsive-web/api-observations.json": {
        "OBS-responsive-api-batch-0", "OBS-responsive-api-batch-1",
        "OBS-responsive-api-batch-2", "OBS-responsive-api-batch-3",
    },
}
OBSERVATION_SCOPE_MARKERS = {
    "specs/design-inspection/scene-observations.json": {
        "OBS-scene-api-fixtures-stable0": "public graph omits node IDs and returned values",
        "OBS-scene-owned-writes-v032": "passed and restored",
        "OBS-scene-api-extra-after-services-v032": "owned Design fixture page",
        "OBS-scene-instance-main-component-read-v032": "linked state from the owned instance",
        "OBS-scene-owned-component-reads-v032": "Unowned instance results were excluded",
        "OBS-scene-owned-instance-list-blocked-v032": "No API-member observation was recorded",
        "OBS-scene-final-safe-properties-v032": "Values and fixture node IDs remain private",
    },
    "specs/design-inspection/service-observations.json": {
        "OBS-SERVICES-032": "Raw values remain private",
    },
    "specs/design-inspection/value-observations.json": {
        "OBS-native-value-61015a9cc0ad5b7a": '"union_coverage"',
    },
    "specs/editable-web/api-observations.json": {
        "OBS-030-api-first": "Registered plugin read on a typed Design selection",
        "OBS-030-api-2": "Registered plugin read on a typed Design selection",
        "OBS-030-api-3": "Registered plugin read on a typed Design selection",
        "OBS-030-vector-first": "Registered plugin read on a typed Design selection",
        "OBS-030-vector-next": "Registered plugin read on a typed Design selection",
        "OBS-030-type-creation": "same graph selected the same component on repeat",
    },
    "specs/graph-review/api-observations.json": {
        "OBS-DESIGN-first-70": "읽기 전용 게터",
        "OBS-DESIGN-next-20": "읽기 전용 게터",
        "OBS-DESIGN-all-90": "읽기 전용 게터",
        "OBS-DESIGN-repeat-70": "읽기 전용 게터",
        "OBS-DESIGN-nine-first": "읽기 전용 게터",
        "OBS-DESIGN-nine-last": "읽기 전용 게터",
        "OBS-DESIGN-nine-complete": "읽기 전용 게터",
        "OBS-FIGJAM": "반복 실행 후 수량을 보존했다",
        "OBS-SLIDES": "반복 실행 시 같은 덱을 선택하고 노드 수를 보존했다",
    },
    "specs/responsive-web/api-observations.json": {
        f"OBS-responsive-api-batch-{i}": "Bounded native Figma Plugin API getter batch" for i in range(4)
    },
}


class RequirementsSurfaceTests(unittest.TestCase):
    def test_registered_source_and_acceptance_declarations_remain_closed(self):
        findings = check_spec_graphs(ROOT)
        blocking = [item for item in findings if item.get("severity", "blocker") not in {"advisory", "warning", "info"}]
        self.assertEqual([], blocking)
        self.assertFalse(any(item["code"] in {"declared-spec-id-unmapped", "referenced-spec-id-unmapped", "missing-source-target", "requirement-unaccepted", "acceptance-unowned", "acceptance-no-test"} for item in findings))

    def test_agent_instructions_retain_codex_and_design_acceptance_boundaries(self):
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        scope = instructions.split("## 제품 범위", 1)[1].split("## 패치 기록과 개선 완료 조건", 1)[0]
        for claim in (
            "Codex 중심 릴레이·뷰어",
            "Figma 패널에 별도 대화 입력, 작업 관리, 프로필 작성 또는 중복 승인을 추가하지 않는다.",
            "정본 graph의 인수 조건을 연결한다.",
            "다른 편집기용 코드·메뉴·SDK 생성기·테스트 앱을 추가하거나 복구하지 않는다.",
            "Computer Use와 hook을 끈 사용자 경로",
            "실제 브라우저·Figma 인수 결과와 함께 기록한다.",
        ):
            self.assertIn(claim, scope)
        self.assertTrue((ROOT / "specs/codex-relay/spec.md").is_file())
        self.assertTrue((ROOT / "specs/design-specialization/spec.md").is_file())

    def test_agent_patch_record_rules_require_preserved_independent_evidence(self):
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        section = instructions.split("## 패치 기록과 개선 완료 조건", 1)[1]
        self.assertIn("CHANGELOG의 짧은 사용자 변화", section)
        self.assertIn("patch_knowledge.py verify --ref HEAD", section)
        self.assertIn("실행하는 검사 파일의 Git blob·모드를 바꿔 완료 기준을 낮추지 않는다.", section)
        self.assertIn("독립 검사로 증명", section)
        self.assertIn("hook을 추가하지 않는다.", section)

    def test_product_constitution_retains_admission_runtime_and_major_gate_claims(self):
        constitution = (ROOT / "CONSTITUTION.md").read_text(encoding="utf-8")
        self.assertIn("제품 범위는 Figma Design이다.", constitution)
        self.assertIn("관계를 정본 그래프에 기록한다", constitution)
        self.assertIn("대화, 작업 선택, 플랜·좌석 설정, 수정 승인, 결과 설명과 오류 복구는 Codex에서 진행한다.", constitution)
        self.assertIn("그래프 누락, 제품 값을 여러 곳에서 독립적으로 선언한 하드코딩", constitution)
        self.assertIn("메이저 ZIP 생성을 중단한다.", constitution)
        self.assertIn('editorType: ["figma"]', constitution)
        self.assertIn("공식 Figma MCP를 필수 의존성이나 실행 경로로 추가하지 않는다.", constitution)

    def test_verification_record_preserves_snapshot_age_and_unverified_limits(self):
        path = ROOT / "specs/verification.md"
        record = path.read_text(encoding="utf-8")
        self.assertTrue(record.startswith("# Verification · 0.26.0 · 2026-11-12"))
        self.assertIn("Historical baseline · 2026-11-11", record)
        self.assertIn("Historical evidence is not automatically current at source_head", (ROOT / "specs/regression-program/cases.json").read_text(encoding="utf-8"))
        self.assertIn("This proves declared scalar synchronization, not whole-page layout synchronization.", record)
        self.assertIn("remain unverified", record)
        for match in re.finditer(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", record):
            target = urlparse(match.group(1))
            if target.scheme or target.netloc or not target.path:
                continue
            self.assertTrue((path.parent / target.path.split("#", 1)[0]).resolve().exists(), match.group(1))

    def test_alignment_example_rules_match_the_written_measurement_contract(self):
        rules = json.loads((ROOT / "specs/alignment-audit/owned-workspace.rules.json").read_text(encoding="utf-8"))
        self.assertEqual("main[data-ready='true'] .data-table", rules["readySelector"])
        self.assertEqual({"app-heading-start", "package-column-start"}, {group["id"] for group in rules["groups"]})
        table = next(group for group in rules["groups"] if group["id"] == "package-column-start")
        self.assertEqual(("x", "start", ".data-table thead th:first-child", [".data-table tbody tr > :first-child"], 0.5),
                         (table["axis"], table["edge"], table["anchor"], table["targets"], table["tolerance"]))
        contract = (ROOT / "specs/alignment-audit/spec.md").read_text(encoding="utf-8")
        self.assertIn("320px와 400px에서 기준선 편차 0.5px 이하", contract)

    def test_live_change_contract_preserves_no_write_and_no_sla_limits(self):
        spec = (ROOT / "specs/live-change-sync/spec.md").read_text(encoding="utf-8")
        self.assertIn("event는 이전 값이나 변경 수행자를 입증하지 않는다.", spec)
        self.assertIn("적용 대상은 로컬 graph와 web module이며 Figma에는 쓰지 않는다.", spec)
        self.assertIn("subsecond 알림 또는 지속 실행 SLA가 아니다.", spec)
        self.assertIn("불확실하면 같은 batch를 자동 재전송하지 않는다.", spec)

    def test_codex_relay_spec_keeps_dialogue_approval_and_task_authority_in_codex(self):
        spec = (ROOT / "specs/codex-relay/spec.md").read_text(encoding="utf-8")
        self.assertIn("현재 Codex 대화가 요청, 방향 선택, 승인, 배경 설명, 결과 보고의 창이다.", spec)
        self.assertIn("플러그인 홈은 대화·설정 폼·작업 버튼 없이 상태를 표시한다.", spec)
        self.assertIn("사용자와의 대화나 자체 승인 기록을 만들지 않는다.", spec)
        self.assertIn("[요구사항 연결](graph.json)", spec)

    def test_profile_contract_keeps_plan_declaration_distinct_from_capability(self):
        spec = (ROOT / "specs/local-profile-init/spec.md").read_text(encoding="utf-8")
        self.assertIn("사용자가 각각 지정하거나 ‘모름’으로 확인", spec)
        self.assertIn("Figma가 공개한 User 객체에는 플랜, 청구 상태, 좌석과 파일 쓰기 권한 필드가 없다.", spec)
        self.assertIn("사용자 입력과 자동 관측은 각각 별도 키에 저장", spec)
        self.assertIn("실제 `dev/inspect`에서만 활성화한다.", spec)

    def test_pre_figma_review_contract_does_not_claim_visual_acceptance(self):
        spec = (ROOT / "specs/pre-figma-quality/spec.md").read_text(encoding="utf-8")
        self.assertIn("does not create an aesthetic score", spec)
        self.assertIn("no generated candidates, design assets, Figma inspection, browser/runtime evidence, or visual-quality certification", spec)
        self.assertIn("blocked/unverified", spec)

    def test_design_specialization_requires_a_real_design_use_path(self):
        spec = (ROOT / "specs/design-specialization/spec.md").read_text(encoding="utf-8")
        self.assertIn("요구사항 → Design 사용 장면 → 구현 → 인수 근거 경로", spec)
        self.assertIn("Design/default만 허용한다.", spec)
        self.assertIn("공식 선언 수집이나 컴파일 통과를 실측으로 승격하지 않는다.", spec)
        self.assertIn("실제 Design 파일에서 재실행해 그래프에 근거를 연결한다.", spec)

    def test_readable_spec_contract_keeps_graph_canonical_and_copy_source_bound(self):
        spec = (ROOT / "specs/readable-specifications/spec.md").read_text(encoding="utf-8")
        self.assertIn("Human-readable purpose, journey, first action, behavior, precondition, result, and failure/limits may be recorded only when supported by the source.", spec)
        self.assertIn("graph.json` owns relationships and status", spec)
        self.assertIn("screen-spec.md` is a projection keyed by graph IDs", spec)
        self.assertIn("Stale getters cannot count as current.", spec)

    def test_startup_contract_keeps_stale_runtime_and_native_proof_boundaries(self):
        spec = (ROOT / "specs/startup-freshness/spec.md").read_text(encoding="utf-8")
        self.assertIn("An installed version that resembles a known release does not prove repository identity.", spec)
        self.assertIn("filesystem, package, or server version is insufficient.", spec)
        self.assertIn("Retirement neither re-admits stale inputs nor authorizes execution.", spec)
        self.assertIn("a source test does not substitute for them", spec)

    def test_activity_contract_separates_history_from_acceptance_and_authority(self):
        spec = (ROOT / "specs/workspace-activity/spec.md").read_text(encoding="utf-8")
        self.assertIn("현재 등록된 뷰어에서 실행 이력과 검증 결과는 Codex가 전달한다.", spec)
        self.assertIn("차트는 전체 제품 인수 완료율이 아니다.", spec)
        self.assertIn("Python control journal의 권한·현재 native 값·클라우드 저장을 인증하지 않는다.", spec)
        self.assertIn("graph 노드의 등록만으로 실행 성공을 주장하지 않는다.", spec)

    def test_interactive_web_specs_keep_observed_transitions_and_exclusions(self):
        carousel = (ROOT / "specs/interactive-web/carousel.md").read_text(encoding="utf-8")
        self.assertIn("5,000 ms 타이머", carousel)
        self.assertIn("해당 레일 밖의 페이지를 드래그해 페이지를 바꾸지는 않는다.", carousel)
        self.assertIn("동적 진행 막대와 네이티브 스크롤 관성은 같은 시간·궤적으로 복원되지 않는다.", carousel)
        tabs = (ROOT / "specs/interactive-web/tabs.md").read_text(encoding="utf-8")
        self.assertIn("관찰하지 않은 전이", tabs)
        self.assertIn("세 번째 미관찰 탭 클릭", tabs)
        disclosure = (ROOT / "specs/interactive-web/disclosure.md").read_text(encoding="utf-8")
        self.assertIn("single-collapsible", disclosure)
        self.assertIn("initialState`에서 directed traversal", disclosure)
        self.assertIn("나머지 3개 질문 조합", disclosure)

    def test_feature_index_resolves_local_links_and_lists_registered_graphs(self):
        findings = check_spec_graphs(ROOT)
        index_findings = [item for item in findings if item["code"] in {"broken-index-link", "unsafe-index-link", "root-not-indexed", "registry-not-indexed"}]
        self.assertEqual([], index_findings)
        index = (ROOT / "specs/README.md").read_text(encoding="utf-8")
        self.assertIn("That registry, rather than every directory beneath `specs/`, defines which graph roots are required", index)
        self.assertIn("Evidence collections such as `design-inspection/` and the case inventory in `regression-program/` have different roles", index)
        self.assertIn("It is not a product relationship graph.", index)
        self.assertIn("They are not implemented feature registrations or evidence of acceptance.", index)

    def test_observation_inventories_preserve_graph_identity_and_sources(self):
        for relative, expected_root_ids in OBSERVATION_ROOT_IDS.items():
            path = ROOT / relative
            with self.subTest(path=path.relative_to(ROOT)):
                inventory = json.loads(path.read_text(encoding="utf-8"))
                nodes = inventory["nodes"]
                identifiers = [node["id"] for node in nodes]
                self.assertEqual(len(identifiers), len(set(identifiers)))
                self.assertTrue(all(isinstance(node.get("source"), str) and node["source"].strip() for node in nodes))
                self.assertTrue(all(isinstance(node.get("detail"), str) and node["detail"].strip() for node in nodes if node.get("type") == "test"))
                for node in nodes:
                    source = urlparse(node["source"])
                    if source.scheme or not source.path:
                        continue
                    target = (path.parent / source.path.split("#", 1)[0]).resolve()
                    self.assertTrue(target.exists(), f"{node['id']} points to missing local source {node['source']}")
                known = set(identifiers)
                self.assertTrue(all(edge["from"] in known and edge["to"] in known for edge in inventory["edges"]))
                observation_roots = {node["id"]: node for node in nodes if node.get("type") == "test"}
                self.assertEqual(expected_root_ids, set(observation_roots))
                for node in observation_roots.values():
                    self.assertIn(OBSERVATION_SCOPE_MARKERS[relative][node["id"]], node.get("detail", ""))
                    if node.get("observed_at"):
                        self.assertRegex(node["observed_at"], r"^\d{4}-\d\d-\d\dT")
                    else:
                        self.assertTrue(node["source"].startswith("https://github.com/"))
                        self.assertRegex(node["source"], r"/blob/v\d+\.\d+\.\d+/")
                    if node.get("receipt_sha256"):
                        self.assertRegex(node["receipt_sha256"], r"^[0-9a-f]{64}$")
                if relative.endswith("scene-observations.json"):
                    blocked = observation_roots["OBS-scene-owned-instance-list-blocked-v032"]
                    self.assertEqual("blocked", blocked["status"])
                    self.assertIn("No API-member observation was recorded", blocked["detail"])
                if relative.endswith("value-observations.json"):
                    self.assertIn('"graph_sha256"', observation_roots["OBS-native-value-61015a9cc0ad5b7a"]["detail"])
                    self.assertIn('"policy_sha256"', observation_roots["OBS-native-value-61015a9cc0ad5b7a"]["detail"])
                if relative.endswith("graph-review/api-observations.json"):
                    self.assertIn("21개", observation_roots["OBS-FIGJAM"]["detail"])
                    self.assertIn("21장", observation_roots["OBS-SLIDES"]["detail"])

    def test_panel_parity_inventory_keeps_each_control_and_evidence_limits(self):
        inventory = json.loads((ROOT / "specs/codex-relay/parity-inventory.json").read_text(encoding="utf-8"))
        description = (ROOT / "specs/codex-relay/parity.md").read_text(encoding="utf-8")
        items = inventory["items"]
        identifiers = [item["id"] for item in items]
        categories = set(inventory["categories"])
        self.assertTrue(items)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(PARITY_CONTROL_IDS, set(identifiers))
        self.assertTrue(all(item["currentStatus"] in categories for item in items))
        self.assertTrue(all(item.get("evidence") and item.get("limits") for item in items))
        self.assertTrue(all(item.get("legacySurface") and item.get("action") for item in items))
        self.assertTrue(all(item.get("codexPath") for item in items if item["currentStatus"] != "figma_runtime_or_direct_interaction"))
        for item in items:
            for reference in item["evidence"]:
                path, _, _ = reference.partition(":")
                if path.startswith(("tools/", "panel-ui/", "figma-bridge/", "docs/", "library/")):
                    self.assertTrue((ROOT / path).exists(), f"{item['id']} points to missing evidence source {path}")
        self.assertIn("does not claim", inventory["scope"]["runtimeBoundary"])
        self.assertIn("source inventory", description)
        self.assertIn("not a claim that an old screenshot or a CLI parser option proves a live native operation", description)

    def test_regression_case_inventory_keeps_unique_cases_and_scoped_receipts(self):
        inventory = json.loads((ROOT / "specs/regression-program/cases.json").read_text(encoding="utf-8"))
        plan = (ROOT / "specs/regression-program/plan.md").read_text(encoding="utf-8")
        cases = inventory["cases"]
        identifiers = [case["id"] for case in cases]
        allowed = set(inventory["status_values"])
        self.assertTrue(cases)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        plan_rows = {
            match.group(1): (match.group(2).strip(), match.group(3).strip(), match.group(4).strip())
            for match in re.finditer(r"^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", plan, re.MULTILINE)
            if match.group(1).startswith("TC-")
        }
        self.assertEqual(set(identifiers), set(plan_rows))
        self.assertIn("현재 케이스 상태는 모두 `unverified`", plan)
        self.assertEqual({"unverified"}, {case["status"] for case in cases})
        for key in ("source_head", "plan_source_head"):
            revision = inventory[key]
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["status"], allowed)
                self.assertEqual((case["title"], case["level"], case["acceptance"]), plan_rows[case["id"]])
                if case["status"] == "passed":
                    self.assertTrue(case.get("verified_scope"))
                    self.assertFalse(case.get("remaining_scope"))
                    self.assertTrue(any(evidence.get("availability") != "owner-local-not-shipped" for evidence in case.get("evidence", [])))
                for evidence in case.get("evidence", []):
                    self.assertTrue(evidence.get("path"))
                    self.assertRegex(evidence.get("sha256", ""), r"^[0-9a-f]{64}$")
                    self.assertTrue(evidence.get("kind"))
                    self.assertTrue(evidence.get("claim"))
                    self.assertTrue(evidence.get("availability"))


if __name__ == "__main__":
    unittest.main()
