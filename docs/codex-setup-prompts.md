# 클론 후 Codex에 붙여 넣는 설치 프롬프트

아직 클론하지 않았다면 [빈 폴더에서 처음부터 설치하는 프롬프트](installation-and-updates.md#1-클론-전부터-codex에-맡기기)를 사용하세요. [회사 private 배포](private-repository.md), [Node LTS·회사 npm·lockfile 정책](npm-environment.md), [Codex와 Figma 각각의 업데이트](installation-and-updates.md#6-업데이트와-되돌리기)도 별도로 안내합니다. 설치 후 반복 연동은 `$figma-plugin-setup`으로 요청할 수 있습니다.

먼저 `git clone --branch v0.18.2 https://github.com/jonsoku-dev/figma-flow.git`으로 받은 폴더를 Codex에서 엽니다. 아래에서 해당하는 **코드 블록 하나**를 복사해 새 채팅에 보내세요. 첫 실행용 워크숍은 실제 회원 정보나 외부 전송을 사용하지 않습니다. [화면으로 따라가기](figma-guide.md)

## A. Computer Use로 Figma Desktop까지 조작 가능한 환경

```text
현재 열어 둔 jonsoku-dev/figma-flow 클론에서 Figma Flow를 설치하고 워크숍 검토 패키지의 실제 Figma 읽기 결과까지 확인해 줘.

1. 저장소 루트, git remote get-url origin, git status, HEAD와 v0.18.2의 일치, plugin.json과 .codex-plugin/plugin.json의 version을 확인해. 다른 작업 트리나 변경 파일이 있으면 보존하고, 태그의 깨끗한 워크트리를 별도로 써. docs/figma-guide.md와 동봉된 native-direction-review 예제를 읽어.
2. Git, Codex CLI의 plugin 명령과 Python 3.13 사용 가능 여부를 확인해. Node는 .nvmrc에 고정된 LTS와 실제 실행 버전을 대조해. docs/npm-environment.md대로 회사 npm 사용 여부, 필요한 전체 HTTPS URL과 미러/스코프 범위를 내게 묻고 프로젝트 .npmrc만 설정해. package-lock=false와 lockfile 비추적을 확인하고 인증값은 요청하거나 저장하지 마. 이미 맞는 설정은 재사용해.
3. codex plugin marketplace list에서 figma-flow-local의 소스 경로를 확인하고, 필요하면 codex plugin marketplace add <클론의 절대 경로>, codex plugin add figma-flow@figma-flow-local --json을 실행해. codex plugin list --marketplace figma-flow-local의 경로, installed, enabled, 0.18.2을 확인해. add의 installedPath에 새 skills/figma-plugin-setup/SKILL.md가 있으면 읽고 연동을 이어가. 이미 실행 중인 채팅에서 스킬이 보이지 않으면 새 채팅에서 이어갈 명령과 현재 위치를 알려 줘.
4. 설치된 복사본을 기준으로 운영체제에 맞게 클론 밖에 Python 가상환경을 만들고 그 Python으로 pip install -r requirements-optional.txt를 실행해. Pillow 등 import를 확인하고 같은 Python으로 examples/native-direction-review/demo.py --out <새 폴더>를 실행해. <새 폴더>/review/directions.json의 현재 단계와 두 후보를 확인해. 시안이 실제 Figma에 만들어졌다는 주장은 아직 보류해.
5. 내게 연습용 Figma Design 파일과 프로젝트 전용 검토 플러그인의 manifest.json 위치를 알려 달라고 해. ID가 없으면 허용된 Figma Desktop의 플러그인 → 개발 → 새 플러그인에서 Figma Design, 사용자 정의 UI를 선택해 전용 폴더에 저장하고, 발급된 ID를 읽어. 실제 계정 로그인, 접근 승인, 앱에서 필요한 확인은 내게 맡겨. Computer Use는 지정한 Figma 파일·메뉴·관련 파일 선택 대화상자에만 써.
6. tools/design_actions.py prepare-native-review --manifest <directions.json> --plugin-id <실제 숫자 ID> --out <새 reviewer 폴더>를 실행해. 품질 오류는 원본에서 확인해. 생성된 reviewer/plugin/manifest.json을 지정한 Figma Desktop의 개발 플러그인 메뉴로 등록해. 실행 전 프로젝트명과 대상 파일을 대조해. 검토 시안 만들기 → 결과 JSON 저장 순서로 진행해.
7. 저장된 실제 읽기 파일로 tools/design_actions.py verify-native-review --manifest <directions.json> --readback <결과 JSON>을 실행해. 데스크톱·모바일, 주석 보드 링크, 주요 조작의 목적지와 복귀를 확인하고 캡처에는 계정과 파일 키가 보이지 않게 해. 실행이 안 되면 패키지 경로, 막힌 버튼, 사용자가 해야 할 조작을 정확히 알려 줘.
8. 현재 리뷰와 후보 ID를 보여 주고, 두 시안을 네가 직접 비교해서 추천해. 본제작은 실제 선택 기록이 필요한 별도 단계야. 대리 사용자 응답이나 선택 영수증을 만들지 마. 내가 실제로 특정 후보를 고른 경우에만 기존 선택 절차로 넘어가.
9. 한국어로 설치 경로·버전, 실제 실행한 명령과 종료 코드, 검토 HTML·Figma 매니페스트·재읽기 결과의 위치, 확인한 것과 남은 것을 알려 줘.
```

## B. Computer Use가 없는 환경

```text
현재 열어 둔 jonsoku-dev/figma-flow 클론에서 Figma Flow와 첫 워크숍 예제를 설정해 줘. 이 환경에는 Computer Use가 없어. 파일·CLI 작업은 네가 완료하고 Figma Desktop 조작은 내가 할 수 있게 단계별로 안내해.

1. 클론 루트, origin, 현재 커밋과 v0.18.2 태그, 두 plugin.json의 버전을 확인해. 변경이 있으면 보존해. docs/figma-guide.md를 읽고 Git, Codex CLI plugin 명령, .nvmrc에 고정된 LTS와 실제 Node, Python 3.13을 확인해. docs/npm-environment.md대로 회사 npm의 전체 HTTPS URL과 미러/스코프 범위를 내게 물어보고 프로젝트 .npmrc만 설정해. lockfile을 생성·Git 추적하지 말고 인증값은 요청하지 마. 내 OS에 맞는 명령을 사용해.
2. codex plugin marketplace list로 현재 상태를 읽고 이 클론이 등록되어 있지 않으면 codex plugin marketplace add <클론 절대 경로>를 실행해. codex plugin add figma-flow@figma-flow-local --json과 codex plugin list --marketplace figma-flow-local로 installed, enabled, 0.18.2과 소스 경로를 확인해. add의 installedPath에 새 skills/figma-plugin-setup/SKILL.md가 있으면 읽어 이어가고, 새 채팅이 필요하면 이어갈 프롬프트를 줘. 설치된 복사본을 기준으로 클론 밖의 가상환경에 requirements-optional.txt를 설치하고 같은 Python으로 Pillow 등 의존성을 확인해.
3. examples/native-direction-review/demo.py --out <클론 밖의 새 워크숍 폴더>를 실행해. review/directions.json, HTML 비교 화면, 후보 ID, 현재 NATIVE_REVIEW_PENDING 상태를 확인해.
4. 내게 필요한 첫 조작을 알려 줘. Figma Desktop에서 새 연습용 Design 파일을 열고 메인 메뉴 → 플러그인 → 개발 → 새 플러그인 → Figma Design → 사용자 정의 UI → 다른 이름으로 저장을 누르면 돼. 이미 이 프로젝트의 검토용 ID가 있으면 그 전용 manifest.json 경로만 받아. 토큰이나 계정 비밀번호, 다른 프로젝트의 ID를 요청하지 마.
5. 내가 파일 경로를 주면 발급된 id를 읽어 tools/design_actions.py prepare-native-review --manifest <directions.json> --plugin-id <실제 숫자 ID> --out <새 폴더>를 실행해. ZIP만 전달해야 하는 환경이면 어디서 압축을 풀어야 하는지 알려 줘. 생성된 plugin/manifest.json의 정확한 경로와 그림이 있는 가이드의 5~6단계를 보여 줘.
6. 내가 할 다음 조작은 “개발 메뉴에서 매니페스트 가져오기 → 생성한 manifest.json 선택 → 해당 검토 플러그인 실행 → 검토 시안 만들기 → 결과 JSON 저장”이야. 파일이 준비되면 그 경로 또는 첨부를 받아 tools/design_actions.py verify-native-review --manifest <directions.json> --readback <저장한 결과>로 대조해. 파일을 받기 전에는 pending으로 두고, 검증 명령과 이어갈 위치를 남겨.
7. 비교와 추천은 네가 해. 현재 후보·리뷰를 보여 주고 실제 사용자 선택 전에는 본제작 선택 기록을 만들지 마. 내가 Figma 작업 없이 HTML만 원한다고 명시하면 프로젝트 브리프를 Local HTML only로 정하고 --review-destination local인 별도 새 리뷰를 만들어. Figma 목적지를 말없이 바꾸지 마.
8. 끝나면 실제 명령·종료 코드, 설치 위치·버전, 패키지와 다음 입력 파일의 경로, 현재 단계, 확인 못 한 범위를 한국어로 정리해.
```

## 내 기획에 적용할 때 덧붙일 문장

> 워크숍 대신 첨부한 팀 초대 기획서로 진행해 줘. 이 저장소의 테마와 컴포넌트를 디자인 시스템 기준으로 사용해. 전문 분석 보고서에서 확인한 사용자 행동과 캡처에서 확인한 화면 배치를 구분하고, 같은 시스템으로 두 시안을 만들어 직접 비교해 줘. 검토 목적지는 [Figma 또는 로컬 HTML]이야.
