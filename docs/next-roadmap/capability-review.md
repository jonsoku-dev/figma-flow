# Figma Design 기능 확장 검토서

> 이 문서는 Figma Design 전용 기능 확장 계획의 정본 검토서다. 작업·의존성·산출물·인수 기준의 기계 판독 정본은 [backlog.graph.json](backlog.graph.json)이며, 이 문서의 각 절 앵커와 1:1로 연결된다. 이 문서는 제안 범위와 인수 기준을 정의하며, 제품 구현 완료나 릴리스 승인을 뜻하지 않는다. [제품 헌법](../../CONSTITUTION.md) · [Design 전용 설계 계약](../../specs/design-specialization/spec.md)

## 목표와 경계

Figma Design 안에서 기획자, 디자이너, 개발자가 같은 그래프를 사용해 검토·편집·대조하는 범위를 SaaS 데스크톱 FAQ의 현재 예보다 넓힌다. 각 항목의 현재 상태(`status` · `evidence_status`)와 선행 충족 여부는 [backlog.graph.json](backlog.graph.json)을 정본으로 따르며, 그래프 등록만으로 미검증 항목의 구현이나 인수를 주장하지 않는다.

<a id="accepted-cta-baseline"></a>

작은손 예약 CTA에 한정한 G2–G5 경로는 인수된 기준선이다. 이미 확인한 정책 영향 리뷰, 한 색의 영속 CSS, 해당 색의 Figma 왕복, 오프라인 인계 결과를 다시 신규 결함이나 미구현으로 세지 않는다. 0.33–0.35에서 다룬 캐러셀·탭·단일 열림 SaaS FAQ 프로토타입 기준선도 별도 정본 그래프에 기록되어 있으며, 남은 일은 그 좁은 경로를 여러 화면·컴포넌트·키보드·복합 미디어 사례로 넓힐 때의 인수다. [Starter G0–G5 계약](../STARTER_ROLE_FEATURE_SPEC.md#ssot-graph-plan) · [이전 own-mode 인수 기록](../llm-wiki/releases.md#v0.28.0) · [상호작용 정본 그래프](../../specs/interactive-web/graph.json) · [SaaS FAQ 인수 기록](../../specs/interactive-web/disclosure.md)

새 경로는 Design 전용으로 유지한다. 개발 플러그인의 일반 UI와 로컬 명령을 쓰며 공식 Figma MCP, 사용자 Computer Use 세션, hook을 추가하지 않는다. Figma 쓰기나 외부 데이터 전달을 암묵적으로 시작하지 않는다.

<a id="current-cli-evidence"></a>

## 현재 CLI 근거 (`p0-api-queue-validation`)

API 우선순위 도구를 현재 저장소의 관측 자료로 다시 빌드한 임시 인벤토리에 실행하면 빌드는 1,382개 audit 행(`sha256`: `4e5480245bf3779a7d39668698be65fd5d0974bee71b5ce9316eea0918c551a5`)으로 끝나고, `--limit 2000` 전체 미관측 queue는 825개 행, `--design-only --feasible-only` Design 전용 feasible queue는 12개 행(`design-api` 8개, `design-node` 4개)을 반환한다. `observed_graph_member_ids` 502는 별도 입력 메트릭이며 제품 지원율이 아니다. 이 결과는 조사 가능한 후보의 크기이며, 12개가 지원된다는 뜻도, 825개가 전부 Figma에서 불가능하다는 뜻도 아니다. 현재 queue 설명상 12개는 서비스/API 속성 8개, 기존 owned fixture에서 예외를 낸 variant getter 2개, 공개 factory가 없는 `TRANSFORM_GROUP` 속성 2개로 나뉜다. [API 우선순위 계약](../api-priority.md) · [Design scene 관측](../../specs/design-inspection/scene-observations.json) · [Design service 관측](../../specs/design-inspection/service-observations.json)

다음 명령은 최신 인벤토리를 임시 폴더에 만들고 queue를 재생한다. 공유 인벤토리나 reference evidence를 덮어쓰지 않는다.

```sh
api_inventory_dir="$(mktemp -d)"
python3 -B tools/api_priority.py build --out "$api_inventory_dir/api-priority.json"
python3 -B tools/api_priority.py queue \
  --inventory "$api_inventory_dir/api-priority.json" \
  --limit 2000
python3 -B tools/api_priority.py queue \
  --inventory "$api_inventory_dir/api-priority.json" \
  --design-only --feasible-only
```

검증자는 출력의 row 수와 `unobserved_members`를 요약해 기록한다. 각 API 후보는 선언·permission·Design route·기존 실제 증거를 대조한 뒤에만 probe 대상으로 삼는다. queue 수, 이름 참조나 테스트 파일 존재를 기능 통과율로 바꾸지 않는다. 재현 수치와 CLI 재분류 요약·최종 상태(`status`·`evidence_status`)의 정본은 [backlog.graph.json](backlog.graph.json)(`p0-api-queue-validation`)에 기록하며, 관련 도구·회귀 검사는 [tools/api_priority.py](../../tools/api_priority.py) · [tests/test_api_priority.py](../../tests/test_api_priority.py)에 연결된다.

## 우선순위와 의존성 그래프 (`backlog.graph.json`)

아래 P0–P2는 [backlog.graph.json](backlog.graph.json)의 `depends-on`·`extends` 관계와 사용자 피해를 기준으로 정리했다. 세 역할은 권한 등급이 아니라 각각 필요한 결과를 뜻한다. 각 작업의 현재 상태와 착수 가능(`next-ready`: `status == "proposed"`이면서 모든 `depends-on` 선행 노드가 `accepted` 또는 `verified`인 작업) 여부는 [backlog.graph.json](backlog.graph.json)에서 판정한다.

<a id="p0-reference-safety"></a>

### P0. 기준 자료 보호와 자체 기준 입력 분리 (`p0-reference-safety`)

원본 참고 자료, 기존 실제 캡처·readback, 생성물과 새 회귀 입력을 분리한다. 기존 증거는 읽기 전용으로 두고 새 비교용 fixture는 독립된 임시 복사본 또는 출처와 사용 권리가 확인된 입력으로 준비한다. 공개 커밋에는 원본 템플릿, 원시 응답, 실제 사용자 문구·계정, 원본 화면 제목과 식별자를 넣지 않는다.

**역할 우선순위:** 엔지니어가 먼저 기준 입력과 명령을 고정하고, 디자이너와 기획자가 변경 소유자·검토 책임을 확인한다.

**산출물:** 기준 입력 manifest, 생성물 경로, 보존 대상 목록, 각 입력의 출처·권리·민감도, 변경 전후 비교 명령. 상세 인수 기록은 [p0-reference-acceptance.md](p0-reference-acceptance.md)에 연결하고, 작업 상태와 `observed_evidence` 정본은 [backlog.graph.json](backlog.graph.json)에서 읽는다.

**P0 인수 근거 경로 및 운영 안내 (`proof_refs` / `spec_refs`):**
- 공개 인수 기록: [p0-reference-acceptance.md](p0-reference-acceptance.md)
- 배포 가드 도구·CI·회귀 검사: [tools/reference_distribution_guard.py](../../tools/reference_distribution_guard.py) · [tests/test_reference_distribution_guard.py](../../tests/test_reference_distribution_guard.py) · [.github/workflows/reference-guard.yml](../../.github/workflows/reference-guard.yml)
- 자체 공개 기준 입력 및 테스트: [examples/owned-design-baseline/README.md](../../examples/owned-design-baseline/README.md) · [manifest.json](../../examples/owned-design-baseline/manifest.json) · [graph.json](../../examples/owned-design-baseline/graph.json) · [tests/test_owned_design_baseline.py](../../tests/test_owned_design_baseline.py)
- 배포·기여 안내: [CONTRIBUTING.md](../../CONTRIBUTING.md) · [docs/guide.md#private-distribution](../guide.md#private-distribution)

**작업 범위와 명령:** 새 계획·manifest·테스트 fixture와 배포 가드만 추가한다. 기존 참고 자료나 인수 파일을 이동·수정하지 않는다.

```sh
python3 -B -m unittest tests.test_design_specialization tests.test_owned_design_baseline tests.test_reference_distribution_guard
python3 -B tools/reference_distribution_guard.py --ref HEAD --format text
python3 -B skills/figma-flow/scripts/graph.py validate examples/owned-design-baseline/graph.json --strict-local
```

**통과 기준:** 실행 전후 기존 자료의 바이트와 파일 수가 바뀌지 않는다. 새 fixture는 기존 자료를 가리키지 않는 독립 입력이다. 이번 기록에 새 기준의 revision과 명령 출력이 연결된다. Design queue 수치는 12 feasible/825 unobserved로 재현되거나, 차이가 나면 차이를 만든 source/receipt와 분류를 설명한다.

<a id="p1-component-families"></a>

### P1. Design component family와 사용자 override 보존 (`p1-native-component-families`)

현재 TEXT·선언 축에서 입력, 선택, Checkbox, Radio, TableRow, TableCell 계열로 확장한다. 디자이너가 같은 계열의 필드 상태와 instance 값을 편집해도 읽기·재생성이 사용자가 바꾼 값을 덮어쓰지 않아야 한다. 현재 실제 main ID·component property 반환 키·target semantic key를 근거로 연결한다. 자동으로 모든 DOM을 컴포넌트화하거나, 선언되지 않은 속성·variant를 추측하지 않는다. [NF-01](NF-01-component-families.md) · [Graph review 스펙](../../specs/graph-review/spec.md)

**역할 우선순위:** 디자이너가 반복 계열을 편집한다. 엔지니어는 typed 값·지원 속성·override를 실제 getter로 대조한다. 기획자는 공개된 상태 명칭과 허용 조합만 검토한다.

**산출물:** 여섯 계열의 제한된 fixture, 선언 schema, source-to-main/instance identity mapping, 속성별 getter receipt, override·rollback 회귀 조건.

**선행 조건:** `p0-reference-safety`, `p0-api-queue-validation` (및 `accepted-narrow-cta-baseline` 확장). API queue의 12 후보는 조사 목록으로 사용하고 해당 속성의 Figma runtime 가용성은 명시적 양성·음성 근거로 판정한다.

**작업 범위와 명령:** 기존 `compile_design`, semantic component 생성 및 선택/CAS 경계를 재사용한다. 기존 테스트 기준을 수정하지 않고, 기존 `metadata` 및 별도 3계열 경로 범위는 건드리지 않는다([P1 공개 인수 영수증](p1-acceptance.md)).

```sh
# 저장소 회귀 검사 및 NF-01 검증:
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_rd04_component_fields.py'
python3 -B -m unittest discover -s tests -p 'test_component_families.py'
python3 -B -m unittest discover -s tests -p 'test_declared_component_properties.py'
python3 -B -m unittest discover -s tests -p 'test_bridge_declared_property_compare.py'
python3 -B -m unittest discover -s tests -p 'test_nf01_app_mapping.py'
python3 -B -m unittest discover -s tests -p 'test_family_provision.py'
python3 -B -m unittest discover -s apps/little-hands/design -p 'test_*.py'
node --test tests/test_semantic_component_reuse.cjs tests/test_graph_token_sync.cjs tests/nf01_component_properties.cjs tests/nf01_semantic_family_runtime.cjs tests/test_family_provision_runtime.cjs tests/test_property_repair_regression.cjs
```

**통과 기준:** 선언된 TEXT·BOOLEAN·INSTANCE_SWAP 각각의 반환 key가 정확한 semantic target에 연결된다. 선언하지 않은 조합은 거절된다. 실제 Figma getter에서 계열 main/instance를 확인하고, instance override 후 재적용해도 해당 값과 관련 없는 레이어가 보존된다. 부분 실패는 이번 작업이 소유한 node만 복구한다.

<a id="p1-causal-history"></a>

### P1. 검토 이력의 원인과 변경 차이 (`p1-causal-review-history`)

기존 History와 dependency view를 다시 만들지 않고, 선택한 실행의 exact task revision·phase·입력 dependency·허용 필드 diff를 읽기 전용 상세 화면에서 연결한다. 이력 간 인과관계를 시각적 위치나 시간 근접성만으로 추정하지 않는다. [NF-03](NF-03-causal-history.md) · [Workspace Activity 스펙](../../specs/workspace-activity/spec.md) · [Workspace Activity 그래프](../../specs/workspace-activity/graph.json) · [Readable Specifications 스펙](../../specs/readable-specifications/spec.md)

**역할 우선순위:** 기획자는 변경 이유와 재검토할 인수 조건을 찾는다. 엔지니어는 어떤 task revision·artifact가 실행에 들어왔는지 확인한다. 디자이너는 같은 graph/native revision에 속한 디자인 차이와 낡은 readback을 구분한다.

**산출물:** bounded operation detail DTO, 실행 상세 UI, 관계를 설명하는 텍스트 목록, stale·legacy·unknown·unavailable 상태, redaction 검사.

**선행 조건:** `p0-reference-safety`의 자료 소유권과 exact revision 기준 (및 `accepted-narrow-cta-baseline` 확장). 기존 canonical journal과 operation ID를 재사용한다.

**작업 범위와 명령:** 새 read-only endpoint와 상세 영역만 만든다. 저장 journal schema, telemetry, 재실행·복구 동작은 바꾸지 않는다. 아래 저장소 회귀 검사·신규 NF-03 검사 및 패키지 build로 검증한다([P1 공개 인수 영수증](p1-acceptance.md)).

```sh
# 저장소 회귀 검사, NF-03 검사 및 빌드:
python3 -B -m unittest discover -s tests -p 'test_rd08_journal_history.py'
python3 -B -m unittest discover -s tests -p 'test_rd08_conflict_detail.py'
python3 -B -m unittest discover -s tests -p 'test_rd03_task_dependencies.py'
python3 -B -m unittest discover -s tests -p 'test_operation_detail.py'
node --test tests/test_workspace_host.cjs tests/test_workspace_activity.cjs tests/nf03_history_detail.cjs tests/test_nf03_panel_ui.cjs
npm --prefix panel-ui run build
```

**통과 기준:** 같은 범위·operation만 읽고, 다른 file/page/runtime이나 바뀐 scope에서는 이전 상세를 지운다. before artifact가 없는 diff는 `unavailable`로 표시하고 내용을 만들어내지 않는다. UI는 키보드로 탐색할 수 있고 색에만 의존하지 않는다. 실행·복구 버튼을 추가하지 않는다.

<a id="p2-production-fixture"></a>

### P2. 권리 정리된 프로덕션 fixture (`p2-rights-cleared-fixture`)

복잡한 UI를 대표할 production-like 입력은 출처·사용 권리·보존 기간이 확인된 별도 fixture로 준비한다. 기존 SaaS 템플릿이나 실제 사용자 문구·이미지를 공개 fixture로 복사하지 않는다. [NF-07](NF-07-web-import-editor-capabilities.md) · [NF-09](NF-09-interactive-web-design.md) · [Editable web 그래프](../../specs/editable-web/graph.json) · [Responsive web 그래프](../../specs/responsive-web/graph.json)

**역할 우선순위:** 기획자는 fixture가 대표하는 사용자 작업과 제외 범위를 승인한다. 디자이너는 실제 프로덕션 비율과 상태를 보되 민감한 원본을 공개하지 않는다. 엔지니어는 출처·권리·hash·계정 정보 제거를 검증한다.

**산출물:** 공개 가능한 fixture, 익명화·민감도 검사, source asset manifest, 생성물과 원본 입력의 별도 보관 기준.

**선행 조건:** `p0-reference-safety`.

**작업 범위와 명령:** 새 독립 fixture와 그 검증만 만든다. 기존 캡처·프로젝트 원본을 변경하지 않는다. `python3 -B -m unittest discover -s tests -p 'test_web_design.py'`를 실행하고 권리·민감도 검사를 추가한다.

**통과 기준:** 원본 계정·세션·개인 문구·외부 전용 이미지가 공개 입력이나 생성 graph에 없다. 허용된 파일만 로드되고 입력 hash와 화면 범위가 receipt에 기록된다. 자동 검사는 권리 승인 자체를 대신하지 않는다.

**실행 계약:** 최소 manifest 형태, 파일 소유, 인수 항목 A1–A8, 상태 승격 규칙은 [p2-wave1-acceptance.md#p2-rights-cleared-fixture](p2-wave1-acceptance.md#p2-rights-cleared-fixture)에 있다. 이 계약은 인수 영수증이 아니다.

<a id="p2-faq-accessibility"></a>

### P2. FAQ mobile·keyboard 접근성 (`p2-faq-mobile-keyboard`)

권리 정리 fixture를 사용해 현재 FAQ의 데스크톱 마우스 사례를 mobile viewport와 실제 키보드 사용으로 확장한다. [NF-09](NF-09-interactive-web-design.md) · [FAQ 범위](../../specs/interactive-web/disclosure.md) · [상호작용 정본 그래프](../../specs/interactive-web/graph.json)

**역할 우선순위:** 기획자는 모든 테스트 상태에서 열기·닫기·전환 결과를 검토한다. 디자이너는 mobile frame의 레이아웃과 편집성을 확인한다. 엔지니어는 `Enter`, `Space`, focus 이동, 접근성 상태와 브라우저·프로토타입 동작 차이를 기록한다.

**산출물:** mobile 캡처, keyboard 동작 graph, 실패·미지원 전이와 스크린리더 수동 검토 checklist.

**선행 조건:** `p2-rights-cleared-fixture` (및 `accepted-narrow-cta-baseline` 확장). CSS 애니메이션이나 실제 외부 페이지 접근을 추가할 경우 별도 사용 권리와 네트워크 범위를 기록한다.

**작업 범위와 명령:** 기존 disclosure compiler와 Design prototype 표현을 확장하되 관측하지 않은 전이를 만들지 않는다. `python3 -B -m unittest discover -s tests -p 'test_web_design.py'`와 `node --test tests/test_web_design.cjs`를 실행한다.

**통과 기준:** 관측한 mobile·keyboard 입력만 graph에 포함한다. 브라우저에서 마우스와 키보드 입력이 같은 목표 상태에 도달하는지 확인한다. 포커스 표시·질문/답변 관계·닫힘 상태를 실제 accessibility tree에서 확인한다. Figma prototype은 웹 접근성 실행 성공으로 보고하지 않는다.

<a id="p2-css-fidelity"></a>

### P2. 복합 CSS·SVG·Canvas·미디어 fidelity (`p2-complex-render-fidelity`)

지원 여부를 CSS 속성 이름 목록으로 선언하지 않는다. 선택된 실제 화면에서 mask/filter, SVG paint/gradient, canvas snapshot, 외부 이미지, video 등 각 미디어 유형을 관측·편집 가능·래스터 대체·미지원으로 나눈다. [NF-04](NF-04-renderer-adapters.md) · [NF-07](NF-07-web-import-editor-capabilities.md) · [웹 캡처 경계](../web-design-capture.md) · [Editable web 그래프](../../specs/editable-web/graph.json) · [Responsive web 그래프](../../specs/responsive-web/graph.json)

**역할 우선순위:** 디자이너는 편집 가능한 결과와 래스터 대체를 구분한다. 엔지니어는 웹 원본·자산 bytes·브라우저 계산값과 Figma getter/export 결과를 대조한다. 기획자는 어떤 상태나 미디어가 근사·제외됐는지 인수 자료에서 확인한다.

**산출물:** 권리 정리 fixture마다 source-to-native mapping, unsupported 목록, asset hash manifest, 실제 픽셀 비교 보고서, 복구 가능한 staged 출력. Canvas와 video를 타임라인·실행 코드로 표현한다고 약속하지 않는다.

**선행 조건:** `p2-rights-cleared-fixture` 및 `p1-native-component-families` (component family가 필요한 consumer 유형은 P1 native component getter 이후 연결). 외부 자산은 로컬 승인 파일과 digest로 고정하고 원격 fetch를 만들지 않는다.

**작업 범위와 명령:** 한 렌더 유형씩 추가하고 기존 import graph·native transaction/rollback을 확장한다. 선택 출력과 bundle 복구를 우선 검증한다. `python3 -B -m unittest discover -s tests -p 'test_web_design.py'`, `node --test tests/test_web_design.cjs`, 그리고 `python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'`를 실행한다.

**통과 기준:** 선택한 fixture의 실제 브라우저와 native 결과만 비교한다. 같은 입력에서 bytes와 output ordering이 결정적이고, 누락·unsupported 유형이 명시되며, stale hash·경로 탈출·쓰기 중단에서 기존 graph와 산출물을 보존한다. 지원하지 않는 CSS를 임의 보정해 일반 지원으로 표시하지 않는다.

<a id="p2-performance-baseline"></a>

### P2. Incremental read 성능 기준선 (`p2-read-performance-baseline`)

최적화 전에 같은 Design 파일·페이지·선택 범위에서 fresh getter를 기준으로 측정한다. cache나 요약 읽기를 완전한 current native state로 승격하지 않는다. [NF-02](NF-02-incremental-native-read.md) · [Design service 관측](../../specs/design-inspection/service-observations.json)

**역할 우선순위:** 엔지니어는 getter 횟수·elapsed time·응답 bytes·완전성 coverage를 측정한다. 디자이너는 변경 전후에 같은 편집 대상과 속성이 표시되는지 확인한다. 기획자는 summary와 full read의 차이를 결과에서 구분한다.

**산출물:** 측정 조건·범위·원본 revision·fresh 결과가 있는 기준선. Summary coverage와 stale 표시의 기존 기대값을 함께 기록한다.

**선행 조건:** `p0-reference-safety`의 독립 측정 입력. measured bottleneck이 확인된 뒤에만 browse cache 구현을 시작한다. 지원 기능 전체를 동시에 읽는 baseline으로 사용하지 않는다.

**작업 범위와 명령:** 기존 summary·coverage·fresh-read 거절 검사를 유지한다. 같은 작업을 여러 번 측정하되 file/page/node/field 범위를 고정한다. 기존 기준은 다음과 같다.

```sh
node --test tests/rd06_fresh_read.cjs tests/rd06_summary_coverage.cjs tests/rd06_reject_partial.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
```

**통과 기준:** 먼저 동일 환경에서 반복한 기준 측정과 분산 범위를 기록한다. 성능 개선 코드가 없으면 이 단계만 완료로 표시하고 최적화 효과는 주장하지 않는다.

**실행 계약:** full discovery 기준 workload의 샘플 형태, 파일 소유, 인수 항목 B1–B9, root 실측 절차는 [p2-wave1-acceptance.md#p2-read-performance-baseline](p2-wave1-acceptance.md#p2-read-performance-baseline)에 있다. 이 계약은 측정 결과가 아니다.

<a id="p2-incremental-read"></a>

### P2. Incremental native read (`p2-incremental-native-read`)

fresh getter와 complete coverage를 기본으로 유지하면서 measured bottleneck에 한해 summary browse를 줄인다. [NF-02](NF-02-incremental-native-read.md) · [Design service 관측](../../specs/design-inspection/service-observations.json)

**선행 조건:** `p2-read-performance-baseline`이 완료되고 적어도 한 병목이 동일한 범위의 반복 측정으로 확인되어야 한다. 기준선이 개선 판단에 쓰이지 않으면 구현을 시작하지 않는다.

**현재 판정:** 기준선은 [인수됐다](p2-wave1-acceptance.md#p2-read-performance-baseline-result). 관측한 full 읽기에서 reader는 end-to-end의 약 8%이고 poll queue 비중이 컸다. reader 병목이 확인되지 않았으므로 착수 조건을 충족하지 않는다. 그래프 규칙상 `next-ready`여도 `proposed`로 둔다.

**작업 범위와 명령:** 미구현 새 검사 제안은 `node --test tests/nf02_summary_cache.cjs`이며, 구현 시 기준선 테스트(`rd06_fresh_read.cjs`, `rd06_summary_coverage.cjs`, `rd06_reject_partial.cjs`)와 함께 실행한다.

**통과 기준:** 최적화 전후로 동일 ID·필드·완전성 결과를 유지한다. coverage가 부족하거나 event 무효화 근거가 불충분하면 `possiblyStale` 또는 명시적 fresh read가 요구된다. 성능 개선은 고정 범위·동일 환경에서만 보고한다.

## 별도 유지보수·호환성·후속 제안

- [NF-05 포크 패치·근거 교환과 개선 러너](NF-05-improvement-runner.md): 개발자 유지보수용 로컬 CLI 제안이며 위 P0–P2 기능 확장 그래프의 선행 순서를 앞지르지 않는다.
- [NF-06 도메인 경계와 버전 전환](NF-06-domain-protocol.md) · [Startup Freshness 스펙](../../specs/startup-freshness/spec.md): 전송/호환 프로토콜 및 런타임 최신성 경계로 별도 추적한다.
- [NF-08 선택적 설치 plugin 경로](NF-08-optional-plugin-routing.md): 핵심 Design 경로와 editor capability matrix 인수 이후 검토하는 선택 기능이다.
- 관련 기존 품질·회귀 계약: [Pre-Figma Quality 스펙](../../specs/pre-figma-quality/spec.md) · [다중 페이지 회귀 계획](../../specs/regression-program/plan.md)

## 병렬화와 종료 순서

P0가 기준 입력·queue 인벤토리·근거 저장 범위를 먼저 고정한다. 그 뒤 P1 component family와 causal history는 소유 파일을 분리해 병렬 탐색할 수 있다. 같은 파일의 최종 수정은 한 writer가 순차로 통합한다. P2에서 권리 정리 fixture와 모바일/키보드 FAQ는 병렬 준비할 수 있다. complex CSS mapping은 `p1-native-component-families`의 native component getter가 필요할 때까지 기다린다. Incremental read 구현은 `p2-read-performance-baseline` 측정을 통과하기 전에 시작하지 않는다.

각 단계는 코드 작성, 자동 검사, 실제 브라우저/Figma 관측, 제품 수용을 구별해 기록한다. 임시 fixture 검사 통과는 실제 Figma runtime 증거가 아니며, Figma readback은 브라우저 접근성 결과가 아니다. 이 계획은 후보 릴리스 상태를 현재 설치 상태로 단정하지 않는다. 게시된 버전과 실제 설치·로드는 각각 해당 release 증거와 호스트 readback으로 확인한다.
