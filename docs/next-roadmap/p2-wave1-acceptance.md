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

두 1차 작업은 서로 의존하지 않는다. 소유 파일을 나눠 병렬로 진행할 수 있다. 측정 입력은 P0의 자체 입력([owned-design-baseline](../../examples/owned-design-baseline/README.md)) 또는 P1의 자체 예제([owned-component-families](../../examples/owned-component-families/README.md))를 쓴다. 따라서 성능 기준선은 새 fixture의 완료를 기다리지 않는다.

## 공통 경계

- Design 전용이다. 개발 플러그인의 일반 UI와 로컬 명령을 사용한다. 공식 Figma MCP, Computer Use 세션, hook을 사용하지 않는다.
- 기존 참고 아카이브, 원본, 보존 사본, 기존 인수 파일의 바이트를 바꾸지 않는다. 원본 사용자 템플릿을 공개 파일로 복사하거나 이름·경로로 가리키지 않는다.
- 동결된 독립 검사(`tests/rd06_fresh_read.cjs`, `tests/rd06_summary_coverage.cjs`, `tests/rd06_reject_partial.cjs`, `tests/test_graph_sync.py`, `tools/reference_distribution_guard.py`)의 Git blob과 모드를 바꾸지 않는다. 새 동작은 새 검사에 둔다.
- 원시 브라우저·Figma 응답, 캡처, 측정 로그는 Git 밖에 둔다. 공개 문서에는 digest, 수치, 범위, 판정만 쓴다. 개인 절대 경로, 계정, 토큰, 원시 Figma file/page/node ID를 넣지 않는다.
- 자동 검사 통과는 실제 브라우저·Figma 관측이 아니다. 실제 관측은 통합 담당(root)이 통합된 소스에서 수행한다.

<a id="status-promotion"></a>

## 상태 승격 규칙

`in-progress`에서 `verified`로 바꾸려면 다음이 모두 있어야 한다.

1. 구현 소스가 `main`에 통합되고, 그 전체 커밋 SHA가 이 문서와 노드의 `observed_evidence`에 기록된다.
2. 아래 작업별 인수 항목마다 판정과 근거가 있다. 미관측 항목이 하나라도 있으면 `in-progress`를 유지하거나 `blocked`로 바꾸고 이유를 적는다.
3. 노드의 `proof_refs`가 저장소에 실존하는 공개 파일만 가리킨다. 그래프 검사가 이를 강제한다.
4. 실제 브라우저·Figma 결과는 root가 직접 관측한 값이다. 하위 작업자의 보고나 과거 실행 수치로 대신하지 않는다.

<a id="p2-rights-cleared-fixture"></a>

## A. 권리 정리 fixture (`p2-rights-cleared-fixture`)

계약 원문은 [capability-review.md#p2-production-fixture](capability-review.md#p2-production-fixture)다. 목적은 이후 FAQ mobile·keyboard와 복합 렌더 fidelity가 공유할 production-like 공개 입력이다.

### 최소 데이터 형태

기존 자체 예제의 manifest 형태를 따른다. [owned-design-baseline manifest](../../examples/owned-design-baseline/manifest.json)(`figma-flow-owned-design-baseline-manifest-v1`)와 [owned-component-families manifest](../../examples/owned-component-families/manifest.json)(`figma-flow-owned-example-manifest-v1`)가 기준이다. 새 fixture는 `examples/` 아래 새 디렉터리 하나에 둔다.

| 필드 | 내용 |
|---|---|
| `ownership` | 저작권, 라이선스, `third_party_sources`, 외부 미디어·폰트·네트워크 요청 수 |
| `external_reference_policy` | 외부 템플릿 이름·URL·스크린샷·문구를 기록하지 않는다는 정책 |
| `artifact_layers` | 공개 입력, 공개 기준, 비공개 생성물의 공유 범위와 Git 추적 여부 |
| `files[]` | 경로, 역할, `sha256`. 로더가 읽을 수 있는 파일의 허용 목록이다 |
| 화면 범위 | viewport, 상태 ID, 대표하는 사용자 작업과 제외 범위 |

제3자 자산을 쓰면 자산마다 출처, 라이선스, 사용 범위, digest를 기록한다. 기록할 수 없으면 쓰지 않는다.

### 인수 항목

| ID | 기준 | 근거 |
|---|---|---|
| A1 | manifest의 모든 `sha256`이 실제 파일 bytes와 같고, 디렉터리의 모든 파일이 manifest에 있다 | 새 fixture 검사 |
| A2 | 로더는 manifest의 허용 목록에 있는 파일만 읽는다. 목록 밖 파일과 경로 탈출은 거절한다 | 새 fixture 검사의 거절 사례 |
| A3 | 공개 입력과 생성 graph에 실제 계정·세션·개인 문구·외부 전용 이미지가 없다 | `python3 -B tools/reference_distribution_guard.py --ref HEAD --format text` clean, 새 민감도 검사 |
| A4 | 입력 digest, 출력 graph digest, 화면 범위가 receipt에 기록된다 | 공개 요약에는 digest와 범위만 쓴다 |
| A5 | 기존 참고 자료와 보존 사본의 bytes·파일 수가 변하지 않는다 | P0 보존 대조 재실행 |
| A6 | 실제 브라우저에서 fixture를 열 때 허용 파일 밖 요청과 외부 네트워크 요청이 0건이다 | root의 격리 브라우저 관측 |
| A7 | 권리 승인은 사람이 한다. 기획자 역할이 대표 작업과 제외 범위를 승인한 기록이 있다 | 자동 검사로 대신하지 않는다 |

### 명령

```sh
python3 -B -m unittest tests.test_design_specialization
python3 -B -m unittest discover -s tests -p 'test_web_design.py'
python3 -B tools/reference_distribution_guard.py --ref HEAD --format text
```

새 fixture 검사 명령은 구현 커밋이 만든 뒤 노드의 `commands`에 추가한다. 존재하지 않는 검사를 미리 등록하지 않는다.

<a id="p2-read-performance-baseline"></a>

## B. Fresh read 성능 기준선 (`p2-read-performance-baseline`)

계약 원문은 [capability-review.md#p2-performance-baseline](capability-review.md#p2-performance-baseline)이고, 설계 배경은 [NF-02](NF-02-incremental-native-read.md)다. 이 작업은 측정만 한다. 캐시나 최적화 코드를 넣지 않는다.

### 최소 데이터 형태

기존 측정 형태를 재사용한다. `figma-bridge/native_semantic_read.js`의 `nativeReadGetterLedger`(`figma-flow-native-read-ledger-v1`)는 full 결과와 처음 읽은 `id.getter` 이름 목록을 낸다. `compareNativeReadProfiles`(`figma-flow-native-read-comparison-v1`)는 같은 요청의 full·summary getter 목록, 요청 필드 일치, UTF-8 JSON bytes를 낸다. 기준선 기록은 여기에 반복 횟수와 경과 시간을 더한다.

| 필드 | 내용 |
|---|---|
| `source_commit` | 측정한 통합 소스의 전체 SHA와 로드된 runtime generation |
| `scope` | file·page·node 집합의 digest, 노드 수, 요청 필드, profile(`summary` 또는 full) |
| `environment` | Figma 클라이언트 종류와 버전, 측정 host |
| `runs[]` | 회차, getter 수, elapsed ms, payload bytes, `coverage.complete`, fresh 여부 |
| `summary` | 회차 수, 최소·중앙값·최대 elapsed, getter 수와 bytes의 회차 간 변동 |
| `bottleneck` | 측정으로 확인한 병목 하나 또는 `none-observed` |

getter 수의 기준은 ledger의 고유 `id.getter` 수다. 실제 호출 횟수를 따로 세면 두 값을 구분해 적는다.

### 인수 항목

| ID | 기준 | 근거 |
|---|---|---|
| B1 | 모든 회차의 `scope` digest와 요청 필드가 같다. 다르면 그 회차를 비교에서 빼고 이유를 적는다 | 기록 대조 |
| B2 | 같은 환경에서 fresh 측정을 최소 5회 반복한다. 첫 회차는 따로 표시한다 | root의 실제 Figma 측정 |
| B3 | 회차마다 getter 수, elapsed, bytes, completeness가 있다. coverage가 불완전한 회차도 버리지 않고 실패로 남긴다 | 기록 대조 |
| B4 | summary 결과는 full 근거로 승격되지 않는다. `requireFullNativeRead`가 summary를 거절한다 | 기존 RD-06 검사 |
| B5 | 동결된 RD-06 검사와 `test_graph_sync.py`가 blob 변경 없이 통과한다 | 아래 명령, blob 대조 |
| B6 | 속도 향상을 주장하지 않는다. NF-02의 과거 실행 수치는 이 기준선에 쓰지 않는다 | 문서 검토 |
| B7 | `bottleneck`이 `none-observed`이면 `p2-incremental-native-read`는 시작하지 않는다 | 그래프 상태 |

### 명령

```sh
node --test tests/rd06_fresh_read.cjs tests/rd06_summary_coverage.cjs tests/rd06_reject_partial.cjs
node --test tests/rd06_full_getter_ledger.cjs tests/rd06_read_comparison.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
```

이 명령은 저장소 fixture 기준만 확인한다. 실제 Figma 지연이나 대형 문서의 동작을 보여 주지 않는다. 실제 측정값은 root가 개발 플러그인으로 등록된 테스트 페이지에서 얻는다.

## Root 실측 절차

root는 두 작업의 구현이 `main`에 통합된 뒤 다음을 수행하고 결과를 이 문서와 그래프에 기록한다.

1. 통합 소스의 SHA를 고정하고, 설치·로드된 개발 플러그인의 runtime generation이 그 소스와 같은지 확인한다.
2. A6. 격리 브라우저에서 새 fixture를 열고 요청 목록을 저장한다. 허용 목록 밖 요청과 외부 요청 수를 센다.
3. B2. 등록된 Design 테스트 페이지에서 같은 범위의 fresh read를 5회 이상 실행한다. 회차별 ledger와 elapsed를 Git 밖에 저장한다.
4. 공개 요약만 이 문서에 쓰고, 노드의 `observed_evidence`·`proof_refs`·`evidence_status`를 갱신한다. 그다음 `python3 -B -m unittest tests.test_next_roadmap_backlog`를 실행한다.
5. 관측하지 못한 항목은 미관측으로 남긴다. 그 작업은 `verified`로 바꾸지 않는다.
