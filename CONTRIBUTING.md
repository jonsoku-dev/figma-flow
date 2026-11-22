# 개발과 릴리스

## Figma 작업을 변경할 때

Figma Desktop의 진입점은 비공개 작업공간의 고정 `manifest.json`입니다. Codex 플러그인 소스에는 생성기와 패널 템플릿을 두고, 프로젝트 데이터·채팅 연결 키·실행 결과는 작업공간에 둡니다.

| 변경 대상 | 소유 코드 | 검증할 경계 |
|---|---|---|
| 작업 준비와 갱신 | [figma_workspace.py](tools/figma_workspace.py) | 허용된 생성기와 원본 선택·파일 핀, 변경 전 리비전, 중단 후 같은 매니페스트로 복구 |
| 목록과 작업 전환 | [workspace_host.js](figma-bridge/workspace_host.js) | 지정 파일에서만 열기, 실행 중 이동 차단, 이전 패널의 응답 격리 |
| 실제 디자인 작업 | `figma_bridge.py`, `figma_draft.py`, `graph_sync.py`와 [네이티브 실행기](figma-bridge/) | 작업의 실제 Figma 읽기 결과, 적용 범위, 저장 JSON 계약 |
| 테마와 패널 | [React 공통 컴포넌트](panel-ui/src/components.jsx), [CSS 계층](panel-ui/src/styles/index.css), [오프라인 렌더러](tools/plugin_panel.py) | 실제 생성 HTML의 밝은·어두운 테마, 좁은 폭, 키보드, 진행·실패·복구 상태 |
| 채팅 전달 | [workspace_chat.js](figma-bridge/workspace_chat.js), [로컬 연결](tools/workspace_chat.py) | 현재 작업의 채팅·리비전에만 전달, 미리보기와 본문 일치, 중복 전송 방지 |

작업 종류를 추가하려면 원래 생성기의 입력 검증을 먼저 통과시키고 작업 목록에서 같은 등록으로 열어 봅니다. Figma 호스트 객체의 불변 속성, 플러그인 ID별 데이터 소유권, 실제 글꼴·바인딩 동작은 브라우저나 가짜 호스트와 다를 수 있습니다. 패널 표시와 실제 네이티브 작업을 각각 확인하고, 예시 JSON과 운영 증거를 구별해 기록합니다. [사용자 절차](docs/guide.md)

React 패널을 수정할 때는 [프런트엔드 빌드와 상태 소유권](panel-ui/README.md)을 따릅니다. 전체 통합 UI는 공통 React 셸과 Lucide React 아이콘을 사용합니다.

## 변경 검증

Node는 `.nvmrc`에 고정된 LTS를 사용합니다. 회사 npm 레지스트리는 사용자가 제공한 실제 URL·적용 범위를 확인해 프로젝트 `.npmrc`에 설정합니다. 인증값은 저장소에 넣지 않습니다. npm·pnpm·Yarn·Bun lockfile은 GitHub에 올리지 않으며, `.gitignore`와 실제 추적 파일을 모두 확인합니다. 루트에는 `package.json`이 없으므로 `npm install`/`npm ci` 대신 아래 기존 검사 명령을 사용합니다. [환경 설정과 추적 해제 절차](docs/guide.md#environment)

저장소 밖의 가상환경에 `requirements-optional.txt`를 설치합니다. Python 3.13, Node.js 26, Codex CLI 0.165.0을 사용한 검사 명령입니다. 코드 실행 격리 테스트는 실제 `codex sandbox` 실행 파일을 필요로 합니다. 공개 CI는 macOS에서 공식 Codex 네이티브 바이너리의 SHA-256을 확인하고 읽기 전용 OS 샌드박스를 실행합니다. Ubuntu hosted runner에서는 bubblewrap의 루프백 설정이 거부됐습니다.

```sh
python -B -m unittest discover -s tests
node --test tests/*.cjs
python -B -m unittest discover -s examples/native-direction-review -p test_demo.py
```

검사 명령을 파이프로 연결하면 마지막 명령의 종료 코드만 보일 수 있습니다. 명령별 종료 코드와 skip 사유를 확인하세요. 깨끗한 클론에는 외부 캠페인의 회귀 레이아웃과 운영자가 제공하는 네이티브 읽기 자료가 없습니다. `FIGMA_DRAFT_LIVE_MANIFEST`와 `FIGMA_DRAFT_LIVE_READBACK`에 제공 권한이 있는 실제 시안 자료를 지정해 선택적 검사를 실행할 수 있습니다. 증거·실행 출력은 저장소 바깥에 둡니다.

로컬 참고 ZIP·압축 해제 폴더·임시 증거·비공개 인용 목록은 저장소나 공유 배포에 넣지 마세요. [배포 가드](tools/reference_distribution_guard.py)는 `--reference-zip`과 `--reference-literals` 없이 실행하면 금지 경로와 임시 증거만 확인(`paths-only`, `status: paths_only_clear`)하며, 커밋·배포 전에는 오프라인에서 로컬 참고 ZIP(`--reference-zip`)과 비공개 1줄 인용 목록(`--reference-literals`)을 지정해 원본·이름 변경·CRLF/LF 변환·문서/테스트 내 고유 인용을 대조하세요. 원문이나 개인 경로는 출력하지 않고 경로·SHA-256·규칙 ID·건수만 보고합니다.

```sh
python -B tools/reference_distribution_guard.py --ref HEAD --format text
python -B tools/reference_distribution_guard.py --worktree --reference-zip /path/to/reference.zip --reference-literals /path/to/literals.json --format text
```

<a id="major-ssot"></a>

## 메이저 배포 전 그래프·하드코딩 검사

메이저 검사는 후보의 테스트를 다시 실행합니다. 프로젝트가 지정한 Node(`.nvmrc`), Chromium, Docker Compose CLI, PostgreSQL 서버 도구, 읽기 전용 OS 샌드박스를 지원하는 Codex CLI를 사용합니다. 격리된 Python 환경에 `requirements-optional.txt`, `library/figma-rest/requirements.txt`와 `apps/little-hands/requirements.lock`의 의존성을 설치합니다. API 검사용 TypeScript 버전은 `library/figma-api/package.json`의 고정값을 사용합니다. CI에서 실행하는 설치·환경 변수 설정은 [배포 워크플로](.github/workflows/reference-guard.yml)에 있습니다.


`plugin.json`에서 버전과 공통 메타데이터를 편집한 뒤 `python3 -B tools/plugin_manifest.py --write`로 Codex 매니페스트를 생성합니다. 마켓플레이스 이름과 독립 패키지의 버전은 각 소유자가 관리합니다.

패널 프로젝트 의존성은 위의 로컬 빌드 절차로 설치합니다. 검사는 별도 임시 폴더에서 후보 소스만으로 패널을 재생성해 ZIP의 산출물과 바이트 단위로 대조합니다. 아래 명령은 현재 커밋의 실제 ZIP 구성으로 다음 메이저 후보를 점검합니다. 제품 버전 변경이나 게시를 수행하지 않습니다. 종료 코드 1이면 `findings`의 파일·식별자와 `surfaces`의 파일 목록을 확인합니다.

```sh
python3 -B tools/major_release.py --ref HEAD --candidate 1.0.0 > major-readiness.json
```

[소유권 그래프](release/authority.json)는 Git 아카이브 파일을 가장 구체적인 경로로 한 번씩 분류합니다. `owned-by`는 영역의 출발점입니다. `review` 영역을 닫으려면 현 소스·소유 원본의 fingerprint에 묶인 `release/reviews/<영역 ID>.json`에 모든 파일의 구체적인 필드 소유자와 행동 검증을 연결합니다. 예를 들어 특정 색·역할을 바꿨을 때 실제 파생 결과가 함께 바뀌는지 검증합니다. 동일 색을 검색한 횟수로는 이 조건을 충족하지 못합니다.

GitHub 작업의 실행 순서는 `library/delivery/*.yml.in`에, 공통 액션 SHA·도구 버전 참조는 `library/delivery/graph.json`에 둡니다. `python3 -B tools/delivery_config.py --write`가 GitHub용 workflow를 생성하고 로컬 마켓플레이스 항목의 제품 이름·분류를 매니페스트와 맞춥니다. 인자 없이 실행하면 배포 파일을 수정하지 않고 차이를 검사합니다. 마켓플레이스 이름과 설치 정책은 기존 설정을 유지합니다.

검토 파일 스키마는 `figma-flow-major-review-v1`입니다. `surface`, `fingerprint`, `openFindings`, `bindings`를 기록합니다. 각 binding의 `files`는 해당 영역의 실제 파일, `authority`는 소유권 그래프가 가리키는 JSON 문서와 JSON Pointer 또는 규범 Markdown의 고유한 제목(`문서.md#/sections/제목`, 슬래시는 `~1`), `reason`은 소유 범위, `witnesses`는 검증 결과 JSON의 저장소 상대 `path`와 `sha256`입니다. 검증 결과에는 같은 `surfaceFingerprint`, `status: passed`, 각 binding의 필드(`authority`)·파일(`covers`)·구체적 단언(`assertion`)·관측값(`observed`)을 담은 `checks`가 필요합니다. 각 check에 저장소 안의 `test` 파일, `testSha256`과 `case`를 지정합니다. 검사기는 후보 소스에서 해당 unittest 메서드 또는 Node 테스트 이름을 재실행합니다. 검토자가 작성한 JSON만으로는 통과할 수 없습니다. 빈 보고서, 빠진 파일, 변경된 원본, 독립적으로 관리되는 중복 선언은 차단 사유입니다. 실제 제품 시나리오와 관측의 의미는 패치 검수에서 대조합니다. 고정된 프로토콜 키·외부 SDK 원문과 독립 테스트의 기대값은 역할을 별도로 기록합니다.

## 버전과 GitHub Release

1. 호환되는 수정·문서는 패치, 호환되는 기능 추가는 마이너 버전을 올립니다. 호환성을 깨는 변경은 릴리스 노트에 영향과 이행 방법을 명시합니다. 범용 매니페스트와 Codex 파생본, README 설치 태그, CHANGELOG 릴리스 번호를 함께 확인합니다.
2. 변경을 커밋하고 최종 트리에서 위 검사를 실행합니다. 처음 설치하는 경로는 깨끗한 클론에서 워크숍 예제를 만들어 Figma용 `manifest.json`까지 검증합니다. 원격의 대상 브랜치와 공개할 Git 사용자 이메일을 확인합니다.
3. 통과한 `main` 커밋에 `vX.Y.Z`로 주석 태그를 만듭니다. `CHANGELOG.md`의 해당 항목을 Release 본문에 쓰고 테스트 범위와 남은 제한을 덧붙입니다. 기존 공개 태그와 파일은 보존하고 변경본에는 새 버전을 부여합니다.
4. 릴리스 ZIP과 체크섬은 저장소 밖에서 만듭니다. 다음은 태그가 `v0.18.2`인 예입니다.

```sh
TAG=v0.18.2
ASSET="figma-flow-plugin-${TAG#v}.zip"
python3 -B tools/major_release.py --if-major --ref "$TAG" --archive "../$ASSET"
(cd .. && shasum -a 256 "$ASSET" > "$ASSET.sha256")
python -B tools/reference_distribution_guard.py --ref "$TAG" --target-zip "../$ASSET" --reference-zip /path/to/reference.zip --reference-literals /path/to/literals.json
```

5. 대상 `main`과 태그만 푸시하고 GitHub Actions 결과를 확인합니다. GitHub Release에 ZIP과 체크섬을 첨부하고 다시 다운로드해 `shasum -a 256 -c 파일명.zip.sha256`으로 확인합니다. Linux에서는 `sha256sum -c`도 사용할 수 있습니다. 받은 ZIP을 풀면 코드와 매니페스트가 `figma-flow-plugin/` 아래에 있습니다.

## 이슈·PR

실패한 단계, 사용한 버전, 실행 명령, 종료 코드, 기대값과 관찰값을 함께 적어 주세요. Figma 화면은 등록, 가져오기, 읽기, 검증 중 어느 단계인지 표시해 주세요. 계정 정보, 실제 파일 키, 초대 링크, 원본 대화·선택 기록을 공개 이슈에 첨부하지 마세요.
