# 유지보수 검증과 회귀 방지

## 저장소 진단

배포 후보의 그래프, 기존 테스트, 코드 경계, 저장소 규칙과 유지보수 스킬을 대조했다.

| 발견 사항 | 현재 강제 수단 | 적용 계층과 결과 | 작업량 |
| --- | --- | --- | --- |
| Python graph CLI, 토큰 로더, 명세·검토 처리기가 각자 JSON을 읽어 중복 키의 마지막 값을 채택 | 메이저 아카이브 일부 검사와 문서 | 단일 디코더와 경계 검사에 연결. 중복 키, NaN, 범위를 벗어난 부동소수점 거절 | 중 |
| 그래프 실행 도구가 다른 폴더에서 동명의 모듈을 불러올 수 있었음 | 각 호출자에서 검색 경로 지정 | 현재 체크아웃의 휴대용 그래프 모듈을 명시적 경로로 선택 | 소 |
| UI나 CLI 실행 근거의 위치·기록 형식이 문서와 작업자마다 달랐음 | 개별 테스트와 패치 기록 | 프로필이 실행 결과와 지문을 수집. Chromium 전후 관측을 지문으로 비교 | 중 |
| 그래프의 기존 예시 케이스만으로 입력 변이를 모두 다루기 어려웠음 | 단위 테스트와 메이저 검사 | 시드가 정해진 속성 테스트 및 릴리스 확대 실행 | 소 |
| 설명을 옮기는 과정에서 외부 라이선스, 검사 이유, 과거 기록이 유실될 수 있음 | 문서와 사람 리뷰 | 실제 소비 경로에서 삭제한 중복 설명만 정리. 라이선스·외부 제약·과거 기록은 원 출처에 유지 | 계속 |
| 좌석 권한, 시각적 적합성, 실제 사용자의 선택 | 일부 자동 검증과 실제 환경의 인수 | 실제 Figma 확인과 사람 판단은 해당 요구사항의 인수 근거로 확인 | 상황별 |

기여 규칙과 모든 등록 스킬의 제목, Git 추적 Python 주석 및 원시 JSON 디코더 후보는 `python3 -B tools/maintenance.py audit`에서 경로와 행으로 확인한다. 전체 검색 결과는 후보 목록으로 사용한다. 실제로 자동화할 조건, 사람에게 남겨야 하는 판단, 이번에 정리한 우회 경로는 [저장소 유지보수 감사](maintenance-audit.md)에 기록한다.

## 직접 실행

아래 프로필을 직접 호출해도 각 `maintenance.run_step` 자식은 전용 임시 XDG 설정 경로를 받는다. 아카이브의 `major_release.rerun_witness`와 `graph_governance.py verify`에서 실행하는 명명된 Node 계약 검사, 나머지 Node 제품군을 실행하는 `graph_governance.py test-other-suites`도 같은 방식으로 매번 새 경로를 만들고 성공·실패 후 정리한다. 개별 테스트나 추가 재현 명령은 `python3 -B tools/test_env.py COMMAND [ARG ...]`로 실행한다.

```sh
python3 -B tools/maintenance.py check
python3 -B tools/maintenance.py verify --profile graph --out .figma-flow/evidence/local-graph
python3 -B tools/maintenance.py verify --profile cli --out .figma-flow/evidence/local-cli
python3 -B tools/maintenance.py verify --profile api --out .figma-flow/evidence/local-api
```

UI 전후 캡처는 같은 Chromium과 폰트로 실행하며 두 체크아웃에 해당 화면 검사가 있어야 한다.

```sh
python3 -B tools/maintenance.py verify --profile ui --base "$BASE_CHECKOUT" --out .figma-flow/evidence/panel
```

출력 폴더는 실행 전 존재하지 않아야 한다. 각 프로필은 자체 임시 디렉터리에서 실행하고, 결과·재실행 명령·실행 환경의 소스 지문·출력 크기와 SHA-256이 있는 `evidence.json` 한 개만 남긴다. UI 캡처 원본은 판정 후 정리한다. PR에는 확인한 화면, 전후 비교 결과, 실행 불가 또는 실패의 이유를 먼저 쓴다.

## 하드코딩·SSoT 스캐너

`python3 -B tools/maintenance.py check`는 [ssot_scan.py](../tools/ssot_scan.py)도 실행한다. 규칙·소유 파일·검증된 `mirrors`·예외는 [ssot-scan.json](../tools/ssot-scan.json), 스키마 ID 레지스트리는 [schema-ids.json](../library/schema-ids.json), 공용 한도는 [runtime-limits.json](../library/runtime-limits.json), 남은 부채 기준선은 [ssot-baseline.json](../tools/ssot-baseline.json)이 관리한다(현재 `entries: {}` 0건).

| 규칙 | 정본(SSoT) | 대상 |
| --- | --- | --- |
| `loopback-literal`, `port-literal`, `network-timeout-literal` | `policy.json`의 `controlEndpoint` → [local_endpoint.py](../tools/local_endpoint.py) | `localhost`·`127.0.0.1` 문자열, 기본 포트, 로컬 HTTP·소켓 timeout |
| `control-route-literal` | `figma_control.py`, `local_endpoint.py`, `workspace_transport.js` | 소유 파일 밖의 `/control/*` 경로 |
| `private-atomic-writer` | [private_io.py](../tools/private_io.py) | `0600`·`os.replace`를 다시 구현한 함수 |
| `vocabulary-literal` | 선언한 Python 상수(`figma_control.SETUP_STEPS`) | 소유 선언 밖에서 반복한 단계 값 |
| `timer-literal`, `inline-limit` | [runtime-limits.json](../library/runtime-limits.json)([runtime_limits.py](../tools/runtime_limits.py)), `WORKSPACE_PROFILE_POLICY`, `controlTransport`, `read-limits.json` 또는 이름 있는 상수 | JS 지연 숫자, 1000 이상의 비교·`read()` 한도(16진수 코드 포인트 제외) |
| `schema-id-spread` | [schema-ids.json](../library/schema-ids.json)([schema_ids.py](../tools/schema_ids.py)) | 두 파일 이상에 반복한 `figma-flow-*-vN` |
| `mirror-drift`, `mirror-stale` | `ssot-scan.json`의 `mirrors` · `schema-ids.json`의 `mirrors` | 직접 `import`가 불가한 JS·패널 사본이 정본과 다르거나 삭제됨(기준선 무관 즉시 실패) |

Python은 `ast`로 검사하고 docstring을 제외한다. JS·JSX는 주석을 버리는 줄 단위 lexer로 문자열·정규식·템플릿·숫자만 본다. 기준선은 규칙·경로·키별 개수로 비교한다. 새 부채가 생기거나 부채를 고친 뒤 기준선을 줄이지 않으면 `check`가 실패한다.

```sh
python3 -B tools/ssot_scan.py summary              # 규칙별 개수와 새 부채
python3 -B tools/ssot_scan.py scan --rule loopback-literal --path 'tools/*'
python3 -B tools/ssot_scan.py baseline --write     # 부채를 고친 뒤 기준선 축소(증가는 거절)
```

`baseline --write --allow-growth`는 처음 기준선을 만들 때나 리뷰한 예외에만 사용하며 `mirror-drift`·`mirror-stale`·`parse-error`가 있으면 거절한다. 오탐은 기준선 대신 `ssot-scan.json`의 `allow`에 규칙·경로·키·사유를 적는다.

## 검증 산출물 정리

| 산출물 | 종료 시 처리 |
| --- | --- |
| 실행이 만든 로그, 캡처 원본, 테스트용 ZIP·설치·백업 | 결과를 기록한 직후 해당 임시 실행 범위에서 제거 |
| 실행이 만든 검증 워크트리 | 소유 범위와 Git 상태를 대조하고 `git worktree remove <검증 경로>` 사용. 보존할 파일이 있으면 원본 소유자를 확인 |
| 영향받은 기준, 재현 명령, 관측 결과와 건너뛴 이유 | Git의 패치 기록·검증 정의 또는 작은 영수증으로 보존 |
| 실제 Figma 작업공간, 기존 사용자 자료, 사용자가 요청한 최종 ZIP | 각 산출물의 소유권·인수 계약에서 관리 |

`maintenance.py verify`는 `TMPDIR` 계열 환경과 캡처 경로를 이번 실행이 소유한 임시 공간으로 제한한다. 성공·실패·시간 초과·정상 취소 시 이를 정리한다. 이름·확장자를 기준으로 기존 파일을 일괄 삭제하는 명령을 사용하지 않는다. 강제 종료나 전원 장애로 정리가 중단됐으면 실행이 남긴 소유 경로를 확인한 뒤 그 경로만 복구 정리한다.

## 입력 변이 재현

릴리스 워크플로는 `release` 프로필로 그래프 6,000건과 저널 입력 4,000건을 실행한다. 저널 검사는 입력 거절 시 파일 바이트 보존, 중복 제출의 멱등성, 커서 관측 순서와 페이지 격리를 확인한다. 실패 시 증거에는 선언된 실행 명령의 시드를 보존한다. 해당 명령을 직접 재실행하면 실패한 JSON 변이와 사례 번호를 확인할 수 있다.

```sh
python3 -B tests/test_graph_properties.py --seed 92821 --trials 6000
python3 -B tests/test_journal_properties.py --seed 562 --count 4000
python3 -B tests/test_journal_properties.py --seed 562 --count 4000 --case 0
```

정상 입력의 순서가 바뀌어도 유효성 검사가 통과하고, 중복 노드와 사라진 대상 및 형식 오류는 거절해야 한다. 기존 예시 테스트는 그대로 실행한다.

## 새 교정의 절차

관측 가능한 실패를 먼저 고정한다. 검사에서 실제 오류가 잡히면 제품 경계를 고치고 같은 입력을 다시 실행한다. 오래된 지시를 교체할 때는 구현을 통해 강제할 수 있는 문장부터 코드와 검사 이름으로 연결한다. 자료나 권한이 없어서 진행할 수 없는 검사는 그 이유와 실제 필요한 환경을 기록한다.

## Figma 패널 Graph 검증

[Figma Flow 제품 헌법](../CONSTITUTION.md)에서 채택한 [Graph SSoT and Code Quality Constitution 1.0.0](graph-governance-constitution.md)을 패널에 먼저 적용한다. [패널 Graph](../library/panel-design/governance.json)는 관리 대상 ID, 방향, 영향 전파와 검증 책임을 선언한다. [유지보수 계약](../tools/maintenance-contract.json)은 소스 경계와 오프라인 산출물의 역할별 경로를 소유한다. [경계 표](generated/panel-boundaries.md)와 번들 생성기, 실제 Figma 패널 로더가 이 경로를 사용한다. [검토 기록](graph-governance-review.json)은 경계, Graph 관계, 고정 도구 버전과 이 문서의 지문을 담는다.

```sh
npm --prefix panel-ui install --ignore-scripts --no-package-lock --no-audit --no-fund
python3 -B tools/graph_governance.py observe
python3 -B tools/graph_governance.py impact --base origin/main
python3 -B tools/graph_governance.py verify --base origin/main
python3 -B tools/graph_governance.py verify --base origin/main --json
```

| 검사 책임 | 담당과 적용 범위 |
| --- | --- |
| 패널 의존성·정적 경계 | esbuild 0.28.2 해석과 동봉 Acorn 8.15.0 관측. 기존 구조 검사가 네트워크·호스트 우회를 막고 관측 결과는 바인딩·수입 관계·진입점 도달성을 구분한다. |
| 계약과 타입 | Node의 패널 경계·디자인 계약 테스트. TypeScript 5.9.3은 기존 SDK 선언과 컴파일 확인에서 사용한다. 패널 프로젝트 전체 타입 검사나 타입 기반 린트는 설정되어 있지 않다. |
| 생성물과 CI | 깨끗한 디렉터리의 생산용 패널 빌드와 워크플로 템플릿을 제출된 파일 집합과 비교한다. `Panel Graph Governance` 잡이 제출 커밋과 비교 기준을 고정하고 로컬과 같은 집계 명령을 실행한다. |
| 포맷·비 JS 정적 검사 | Biome 2.6.8이 패널 JSON 포맷과 CSS·JSON 규칙을 담당한다. import 정렬은 명시적인 로컬 명령으로 실행한다. |
| JS·React 정적 검사 | Oxlint 1.94.0이 패널 JavaScript 정확성, 로컬 미사용 바인딩, Hook 호출 순서와 JSX 키·속성을 검사한다. |
| 프로젝트 미사용 검사 | Knip 6.48.0이 실제 패널 진입점과 화면 등록부를 사용해 생산 파일·export·의존성을 분석한다. 기본 모드는 도구 명령과 지정된 검사 파일을 진입점으로 삼아 개발 파일·export·의존성 및 해석 실패를 확인한다. |

Graph 소유 값을 바꿀 때 값의 원본과 구현 소비 경로를 확인한다. 패널 번들은 `npm --prefix panel-ui run build`, 경계 표는 `python3 -B tools/graph_governance.py write-doc`, CI 투영은 `python3 -B tools/delivery_config.py --write`에서 갱신한다. 생성물을 재현한 후 비교 기준을 명시하여 집계를 실행한다. 관련 정책이나 설명을 바꾼 경우 이 절을 검토하고 `graph-governance-review.json`에 검토한 입력과 내용의 근거를 기록한다. 검토 결과가 그대로여도 이유가 필요하다.

- 집계는 Graph, 구조, 도달성, 생성, 계약, 도구, 문서, 영향, 입력 최신성의 결과를 요구한다. 관측한 모든 모듈의 사용 판정과 지정된 파일에서 실행된 개별 계약 테스트를 검증한다. 증거가 빠지거나 테스트를 건너뛰면 집계에서 실패한다.
- 영향 보고서는 Git 인덱스·미커밋 파일, 이전과 현재의 선언 관계 및 실제 정적 소비 경로를 표시한다. 이전 관측은 기준 커밋의 관리 소스를 임시 위치에 꺼내 확인한다. 현재와 이전의 검증 입력이 모두 같으면 현재 관측을 사용한다.
- 검토 패널과 로컬 전송 사이에 필요한 직접 호출은 import 위치와 호출 위치가 함께 있어야 한다. 정적 분석이 지역 선언과 실제 호출 대상을 구분할 수 없으면 분석 불가로 남긴다. 선언된 정책·생성·문서 관계는 각 단계의 실행 증거로 대조한다.
- 실제 앱 진입점에서의 정적 도달성은 모듈 수준 후보다. 알려진 작업 리포트 CLI 소비 경계, 도달 가능한 코드와 동적 연결을 구분한다. 함수별 호출 대상이나 DB, 외부 시스템의 사용 여부는 별도 증거가 필요하다. 후보를 자동 삭제하지 않는다.
- Graph 검사·생성기·워크플로·ignore·판정 예외는 `.github/CODEOWNERS` 지정 범위에서 검토한다. GitHub에서 실제 실행된 커밋의 결과, 필수 체크 및 우회 금지, 코드 소유자 리뷰 설정을 각각 확인한다. 이 파일들만으로 브랜치 보호가 활성화되지는 않는다.

### 독립 도구 실행

```sh
npm --prefix panel-ui run format:check
npm --prefix panel-ui run lint:biome
npm --prefix panel-ui run lint:oxlint
npm --prefix panel-ui run lint:knip -- --json
```

Biome의 JSON 검사와 Oxlint의 JS 검사는 파일 형식에 따라 역할을 나눈다. Knip의 파일·export·패키지 판단에는 전체 분석 대상과 진입점이 필요하다. 현재 테스트가 직접 호출하는 생산 export의 유지 근거는 Graph에 각 심볼과 소비자 경로로 둔다. 임시 가상 진입점과 검사 로그는 실행이 종료될 때 정리한다. Oxlint 타입 기반 규칙과 실험적 React Compiler 규칙은 이 범위에서 활성화하지 않았다. 도구는 직접 버전을 고정하며 npm의 전이 의존성은 기존 lockfile 정책을 따른다.
