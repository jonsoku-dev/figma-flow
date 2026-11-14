# P2 1차 실행 계약 (`p2-rights-cleared-fixture` · `p2-read-performance-baseline`)

이 문서는 P2 1차 두 작업의 실행 계약과 인수 경계다. 인수 영수증이 아니다. 두 작업의 현재 상태(`status` · `evidence_status`)와 선행 관계의 정본은 [backlog.graph.json](backlog.graph.json)이며, 범위·역할·통과 기준의 원문은 [capability-review.md](capability-review.md)의 해당 절이다. 이 문서는 구현 완료, 실제 브라우저·Figma 결과 또는 성능 수치를 주장하지 않는다.

- **착수 근거:** 두 작업은 각자의 유일한 `depends-on` 선행 노드 `p0-reference-safety`가 `verified`라서 `next-ready`였다. 착수 후 두 노드는 `in-progress`이고 `evidence_status`는 `pending-root-live-evidence`다.
- **후속 노드:** `p2-faq-mobile-keyboard`, `p2-complex-render-fidelity`, `p2-incremental-native-read`는 `proposed`로 남는다. 각 선행 작업이 `verified`가 되기 전에는 `next-ready`가 아니다.
- **그래프 검사:** `python3 -B -m unittest tests.test_next_roadmap_backlog`. `in-progress` 작업은 모든 `depends-on` 선행이 충족돼야 하고, 충족 상태의 근거 표시(`verified*` 등)를 가질 수 없다.

## 의존성 그래프

```text
p0-reference-safety (verified)
├── p2-rights-cleared-fixture (in-progress)
│   ├── p2-faq-mobile-keyboard (proposed)
│   └── p2-complex-render-fidelity (proposed; p1-native-component-families도 선행)
└── p2-read-performance-baseline (in-progress)
    └── p2-incremental-native-read (proposed)
```

두 1차 작업은 서로 의존하지 않는다. 서로의 파일을 기다리지 않는다. 측정 입력은 P0의 자체 입력([owned-design-baseline](../../examples/owned-design-baseline/README.md)) 또는 P1의 자체 예제([owned-component-families](../../examples/owned-component-families/README.md))를 쓴다. 따라서 성능 기준선은 새 fixture의 완료를 기다리지 않는다.

<a id="file-ownership"></a>

## 파일 소유

한 파일은 한 writer만 바꾼다. 아래 경로 중 기준 커밋 `9962afa`에 있는 것은 없다. 경로가 있다는 사실만으로 구현이나 인수를 뜻하지 않는다.

| 작업 | writer | 소유 경로 |
|---|---|---|
| `p2-rights-cleared-fixture` | fixture writer | `examples/owned-production-workspace/**`, `tests/test_owned_production_workspace.py`, `tools/owned_production_workspace.py` |
| `p2-read-performance-baseline` | baseline writer | `tools/native_read_benchmark.py`와 그 전용 새 검사, [NF-02](NF-02-incremental-native-read.md)의 측정 기록 부록 |
| 두 작업의 기록 | records writer | `docs/next-roadmap/backlog.graph.json`, `capability-review.md`, `README.md`, 이 문서, `tests/test_next_roadmap_backlog.py`, `CHANGELOG.md`, `docs/llm-wiki/` |

fixture·baseline writer는 그래프, CHANGELOG, Wiki를 바꾸지 않는다. 두 writer 모두 코어 캡처·컴파일러·플러그인, 기존 `examples/owned-design-baseline/`·`examples/owned-component-families/`, 패널 UI, `figma-bridge/assets/panels.js`, `docs/development-roadmap/RD-06-native-read/tasks.md`를 바꾸지 않는다. 범위 밖 파일이 필요하면 변경 전에 root에 보고한다.

## 공통 경계

- Design 전용이다. 개발 플러그인의 일반 UI와 로컬 명령을 사용한다. 공식 Figma MCP, Computer Use 세션, hook을 사용하지 않는다.
- 기존 참고 아카이브, 원본, 보존 사본, 기존 인수 파일의 바이트를 바꾸지 않는다. 원본 사용자 템플릿을 공개 파일로 복사하거나 이름·경로로 가리키지 않는다.
- 동결된 독립 검사(`tests/rd06_fresh_read.cjs`, `tests/rd06_summary_coverage.cjs`, `tests/rd06_reject_partial.cjs`, `tests/test_graph_sync.py`, `tools/reference_distribution_guard.py`)의 Git blob과 모드를 바꾸지 않는다. 새 동작은 새 검사에 둔다.
- 원시 브라우저·Figma 응답, 캡처, 측정 로그는 Git 밖에 둔다. 공개 문서에는 digest, 수치, 범위, 판정만 쓴다. 개인 절대 경로, 계정, 토큰, 원시 Figma file/page/node ID를 넣지 않는다.
- 자동 검사 통과는 실제 브라우저·Figma 관측이 아니다. 실제 관측은 통합 담당(root)이 통합된 소스에서 수행한다.
- 다음을 주장하지 않는다. 법률 검토나 법적 권리 확인, writer 보고만으로 얻은 브라우저·Figma 성공, 비교 가능한 측정 없는 속도 향상, 후속 노드(FAQ 키보드, 복합 렌더 fidelity, browse 캐시)의 인수.

<a id="status-promotion"></a>

## 상태 승격 규칙

`in-progress`에서 `verified`로 바꾸려면 다음이 모두 있어야 한다.

1. 구현 소스가 `main`에 통합되고, 그 전체 커밋 SHA가 이 문서와 노드의 `observed_evidence`에 기록된다.
2. 아래 작업별 인수 항목마다 판정과 근거가 있다. 미관측 항목이 하나라도 있으면 `in-progress`를 유지하거나 `blocked`로 바꾸고 이유를 적는다.
3. 노드의 `proof_refs`가 저장소에 실존하는 공개 파일만 가리킨다. 그래프 검사가 이를 강제한다.
4. 실제 브라우저·Figma 결과는 root가 직접 관측한 값이다. 하위 작업자의 보고나 과거 실행 수치로 대신하지 않는다.

<a id="p2-rights-cleared-fixture"></a>

## A. 권리 정리 fixture (`p2-rights-cleared-fixture`)

계약 원문은 [capability-review.md#p2-production-fixture](capability-review.md#p2-production-fixture)다. 그래프 인수는 세 줄이다. 실제 계정과 비공개 원문을 게시하지 않는다. 승인된 자산만 읽는다. 입력·출력 digest를 기록한다. 목적은 이후 FAQ mobile·keyboard와 복합 렌더 fidelity가 공유할 production-like 공개 입력이다.

### 최소 데이터 형태

새 manifest는 새 schema ID를 쓴다. [owned-design-baseline manifest](../../examples/owned-design-baseline/manifest.json)(`figma-flow-owned-design-baseline-manifest-v1`)에는 파일별 digest가 없으므로 그 schema 문자열을 재사용하지 않는다. 대신 그 manifest의 `ownership`, `external_reference_policy`, 세 artifact layer(`reference-input`, `owned-public-baseline`, `generated-private-output`)를 이어서 쓴다.

`files[]`의 각 항목은 공개 파일 하나다.

| 필드 | 내용 |
|---|---|
| `path` | fixture 디렉터리 기준 상대 경로. 절대 경로, `..`, 백슬래시, NUL이 없다 |
| `role`, `layer` | 파일 역할과 세 layer 중 하나 |
| `ownership`, `license`, `license_path` | `repo-authored`, `MIT`, 저장소 `LICENSE` |
| `sharing_scope` | 공개 소스는 `public`, 내부 계약 참조만 `public-contract-only` |
| `retention` | 공개 소스는 Git에 남는 저장소 수명. 캡처·컴파일 graph·native plan·readback은 `private-evidence-untracked`. 달력 기준 보존 일수를 새로 만들지 않는다 |
| `sha256` | 파일 bytes의 SHA-256 |

허용 목록은 `files[].path`의 집합이다. 디렉터리 나열이 아니다. 정본은 fixture의 `graph.json` 하나다. 의미 ID, 문구, 화면, 상태, 액션, 디자인 값, 접근 가능한 이름을 이 그래프가 가진다. 렌더러 파일은 이 문자열을 다시 적지 않는다. 정규 투영은 기존 `review_graph.project_graph`를 쓴다.

비공개 receipt는 Git 밖에 둔다. 입력 manifest SHA-256, 파일별 SHA-256, 그래프 화면 ID, 선언한 데스크톱·모바일 크기, 생성물 SHA-256을 가진다.

외부 래스터, 폰트 파일, 제3자 자산은 `repo-authored`로 넣지 않는다. 이번 fixture는 저장소에서 직접 만든 파일만 쓴다.

### 인수 항목

| ID | 기준 | 근거 |
|---|---|---|
| A1 | manifest의 모든 `sha256`이 실제 파일 bytes와 같고, 디렉터리의 모든 공개 파일이 manifest에 있다 | `tests/test_owned_production_workspace.py` |
| A2 | `tools/owned_production_workspace.py`는 열기 전에 경로 문법 위반, 일반 파일이 아닌 항목(symlink 포함), fixture 밖으로 해석되는 경로, manifest에 없는 경로, 선언과 다른 bytes, 텍스트의 외부 URL(SVG namespace 제외)을 거절한다 | 같은 검사의 거절 사례 |
| A3 | 공개 입력과 생성 graph에 실제 계정·세션·개인 문구·외부 전용 이미지가 없다 | `python3 -B tools/reference_distribution_guard.py --ref HEAD --format text` clean, 새 민감도 검사 |
| A4 | 입력 digest, 출력 graph digest, 화면 범위가 receipt에 기록된다 | 공개 요약에는 digest와 범위만 쓴다 |
| A5 | 기존 참고 자료와 보존 사본의 bytes·파일 수가 변하지 않는다 | P0 보존 대조 재실행 |
| A6 | 실제 브라우저에서 fixture를 열 때 허용 파일 밖 요청과 외부 네트워크 요청이 0건이다 | root의 격리 브라우저 관측 |
| A7 | 대표 작업과 제외 범위를 기획자 역할이 승인한 기록이 있다. 이 기록과 자동 검사는 법률 검토가 아니다 | 사람의 승인 기록 |
| A8 | 공개 트리에 캡처 PNG, compiled plan, 파일 키, 페이지 ID가 없다 | 새 fixture 검사, 배포 가드 |

### 명령

```sh
python3 -B -m unittest tests.test_design_specialization
python3 -B -m unittest discover -s tests -p 'test_web_design.py'
python3 -B tools/reference_distribution_guard.py --ref HEAD --format text
```

`test_web_design.py`는 비회귀 검사다. 새 허용 목록을 검사하지 않는다. 새 fixture 검사 명령은 구현 커밋이 통합된 뒤 노드의 `commands`에 추가한다. 존재하지 않는 검사를 미리 등록하지 않는다. 화면이나 모바일 레이아웃이 fixture에 있다는 사실로 `p2-faq-mobile-keyboard`나 `p2-complex-render-fidelity`를 통과시키지 않는다.

<a id="p2-read-performance-baseline"></a>

## B. Fresh read 성능 기준선 (`p2-read-performance-baseline`)

계약 원문은 [capability-review.md#p2-performance-baseline](capability-review.md#p2-performance-baseline)이고, 설계 배경은 [NF-02](NF-02-incremental-native-read.md)다. 이 작업은 측정만 한다. 캐시나 최적화 코드를 넣지 않는다.

### 최소 데이터 형태

측정 대상은 `figma-bridge/native_semantic_read.js`의 `readNativeSemantics`다. 기준 트리의 reader blob은 `57aa184daa152843fe5954d69586ecaf16c580a4`, 플러그인 버전은 `0.35.0`이다. 계측은 함수 시그니처나 반환값에 넣지 않는다. 러너가 호출 밖에서 시간을 잰다.

워크로드는 두 개다. 둘의 차이를 개선으로 적지 않는다.

- `readNativeSemantics-full`. `readNativeSemantics(figma, page)` 호출 하나다.
- `readNativeSemantics-summary-default`. 패널 기본 요청과 같은 `profile: "summary"`, 그 페이지의 노드 ID, `fields: ["width", "height"]`다. 반환 schema가 `figma-flow-native-read-summary-v1`이 아니면 summary 샘플이 아니다.

export, sync, discovery 전체 경로는 이 두 워크로드가 아니다. 재야 하면 셋째 이름으로 분리한다. `compareNativeReadProfiles` 한 번은 네 번 읽으므로 샘플 1회로 쓰지 않는다.

샘플 한 건의 필드:

| 필드 | 내용 |
|---|---|
| `source_commit`, `reader_blob`, `plugin_version` | 측정한 통합 소스와 실제 로드본 |
| `workload` | 위 두 이름 중 하나 |
| `file_id`, `page_id`, `node_ids`, `fields` | 범위. ID는 비공개 기록에만 둔다. 공개 요약에는 digest와 노드 수만 쓴다 |
| `profile_requested`, `schema_returned` | 요청 profile과 반환 schema |
| `reader_elapsed_ms` | `readNativeSemantics` await 시간만 |
| `end_to_end_elapsed_ms` | 같은 워크로드의 host 왕복. 전송·직렬화 포함, 진단 ledger 제외 |
| `bytes` | 기존 `utf8JsonBytes`로 잰 그 읽기 결과 |
| `coverage_complete` | summary는 false. full은 coverage 객체가 없다는 표시 |
| `content_sha256` | 비교용 정규 JSON의 SHA-256 |
| `getter_count` | 시간 샘플에서는 null |
| `failures`, `timeouts`, `retries` | 실패를 지우지 않는다 |
| `execution` | `unit-mock` 또는 `root-live` |

getter 수는 별도 진단 회차에서 `nativeReadGetterLedger`(`figma-flow-native-read-ledger-v1`)로 얻는다. ledger는 노드 속성의 첫 읽기를 `nodeId.property`로 한 번만 기록한다. 호출 횟수나 API 호출 수가 아니다. 진단 회차는 시간 샘플 밖에 둔다.

### 인수 항목

| ID | 기준 | 근거 |
|---|---|---|
| B1 | 한 워크로드의 모든 샘플에서 범위와 요청 필드가 같다 | 기록 대조 |
| B2 | 같은 환경에서 워크로드마다 `root-live` 샘플이 5건 이상이다 | root의 실제 Figma 측정 |
| B3 | 다섯 샘플의 `content_sha256`이 같다. 갈라지면 median을 만들지 않고 드리프트 실패로 센다 | 기록 대조 |
| B4 | 각 시계는 median, 최소, 최대만 보고한다. 평균을 개선율로 바꾸지 않는다. 실패·시간 초과를 빼거나 성공할 때까지 재시도한 결과만 남기지 않는다 | 기록 대조 |
| B5 | summary 결과를 full 근거나 complete로 적지 않는다. `requireFullNativeRead`가 summary를 거절한다 | 기존 RD-06 검사 |
| B6 | 동결된 RD-06 검사와 `test_graph_sync.py`가 blob 변경 없이 통과한다 | 아래 명령, blob 대조 |
| B7 | `unit-mock` 샘플이나 ledger 길이를 `root-live` 값으로 적지 않는다 | 기록 대조 |
| B8 | 속도 향상을 주장하지 않는다. NF-02의 과거 실행 수치는 이 기준선에 쓰지 않는다 | 문서 검토 |
| B9 | 병목을 측정으로 확인하지 못하면 `p2-incremental-native-read`를 시작하지 않는다 | 그래프 상태 |

### 명령

```sh
node --test tests/rd06_fresh_read.cjs tests/rd06_summary_coverage.cjs tests/rd06_reject_partial.cjs
node --test tests/rd06_full_getter_ledger.cjs tests/rd06_read_comparison.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
```

이 명령은 저장소 fixture 기준만 확인한다. 실제 Figma 지연이나 대형 문서의 동작을 보여 주지 않는다. 실제 측정값은 root가 개발 플러그인으로 등록된 테스트 페이지에서 얻는다. 기본은 호출부 수정 없음이다. RD-06 검사는 `code.js`, `native_edit.js`, `tools/graph_sync.py`, 패널 소스의 호출 문자열을 고정하므로 이 파일들을 바꿔야 하면 변경 전에 root에 보고한다.

## Root 실측 절차

root는 두 작업의 구현이 `main`에 통합된 뒤 다음을 수행하고 결과를 이 문서와 그래프에 기록한다.

1. 통합 소스의 SHA를 고정하고, 설치·로드된 개발 플러그인의 runtime generation이 그 소스와 같은지 확인한다.
2. A6. 격리 브라우저에서 새 fixture를 열고 요청 목록을 저장한다. 허용 목록 밖 요청과 외부 요청 수를 센다.
3. B2. 로드된 reader blob과 플러그인 버전을 샘플에 적는다. 기준 트리와 다르면 이 트리의 측정으로 보고하지 않는다. 등록된 Design 테스트 페이지에서 워크로드마다 같은 범위의 fresh read를 5회 이상 실행한다. 샘플과 별도 진단 ledger를 Git 밖에 저장한다.
4. 공개 요약만 이 문서에 쓰고, 노드의 `observed_evidence`·`proof_refs`·`evidence_status`를 갱신한다. 그다음 `python3 -B -m unittest tests.test_next_roadmap_backlog`를 실행한다.
5. 관측하지 못한 항목은 미관측으로 남긴다. 그 작업은 `verified`로 바꾸지 않는다.
