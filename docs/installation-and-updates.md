# 프롬프트로 설치하고 Figma 연결·업데이트까지 진행하기

Codex가 저장소 확인, Codex 플러그인 설치, 한 번 등록한 Figma 작업공간의 작업 준비와 실제 읽기 결과 검증을 담당합니다. Computer Use를 사용할 수 있으면 허용된 Figma Desktop 조작도 맡깁니다. 사용할 수 없으면 같은 파일을 만들고 같은 검사 명령을 쓰며, 사용자가 Figma 버튼을 누르고 결과 JSON을 전달합니다.

이 문서는 **로컬 파일·CLI 실행이 가능한 Codex**와 macOS/Windows의 Figma Desktop을 기준으로 합니다. Codex 자체의 최초 로그인, GitHub 인증, Figma 로그인과 조직 접근 승인은 사용자 단계입니다. Computer Use가 없다는 이유로 CLI·파일 실행까지 불가능한 것은 아닙니다. 원격 Codex에서 파일을 만들면 Figma Desktop이 있는 컴퓨터로 패키지 전체를 전달해야 합니다. 브라우저 전용 Figma에서는 이 개발 플러그인 등록 경로를 완료할 수 없습니다. [Figma 공식 개발 플러그인 안내](https://help.figma.com/hc/en-us/articles/360042786733-Create-a-classic-plugin-for-development)

현재 설치 기준은 **0.22.0**입니다. 단일 작업공간 CLI는 현재 POSIX 파일 보호를 지원하는 macOS/Linux에서 준비·갱신합니다. Windows 로컬 CLI는 standalone 호환 경로를 유지하며, POSIX에서 준비한 폴더를 다른 머신으로 전달하는 경우 실제 실행 범위를 따로 검증합니다. 원본 태그 `v0.22.0`, 설치 목록, 설치 복사본의 두 플러그인 매니페스트 버전을 대조하세요. Figma에는 고정 `WORKSPACE/manifest.json` 하나를 등록합니다. Codex가 프로젝트별 작업을 준비·갱신하고 사용자는 홈에서 실제 작업을 선택합니다. 작업을 갱신한 뒤 열린 창을 닫고 같은 플러그인을 다시 실행합니다.

## 1. 클론 전부터 Codex에 맡기기

Codex에서 비어 있는 작업 폴더를 열고 아래 프롬프트 하나를 보냅니다. 회사 저장소라면 URL을 회사 private URL로 바꿉니다. 최초 설치에는 `$figma-plugin-setup`이 아직 없으므로 일반 프롬프트로 시작합니다. 새 스킬이 포함된 회사 릴리스·브랜치를 지정하세요. 과거 릴리스에 새 스킬이 있다고 가정하지 않습니다.

### A. Computer Use 사용 가능

```text
이 빈 작업 폴더에서 Figma Flow를 처음부터 설치하고 실제 Figma 연결 테스트까지 진행해 줘.
저장소: https://github.com/jonsoku-dev/figma-flow.git
설치할 버전: v0.22.0
Computer Use: 가능. 허용 범위는 연습용 Figma Desktop Design 파일, 개발 플러그인 메뉴와 관련 파일 선택/저장 창이야.

1. 기존 폴더·Git 작업·Codex 마켓플레이스·설치를 먼저 읽고 보존해. private이면 내 Git 인증으로 읽을 수 있는지 확인해. v0.22.0 태그와 정확한 커밋을 기록해. 이미 등록된 다른 회사/개인 소스를 바꾸지 마.
2. 새 전용 폴더에 해당 버전을 클론해 docs/installation-and-updates.md, docs/npm-environment.md를 읽어. 두 플러그인 매니페스트의 버전과 마켓플레이스 이름·경로를 대조하고 현재 Codex CLI --help 문법으로 Codex 플러그인을 먼저 설치해. add 결과의 installedPath와 list의 installed/enabled/version/source를 확인해. 새 스킬이 현재 채팅에 안 보이면 정확한 이어가기 프롬프트를 남겨 새 채팅에서 쓰게 해.
3. 설치된 skills/figma-plugin-setup/SKILL.md에 따라 나머지를 진행해. 회사 npm 레지스트리의 전체 HTTPS URL과 전체 미러/패키지 스코프 여부를 먼저 내게 물어보고 프로젝트 .npmrc만 설정해. 도메인만 주면 필요한 서비스 경로를 추가로 확인해. 토큰은 요청하지 마. .nvmrc의 LTS 버전, Python 가상환경과 의존성을 확인하고 lockfile을 생성·Git 추적하지 마.
4. 새 워크숍 폴더에 동봉 예제를 생성하고 NATIVE_REVIEW_PENDING을 확인해. 내 연습용 Design 파일과 등록된 Figma Flow 작업공간 manifest·ID를 확인해. 최초에만 Figma Desktop의 새 플러그인에서 사용자 소유 ID를 발급받고 고정 작업공간을 등록해. 로그인·접근 승인과 앱이 요구하는 사용자 확인은 내가 해.
5. figma_workspace.py prepare --kind review로 현재 채팅 thread ID를 가진 검토 작업을 준비해. Figma Flow의 준비된 작업에서 프로젝트·제목·범위를 대조하고 열기 → 검토 시안 만들기 → 완료 확인 → 결과 JSON 저장을 진행해. 실제 저장한 JSON으로 verify-native-review와 status를 실행하고 WAIT_SELECTION인지 확인해.
6. 데스크톱·모바일의 글자 잘림, 주요 버튼과 복귀, 주석 링크를 실제로 확인하고 비교·추천해. 내가 특정 후보를 선택하기 전에는 본제작이나 선택 기록을 만들지 마.
7. 실제 명령과 종료 코드, 설치/패키지/읽기 결과의 절대 경로, 검증한 범위, 사용자에게 필요한 다음 행동을 한국어로 보고해. 패키지 생성이나 오프라인 테스트를 실제 Figma 실행 성공으로 보고하지 마.
8. 원격 Codex라면 Figma Desktop이 있는 PC에 전체 패키지 ZIP을 전달해. Computer Use가 중단되면 현재 패키지를 보존하고 문서 4절의 다음 수동 단계부터 안내해. 실제 JSON이 없으면 Figma 검증은 pending이야.
```

### B. Computer Use 사용 불가능

```text
이 빈 작업 폴더에서 Figma Flow를 처음부터 설치하고 실제 Figma 연결 테스트까지 진행해 줘.
저장소: https://github.com/jonsoku-dev/figma-flow.git
설치할 버전: v0.22.0
Computer Use: 불가능. CLI·파일 작업은 네가 하고 Figma Desktop 버튼은 내가 누를 거야.

1. 기존 폴더·Git 작업·Codex 마켓플레이스·설치를 먼저 읽고 보존해. private이면 내 Git 인증으로 접근을 확인해. 새 전용 폴더에 검증한 버전을 클론하고 태그·커밋·두 매니페스트 버전·마켓플레이스 이름을 기록해. 두 매니페스트가 0.22.0인지 대조해.
2. docs/installation-and-updates.md와 현재 CLI --help에 따라 Codex 플러그인을 먼저 설치하고 installedPath, installed/enabled/version/source를 확인해. 새 skills/figma-plugin-setup/SKILL.md를 사용해. 새 채팅이 필요하면 정확한 설치 경로와 이어가기 프롬프트를 줘.
3. docs/npm-environment.md에 따라 회사 npm URL과 전체 미러/스코프 여부를 내게 물어보고 프로젝트 .npmrc를 설정해. 인증값은 요청하지 마. .nvmrc의 LTS, Python 가상환경과 의존성을 확인하고 lockfile은 생성·Git 추적하지 마.
4. 새 워크숍 폴더에서 동봉 예제를 생성하고 NATIVE_REVIEW_PENDING, 후보 ID와 검토 HTML 경로를 알려 줘. 내 첫 Figma 작업은 새 연습용 Design 파일 열기 → 플러그인 → 개발 → 새 플러그인 → Figma Design → 사용자 정의 UI → 전용 폴더에 저장이야. 이미 Figma Flow 작업공간이 있으면 고정 manifest 경로·ID를 재사용해.
5. 내가 저장한 manifest.json에서 실제 ID를 읽어 figma_workspace.py init으로 비공개 고정 작업공간을 준비하고 prepare --kind review로 현재 채팅에 연결된 작업을 만들어. 원격이면 숨김 .generations를 포함한 작업공간 전체를 내 PC로 전달해.
6. 최초 한 번 고정 WORKSPACE/manifest.json 등록 → Figma Flow 실행 → 준비된 작업에서 해당 프로젝트의 검토 작업 열기 → 검토 시안 만들기 → 완료 확인 → 결과 JSON 저장 순서로 안내해. 완료 후 작업 목록으로 돌아가. 새 프로젝트마다 새 ID나 manifest 등록을 요구하지 마. 다른 ID의 기존 private data는 자동 이관하지 마.
7. 결과 파일을 받기 전에는 Figma 검증을 pending으로 유지해. 내가 저장 경로/파일을 주면 verify-native-review와 status를 실행해 WAIT_SELECTION을 확인해. 실제 Figma PNG와 버튼·복귀·주석 링크의 수동 확인 방법도 줘. 관찰하지 못한 항목은 미확인으로 표시해.
8. 같은 후보를 비교·추천하고 실제 사용자 선택 전에는 선택 기록·본제작을 만들지 마. 실제 명령·종료 코드, 설치/패키지/읽기 결과의 경로와 남은 수동 단계·이어가기 프롬프트를 한국어로 보고해. Figma 목적지를 HTML로 바꾸지 마.
```

두 프롬프트는 첫 Figma 조작과 JSON 전달에서 사람이 개입합니다. Computer Use도 계정 로그인·접근 승인·앱 확인을 없애지는 못합니다. CLI나 파일 기능이 없는 Codex에서는 로컬 실행 가능한 Codex로 전환하거나 아래 명령을 사용자가 직접 실행합니다.

## 2. 단계별 담당과 완료 기준

| 단계 | Computer Use 사용 | Computer Use 없음 | 완료 기준 |
|---|---|---|---|
| 저장소·릴리스·npm·Node 확인 | Codex CLI/파일 | 동일 | 정확한 원본·커밋, LTS, 사용자 지정 npm 범위 |
| Codex 플러그인 설치 | Codex CLI | 동일 | 설치 경로·버전·소스·enabled 확인 |
| 예제·Figma 작업 준비 | Codex CLI | 동일 | 현재 리뷰·후보·고정 manifest·작업 키/revision |
| Figma ID 발급·작업공간 등록 | 최초 한 번의 허용된 Desktop 조작 | 최초 한 번 사용자 조작 | 실제 소유 ID와 고정 manifest 등록 경로 |
| Figma 시안 생성·JSON 저장 | 허용된 Desktop 조작 | 사용자 조작 | 현재 리뷰에서 실제 내보낸 JSON |
| 원본과 읽기 결과 비교 | Codex CLI | 동일 | 검증 성공과 `WAIT_SELECTION` |
| 화면·프로토타입 확인 | 실제 화면에서 관찰 | 사용자 조작·내보낸 PNG로 확인 | 관찰 결과와 미확인 항목 구분 |
| 후보 선택 | 실제 사용자 답변 | 동일 | 현재 리뷰의 특정 후보에 대한 사용자 선택 |

## 3. 파일·CLI 설치의 실제 명령

아래는 macOS/Linux에서 이미 해당 릴리스를 클론한 경우입니다. Windows에서는 `py -3.13 -m venv`와 `Scripts/python.exe` 경로를 사용하며, Codex에게 PowerShell 명령으로 변환하도록 요청할 수 있습니다. 패키지 생성·Figma 등록·검증 기준은 같습니다.

```sh
PLUGIN_SOURCE="$PWD"
codex plugin marketplace list --json
codex plugin marketplace add "$PLUGIN_SOURCE" --json
```

`.agents/plugins/marketplace.json`에서 실제 이름을 읽고 설치합니다. 공개 기본값은 `figma-flow-local`이고 회사 복제본은 바뀔 수 있습니다. 같은 이름의 기존 소스가 다른 경로를 가리키면 먼저 비교하고 별도 이름을 사용합니다.

```sh
MARKETPLACE=$(python3 -c 'import json; print(json.load(open(".agents/plugins/marketplace.json"))["name"])')
codex plugin add "figma-flow@$MARKETPLACE" --json
codex plugin list --marketplace "$MARKETPLACE" --json
```

`add` 결과의 **실제 `installedPath`**를 다음 변수에 넣습니다. 설치 캐시 위치를 직접 조합하지 않습니다. 목록의 `source.path`는 원본 소스 경로일 수 있어 설치 캐시와 동일하다고 가정하지 않습니다. `add` 결과를 잃었다면 같은 플러그인의 지원되는 설치 조회/`add --json` 결과나 호스트가 제공하는 설치 메타데이터로 실제 경로를 확인합니다. [OpenAI CLI 명령과 출력 필드](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

```sh
PLUGIN_ROOT="/위 add 결과의 installedPath"
PROJECT_PARENT="/새 워크숍을 만들 상위 폴더"
python3.13 -m venv "$PROJECT_PARENT/figma-flow-env"
PY="$PROJECT_PARENT/figma-flow-env/bin/python"
"$PY" -m pip install -r "$PLUGIN_ROOT/requirements-optional.txt"
"$PY" -B "$PLUGIN_ROOT/tools/skill_dependencies.py" --check
"$PY" -B "$PLUGIN_ROOT/examples/native-direction-review/demo.py" --out "$PROJECT_PARENT/workshop-run"
PROJECT="$PROJECT_PARENT/workshop-run"
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" status --manifest "$PROJECT/review/directions.json"
```

사전에 [npm·LTS 설정](npm-environment.md)을 완료합니다. 이 저장소 루트는 npm 앱이 아니며 `npm install`이나 `npm ci`가 필요하지 않습니다. 예제는 Python 의존성을 사용합니다. [동봉 스킬 검사](../skills/figma-flow/references/skill-dependencies.md)가 `ready`인지 확인하고 진행합니다. 과거 릴리스에는 새 검사·동봉 원문이 없으므로 해당 버전의 설치 절차를 사용합니다. 예제 생성 뒤 상태는 `NATIVE_REVIEW_PENDING`이어야 하며, 이 단계만으로 실제 Figma 화면이 생기지는 않습니다. `workshop-run`은 새 폴더여야 합니다.

Codex 플러그인 설치 후 새 채팅이 필요하면 다음처럼 이어갑니다. 사용자가 새 채팅을 열고 이 프롬프트를 보냅니다.

```text
$figma-plugin-setup 설치된 Figma Flow의 Figma 연결 테스트를 이어가 줘.
Codex 플러그인 ID: [figma-flow@실제 marketplace]
설치 경로: [installedPath 절대 경로], 버전/커밋: [확인한 값]
워크숍: [절대 경로 또는 아직 생성 전], Python: [가상환경 실행 파일 절대 경로]
Computer Use: [가능/불가능]. 완료한 단계를 재실행하지 말고 현재 파일과 상태를 다시 확인해 이어가.
```

## 4. Computer Use가 없는 경우의 Figma 조작

다음 단계는 Computer Use 사용자가 Codex에 맡기는 작업과 동일합니다. 새 연습용 Design 파일에서 진행하세요. Figma의 일반 Design 모드에서 작업하며 Dev Mode는 필요하지 않습니다. 실제 메뉴 캡처는 [기존 그림 가이드](figma-guide.md#4-figma에서-내-프로젝트-전용-id-받기)에 있습니다.

### 4-1. 개발 플러그인 ID를 받기

1. Figma Desktop에서 연습용 **Figma Design** 파일을 엽니다.
2. **메인 메뉴 → 플러그인 → 개발 → 새 플러그인…**을 선택합니다.
3. 작업공간 이름(예: `Figma Flow`)을 입력하고 **Figma Design → 사용자 정의 UI(Custom UI)**를 선택합니다.
4. 새 전용 폴더에 저장합니다. 기존 플러그인 폴더는 선택하지 않습니다.
5. 그 폴더의 `manifest.json` 경로를 Codex에 전달합니다. 별도 머신이면 해당 파일만 첨부할 수 있습니다. ID는 JSON의 숫자 **문자열** 그대로 사용합니다.

```text
Figma Flow용 템플릿 또는 기존 작업공간의 manifest.json은 [내 PC의 절대 경로]야.
이 ID를 유지하는 고정 작업공간을 구성하고 현재 워크숍의 검토 작업을 준비해 줘. 기존 작업은 보존해.
```

Figma 파일 URL의 키나 `12:34` 형태의 node ID는 개발 플러그인 ID가 아닙니다. 프로젝트·작업 종류가 달라도 같은 작업공간 ID를 유지합니다. 다른 ID로 작성한 기존 문서는 그 ID의 private plugin data를 사용하므로 원래 ID·패키지를 보존하고, [ID와 명시적 이관 기준](figma-guide.md#5-고정-작업공간-등록과-검토-작업-준비)을 먼저 확인합니다.

### 4-2. Codex가 작업공간과 검토 작업 준비

```sh
WORKSPACE="/내/비공개/Figma-Flow-Workspace"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" init \
  --workspace "$WORKSPACE" --id-from "/Figma에서 저장한 템플릿/manifest.json"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" prepare \
  --workspace "$WORKSPACE" --key workshop-review --title "워크숍 시안 검토" \
  --project "워크숍" --kind review -- --manifest "$PROJECT/review/directions.json"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" list --workspace "$WORKSPACE"
```

Codex 실행의 `CODEX_THREAD_ID` 또는 명시적인 실제 `--thread-id UUID`로 원래 채팅을 기록합니다. 둘 다 없으면 thread 없는 오프라인 작업이 되며 **대화 미연결**로 표시됩니다. 잘못된 명시적 UUID는 거부합니다. `--` 뒤에는 생성기 옵션만 전달합니다. 출력 위치·플러그인 ID·웹 모듈 경로는 작업공간 도구가 관리합니다. 원격 Codex에서 생성했다면 **숨김 `.generations`를 포함한 작업공간 전체**를 Desktop 머신에 전달하고 같은 구조를 유지합니다. 개별 작업의 manifest는 기본 등록 대상이 아닙니다.

### 4-3. 최초 등록하고 작업 열기

1. 최초에만 **플러그인 → 개발 → 매니페스트에서 플러그인 가져오기…**에서 고정 **`WORKSPACE/manifest.json`**을 선택합니다.
2. 같은 ID의 템플릿과 중복이면 실제 ID·등록 경로를 대조하고 템플릿을 보존한 뒤 고정 manifest로 등록 경로를 맞춥니다. 다른 플러그인 폴더는 덮어쓰지 않습니다.
3. **Figma Flow → 준비된 작업**에서 프로젝트·제목·작업 종류·대상 범위를 확인하고 검토 작업의 **열기**를 누릅니다. 홈은 작업 목록이며 선택·승인 기록이 아닙니다.
4. **검토 시안 만들기**를 누르고 완료 메시지를 기다립니다. 생성된 페이지에서 후보별 데스크톱·모바일, 팔레트, 주석 보드를 확인합니다.
5. **결과 JSON 저장**으로 보관한 뒤 **작업 목록으로** 돌아갑니다. 실행 중에는 완료·오류를 기다립니다. 실제 파일을 Codex에 전달해야 검증이 이어집니다.

같은 키의 입력을 바꾸려면 `list`의 현재 revision을 `prepare --replace-expected REVISION`에 전달해 교체합니다. 변경 없는 재시도는 동일 작업을 유지합니다. 작업 준비 뒤 열린 이전 창을 닫고 **같은 Figma Flow**를 다시 실행하며, 새 ID를 만들거나 manifest를 반복 등록하지 않습니다.

### 4-4. Codex에 결과 전달하기

```text
현재 워크숍에서 결과 JSON을 저장했어: [절대 경로 또는 첨부 파일].
현재 review/directions.json과 verify-native-review로 대조하고 status도 확인해 줘.
성공/실패와 실제 관찰한 항목을 알려 줘. 아직 후보를 선택한 것은 아니야.
```

```sh
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" verify-native-review \
  --manifest "$PROJECT/review/directions.json" --readback "$PROJECT/review-readback.json"
"$PY" -B "$PLUGIN_ROOT/tools/design_actions.py" status --manifest "$PROJECT/review/directions.json"
```

실제 현재 리뷰와 일치해 검증이 성공하면 `WAIT_SELECTION`입니다. 파일을 전달받기 전까지 Codex는 “Figma 실행·읽기 검증 대기”로 보고합니다. 오류는 **상세 진단 보기**에서 확인합니다. 화면 배치 검증 실패 시 **실패 진단 JSON 저장**을 사용하고, 읽기 결과나 검사 조건을 고치지 말고 원본 레이아웃을 수정합니다.

### 4-5. 화면·조작 확인

후보별 데스크톱·모바일 프레임을 실제 크기로 보고 글자 잘림·겹침, 버튼 정렬, 입력 오류·로딩·완료 상태를 확인합니다. 프로토타입의 주요 버튼과 복귀 경로를 재생하고 주석 보드의 링크가 대상 화면으로 가는지 확인합니다. Figma에서 프레임 PNG를 내보내 Codex에 전달하면 이미지 비교도 맡길 수 있습니다. 사용자 계정·파일 키·초대 링크가 보이는 전체 화면 캡처는 필요하지 않습니다.

읽기 검증 통과, 프로토타입 재생, 사용자 디자인 선택은 각각 다른 증거입니다. Codex는 관찰한 범위만 보고하며, 사람이 결과를 “저장했다”고 말한 것만으로 JSON 비교가 통과했다고 쓰지 않습니다.

## 5. Computer Use 사용 시의 같은 검사

Codex가 허용된 Figma Desktop에서 4-1~4-5를 진행합니다. 시작 전에 대상 파일·프로젝트·허용 동작과 고정 작업공간 경로를 특정합니다. 계정 로그인과 접근 승인, 앱에서 요구하는 사용자 확인은 사용자에게 넘깁니다. 승인된 앱/사이트만 사용합니다.

접근이 거절되거나 Computer Use가 끊기면 이미 생성한 예제·패키지를 보존하고 4절의 해당 단계부터 이어갑니다. 새 개발 ID를 중복 발급하거나 자동화 편의를 위해 공개 배포할 필요가 없습니다. 성공 보고에는 같은 실제 JSON 검증과 화면 관찰 근거가 필요합니다.

## 6. 업데이트와 되돌리기

### 6-1. 무엇을 업데이트하는지 구분

| 대상 | 갱신 작업 | 성공 증거 |
|---|---|---|
| 소스 저장소/마켓플레이스 | 새 릴리스의 코드·목록 확보 | 원본 URL·태그·커밋·매니페스트 버전 |
| 설치된 Codex 플러그인 | 해당 소스에서 다시 설치 | 새 installedPath/버전/스킬·도구 일치 |
| 고정 Figma 작업공간 | 새 도구로 작업 재준비·revision 교체, 같은 manifest 다시 실행 | 작업 키·버전과 실제 새 읽기 결과 비교 |
| 선택적 paired sync | 새 전용 상태로 컴패니언 구성·baseline | 정확한 페이지·키·인증·상태 체인 검증 |

Codex 플러그인을 바꿔도 열린 Figma 작업은 저절로 바뀌지 않습니다. 새 설치본의 `figma_workspace.py prepare`로 같은 작업 키를 갱신해야 새 코드와 UI가 들어갑니다. 고정 manifest는 새 불변 generation을 가리키며, 이전 창을 닫고 다시 실행해야 새 작업 목록을 읽습니다. Figma 앱 자체의 업데이트도 이 작업과 별개입니다.

### 6-2. Codex 플러그인 갱신

1. 현재 `plugin list`와 `marketplace list`를 읽고 소스·설치 경로·버전·활성 상태를 기록합니다. 이전의 깨끗한 소스와 재설치 가능한 릴리스 태그를 보존합니다. **캐시 경로만 기록하면 재설치 때 지워질 수 있으므로 롤백 사본으로 충분하지 않습니다.** 진행 중인 파일·선택 기록·Figma 페이지도 보존합니다.
2. GitHub의 최신 **정식 릴리스** 또는 사용자가 지정한 버전을 확인합니다. 태그 문자열의 사전순 정렬이나 `main`을 최신 배포판으로 취급하지 않습니다. [공개 변경 기록](../CHANGELOG.md)과 회사 릴리스 차이를 읽습니다. private 복제본은 회사가 배포한 버전을 사용합니다.
3. 새 릴리스를 **별도 클론**에 받습니다. 기존 작업 폴더에서 `reset --hard`, 강제 checkout, 무단 stash를 하지 않습니다. Node LTS와 npm 설정은 [환경 가이드](npm-environment.md)를 따릅니다.
4. 현재 CLI의 `marketplace add/upgrade/remove`와 `plugin add/remove` 도움말을 확인합니다. Git 소스를 같은 ref로 새로 읽을 때는 `codex plugin marketplace upgrade <정확한 이름>`을 사용합니다. **이 명령만으로 설치 캐시 갱신을 단정하지 않습니다.** 태그 고정 소스의 다음 태그 설치는 새 클론 등록 또는 해당 CLI가 지원하는 명시적 소스 재등록으로 수행합니다.
5. 기존과 다른 이름의 마켓플레이스로 시험하면 기존 설치와 함께 활성화된 동명 스킬을 구분합니다. 확인 전 기존 설치를 삭제하지 않습니다. 같은 이름의 소스를 바꿔야 한다면 정확한 기존 경로/ref를 기록하고, 새 코드와 롤백 소스를 먼저 준비한 뒤 **그 소스만** 재등록합니다. 다른 마켓플레이스를 일괄 `upgrade`/제거하지 않습니다.
6. 선택한 소스에서 `codex plugin add figma-flow@<실제 이름> --json`을 실행합니다. 기존 캐시가 남으면 현재 CLI 지원 절차로 **해당 플러그인만** 재설치합니다. 현재 `--help`에 없는 `codex plugin update` 명령이나 캐시 수동 삭제를 사용하지 않습니다.
7. 목록의 `0.22.0`·소스·enabled, 실제 설치 복사본의 두 매니페스트 `0.22.0`, 새 스킬 파일을 대조합니다. 새 채팅에서 해당 스킬을 사용하고 새 워크숍 테스트로 확인합니다.

현재 CLI `0.165.0`에서 캐시 재설치가 필요할 때의 구체적인 명령은 아래와 같습니다. `MARKETPLACE`는 앞에서 읽은 실제 이름입니다. 새 소스 등록과 이전 버전 재설치 수단을 먼저 준비한 뒤 해당 플러그인만 제거·설치합니다.

```sh
codex plugin remove "figma-flow@$MARKETPLACE" --json
codex plugin add "figma-flow@$MARKETPLACE" --json
codex plugin list --marketplace "$MARKETPLACE" --json
```

기존 로컬 마켓플레이스가 다른 클론을 가리켜 소스 교체도 필요하면, 이전 경로를 기록하고 `codex plugin marketplace remove "$MARKETPLACE" --json` 후 `codex plugin marketplace add "/새 릴리스 클론의 절대 경로" --json`으로 그 소스만 재등록합니다. 이전 소스를 다시 등록하고 같은 remove/add 절차를 쓰면 Codex 설치를 되돌릴 수 있습니다. 재설치 전후 활성 상태도 대조합니다.

### 6-3. Figma 개발 플러그인 갱신: Computer Use 없음

1. 기존 작업공간 전체, 고정 manifest·ID·등록 경로와 `list` 결과를 보존합니다. 현재 Figma 페이지·선택 기록·읽기 자료도 유지합니다.
2. 새 설치본의 `figma_workspace.py prepare`로 해당 작업을 갱신합니다. 바뀐 입력에는 목록의 현재 revision을 `--replace-expected`로 전달합니다. 같은 프로젝트·작업은 같은 키를 쓰고 새 종류의 작업은 별도 키를 사용합니다. 본제작의 선택 기록이 새 입력과 맞지 않으면 기존 재검토·선택 절차로 돌아갑니다.
3. 등록 manifest 경로는 유지합니다. 실행 중인 Figma Flow 창을 닫고 다시 열어 홈의 프로젝트·작업·범위를 확인합니다. 다른 머신이면 숨김 generation을 포함한 작업공간 전체를 보존·전달합니다. 내부 code/UI 파일을 개별로 덮어쓰지 않습니다.
4. [현재 패널 조작](figma-guide.md#현재-패널-빠른-찾기)에 따라 작업을 엽니다. 열기 자체는 문서를 변경하지 않습니다. 본제작의 반복 가져오기는 기존 편집을 보존하며, 그래프 동기화는 **적용 범위 확인 → 확인한 범위에 적용**에서만 씁니다.
5. 현재 실행에서 새 JSON을 저장해 Codex에 전달합니다. 검토는 `verify-native-review`·`status`, 본제작은 [두 native 검사](figma-guide.md#9-선택한-안을-figma-본제작으로-전달), 그래프 작업은 실제 native/web 증거와 `pair`로 확인합니다. 예전 JSON과 작업 목록의 갱신만으로 새 실행을 통과시키지 않습니다.
6. 실패하면 새 진단과 복구 충돌을 보관하고 이전 작업공간 **전체**와 설치 소스로 되돌립니다. Figma의 사용자 변경이나 기존 페이지를 자동 삭제·강제 덮어쓰지 않습니다.

기존 standalone 패키지를 계속 쓰는 경우만 그 ID·등록 경로와 전체 패키지를 별도로 갱신합니다. 다른 ID의 private data를 한 작업공간으로 자동 합치지 않습니다.

### 6-4. Figma 개발 플러그인 갱신: Computer Use 사용

Codex가 6-3의 동일한 백업·ID 대조·패키지 교체·재실행·읽기 검증을 허용된 Desktop에서 수행합니다. 사용자 수정 보존과 실제 후보 선택의 경계는 같습니다. 자동 조작이 불가능해지면 준비한 새/이전 패키지 경로와 6-3의 다음 수동 단계를 전달합니다.

### 6-5. 선택적 로컬 동기화 사용 중이라면

처음 설치·검토에는 `serve_figma_sync.py`가 필요하지 않습니다. 사용 중인 경우에만 [토큰 동기화 계약](../skills/figma-flow/references/token-sync.md)과 [브리지의 paired companion 안내](../figma-bridge/README.md)를 읽습니다. 상태 폴더에는 pairing 비밀값이 있으므로 Git·공유 ZIP·지원 로그에 넣지 않습니다.

진행 중인 동기화 서버의 PID·프로젝트·상태 폴더를 확인한 뒤 그 서버만 종료합니다. 새 코드가 상태 폴더 안의 기존 플러그인 변경을 거부하면 **새 private 상태 디렉터리**로 새 컴패니언을 만들고 기존 체인을 보존합니다. `--prior-sync`는 아무 읽기 파일을 받는 일반 업그레이드 옵션이 아니며, 도구가 명시적으로 지원하는 이전 성공 apply wrapper에만 사용합니다. 예전 pairing 키로 다른 파일·페이지를 연결하지 않습니다.

같은 ID의 기존 paired state가 있으면 작업공간에 `prepare --kind import -- --input ORIGINAL_RESOLVED --reviewed-sha256 ACTUAL_SHA --paired-state PRIVATE_STATE`로 준비할 수 있습니다. 해당 서버는 실행 중이어야 하며 파일·페이지·원본 해시·ID가 정확히 같아야 합니다. 다른 ID의 상태는 거부하며 ID만 바꾸지 않습니다. 사용자는 홈에서 작업을 열어 **앱에 반영**을 수행하고 실제 결과를 전달합니다. 기존 standalone 컴패니언 등록은 호환 경로로 유지합니다. Codex는 같은 파일/page/원본·인증·저널 검증을 수행합니다. 일반 검토 플러그인 업데이트만을 위해 로컬 서버나 네트워크 권한을 추가하지 않습니다.

검토 시안의 인증된 `/draft-readback` 수신기를 쓰던 프로젝트도 별도 분기입니다. 일반 검토 작업은 JSON 저장만으로 검증할 수 있으며 수신기가 필수는 아닙니다. 자동 전달을 유지하려면 사용자 소유 0700 `REVIEW_PAIR` 폴더를 먼저 준비하고 다음처럼 명시합니다. 포트는 양쪽이 같아야 하며 실제 대상 파일을 고정합니다.

```sh
REVIEW_PAIR="/내/비공개/검토수신기"
# 처음 사용할 새 경로에만 생성합니다. 기존 private 폴더가 있으면 보존·검사합니다.
mkdir -m 700 "$REVIEW_PAIR"
"$PY" -B "$PLUGIN_ROOT/tools/figma_workspace.py" prepare \
  --workspace "$WORKSPACE" --key workshop-review-paired --title "워크숍 검토와 수신 확인" \
  --project "워크숍" --kind review -- \
  --manifest "$PROJECT/review/directions.json" --file-key ACTUAL_FILE_KEY \
  --pair-dir "$REVIEW_PAIR" --receiver-port 49185
# REVIEW_ARTIFACTS에는 위 prepare 출력의 artifacts 경로를 넣습니다.
"$PY" -B "$PLUGIN_ROOT/tools/figma_draft.py" serve \
  --packet "$REVIEW_ARTIFACTS/packet.json" --out "$PROJECT/received-review" \
  --pair-dir "$REVIEW_PAIR" --port 49185
```

capability는 비공개 폴더에서 생성·재사용되며 공개하지 않습니다. 수신기의 성공·거부 영수증과 수신기 중단 시 **결과 JSON 저장** 수동 경로를 각각 확인하세요. 거부 영수증은 **상세 진단 보기**에서 사유를 확인합니다. 이 전달은 앱 반영 `/sync` 또는 원래 채팅 relay와 다른 동작이며, 기존 등록을 없애기 전에 필요한 경로를 실제로 대조합니다.

### 6-6. 선택적 원래 채팅 연결

[채팅 연결 절차](figma-guide.md#11-작업을-준비한-codex-채팅으로-연결)는 기록된 thread를 열고 선택·요청을 미리 확인한 뒤 복사하거나 명시적으로 큐에 넣습니다. relay가 필요하면 같은 ID의 `init --chat-port PORT`로 설정하고 `python3 tools/workspace_chat.py --workspace DIR`를 실행합니다. 직접 전송은 사용자가 **채팅에 보내기**를 눌렀을 때만 수행하며 큐 접수와 에이전트 실행을 구분합니다. 현재 앞에 열린 채팅을 추정하지 않습니다.

### 6-7. 이전 개발 플러그인 등록 정리

새 프로젝트에서 필요한 작업과 실제 읽기 검증, 사용하는 수신기·웹 경로를 확인한 뒤 사용자가 퇴역 대상으로 지정한 예전 등록만 해제합니다. 먼저 ID·manifest 절대 경로·전체 패키지와 읽기 자료를 보관하고, **현재 고정 작업공간 등록은 제외**합니다. 같은 ID가 서로 다른 경로에 등록돼 있을 수 있으므로 이름만 보고 제거하지 않습니다. 등록 정리는 문서 페이지·변수·선택 기록을 삭제하는 작업이 아닙니다. 문제가 생기면 보관한 원래 manifest를 원래 ID로 다시 등록합니다.

### 업데이트 프롬프트

```text
$figma-plugin-setup 현재 Figma Flow를 v0.22.0으로 업데이트하고 연동을 재검증해 줘.
저장소/마켓플레이스: [실제 값], 기존 프로젝트/등록 manifest: [절대 경로]
Computer Use: [가능/불가능]. paired sync: [사용 안 함 / 상태 폴더의 로컬 경로만 지정]
docs/installation-and-updates.md의 6절대로 기존 작업·페이지·선택 기록·이전 재설치 소스를 보존해.
Codex 설치와 고정 Figma 작업공간의 작업을 각각 갱신하고 실제 새 읽기 결과를 검증해. 회사 npm URL·적용 범위는 기존 값과 대조하고, 없을 때만 내게 물어봐.
lockfile을 생성하거나 Git 추적하지 마. 실제 명령·종료 코드, 전후 버전·소스·설치 경로, 롤백 경로와 미확인 항목을 보고해.
Computer Use가 없으면 수동 조작을 한 단계씩 알려 주고 JSON이 올 때까지 Figma 완료를 pending으로 유지해.
```

## 7. 자주 막히는 지점

| 증상 | 확인·복구 |
|---|---|
| private clone/마켓플레이스 404·인증 실패 | 실제 Git URL로 읽기 확인, 조직 SSO와 저장소 권한 확인. 토큰을 URL에 넣지 않기 |
| Codex에 새 스킬이 없음 | 올바른 릴리스에 새 파일이 있는지, installed/enabled와 설치된 파일 확인. 새 채팅에서 이어가기 |
| 업데이트 후 Figma 작업만 그대로 | `list`의 키·revision, 고정 manifest 등록 경로, 이전 창 종료 후 재실행 확인 |
| 업데이트 후 버전이 그대로 | 마켓플레이스 ref·로컬 경로와 설치 캐시를 각각 확인. 현재 CLI의 해당 플러그인 재설치 사용 |
| npm 401/403·인증서 오류 | 전체 URL·서비스 경로·스코프·사용자 인증·회사 CA 확인. TLS 검증을 끄지 않기 |
| `npm ci`가 lockfile을 요구 | 이 저장소 루트에서는 불필요. 별도 앱도 이 저장소의 lockfile 비추적 정책에 맞는 설치 절차 사용 |
| Figma 개발 메뉴가 없음 | 브라우저 대신 macOS/Windows Desktop에서 Design 파일·접근 권한 확인 |
| 같은 ID 등록 오류 | 프로젝트/용도/등록 폴더 대조. 해당 전용 폴더만 백업·교체 |
| 글꼴 누락·화면 잘림 | 필요한 글꼴의 실제 가용성과 진단 JSON 확인. 글꼴 대체나 검증 우회로 성공 처리하지 않기 |
| readback 실패·현재 리뷰 불일치 | 올바른 플러그인·페이지에서 다시 저장. JSON이나 선택 기록을 조작하지 않기 |
| HTML만 생성됨 | 패키지 준비까지만 완료. 실제 Figma 생성·읽기 단계를 계속 진행 |

## 8. 최종 보고 양식

```text
설치: 원본/마켓플레이스, 태그·커밋, installed/enabled, 실제 설치 경로와 버전
환경: .nvmrc와 실제 Node, Python 경로, npm 레지스트리 적용 범위(인증값 제외), lockfile 추적 여부
작업공간: 고정 manifest·Figma ID·등록 경로, 프로젝트·작업 키/revision·원래 채팅 ID, 현재 리뷰/후보
실행: 명령별 종료 코드, 실제 Figma 읽기 JSON과 검증 결과, 현재 워크플로 상태
관찰: 화면·프로토타입·주석 링크의 확인 항목과 확인 주체
남은 일: 실제 사용자 선택, 수동 조작 또는 환경 차이, 업데이트 전 버전으로 복구할 경로
```

이 문서의 명령은 로컬 Codex CLI `0.165.0` 도움말과 저장소 도구를 기준으로 확인했습니다. 호스트별 설치 기능·조직 정책은 다를 수 있으므로 현재 `--help`와 실제 결과를 우선합니다. 공식 근거: [OpenAI 플러그인 구조](https://developers.openai.com/plugins/build/plugins), [CLI 명령](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [Figma 개발 플러그인](https://help.figma.com/hc/en-us/articles/360042786733-Create-a-classic-plugin-for-development).
