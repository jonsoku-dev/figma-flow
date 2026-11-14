# P2 1차 실행 계약 (`p2-rights-cleared-fixture` · `p2-read-performance-baseline`)

이 문서는 P2 1차 두 작업의 실행 계약과 인수 경계다. `p2-read-performance-baseline`의 인수 결과는 [B 인수 결과](#p2-read-performance-baseline-result)에 있다. `p2-rights-cleared-fixture`는 아직 인수 영수증이 없다. 두 작업의 현재 상태(`status` · `evidence_status`)와 선행 관계의 정본은 [backlog.graph.json](backlog.graph.json)이며, 범위·역할·통과 기준의 원문은 [capability-review.md](capability-review.md)의 해당 절이다. 인수 결과 절 밖의 내용은 구현 완료, 실제 브라우저·Figma 결과 또는 성능 수치를 주장하지 않는다.

- **착수 근거:** 두 작업은 각자의 유일한 `depends-on` 선행 노드 `p0-reference-safety`가 `verified`라서 `next-ready`였다.
- **현재 상태:** `p2-read-performance-baseline`은 `verified`다. `p2-rights-cleared-fixture`는 `in-progress`(`pending-root-live-evidence`)다.
- **후속 노드:** `p2-faq-mobile-keyboard`와 `p2-complex-render-fidelity`는 fixture가 `verified`가 되기 전에는 `next-ready`가 아니다. `p2-incremental-native-read`는 그래프 규칙상 `next-ready`지만 `proposed`로 남는다. 이번 기준선의 관측 병목은 reader가 아니라 poll queue이므로 [착수 조건](capability-review.md#p2-incremental-read)을 충족하지 않는다.
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

한 파일은 한 writer만 바꾼다. 신규 경로는 기준 커밋 `9962afa`에 없던 파일이다. 기존 경로는 그 커밋에 있던 파일이며 아래 조건 안에서만 바꾼다. 경로가 있다는 사실만으로 구현이나 인수를 뜻하지 않는다.

| 작업 | writer | 신규 경로 | 기존 경로 |
|---|---|---|---|
| `p2-rights-cleared-fixture` | fixture writer | `examples/owned-production-workspace/**`, `tools/owned_production_workspace.py`, `tests/test_owned_production_workspace*.py` | 없음 |
| `p2-read-performance-baseline` | baseline writer | `figma-bridge/native_read_measurement.js`, `tools/native_read_benchmark.py`, `tests/p2_native_read_*.cjs`, `tests/test_native_read_benchmark*.py` | `figma-bridge/native_semantic_read.js`의 공유 `utf8JsonBytes`, `tools/graph_sync.py`·`tools/figma_workspace.py`의 최소 discovery 호출부, [NF-02](NF-02-incremental-native-read.md)의 측정 기록 부록 |
| 두 작업의 기록 | records writer | 이 문서 | `docs/next-roadmap/backlog.graph.json`, `capability-review.md`, `README.md`, `tests/test_next_roadmap_backlog.py`, `CHANGELOG.md`, `docs/llm-wiki/`, 공식 generator 출력인 `library/figma-api/coverage-baseline.json` |

fixture·baseline writer는 그래프, CHANGELOG, Wiki를 바꾸지 않는다. fixture writer는 코어 캡처·컴파일러·플러그인을 바꾸지 않는다. 두 writer 모두 기존 `examples/owned-design-baseline/`·`examples/owned-component-families/`, 패널 UI, `figma-bridge/assets/panels.js`, `docs/development-roadmap/RD-06-native-read/tasks.md`를 바꾸지 않는다.

baseline writer의 기존 파일 변경은 다음 계측 조건을 모두 지킨다.

- 기본 경로는 그대로다. flag 없이 호출하면 `readNativeSemantics`와 discovery 호출부의 시그니처, 반환값, 읽는 getter가 기준 커밋과 같다.
- 실기에서 드러난 결함은 기존 공유 함수를 최소로 고친다. Figma 플러그인 VM에는 `TextEncoder`가 없으므로 공유 `utf8JsonBytes`를 고칠 수 있다. 새 전역 polyfill이나 중복 helper는 만들지 않는다. 이 경우 `native_semantic_read.js`의 파일 blob은 바뀌지만, `readNativeSemantics` 본문과 full 필드 범위는 기준과 같아야 한다.
- 계측은 명시적 선택 flag를 줄 때만 동작한다.
- 동결된 RD-06 검사와 `tests/test_graph_sync.py`가 blob·모드 변경 없이 통과한다.

Native 조작, 패널 UI 조작, 원본 작업 페이지의 실제 실행은 root만 한다. 범위 밖 파일이 필요하면 변경 전에 root에 보고한다.

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
| A2 | `tools/owned_production_workspace.py`는 열기 전에 경로 문법 위반, 일반 파일이 아닌 항목(symlink 포함), fixture 밖으로 해석되는 경로, manifest에 없는 경로, 선언과 다른 bytes, 텍스트의 외부 URL(scheme-relative `//` URI 포함, SVG namespace 제외)을 거절한다. 검증한 manifest의 한 번 파싱한 결과로 서빙 목록을 정하고, 검증 뒤 manifest를 다시 파싱해 목록을 바꾸지 않는다 | 같은 검사의 거절 사례 |
| A3 | 공개 입력과 생성 graph에 실제 계정·세션·개인 문구·외부 전용 이미지가 없다 | `python3 -B tools/reference_distribution_guard.py --ref HEAD --format text` clean, 새 민감도 검사 |
| A4 | 입력 digest, 출력 graph digest, 화면 범위가 receipt에 기록된다 | 공개 요약에는 digest와 범위만 쓴다 |
| A5 | 기존 참고 자료와 보존 사본의 bytes·파일 수가 변하지 않는다 | P0 보존 대조 재실행 |
| A6 | 실제 브라우저에서 fixture를 열 때 허용 파일 밖 요청과 외부 네트워크 요청이 0건이다 | root의 격리 브라우저 관측 |
| A7 | 사용 근거를 기록한다. 현재 사용자의 P2 진행 승인, 모든 파일의 저장소 자체 저작, 저장소 MIT 라이선스가 근거다. 이 근거 외에 새 인간 승인을 요구하지 않는다. 제3자 권리는 자동 검사만으로 인정하지 않으므로 제3자 자산을 넣지 않는다. 이 기록과 자동 검사는 법률 검토가 아니다 | manifest `ownership`, 승인 범위 기록 |
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

라이브 기준선은 고정 범위의 fresh full discovery 읽기 하나다. 기본 discovery 경로가 flag 없이 수행하는 full `readNativeSemantics(figma, page)` 읽기이며, 기본 호출의 시그니처와 반환값에는 계측을 넣지 않는다.

기준 커밋 `9962afa`의 reader blob은 `57aa184daa152843fe5954d69586ecaf16c580a4`, 플러그인 버전은 `0.35.0`이었다. 공유 `utf8JsonBytes` 수정 뒤에는 파일 blob이 달라진다. 그래서 기준선은 측정한 통합 소스의 실제 reader blob을 핀으로 쓰고, 파일 전체가 기준과 byte 단위로 같다고 주장하지 않는다. 같다고 확인한 것은 `readNativeSemantics` 본문과 full 필드 범위다. 이전에 확인한 byte 동일성은 그때 비교한 두 소스 사이에서만 유효하며 최종 코드로 넓히지 않는다. 생성된 API baseline과 recipe helper는 최종 소스를 받은 뒤 공식 generator로만 갱신한다.

| 이름 | 뜻 | 보고 방식 |
|---|---|---|
| `discovery-full-default` | 유일한 기준 workload. flag 없는 fresh full discovery | 시간 통계의 기준 |
| `discovery-full-timed` | 같은 full 읽기에 선택 flag 계측을 붙인 회차. 기본과의 차이는 관측 overhead다 | overhead 판정에만 쓴다. 둘째 profile이나 속도 차이가 아니다 |
| 진단 counts | median 밖 진단 회차의 getter·API 접근 수 | 시간 통계와 다른 단위로 따로 표시한다 |

summary profile의 라이브 성능은 이번 범위에서 측정하지 않는다. 단위 mock 결과는 상한일 뿐이다. summary 수치나 reader 시간의 end-to-end 비중을 `p2-incremental-native-read`(browse 캐시)의 성능 근거나 최적화 효과로 쓰지 않는다. `compareNativeReadProfiles` 한 번은 네 번 읽으므로 샘플 1회로 쓰지 않는다.

샘플 한 건의 필드:

| 필드 | 내용 |
|---|---|
| `source_commit`, `reader_blob`, `plugin_version` | 측정한 통합 소스와 실제 로드본 |
| `workload` | `discovery-full-default` 또는 `discovery-full-timed` |
| `file_id`, `page_id`, `node_ids` | 범위. ID는 비공개 기록에만 둔다. 공개 요약에는 digest와 노드 수만 쓴다 |
| `reader_elapsed_ms` | reader await 시간. 계측 회차에만 있다 |
| `end_to_end_elapsed_ms` | 러너 시계로 잰 host 왕복. 전송·직렬화 포함, 진단 회차 제외 |
| `bytes` | 공유 `utf8JsonBytes`로 잰 그 읽기 결과. 값은 결과 JSON의 UTF-8 길이와 같다 |
| `coverage_complete` | discovery 결과에는 coverage 객체가 없으므로 `null`. `true`로 추정하지 않는다 |
| `content_sha256` | 관측 시각과 계측 필드를 뺀 정규 JSON의 SHA-256 |
| `getter_count` | 시간 샘플에서는 `null` |
| `attempt`, `outcome` | 계획 순번과 결과(`ok`, `failure`, `timeout`, `retry`, `drift`). 모든 시도를 남긴다 |
| `execution` | `unit-mock` 또는 `root-live` |

진단 counts는 그 회차가 정한 단위를 따른다. 반복 속성 접근과 API 호출 횟수를 세면, `nativeReadGetterLedger`(`figma-flow-native-read-ledger-v1`)의 고유 `nodeId.property` 접근 수와 다른 단위다. 두 값을 섞지 않는다. reader 안의 counts와 discovery가 reader 뒤에 하는 stroke·글꼴 조회도 구분한다. 진단 회차는 시간 샘플 밖에 두고, 보고할 때는 같은 scope 핀(범위 digest, reader blob)을 함께 적는다.

기록은 네 가지를 구분한다. native getter 접근(진단 counts), reader 시계(`reader_elapsed_ms`), 전송을 포함한 host 왕복(`end_to_end_elapsed_ms`), 저장소 fixture 파이프라인(`unit-mock`)이다. 한 값을 다른 값으로 바꿔 쓰지 않는다.

### 인수 항목

| ID | 기준 | 근거 |
|---|---|---|
| B1 | 같은 환경에서 workload마다 같은 scope의 `root-live` 시도를 5회 이상 미리 계획하고, 모든 시도를 순번대로 보존한다. 실패, 시간 초과, 재시도, drift를 조용히 빼거나 성공한 5건만 고르지 않는다 | root의 실제 Figma 측정, 시도 기록 |
| B2 | 계획한 시도 중 실패가 있거나, 범위가 바뀌거나, 요청한 file·page와 readback의 file·page가 다르거나, `content_sha256`이 갈라지면 통계를 만들지 않고 실패, 비교 불가 또는 판정 불가로 보고한다 | 기록 대조 |
| B3 | discovery full의 coverage 부재를 `true`로 추정하지 않는다. summary 결과를 full 근거로 적지 않으며 `requireFullNativeRead`가 summary를 거절한다 | 기록 대조, 기존 RD-06 검사 |
| B4 | 기준 workload의 각 시계는 median, 최소, 최대만 보고한다. 평균을 개선율로 바꾸지 않는다. `discovery-full-timed`와의 차이는 관측 overhead로만 적는다 | 기록 대조 |
| B5 | 시간 샘플의 `getter_count`는 `null`이다. 진단 counts는 같은 scope 핀과 함께 별도 단위로 표시한다. 진단 회차가 실패하면 getter 수가 기록되지 않았으므로 그 실측은 인수하지 않고, 시간 샘플이 모두 성공해도 성공으로 보고하지 않는다 | 기록 대조 |
| B6 | 동결된 RD-06 검사와 `test_graph_sync.py`가 blob 변경 없이 통과한다 | 아래 명령, blob 대조 |
| B7 | `unit-mock` 샘플이나 ledger 길이를 `root-live` 값으로 적지 않는다 | 기록 대조 |
| B8 | 속도 향상을 주장하지 않는다. NF-02의 과거 실행 수치와 측정하지 않은 summary profile을 이 기준선이나 후속 캐시의 근거로 쓰지 않는다 | 문서 검토 |
| B9 | 병목을 측정으로 확인하지 못하면 `p2-incremental-native-read`를 시작하지 않는다 | 그래프 상태 |

### 명령

```sh
node --test tests/rd06_fresh_read.cjs tests/rd06_summary_coverage.cjs tests/rd06_reject_partial.cjs
node --test tests/rd06_full_getter_ledger.cjs tests/rd06_read_comparison.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
```

baseline 구현의 새 검사(측정 단위 검사와 러너 검사)는 통합된 뒤 노드의 `commands`에 추가한다. 이 명령은 저장소 fixture 기준만 확인한다. 실제 Figma 지연이나 대형 문서의 동작을 보여 주지 않는다. 실제 측정값은 root가 개발 플러그인으로 등록된 테스트 페이지에서 얻는다. 호출부 변경은 [파일 소유](#file-ownership)의 선택 flag 범위에 한한다. RD-06 검사는 `code.js`, `native_edit.js`, `tools/graph_sync.py`, 패널 소스의 호출 문자열을 고정하므로 기본 경로의 문자열을 유지한다.

<a id="p2-read-performance-baseline-result"></a>

### B 인수 결과

root가 통합 소스 `3b3fa8f`에서 실측했고, 독립 검토가 저장된 샘플 11건 전체를 다시 계산해 보고서·공개 요약과 같음을 확인했다. 작업 트리는 깨끗했고 플러그인 버전은 `0.35.0`이다. `readNativeSemantics` 본문은 기준 `9962afa`와 같다. 범위는 1개 페이지, 108개 노드, profile `full`이다. 원시 file·page·node ID와 샘플은 Git 밖 비공개 증거에 있다.

| ID | 결과 | 판정 |
|---|---|---|
| B1 | `discovery-full-default` 5/5, `discovery-full-timed` 5/5, 진단 1/1 성공. 재시도 0, 시간 초과 0 | 충족 |
| B2 | 11건 모두 요청 file·page와 readback file·page, 노드 108개가 같다. `content_sha256` 1개 | 충족 |
| B3 | 10건 모두 `coverage.complete` `null`, `reported` false, `unavailable_fields` 1,964. summary는 측정하지 않았다 | 충족 |
| B4 | 기본 end-to-end median 976.19 ms(512.39–1,129.87, n=5). timed와 범위가 겹치므로 차이는 관측 overhead로만 적는다 | 충족 |
| B5 | 시간 샘플의 `getter_count`는 `null`. 진단 counts는 속성 get 10,969회, has 6,288회다. 진단 회차는 성공했다 | 충족 |
| B6 | 동결 검사 5개의 blob·모드가 측정 소스에서 기준과 같다 | 충족 |
| B7 | 실행은 `root-live`뿐이다 | 충족 |
| B8 | 속도 향상, summary 성능, 캐시 효과를 주장하지 않는다 | 충족 |
| B9 | timed reader median 80 ms(77–85, `Date.now` 1 ms 해상도), end-to-end의 약 8%. queue median은 timed 627.55 ms, 기본 605.86 ms다. 이 full 읽기의 사용자 대기에서는 poll queue 비중이 크다. reader 병목이 아니므로 `p2-incremental-native-read`를 시작하지 않는다 | 충족 |

stage가 다른 bytes를 구분한다. reader가 만든 compact JSON은 438,955 bytes이고, 저장된 readback은 263,238 bytes다.

한계. 로드된 편집기 상태만 관측했다. Figma UI에 cloud sync 경고가 보였고 cloud 동기화는 검증하지 않았다. 대형 문서 동작을 대표하지 않는다. 기존 P1 작업 기록 101개와 native component family 상태는 바뀌지 않았다. live-001은 진단 실패로 거절했고, diagnostic v2의 `TextEncoder` 실패도 이력으로 보존한다.

통합 커밋. 측정 계약 `8e3bb31`, 선택 계측 `10e221f`, 러너 `5d068b0`, 진단 요구 `9c4e787`, 진단 수정 `a5e4a09`, sandbox 기준 `24f34f9`, UTF-8 bytes 수정 `3b3fa8f`, coverage baseline `9669bc5`.

## Root 실측 절차

root는 두 작업의 구현이 `main`에 통합된 뒤 다음을 수행하고 결과를 이 문서와 그래프에 기록한다.

1. 통합 소스의 SHA를 고정하고, 설치·로드된 개발 플러그인의 runtime generation이 그 소스와 같은지 확인한다. 소스 작업 트리에 커밋되지 않은 변경이 있으면 그 측정은 판정 불가다.
2. A6. 격리 브라우저에서 새 fixture를 열고 요청 목록을 저장한다. 허용 목록 밖 요청과 외부 요청 수를 센다.
3. B1–B5. 로드된 reader blob과 플러그인 버전을 샘플에 적는다. 측정한 통합 소스의 blob과 다르면 그 소스의 측정으로 보고하지 않는다. 등록된 Design 테스트 페이지에서 `discovery-full-default`와 `discovery-full-timed`를 각각 같은 범위로 5회 이상 실행한다. 성공 여부와 관계없이 모든 시도와 별도 진단 ledger를 Git 밖에 저장한다.
4. 공개 요약만 이 문서에 쓰고, 노드의 `observed_evidence`·`proof_refs`·`evidence_status`를 갱신한다. 그다음 `python3 -B -m unittest tests.test_next_roadmap_backlog`를 실행한다.
5. 관측하지 못한 항목은 미관측으로 남긴다. 그 작업은 `verified`로 바꾸지 않는다.
