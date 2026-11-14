# 다음 기능 설계안

신규 기능과 최적화는 [제품 헌법](../../CONSTITUTION.md)과 [Design 전용 설계](../../specs/design-specialization/spec.md)에 따라 채택한다. 각 작업에 실제 Design 사용 장면과 정본 그래프의 인수 근거를 연결한다.

이 폴더의 현재 우선순위·의존성·산출물·상태의 **유일한 정본 시작점**은 [backlog.graph.json](backlog.graph.json)과 [capability-review.md](capability-review.md)다. 현재 구현 동작과 인수 결과는 [최종 인수 기록](../development-roadmap/FINAL_ACCEPTANCE.md), [기능 스펙 색인](../../specs/README.md) 및 각 소스의 독립 검사에서 확인한다.

예약·대기·취소는 Little Hands 앱의 업무 기능이다. 이를 Figma Flow 제품에 다시 제안하지 않는다. 전체 suite의 과거 통과나 일부 Figma getter 확인은 전체 화면 인수가 아니다.

## 정본 그래프와 실행 진입점

- **기계 판독 작업 그래프:** [backlog.graph.json](backlog.graph.json) (`schema: figma-flow-capability-backlog-v1`)
- **정본 검토·인수 기준서:** [capability-review.md](capability-review.md)
- **P0 기준 보호·자체 입력 인수 기록:** [p0-reference-acceptance.md](p0-reference-acceptance.md)
- **그래프 검증 검사:** `python3 -B -m unittest tests.test_next_roadmap_backlog`

중복 우선순위 표나 고정된 운영 상태 목록을 두지 않는다. 모든 작업의 상태, 선행 `depends-on`·`extends` 관계, `next-ready` 판정(`status == "proposed"`이면서 모든 `depends-on` 선행 노드가 `accepted` 또는 `verified`인 작업), 산출물, 검증 명령은 [backlog.graph.json](backlog.graph.json)에서 직접 읽는다.

- **기준선 및 작업 그래프:** [backlog.graph.json](backlog.graph.json)은 기준선 노드(`accepted-narrow-cta-baseline`, [Starter Role 기능 계약](../STARTER_ROLE_FEATURE_SPEC.md#ssot-graph-plan) · [이전 own-mode 기록](../llm-wiki/releases.md#v0.28.0) · [상호작용 정본 그래프](../../specs/interactive-web/graph.json))와 후속 P0–P2 작업 노드 간의 `depends-on`·`extends` 관계를 정의한다.
- **P0 API queue 재검증 근거 (`p0-api-queue-validation`):** [tools/api_priority.py](../../tools/api_priority.py) · [tests/test_api_priority.py](../../tests/test_api_priority.py) · [docs/api-priority.md](../api-priority.md) · [scene-observations.json](../../specs/design-inspection/scene-observations.json) · [service-observations.json](../../specs/design-inspection/service-observations.json) (상세 재현 수치·재분류 근거·인수 상태 정본은 [backlog.graph.json](backlog.graph.json))
- **P0 인수 근거 경로 및 운영 안내 (`p0-reference-safety`):**
  - 공개 인수 기록: [p0-reference-acceptance.md](p0-reference-acceptance.md)
  - 배포 가드·CI·회귀 검사: [tools/reference_distribution_guard.py](../../tools/reference_distribution_guard.py) · [tests/test_reference_distribution_guard.py](../../tests/test_reference_distribution_guard.py) · [.github/workflows/reference-guard.yml](../../.github/workflows/reference-guard.yml)
  - 자체 공개 기준 입력 및 테스트: [examples/owned-design-baseline/README.md](../../examples/owned-design-baseline/README.md) · [tests/test_owned_design_baseline.py](../../tests/test_owned_design_baseline.py)
  - 배포·기여 안내: [CONTRIBUTING.md](../../CONTRIBUTING.md) · [docs/guide.md#private-distribution](../guide.md#private-distribution)
- **P1 인수 근거 및 검증 위치:**
  - 공개 인수 영수증: [p1-acceptance.md](p1-acceptance.md)
  - `p1-native-component-families` (`NF-01`) 구현·검증 위치: [tools/design_system.py](../../tools/design_system.py) · [tools/figma_bridge.py](../../tools/figma_bridge.py) · [tools/family_provision.py](../../tools/family_provision.py) · [figma-bridge/code.js](../../figma-bridge/code.js) · [figma-bridge/semantic_components.js](../../figma-bridge/semantic_components.js) · [examples/owned-component-families/README.md](../../examples/owned-component-families/README.md) · [tests/test_component_families.py](../../tests/test_component_families.py) · [tests/test_bridge_declared_property_compare.py](../../tests/test_bridge_declared_property_compare.py) · [tests/nf01_semantic_family_runtime.cjs](../../tests/nf01_semantic_family_runtime.cjs) · [tests/test_property_repair_regression.cjs](../../tests/test_property_repair_regression.cjs)
  - `p1-causal-review-history` (`NF-03`) 구현·검증 위치: [tools/operation_detail.py](../../tools/operation_detail.py) · [tools/figma_control.py](../../tools/figma_control.py) · [tests/test_operation_detail.py](../../tests/test_operation_detail.py) · [figma-bridge/workspace_host.js](../../figma-bridge/workspace_host.js) · [tests/nf03_history_detail.cjs](../../tests/nf03_history_detail.cjs) · [panel-ui/src/operationDetail.mjs](../../panel-ui/src/operationDetail.mjs) · [tests/test_nf03_panel_ui.cjs](../../tests/test_nf03_panel_ui.cjs)

- **P2 1차 실행 계약 (`p2-rights-cleared-fixture`, `p2-read-performance-baseline`):** [p2-wave1-acceptance.md](p2-wave1-acceptance.md). 최소 데이터 형태, 의존성 그래프, 인수 항목, root 실측 절차를 정한다. 인수 영수증이 아니다.

> 모든 작업의 현재 상태(`status`·`evidence_status`)와 근거 승격은 [backlog.graph.json](backlog.graph.json)에서 직접 판정하며, `tests/test_next_roadmap_backlog.py`가 그래프 불변식(`verified`/`accepted` 시 공개 근거 실존 및 `depends-on` 선행 충족, `in-progress` 시 `depends-on` 선행 충족과 미검증 유지, `proposed` 시 미검증 유지, `depends-on` 비순환)을 검증한다.

## 0.29–0.35 구현 범위와 제안의 경계

기존 Design 페이지의 검토 보드, 같은 출처 에셋의 명시적 입력 매핑, 선택한 네이티브 속성의 관측과 재실행 비교가 추가됐다. [정본 기능 그래프](../../specs/graph-review/graph.json)와 [실제 인수 결과](../../specs/graph-review/spec.md)에서 구체적인 범위를 확인한다.

Little Hands의 `apps/little-hands/design/source.py`는 실제 캡처를 그래프와 디자인 파일로 변환한다. `reconcile()`은 graph source와 사람이 편집한 값을 비교한다. baseline이 없는 기존 값은 `retained_legacy_edits`에 보존하고, 양쪽에서 같은 필드를 다르게 바꾸면 충돌로 중단한다. `--expected-sha256`는 오래된 graph 입력을 거절한다. `v0.34.0` 이후 `main`에 통합된 G1 소스 재생성 변경(`0.35.0` 배포 버전 연결)은 `REQS`·`STATES`의 명시적 ID 이관과 채택된 토큰·직접 작성 관계 보존, 차단된 CSS epoch와 재시도에 걸친 `retained_without_source` 고아 후보 유지를 구현했다. G0~G5 전체 직군 인수는 별도로 남아 있다.

`share_control_styles()`는 기존 492개 컨트롤 선언을 12개 profile 계열의 desktop/mobile main 선언 24개로 공유한다. 이는 현재 authored declaration 재사용이다. 입력·선택·표 계열의 6개 family·선언 속성·반복 실행 편집 보존 지원은 `p1-native-component-families`([NF-01](NF-01-component-families.md))에서 구현·검증했으며, main/instance 실제 readback 결과와 범위 경계는 [p1-acceptance.md](p1-acceptance.md)와 [backlog.graph.json](backlog.graph.json)에서 다룬다.

Native 제작의 같은 실행 안에서 반복하던 container·annotation 탐색은 공유 index를 사용하는 경로가 있다. 이는 `p2-read-performance-baseline` / `p2-incremental-native-read`([NF-02](NF-02-incremental-native-read.md))의 세션 browse cache와 다르다. NF-02를 시작할 때 통합 소스에서 동일 작업의 기준을 다시 잰다. Figma event 전달만으로 모든 main·style 파생 변경의 최신성을 증명하지 않는다.

상호작용 프로토타입은 캐러셀(0.33.0, [기록](../../specs/interactive-web/carousel.md)), 탭 A→B→A(0.34.0, [기록](../../specs/interactive-web/tabs.md)), 단일 열림 SaaS FAQ 아코디언(0.35.0, 5개 중 2개 질문·7번 브라우저 입력 → 3개 상태·6방향 전이, [기록](../../specs/interactive-web/disclosure.md) · [버전 기록](../llm-wiki/releases.md#v0.35.0))까지를 기존 범위로 두고, 모바일 뷰포트와 키보드 접근성 확장은 `p2-faq-mobile-keyboard`에서 다룬다.

## 이전 개별 설계 제안 (`NF-01`–`NF-09`, Historical Proposals)

아래 `NF-01`–`NF-09` 문서는 항목별 상세 설계 배경을 보존한 이전 개별 제안서다. 각 문서 안의 개별 제안 상태나 순서는 아래 매핑에 따라 정본 그래프([backlog.graph.json](backlog.graph.json)) 또는 관련 스펙으로 연결되며, 이 목록은 그래프와 별도의 상태·우선순위 목록을 만들지 않는다.

| 문서 | 원래 제안 주제 | 정본 그래프 및 관련 스펙 연결 |
| --- | --- | --- |
| [NF-01](NF-01-component-families.md) | 입력·선택·표 컴포넌트 계열 | [capability-review.md#p1-component-families](capability-review.md#p1-component-families) (`p1-native-component-families`) · [Design 전용 설계](../../specs/design-specialization/spec.md) |
| [NF-02](NF-02-incremental-native-read.md) | 안전한 증분 네이티브 읽기 | [capability-review.md#p2-performance-baseline](capability-review.md#p2-performance-baseline), [capability-review.md#p2-incremental-read](capability-review.md#p2-incremental-read) (`p2-read-performance-baseline`, `p2-incremental-native-read`) |
| [NF-03](NF-03-causal-history.md) | 실행 원인과 상세 차이 탐색 | [capability-review.md#p1-causal-history](capability-review.md#p1-causal-history) (`p1-causal-review-history`) · [Workspace Activity](../../specs/workspace-activity/spec.md) |
| [NF-04](NF-04-renderer-adapters.md) | SSR 어댑터와 CSS 내보내기 | [capability-review.md#p2-css-fidelity](capability-review.md#p2-css-fidelity) (`p2-complex-render-fidelity`) · G3 첫 사례는 [Starter 계약](../STARTER_ROLE_FEATURE_SPEC.md) |
| [NF-05](NF-05-improvement-runner.md) | 포크 패치·근거 교환과 개선 러너 | 별도 개발자 유지보수 CLI 제안 (`backlog.graph.json`의 P0–P2 기능 확장 순서 외부) |
| [NF-06](NF-06-domain-protocol.md) | 도메인 경계와 버전 전환 | 별도 전송/호환 프로토콜 제안 · [Startup Freshness](../../specs/startup-freshness/spec.md) |
| [NF-07](NF-07-web-import-editor-capabilities.md) | 웹 가져오기와 에디터 기능 범위 | [capability-review.md#p2-production-fixture](capability-review.md#p2-production-fixture), [capability-review.md#p2-css-fidelity](capability-review.md#p2-css-fidelity) · [웹 캡처 경계](../web-design-capture.md) · [API 우선순위](../api-priority.md) |
| [NF-08](NF-08-optional-plugin-routing.md) | 선택적 설치 plugin 경로 | 핵심 Design 경로·capability matrix 인수 이후 검토하는 후속 선택 제안 |
| [NF-09](NF-09-interactive-web-design.md) | 웹 상호작용의 Design 프로토타입 변환 | [capability-review.md#p2-production-fixture](capability-review.md#p2-production-fixture), [capability-review.md#p2-faq-accessibility](capability-review.md#p2-faq-accessibility) · [상호작용 정본 그래프](../../specs/interactive-web/graph.json) |

## 문서를 실행하는 방법

1. [backlog.graph.json](backlog.graph.json)에서 현재 `next-ready` 작업과 `depends-on` 선행 조건, 연결된 `doc_ref`·`proof_refs`·`commands`를 확인한다.
2. [capability-review.md](capability-review.md)의 해당 앵커 절과 연결된 `NF-*` 및 `specs/` 문서를 읽고, 현재 checkout·dirty files·실제 함수 caller와 파일 소유를 다시 확인한다. 범위 밖 파일이 필요하면 변경을 멈추고 필요한 계약을 보고한다.
3. 기존 명령(`commands`)은 저장소에 있는 회귀 검사이며, `proposed_checks`("미구현 새 검사 제안")는 아직 구현되지 않은 검사다. 제품 변경에는 각 설계의 독립 인수 조건과 필요한 실제 browser/Figma 관찰을 추가한다.
4. `skills/patch-knowledge/SKILL.md`에 따라 CHANGELOG와 Wiki를 갱신하고 `python3 tools/patch_knowledge.py verify --ref HEAD`를 실행한다. 실패 기반 개선은 수정하지 않은 기준으로 `python3 tools/patch_knowledge_check.py gate <proposal.json> --execute`를 통과해야 한다.

이 문서들은 기능 구현, 실제 native 인수, 성능 수치, 클라우드 저장 또는 배포 성공을 주장하지 않는다. 공식 API 문서는 구현 시 다시 읽고, API 존재와 현재 host/runtime에서 사용할 수 있는지는 각각 검증한다.
