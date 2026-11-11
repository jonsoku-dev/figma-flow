# 처음 설치해서 Figma 화면을 검증하기까지

[English quick start](figma-guide-en.md) · [日本語クイックスタート](figma-guide-ja.md)

이 가이드는 **내 컴퓨터의 Codex와 Figma Desktop에서** 워크숍 예제의 두 시안을 비교하는 과정부터 시작합니다. 실제 프로젝트로 옮길 때는 8단계에서 내 브리프와 디자인 시스템을 연결하세요. 클릭을 Codex에 맡기거나 직접 수행하는 두 방식 모두 같은 결과 JSON으로 검증합니다. [복사해서 쓰는 설치 프롬프트](codex-setup-prompts.md)

## 1. 두 플러그인의 위치 확인

| 어디에서 | 설치하거나 여는 것 | 역할 |
|---|---|---|
| Codex | 이 저장소의 `.agents/plugins/marketplace.json`을 통해 `figma-flow` 설치 | 브리프·자료를 읽고, 시안·그래프·Figma용 패키지를 생성하고 검증 |
| Figma Desktop | 한 번 등록한 비공개 `WORKSPACE/manifest.json` | **준비된 작업**에서 프로젝트 작업을 열고, 명시적 실행 후 실제 결과를 저장 |

Figma 작업공간 CLI의 준비·갱신은 현재 macOS/Linux의 POSIX 파일 보호를 사용합니다. Windows 로컬 CLI는 이 경로를 지원하지 않으므로 기존 standalone 호환 절차를 유지하거나 지원되는 POSIX 환경에서 준비한 전체 폴더의 전달·실행 범위를 별도로 확인합니다.

Mac 또는 Windows용 Figma Desktop에서 편집할 수 있는 **Figma Design** 파일을 엽니다. 첫 연습은 여유 페이지가 있는 연습용 파일을 권장합니다. 일반 Design 모드에서 진행합니다. Figma 계정의 가입·로그인은 사용자가 수행합니다. [Figma 개발 플러그인 안내](https://help.figma.com/hc/en-us/articles/360042786733-Create-a-classic-plugin-for-development)

## 기본 흐름: 한 번 실행하고 Codex에 맡기기

소비자에게 Computer Use나 공식 Figma MCP 연결을 요구하지 않습니다. Codex는 이 플러그인의 localhost 명령을 사용합니다. 개발자는 별도로 허용된 환경에서 Computer Use로 검수할 수 있지만 제품 실행 의존성은 아닙니다.

1. Codex가 실제 Figma ID로 고정 작업공간과 필요한 작업을 준비합니다. 최초 등록은 4~5절을 따릅니다.
2. 사용자가 대상 Figma Design 파일에서 **Figma Flow**를 직접 한 번 실행하고 열린 상태로 둡니다. 이 실행 세션이 유지되는 동안 Codex가 아래 로컬 제어 명령을 사용할 수 있습니다.
3. Codex가 작업 키·operation·파일·페이지·현재 revision을 고정해 실행하고, 반환된 실제 JSON을 기존 검증기로 대조합니다. 후보 선택은 여전히 사용자의 실제 답변이 필요합니다.
4. 홈의 **다음 작업**과 **이력**에서 진행·실패·읽기·검증 상태를 확인합니다. 제어 연결이 없으면 **준비된 작업 → 열기**와 아래 패널 버튼이 수동 대체 경로입니다.

```sh
# Codex가 기존 private 작업공간에서 한 번 구성합니다. 포트는 예시입니다.
"$PY" -B "$PLUGIN_ROOT/tools/figma_control.py" enable --workspace "$WORKSPACE" --port 43180
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" refresh --workspace "$WORKSPACE"
"$PY" -B "$PLUGIN_ROOT/tools/figma_control.py" serve --workspace "$WORKSPACE"
```

`enable`만으로 열린 플러그인 코드가 바뀌지는 않습니다. `refresh` 후 Figma Flow를 실행하세요. `serve`는 보이는 로컬 실행 세션에서 유지하고, 아래 `run`은 Codex의 다른 CLI 실행에서 사용합니다. relay와 Figma Desktop은 같은 컴퓨터의 localhost 연결을 사용합니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/figma_control.py" run --workspace "$WORKSPACE" \
  --key invite-discovery --operation read --file-key ACTUAL_FILE_KEY --page-id ACTUAL_PAGE_ID \
  --expected-revision CURRENT_TASK_REVISION --timeout 120
"$PY" -B "$PLUGIN_ROOT/tools/figma_control.py" status --workspace "$WORKSPACE" --id OPERATION_ID
```

| 준비한 작업 종류 | 허용되는 operation |
|---|---|
| `review` | `create` |
| `import` | `import`, `read`; 지원되는 paired app 상태가 있을 때만 `sync` |
| `discover` | `read` |
| `sync` | `read`, `apply` |
| `native-edit` | `read`, `apply` — 준비한 네이티브 편집 계획 |

파일 키·페이지·revision은 실제 `list`와 현재 Figma/읽기 자료에서 가져옵니다. `--focus-page`는 **서명된 작업의 정확한 파일·페이지**가 있을 때 같은 파일 안의 그 페이지로만 이동합니다. 다른 파일을 열거나 사용자 화면을 추측하지 않습니다. `--no-wait`는 접수만 반환하므로 `status`로 완료를 확인해야 합니다.

성공 결과의 `readback` 경로를 정상 읽기 자료로 검증합니다. 검토는 `verify-native-review`, 선택된 풍부한 본제작은 `verify-production`을 사용합니다. 구조화된 가져오기는 9절의 `--require-match`·`native_handoff.py`, 그래프는 실제 웹 자료와 `pair`로 대조합니다. `state: ok`와 이력 표시가 디자인 승인·웹 일치·독립적인 출처 인증을 대신하지 않습니다. `error`·`expired`·`uncertain`이면 영수증을 보관하고 현재 상태를 다시 읽으세요. 접수된 쓰기의 결과가 불확실할 때 자동 재시도하지 않습니다.

Figma 플러그인은 사용자가 시작한 실행 모델이며 사용자가 닫을 수 있습니다([공식 실행 모델](https://developers.figma.com/docs/plugins/how-plugins-run/), [등록·실행 안내](https://developers.figma.com/docs/plugins/plugin-quickstart-guide/)). 닫힌 플러그인을 숨겨서 실행하거나 원격 코드를 평가하지 않습니다. 새 `prepare`/`refresh` 후 자동 재로드 여부는 Desktop 환경에 따라 다릅니다. 이전 revision이면 창을 닫고 **같은 고정 플러그인**을 다시 실행하며 영구 무재시작을 약속하지 않습니다.

![실제 Figma에서 연 Figma Flow 작업공간](images/panel-workspace.png)

### Computer Use 없이 글꼴 적용하기

1. Codex가 시안 원본에 글꼴 패밀리와 스타일을 함께 지정합니다. 예를 들어 제목은 `Hahmlet Bold`, 본문은 `Noto Sans KR Regular`로 준비합니다.
2. 대상 Design 파일에서 Figma Flow를 엽니다. 시안을 생성하면 플러그인이 Figma가 제공하는 패밀리·스타일 목록을 확인하고 필요한 글꼴을 로드합니다. 글꼴 메뉴를 클릭할 필요가 없습니다.
3. 필요한 스타일이 없으면 시안 생성 전 진단에 나온 이름을 확인합니다. 조직에서 제공하는 글꼴을 사용하거나 원본에 사용 가능한 스타일을 지정해 다시 준비합니다. 웹에 포함한 폰트 파일은 Figma에서 별도로 사용할 수 있어야 합니다.
4. 로컬 제어 연결이 허용되면 Codex가 결과를 회수합니다. 연결도 차단된 경우 사용자가 **검토 시안 만들기 → 결과 JSON 저장**을 실행하고 파일을 전달합니다. Codex가 실제 텍스트의 `fontName.family`와 `fontName.style`을 원본과 대조합니다.

### 이력, 다음 작업, 언어와 접근성

**다음 작업**은 현재 작업 revision과 최근 실행 자료를 바탕으로 제안합니다. **이력**에서 요청·실행 완료·실제 읽기·검증·실패를 구분하고, 이전 revision의 기록을 현재 결과로 사용하지 않습니다. 최근 기록은 이 기기에 보관되며 로컬 저장소가 없으면 세션 기록만 보일 수 있습니다. 최종 근거는 실제 JSON·검증 명령·웹 관찰 자료입니다.

![작업별 실행·읽기·실패를 구분하는 이력 패널](images/panel-history.png)

상단 **언어 / Language / 言語**에서 한국어·English·日本語를 선택합니다. 화면명·프로젝트명·사용자 문구와 원본 오류는 번역하지 않습니다. 키보드 Tab·Shift+Tab으로 이동하고, 탭은 방향키와 Enter/Space, 펼침 영역은 Enter/Space로 조작합니다. 초점 표시, 상태 알림, Figma 밝은/어두운 테마를 지원하지만 모든 보조기기 조합의 접근성 인증을 뜻하지는 않습니다.

아래 4~11절은 최초 설치, 작업 준비와 **수동 대체 경로**의 자세한 설명입니다.

### 현재 패널 빠른 찾기

| 패널 | 실제 조작과 결과 |
|---|---|
| 디자인 가져오기 | **가져오기 · 기존 페이지 열기** 또는 별도 페이지 선택 → **현재 디자인 읽기** → **JSON 파일 저장**. 연결된 앱 전용 패키지는 **앱 동기화 / 앱에 반영**을 표시합니다. |
| 디자인 방향 검토 | **검토 시안 만들기** → 완료 확인 → **결과 JSON 저장**. 오류는 **상세 진단 보기**, 배치 실패는 **실패 진단 JSON 저장**에서 확인합니다. |
| Figma 값 읽기 | **Figma 값 읽고 저장**으로 지정 페이지를 읽고 JSON을 다운로드합니다. Figma 파일을 변경하지 않습니다. |
| 컴포넌트 동기화 | 읽기 또는 **적용 범위 확인** → **확인한 범위에 적용**. **취소**는 확인창만 닫습니다. 완료 후 **JSON 다시 저장**으로 결과를 보관합니다. |

## 2. 클론하고 Codex에 설치

아래 셸 예제는 macOS/Linux의 새 작업 폴더 기준입니다. Windows에서는 [설치 프롬프트](codex-setup-prompts.md)가 PowerShell과 실제 경로에 맞는 명령을 실행하도록 할 수 있습니다. Figma를 직접 조작할 때는 Desktop을 실행한 컴퓨터가 생성된 패키지에 접근할 수 있어야 합니다.

```sh
git clone --branch v0.24.0 https://github.com/jonsoku-dev/figma-flow.git
cd figma-flow
git describe --tags --exact-match
codex plugin marketplace add "$PWD"
codex plugin add figma-flow@figma-flow-local
codex plugin list --marketplace figma-flow-local
```

태그는 `v0.24.0`, 목록은 `figma-flow@figma-flow-local`, `installed, enabled`, `0.24.0`이어야 합니다. Codex에서 이 폴더를 열고 새 채팅을 시작해 `$figma-flow`를 선택합니다. 같은 이름의 다른 체크아웃이 등록돼 있다면 목록의 SOURCE 경로부터 확인하세요.

## 3. 첫 비교 예제 준비

Python 3.13, Node.js 26에서 테스트했습니다. 가상환경과 설계 산출물은 클론 폴더의 **바깥**에 둡니다. 아래 명령은 같은 셸에서 순서대로 실행합니다. `workshop-run`은 새 경로여야 합니다.

```sh
PLUGIN_ROOT="$PWD"
python3.13 -m venv ../figma-flow-env
PY="$(cd ../figma-flow-env/bin && pwd)/python"
"$PY" -m pip install -r requirements-optional.txt
"$PY" -B examples/native-direction-review/demo.py --out ../workshop-run
PROJECT="$(cd ../workshop-run && pwd)"
"$PY" -B tools/design_actions.py status --manifest "$PROJECT/review/directions.json"
```

워크숍 안내 게시판과 일정표 두 안이 생성됩니다. 예제 미리보기는 동봉된 Pillow 렌더입니다. 이 시점의 예상 단계는 `NATIVE_REVIEW_PENDING`입니다. 다음 단계에 쓸 매니페스트는 `workshop-run/review/directions.json`입니다.

<a id="4-figma에서-내-프로젝트-전용-id-받기"></a>

## 4. Figma Flow 작업공간 ID를 한 번 받기

이미 등록한 Figma Flow 작업공간이 있으면 그 고정 manifest와 ID를 재사용합니다. 처음이면 다음 순서로 사용자 소유 개발 ID를 받습니다.

1. Design 파일의 왼쪽 위 **메인 메뉴 → 플러그인 → 개발**을 엽니다. 목록 아래 **새 플러그인…**을 누릅니다. 아래 첫 화면에서 나중에 사용할 **매니페스트에서 플러그인 가져오기…** 항목도 확인할 수 있습니다.
2. 이름에는 `Figma Flow`를 입력하고 **Figma Design → 다음**을 누릅니다.
3. **사용자 정의 UI(Custom UI) → 다른 이름으로 저장**을 누릅니다. 새 전용 폴더를 지정합니다.
4. 저장한 템플릿의 `manifest.json` 경로를 Codex에 전달합니다. 숫자 문자열 `id`는 Figma가 발급한 플러그인 ID이며 파일 URL의 키나 node ID가 아닙니다. 이 ID로 고정 작업공간을 구성하고 이후 모든 작업에 유지합니다. 다른 사람이 소유한 ID를 복사하지 않습니다.

![Figma 개발 메뉴에서 새 플러그인과 매니페스트 가져오기 위치](images/development-menu.png)

![플러그인 이름을 입력하고 Figma Design을 선택한 실제 창](images/new-plugin-dialog.png)

![사용자 정의 UI를 선택한 뒤 다른 이름으로 저장하는 창](images/custom-ui-template.png)

메뉴 표기는 Figma 버전·언어에 따라 달라질 수 있습니다. [Figma 공식 Quickstart](https://developers.figma.com/docs/plugins/plugin-quickstart-guide/) · [manifest의 id 설명](https://developers.figma.com/docs/plugins/manifest/)

## 5. 고정 작업공간 등록과 검토 작업 준비

아래 경로는 자신의 템플릿·비공개 작업공간으로 바꿉니다. `WORKSPACE`는 Git·공유 ZIP 밖에 두고 이후에도 같은 경로를 사용합니다.

```sh
WORKSPACE="/내/비공개/Figma-Flow-Workspace"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" init \
  --workspace "$WORKSPACE" --id-from "/내가/저장한/Figma Flow/manifest.json"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" prepare \
  --workspace "$WORKSPACE" --key workshop-review --title "워크숍 시안 검토" \
  --project "워크숍" --kind review -- \
  --manifest "$PROJECT/review/directions.json"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" list --workspace "$WORKSPACE"
```

Codex는 작업을 요청한 기본 채팅의 `CODEX_THREAD_ID`를 기록하며 하위 실행용 임의 ID로 바꾸지 않습니다. 일반 셸에서는 실제 채팅 UUID를 `prepare --thread-id UUID`로 지정할 수 있습니다. 둘 다 없으면 오프라인 작업으로 준비되고 **대화 미연결**로 표시됩니다. 잘못된 UUID는 거부하며 임의의 ID를 만들지 않습니다. 명령의 `--` 뒤에는 해당 종류의 생성기 **옵션만** 전달합니다. `--out`·`--plugin-id`·`--web-module`은 작업공간 도구가 관리합니다.

1. Figma Desktop에서 **플러그인 → 개발 → 매니페스트에서 플러그인 가져오기…**를 선택하고 고정 경로의 **`WORKSPACE/manifest.json`**을 한 번 등록합니다. 내부 `.generations`의 파일이나 개별 작업 manifest를 대신 등록하지 않습니다.
2. 같은 ID의 템플릿이 이미 등록돼 있으면 실제 등록 경로와 ID를 먼저 대조하고 템플릿을 보존한 뒤 이 고정 manifest로 등록 경로를 맞춥니다. 다른 플러그인 폴더를 덮어쓰지 않습니다.
3. 개발 메뉴에서 **Figma Flow**를 열고 **준비된 작업 → 워크숍 시안 검토 → 열기**를 누릅니다. 목록이 비어 있으면 Codex가 작업을 준비했는지 확인한 뒤 플러그인을 다시 엽니다.

![Figma 파일 선택 창에서 manifest를 등록하는 위치](images/manifest-picker.png)

같은 작업 키의 입력이 같으면 재시도는 같은 작업을 유지합니다. 바뀐 원본으로 교체할 때는 `list`가 표시한 현재 revision을 **`--replace-expected REVISION`**에 전달합니다. 작업공간 manifest와 Figma ID는 유지하고 열린 이전 창을 닫아 다시 실행합니다.

새 프로젝트 검증 후 예전 등록을 정리할 때는 [ID·경로 보관과 복원 절차](installation-and-updates.md#6-7-이전-개발-플러그인-등록-정리)를 따릅니다. 현재 고정 작업공간과 문서 데이터는 유지합니다.

**다른 ID의 기존 문서:** private plugin data는 작성한 플러그인 ID에 묶입니다. 원래 ID로 작업공간을 만들거나 원래 standalone 패키지를 유지하세요. 다른 ID의 상태·패키지를 문자열만 바꿔 넣으면 소유권이 이전되지 않습니다. 하나의 새 ID로 통합하려면 기존 ID에서 실제 읽기 자료를 보관하고 별도의 명시적 이관을 준비합니다.

## 6. 시안 만들기, 결과 저장, 대조

1. 수동 경로에서는 홈에서 검토 작업을 열고 패널에 표시된 프로젝트·후보와 대상 파일·페이지를 대조한 뒤 **검토 시안 만들기**를 누릅니다. 생성 중에는 다시 누르지 않고 완료 또는 오류 상태를 확인합니다.
2. 생성된 검토 페이지에서 후보별 데스크톱·모바일 화면, 팔레트, **주석 읽기** 보드를 확인합니다. 주석의 링크가 해당 화면·버튼으로 이동하는지, 프로토타입의 주요 버튼과 복귀 경로가 각 후보 안에서 연결되는지 봅니다.
3. 같은 창에서 **결과 JSON 저장**을 누릅니다. 예를 들어 프로젝트 안에 `review-readback.json`으로 저장합니다. 로컬 제어 연결도 사용할 수 없을 때는 사용자가 패널에서 생성·저장하고 파일 위치를 Codex에 알려 줍니다.
4. 실제로 저장된 파일 경로로 아래 명령을 실행합니다.

![0.23.0 검토 패널: 시안 생성, 상태, 결과 저장](images/panel-review.png)

위 이미지는 생성 패키지의 HTML 미리보기입니다. 실제 Figma 생성·검증의 증거는 실행 후 저장한 JSON과 해당 파일의 화면으로 확인합니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" verify-native-review \
  --manifest "$PROJECT/review/directions.json" \
  --readback "$PROJECT/review-readback.json"
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" status \
  --manifest "$PROJECT/review/directions.json"
```

검증 성공 시 `WAIT_SELECTION`입니다. 0.18.2부터는 네이티브 글자 높이·겹침·버튼 정렬도 확인합니다. 생성이 차단되면 **실패 진단 JSON 저장**으로 문제 레이어의 배정값과 실측값을 읽고, 해당 위치를 원본 레이아웃에서 수정합니다. 최종 시안은 Figma에서 내보낸 PNG를 실제 화면 크기로 열어 데스크톱과 모바일의 문구·입력 오류·로딩·완료 상태를 비교하세요. 원본과 다른 Figma 파일·패킷·후보의 결과를 썼다는 오류가 나오면, 사용한 검토 플러그인과 대상 페이지를 확인하고 다시 내보냅니다. JSON을 손으로 수정하면 재검증 근거가 사라집니다.

## 7. 비교와 실제 선택 기록

Codex가 화면을 열어 읽기 순서, 주 행동의 위치, 입력 오류·복귀, 모바일에서의 접근성을 비교하고 추천안을 설명할 수 있습니다. 검토 갤러리와 현재 리뷰 ID·해시·후보 ID를 제시한 뒤, 본제작에 사용할 후보를 사용자가 실제 채팅에서 지정합니다. Codex는 그 답이 들어 있는 로컬 관리 기록을 확인해 `design_actions.py select`와 `validate-selection`을 실행합니다. 관리 기록에는 다른 대화가 있을 수 있으므로 GitHub에 첨부하지 않습니다. 후보나 리뷰가 바뀌면 새 후보를 다시 비교합니다. [선택 명령과 기록 계약](../skills/figma-flow/references/direction-selection.md#선택과-후속-작업)

## 8. 내 기획과 디자인 시스템으로 시작

예제 대신 새 프로젝트 폴더에 기획서와 자료를 두고 Codex에 다음처럼 요청합니다.

> 첨부한 기획서로 팀원 초대 화면을 만들어 줘. 이 GitHub 저장소의 MUI 테마와 컴포넌트를 기준으로 해. 전문 분석 보고서와 모바일 캡처를 참고하고, 이메일 오류·제출 중·완료 상태를 포함해. 두 가지 배치를 비교해서 네 추천과 근거를 보여 줘. 검토 목적지는 Figma야.

Codex는 실제 적용 버전·테마·컴포넌트 경로와 상태를 확인해 `brief.md`, `research.md`, 그래프, 후보 파일과 `candidate-spec.json`을 준비합니다. 단일 텍스트 분석 보고서는 기존 `--research`에 그대로 지정할 수 있습니다. 출처가 여러 개면 핵심 관찰과 URL·커밋·파일 위치를 한 문서에 모읍니다. 코드 라이브러리에 대응해 만든 Figma 컴포넌트와 실제 연결된 Figma 라이브러리는 명세에서 구분합니다.

```sh
# 프로젝트 루트에서, 후보 원본과 에이전트의 비교 자료가 준비된 순서대로 실행
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" draft --project . \
  --brief brief.md --research research.md --from-existing candidate-spec.json \
  --review-destination figma --out reviews/r1
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" review \
  --manifest reviews/r1/directions.json --judgement agent-review.json
```

새 UI를 본제작할 때는 [디자인 검토 계약](../skills/figma-flow/references/design-review.md)에서 요구하는 Impeccable 및 제품에 적용할 디자인 스킬의 원본도 확인합니다. 브라우저에서 흐름을 재현한 캡처는 분석 자료로 쓸 수 있습니다. 최종 디자인 검토에는 해당 검사기가 허용하는 캡처 출처와 폰트·상태·에셋 증거가 필요합니다.

이후 같은 작업공간에서 검토 작업의 입력을 `reviews/r1/directions.json`으로 맞추고 6~7단계를 진행합니다. **브라우저에서만 비교하려는 요청**은 브리프에 `Local HTML only`라고 명시하고 `--review-destination local`을 사용합니다. 이 경로에서는 로컬 HTML·스크린샷을 비교하며 Figma 등록을 생략합니다. [두 디자인 시스템의 실제 비교 예시](design-system-trials.md)

## 9. 선택한 안을 Figma 본제작으로 전달

<a id="selected-rich-production"></a>

### 선택한 이미지·배치를 보존하는 본제작

풍부한 시안의 본제작은 실제 사용자 선택에 연결된 **한 방향**으로 준비합니다. Codex가 원본 검토 자료와 선택 기록을 읽고, 별도의 본제작 레이아웃·그래프·변경 요청을 고정합니다. 기존 원화·글자·글꼴·배치·이동 의미를 보존하면서 사용자가 요청한 대비 수정과 동기화 선언을 정확한 변경 전·후 값으로 연결합니다. 원래 검토 파일과 실제 읽기 자료는 덮어쓰지 않습니다.

| 입력 | 검사하는 계약 |
|---|---|
| `--selection` | 실제 관리 대화에서 확인한 선택 기록. 경로·해시·후보·사용자 원문 접두부가 현재 검토와 일치 |
| `--layout` | `figma-flow-authored-native-production-v1`, `scope: selected-production`, 선택된 후보 1개. `sourceSelection`에 선택 경로·해시, 후보 ID·해시, 검토 레이아웃 해시 보존 |
| `--product-graph` | 선택한 제품의 노드·연결·동작·프로토타입 의미 유지. 허용된 디자인 기반값과 동기화 선언만 반영 |
| `--change-request` | `figma-flow-selected-production-change-v1`. 선택·검토 레이아웃·본제작 레이아웃·본제작 그래프의 경로/해시, 실제 사용자 요청의 경로·접두부 길이/해시·원문 `directive`, `categories`, 각 변경의 `path/before/after/category` |

현재 변경 범주는 실제 요청으로 연결된 `contrast`와 `sync`입니다. `sync`는 시각 배치 변경 권한이 아닙니다. 대비용 면을 명시적으로 추가할 때는 덮는 기존 `text_ids`와 실제 범위를 선언하며, 참고 캡처 교체는 원본/새 파일의 `reference_changes` 핀으로 구분합니다. 별도 승인문이나 관리 대화 기록을 만들어 선택을 대신하지 않습니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" prepare \
  --workspace "$WORKSPACE" --key selected-production --title "선택한 방향 본제작" \
  --project "내 프로젝트" --kind review -- \
  --selection "$PROJECT/review/selection.json" \
  --layout "$PROJECT/production/native-layout.json" \
  --product-graph "$PROJECT/production/graph.json" \
  --change-request "$PROJECT/production/change-request.json" --file-key "$FILE_KEY"
"$PY" -B "$PLUGIN_ROOT/tools/figma_control.py" run --workspace "$WORKSPACE" \
  --key selected-production --operation create --file-key "$FILE_KEY" --page-id "$PAGE_ID" \
  --expected-revision "$REVISION" --timeout 120
"$PY" -B "$PLUGIN_ROOT/tools/figma_draft.py" verify-production \
  --packet "$PRODUCTION_ARTIFACTS/packet.json" --readback "$ACTUAL_READBACK"
```

경로·파일·페이지·revision은 실제 프로젝트와 `prepare`/`list` 출력에서 가져옵니다. `PAGE_ID`는 실행 시 열린 대상 페이지이며, 생성된 PRODUCTION 페이지 ID는 실제 읽기 결과에서 확인합니다. `PRODUCTION_ARTIFACTS`는 작업 준비가 반환한 `artifacts` 경로입니다. 독립 패키지가 필요하면 같은 입력을 `figma_draft.py prepare --out … --plugin-id …`에 전달할 수 있으나, 새 작업의 기본 등록은 고정 작업공간 하나입니다.

실행 패킷은 `figma-flow-native-selected-production-v1`, 반환 자료는 `figma-flow-native-selected-production-readback-v1`입니다. `verify-production`은 `sourceSelection`, 그래프·변경 요청 핀, 실제 화면·주석·컴포넌트·변수·이동과 복귀를 대조합니다. 탐색 검토용 `verify-native-review`나 탐색용 로컬 수신기로 본제작을 검증하지 않습니다. 패널의 **본제작 화면 만들기**와 JSON 저장은 로컬 명령을 쓸 수 없는 경우의 수동 경로입니다. 준비·생성·읽기·검증 완료와 새로운 선택·승인은 각각 다른 사실입니다.

<a id="contrast-evidence"></a>

### 이미지·그라디언트 위 글자의 대비 확인

`contrast-unknown`은 **대비를 판정할 수 없다는 경고**이며 낮은 대비를 측정했다는 뜻이 아닙니다. `design_quality.py`는 경로와 SHA-256이 고정된 원본 이미지, 지원하는 가로/세로 그라디언트와 기존 레이어의 합성을 사용해 글자 상자 아래 모든 배경 픽셀의 최소 대비를 보수적으로 계산합니다. 참조용 스크린샷을 원본 자산으로 대신하지 않습니다.

해시가 다르거나 지원하지 않는 변환·효과·그리기 방식, 측정 범위 제한 등으로 계산할 수 없으면 사유와 `min_ratio: null`을 남깁니다. 실제 Figma·웹의 렌더링과 확인한 한계도 함께 기록합니다. 경고를 없애기 위해 불투명 배경판을 기본으로 추가하지 않습니다. 원래 아트와 요청한 수정 범위를 유지하고, 변경이 필요하면 실제 측정과 정확한 변경 핀으로 연결합니다.

### 구조화된 `design.json` 가져오기

본제작은 **검토와 별도 작업**이며 같은 Figma Flow 작업 목록에서 엽니다. Codex가 선택 기록과 정확히 같은 제품 그래프, 디자인 원본을 읽습니다. 생성 에셋이 필요한 기획은 먼저 배치를 고정해 실제 생성 결과와 영수증을 연결합니다. 아래 예시에서 파일명은 해당 프로젝트의 실제 출력으로 바꿉니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/design_bundle.py" --design production/design.json \
  --graph selected/graph.json --selection reviews/r1/selection.json \
  --id-from "$WORKSPACE/manifest.json" --out production/bundle
# 에셋이 필요한 프로젝트는 같은 명령에 --batch BATCH.json --asset-receipts RECEIPTS.json 추가
# 이 번들 안의 개별 manifest는 등록하지 않고 아래 작업 준비에 입력으로 사용합니다.
```

1. 생성된 `production/bundle/preview/resolved.json`의 실제 SHA-256을 확인하고 다음처럼 같은 작업공간에 본제작 작업을 준비합니다. `REVIEWED_SHA256`은 해당 파일을 검토한 실제 해시입니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" prepare \
  --workspace "$WORKSPACE" --key invite-production --title "팀 초대 본제작" \
  --project "팀 초대" --kind import -- \
  --input production/bundle/preview/resolved.json --reviewed-sha256 "$REVIEWED_SHA256" \
  --selection reviews/r1/selection.json --product-graph selected/graph.json
```

2. 고정 플러그인을 다시 실행하고 **준비된 작업 → 팀 초대 본제작 → 열기**를 선택합니다. 제목 근처의 입력 디자인과 현재 페이지를 확인하고 **가져오기 · 기존 페이지 열기**를 누릅니다. 같은 원본은 편집을 유지한 채 기존 페이지를 엽니다. 별도 복사본이 필요할 때만 **별도 페이지로 새로 가져오기**를 선택한 뒤 **새 페이지로 가져오기**를 누릅니다.
3. 화면과 컴포넌트를 확인하고 **현재 디자인 읽기**를 누릅니다. 완료 후 나타나는 **JSON 파일 저장**으로 읽기 결과를 보관합니다. **JSON 원문 확인**은 선택 사항이며 파일 저장을 위해 열 필요가 없습니다. **앱에 반영**은 연결된 앱이 있는 패키지에만 나타납니다.

![0.23.0 가져오기 패널: 기존 페이지 열기와 별도 복사본 선택](images/panel-import.png)

위 이미지는 생성 패키지의 HTML 미리보기입니다. 본제작의 실제 Figma 실행 결과를 대신하지 않습니다.

![과거 캠페인의 실제 Figma 결과 예시: 별씨 정원의 데스크톱과 모바일 화면](images/finished-preview.jpg)

4. `prepare` 출력의 실제 `artifacts` 경로를 `IMPORT_ARTIFACTS`로 보관합니다. 현재 작업이 생성한 기대 계약과 같은 읽기 결과로 두 검사를 실행합니다. 예시 JSON은 프로젝트의 `production/production-readback.json`에 저장했다고 가정합니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/figma_bridge.py" --inspect-readback production/production-readback.json \
  --input production/bundle/preview/resolved.json \
  --expected "$IMPORT_ARTIFACTS/expected-native-handoff.json" --require-match
"$PY" -B "$PLUGIN_ROOT/tools/native_handoff.py" --readback production/production-readback.json \
  --contract "$IMPORT_ARTIFACTS/expected-native-handoff.json" --out production/native-handoff
```

첫 검사는 종료 코드 0과 `matches_supplied_source: true`, 두 번째는 `report.json`의 `passed: true`를 확인합니다. `screen-spec.md`에서 실제 화면·조작·상태·토큰을 읽을 수 있습니다. 프로젝트 전체는 실제 앱·상태·테스트와 `bindings.json`을 연결한 뒤 `check_project.py --init --brief … --graph … --bindings … --out 새_검사_폴더`로 확인합니다. `summary.json`에서 신선도·네이티브 전달·디자인 검토를 각각 읽으세요. 게임 캠페인의 Figma 생성 스킨과 글자 길이 측정은 0.18 계열의 미완료 범위입니다.

## 10. 그래프와 Figma 컴포넌트 동기화

컴포넌트의 디자인 값을 그래프 정본으로 관리하고 실제 Figma·웹과 왕복하려면 [Graph SSOT 명령 가이드](../examples/graph-ssot/README.md)를 사용합니다. 본제작의 사용자 선택과 실제 화면 검증은 계속 별도입니다.

1. 아래 [Graph SSOT 가이드](../examples/graph-ssot/README.md)의 `figma_workspace.py prepare --kind discover` 예제로 읽기 작업을 준비하고 홈에서 엽니다. **Figma 값 읽기** 패널의 페이지 범위를 확인한 뒤 **Figma 값 읽고 저장**을 누릅니다. `graph-native-discovery.json`이 다운로드됩니다. 생성·이관·값 변경은 실행하지 않습니다.

![읽기 전용 Figma 값 읽기 패널](images/panel-discovery.png)

위 이미지는 생성된 읽기 전용 패키지의 HTML 미리보기입니다.

2. 실제 읽기 결과로 `prepare --kind sync --` 뒤에 `--adopt` 또는 기존 `--pairing` 옵션을 전달합니다. 홈에서 그 **그래프 동기화** 작업을 열어 **컴포넌트 동기화**로 들어갑니다. **Figma 값 읽고 저장**은 현재 상태만 읽습니다. **적용 범위 확인**도 쓰기 전 확인 단계이며, 토큰 변경·새 토큰·연결 조정과 영향을 받는 메인·인스턴스를 표시합니다.
3. 범위가 맞으면 **확인한 범위에 적용**을 누릅니다. **취소**는 확인창만 닫으며 적용하지 않습니다. 이미 시작한 적용을 되돌리는 버튼은 아닙니다. 실제 쓰기 이후에는 완료 또는 복구 상태를 기다립니다.
4. 완료 시 `graph-token-readback.json`이 자동 다운로드됩니다. 다운로드를 놓쳤으면 **JSON 다시 저장**을 누릅니다. 오류에서도 마지막 자료와 **실행 기록과 복구 정보**를 보관하세요. 이전 성공 자료를 현재 실행의 성공으로 사용하지 않습니다. 충돌은 실제 상태를 다시 읽고 새 계획으로 해결하며, 복구 충돌이 있으면 자동 재적용하지 않습니다.
5. 실제 웹 화면의 값을 읽고 `graph_sync.py pair`로 현재 네이티브·웹 결과를 대조합니다. Figma 완료 메시지만으로 웹 반영이나 디자인 승인을 판단하지 않습니다.

![실제 Figma에서 연 컴포넌트 동기화 패널의 범위 확인과 적용](images/panel-graph-sync.png)

![그래프 값의 적용 전·후와 색·길이 차이를 보여 주는 확인 패널](images/panel-graph-diff.png)

위 이미지는 실제 Figma에서 연 동기화 패널입니다. 파일 키 등 비공개 정보는 가렸습니다. 특정 프로젝트의 실행 장면이며 다른 프로젝트의 적용 성공을 보증하지 않습니다.

작업이 갱신되지 않으면 Codex 설치 버전만 확인하지 말고, 같은 작업 키의 revision과 고정 등록 경로를 대조하고 [작업을 재생성한 뒤 플러그인을 다시 실행](installation-and-updates.md#6-3-figma-개발-플러그인-갱신-computer-use-없음)했는지 확인하세요.

<a id="prepared-native-edit"></a>

### 준비된 JSON으로 Figma 값 편집하기

`native-edit`는 그래프 동기화와 구분되는 작업 종류입니다. operation은 `read`와 `apply`이며, 허용한 JSON 계획을 플러그인 안의 Figma API로 실행합니다. 임의 JavaScript를 전달하거나 Computer Use로 버튼을 조작하지 않습니다. 계획 준비만으로 Figma를 변경하지 않습니다.

예시는 ID와 값을 실제 getter 자료로 바꿔 사용합니다.

```json
{
  "schema": "figma-flow-native-edit-plan-v1",
  "file_key": "FILE",
  "page_id": "12:1",
  "edits": [
    {"node_id": "12:3", "main_id": "12:2", "field": "fontSize", "before": 18, "after": 20}
  ]
}
```

현재 노드 편집은 로컬 메인 컴포넌트와 그 안의 명시된 텍스트를 대상으로 하며 `fontSize`, `fontFamily`, `paddingLeft`, `paddingRight`, `backgroundColor`, `color`, `borderRadius`를 지원합니다. 텍스트에는 `main_id`를 지정하고 한 트랜잭션에서 같은 텍스트의 글꼴 변경은 하나만 선언합니다. 노드 편집은 1–32개, 계획 JSON은 최대 128,000바이트입니다. `edits` 대신 `variableedit: {variable_id, mode_id, before, after}`로 해당 페이지에서 사용하는 로컬 변수의 한 모드 값을 준비할 수도 있습니다. 같은 변수의 연결된 소비자는 그 값을 함께 사용합니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" prepare --workspace "$WORKSPACE" \
  --key selected-font-edit --title "선택한 컴포넌트 글자 크기" --project "내 프로젝트" \
  --kind native-edit -- --plan "$PROJECT/native-edit.json"
"$PY" -B "$PLUGIN_ROOT/tools/figma_control.py" run --workspace "$WORKSPACE" \
  --key selected-font-edit --operation apply --file-key "$FILE_KEY" --page-id "$PAGE_ID" \
  --expected-revision "$REVISION" --timeout 120
```

정확한 파일·페이지·노드/변수·모드·현재 revision과 실제 `before` 값이 일치해야 적용합니다. 반환 자료의 `native_edit.plan_sha256`, `applied`, 실제 전후 값을 확인하고, 실패 시 복구 자료와 충돌을 보존합니다. 결과가 `uncertain`이면 쓰기를 자동 재시도하지 않고 현재 범위를 다시 읽어 복구합니다. `native-edit`는 Figma 값을 먼저 편집하므로 그래프 정본 반영은 아래 [직접 편집 역수입 절차](../examples/graph-ssot/README.md#designer-edits-to-graph)로 별도 수행합니다. 새 리비전 준비·재시작·수동 JSON 대체 경로는 다른 작업과 같습니다.

## 11. 작업을 준비한 Codex 채팅으로 연결

홈의 작업 옆 또는 실행이 끝난 작업 상단의 **Codex 연결**을 누릅니다. 대상은 그 작업에 기록된 원래 thread ID입니다. 화면 전환 시 입력은 초기화되므로 저장할 결과는 먼저 보관하세요. 현재 데스크톱에서 앞에 떠 있는 채팅을 추정해 전송하지 않습니다. 오프라인 작업에 thread가 없으면 연결 버튼은 비활성입니다.

1. 선택한 Figma 노드에 대한 요청을 적고 **보낼 내용 확인**을 누릅니다. 노드를 포함하면 요청 문장은 생략할 수 있고, 선택이 없으면 요청이 필요합니다. **현재 선택한 노드 포함**은 ID·이름·종류·위치·크기와 파일/페이지 링크를 미리보기에 담습니다. 전체 페이지를 순회하거나 이미지·전체 문서를 자동 첨부하지 않습니다.
2. 선택 노드는 최대 20개입니다. 텍스트는 기본 제외되며 **선택한 텍스트 일부 포함**을 직접 선택할 때만 노드당 200자·합계 1000자 이내를 넣습니다. 이름·문구·링크도 공개해도 되는지 **실제로 전달할 내용**을 확인합니다.
3. 기본 경로는 **내용 복사 → 링크로 채팅 열기 → 직접 붙여 넣기·전송**입니다. 복사가 차단되면 선택된 미리보기 내용을 복사 단축키로 보관합니다. 링크는 원래 채팅을 여는 요청이며 메시지를 자동 전송하지 않습니다.
4. 로컬 relay를 설정했다면 **채팅 열기**와 **채팅에 보내기**도 사용할 수 있습니다. 보내기는 확인한 미리보기와 같은 텍스트를 해당 채팅의 대기열에 넣습니다. **채팅 대기열에 추가했습니다**는 에이전트가 읽거나 실행했다는 뜻이 아닙니다. Codex에서 실제 접수와 다음 작업을 확인하세요.

선택적 relay는 작업공간을 준비·갱신하는 지원 POSIX 환경에서 다음과 같이 설정합니다. `43179`는 예시 포트이며 기존 작업공간에 다른 포트가 있으면 그 설정을 확인해 사용합니다. 고정 manifest를 다시 실행해야 추가된 연결 설정을 읽습니다.

```sh
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" init \
  --workspace "$WORKSPACE" --id-from "$WORKSPACE/manifest.json" --chat-port 43179
"$PY" -B "$PLUGIN_ROOT/tools/workspace_chat.py" --workspace "$WORKSPACE"
```

relay를 실행하지 않아도 복사·명시적 링크 열기는 가능합니다. relay는 비공개 작업공간의 작업·thread·revision과 인증을 대조합니다. 직접 큐 전송에는 `PATH`의 공식 Codex CLI가 필요하며, Windows에서 relay를 별도로 사용하는 경우 native `codex.exe`가 필요합니다. 비밀값이 든 작업공간을 공개 ZIP·Git·지원 로그로 공유하지 않습니다. 접수 여부가 불확실하면 원래 채팅을 먼저 확인하고 같은 요청을 자동 재전송하지 않습니다.

공식 동작은 [Codex 앱 명령과 채팅 링크](https://learn.chatgpt.com/docs/app/commands), [Codex CLI `queue`](https://learn.chatgpt.com/docs/cli/reference#codex-queue)를 참고하세요. 이 연결이 Figma 적용·디자인 선택·후속 실행의 승인을 대신하지 않습니다.

디자인 비평의 출처와 각색 범위는 [Unslop attribution](../README.md#라이선스와-참고)을 참고하세요.

## 막힌 위치 찾기

| 보이는 현상 | 확인할 위치와 다음 행동 |
|---|---|
| Codex에서 플러그인이 보이지 않음 | `codex plugin list --marketplace figma-flow-local`에서 설치 경로·버전·활성 여부를 확인하고 새 Codex 채팅을 엽니다. |
| Figma에서 manifest 오류, 다른 작업이 열림 | 고정 `WORKSPACE/manifest.json`의 실제 등록 경로·ID와 홈의 프로젝트·작업 키를 확인합니다. 개별 작업 manifest 등록은 standalone 호환용입니다. |
| 품질 검사에서 패키지 생성 중단 | `design-quality.json`의 오류가 지목한 레이어·버튼·폰트를 고친 다음 원본과 검토 패킷을 다시 생성합니다. |
| 임베드 에셋 용량 경고 | base64 합계가 4 MB를 넘었다는 뜻입니다. 생성된 ZIP은 사용할 수 있습니다. 줄일 경우 원본이 달라지므로 다시 패키징·검증합니다. |
| 저장 버튼이 없거나 비활성 | 가져오기는 읽기가 끝나면 **JSON 파일 저장**이 나타납니다. 검토는 시안 생성 또는 진단 자료가 필요합니다. 그래프 패널은 읽기·적용 후 **JSON 다시 저장**을 사용합니다. |
| 열기 대신 다른 파일로 표시됨 | 홈에 표시된 지정 Design 파일에서 같은 Figma Flow를 다시 엽니다. 파일 범위를 임의로 바꾸지 않습니다. |
| 대화 미연결 또는 전송 비활성 | 실제 원래 thread ID와 선택적 relay 연결을 확인합니다. thread가 없는 오프라인 작업은 그대로 사용할 수 있고, 자동 추정하지 않습니다. |
| 업데이트했는데 예전 작업이 보임 | 새 설치본으로 같은 작업 키를 갱신하고 `list`의 revision·고정 등록 경로를 확인합니다. 열린 플러그인 창을 닫고 다시 실행합니다. |
| 페이지 부족, 끊긴 연결 | 편집 가능한 여유 페이지와 연결 상태를 확인한 다음 대상에 맞게 다시 실행합니다. 기존 페이지·파일을 삭제할 필요는 없습니다. |
| 검사 결과가 stale 또는 blocked | `freshness_unverified`의 노드·사유·누락 파일과 개별 검사 영수증을 확인합니다. 실제 원본·근거를 보완하고 새 출력 폴더에서 다시 검사합니다. |
