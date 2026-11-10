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

작업 종류를 추가하려면 원래 생성기의 입력 검증을 먼저 통과시키고 작업 목록에서 같은 등록으로 열어 봅니다. Figma 호스트 객체의 불변 속성, 플러그인 ID별 데이터 소유권, 실제 글꼴·바인딩 동작은 브라우저나 가짜 호스트와 다를 수 있습니다. 패널 표시와 실제 네이티브 작업을 각각 확인하고, 예시 JSON과 운영 증거를 구별해 기록합니다. [사용자 절차](docs/figma-guide.md)

React 패널을 수정할 때는 [프런트엔드 빌드와 상태 소유권](panel-ui/README.md)을 따릅니다. 전체 통합 UI는 공통 React 셸과 Lucide React 아이콘을 사용합니다.

## 변경 검증

Node는 `.nvmrc`에 고정된 LTS를 사용합니다. 회사 npm 레지스트리는 사용자가 제공한 실제 URL·적용 범위를 확인해 프로젝트 `.npmrc`에 설정합니다. 인증값은 저장소에 넣지 않습니다. npm·pnpm·Yarn·Bun lockfile은 GitHub에 올리지 않으며, `.gitignore`와 실제 추적 파일을 모두 확인합니다. 루트에는 `package.json`이 없으므로 `npm install`/`npm ci` 대신 아래 기존 검사 명령을 사용합니다. [환경 설정과 추적 해제 절차](docs/npm-environment.md)

저장소 밖의 가상환경에 `requirements-optional.txt`를 설치합니다. Python 3.13, Node.js 26, Codex CLI 0.165.0을 사용한 검사 명령입니다. 코드 실행 격리 테스트는 실제 `codex sandbox` 실행 파일을 필요로 합니다. 공개 CI는 macOS에서 공식 Codex 네이티브 바이너리의 SHA-256을 확인하고 읽기 전용 OS 샌드박스를 실행합니다. Ubuntu hosted runner에서는 bubblewrap의 루프백 설정이 거부됐습니다.

```sh
python -B -m unittest discover -s tests
node --test tests/*.cjs
python -B -m unittest discover -s examples/native-direction-review -p test_demo.py
```

검사 명령을 파이프로 연결하면 마지막 명령의 종료 코드만 보일 수 있습니다. 명령별 종료 코드와 skip 사유를 확인하세요. 깨끗한 클론에는 외부 캠페인의 회귀 레이아웃과 운영자가 제공하는 네이티브 읽기 자료가 없습니다. `FIGMA_DRAFT_LIVE_MANIFEST`와 `FIGMA_DRAFT_LIVE_READBACK`에 제공 권한이 있는 실제 시안 자료를 지정해 선택적 검사를 실행할 수 있습니다. 증거·실행 출력은 저장소 바깥에 둡니다.

## 버전과 GitHub Release

1. 호환되는 수정·문서는 패치, 호환되는 기능 추가는 마이너 버전을 올립니다. 호환성을 깨는 변경은 릴리스 노트에 영향과 이행 방법을 명시합니다. 코덱스·범용 매니페스트의 `version`, README의 설치 태그, `CHANGELOG.md`의 릴리스 번호를 함께 갱신합니다.
2. 변경을 커밋하고 최종 트리에서 위 검사를 실행합니다. 처음 설치하는 경로는 깨끗한 클론에서 워크숍 예제를 만들어 Figma용 `manifest.json`까지 검증합니다. 원격의 대상 브랜치와 공개할 Git 사용자 이메일을 확인합니다.
3. 통과한 `main` 커밋에 `vX.Y.Z`로 주석 태그를 만듭니다. `CHANGELOG.md`의 해당 항목을 Release 본문에 쓰고 테스트 범위와 남은 제한을 덧붙입니다. 기존 공개 태그와 파일은 보존하고 변경본에는 새 버전을 부여합니다.
4. 릴리스 ZIP과 체크섬은 저장소 밖에서 만듭니다. 다음은 태그가 `v0.18.2`인 예입니다.

```sh
TAG=v0.18.2
ASSET="figma-flow-plugin-${TAG#v}.zip"
git archive --format=zip --prefix=figma-flow-plugin/ --output="../$ASSET" "$TAG"
(cd .. && shasum -a 256 "$ASSET" > "$ASSET.sha256")
```

5. 대상 `main`과 태그만 푸시하고 GitHub Actions 결과를 확인합니다. GitHub Release에 ZIP과 체크섬을 첨부하고 다시 다운로드해 `shasum -a 256 -c 파일명.zip.sha256`으로 확인합니다. Linux에서는 `sha256sum -c`도 사용할 수 있습니다. 받은 ZIP을 풀면 코드와 매니페스트가 `figma-flow-plugin/` 아래에 있습니다.

## 이슈·PR

실패한 단계, 사용한 버전, 실행 명령, 종료 코드, 기대값과 관찰값을 함께 적어 주세요. Figma 화면은 등록, 가져오기, 읽기, 검증 중 어느 단계인지 표시해 주세요. 계정 정보, 실제 파일 키, 초대 링크, 원본 대화·선택 기록을 공개 이슈에 첨부하지 마세요.
