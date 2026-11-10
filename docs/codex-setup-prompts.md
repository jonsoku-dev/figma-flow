# 클론 후 Codex에 붙여 넣는 설치 프롬프트

아직 클론하지 않았다면 [처음 설치 프롬프트](installation-and-updates.md#1-클론-전부터-codex에-맡기기)를 사용하세요. 직접 받을 때는 `git clone --branch v0.22.0 https://github.com/jonsoku-dev/figma-flow.git`입니다. 기본은 **Figma에 고정 manifest 하나를 등록하고 Codex가 준비한 작업을 홈에서 여는 방식**입니다. 개별 작업 manifest 등록은 기존 standalone 호환용입니다. [화면과 명령 가이드](figma-guide.md)

아래 두 코드 블록 중 환경에 맞는 하나를 새 채팅에 보내세요. 회사 환경은 [private 배포](private-repository.md)와 [npm·Node 정책](npm-environment.md)을 함께 확인합니다.

## A. Computer Use로 Figma Desktop까지 조작 가능한 환경

```text
현재 figma-flow 클론에서 Figma Flow 0.22.0을 설치하고, 하나의 등록된 Figma Flow 작업공간으로 워크숍 검토까지 확인해 줘.

1. 저장소 루트·origin·git status·HEAD와 v0.22.0 태그, 두 plugin.json 버전을 확인해. 기존 변경은 보존해. docs/figma-guide.md와 설치된 skills/figma-plugin-setup/SKILL.md를 따라.
2. 현재 Codex CLI 도움말로 marketplace/plugin 설치와 installedPath·installed/enabled/version/source를 확인해. Python 3.13 가상환경과 Pillow를 클론 밖에 준비해. 회사 npm이 필요하면 확인한 URL·범위만 프로젝트 .npmrc에 반영하고 인증값과 lockfile은 저장소에 넣지 마.
3. 기존 Figma Flow 작업공간 manifest·ID·등록 경로가 있으면 재사용해. 최초에만 지정한 연습용 Design 파일의 개발 메뉴에서 내 ID를 발급받고, figma_workspace.py init --id-from으로 만든 고정 WORKSPACE/manifest.json을 등록해. 계정 로그인·접근 승인은 내가 해.
4. 동봉 워크숍을 만들고 NATIVE_REVIEW_PENDING을 확인해. prepare --kind review로 프로젝트·작업 키·제목과 현재 CODEX_THREAD_ID 또는 실제 --thread-id를 고정해. Figma의 준비된 작업에서 그 검토 작업을 열고 검토 시안 만들기 → 완료 확인 → 결과 JSON 저장을 진행해. 열기 자체를 문서 생성으로 보고하지 마.
5. 실제 결과 JSON과 현재 directions.json을 verify-native-review·status로 비교해 WAIT_SELECTION을 확인해. 데스크톱·모바일·주석 링크·주요 이동과 복귀를 실제 관찰하고, 미확인 항목은 구분해. 실제 내 선택 전에는 선택 기록·본제작을 만들지 마.
6. 완료하면 작업 목록으로 돌아가. 이후 본제작·문서 읽기·그래프 동기화도 같은 작업공간에 준비해. 같은 키의 변경은 list의 현재 revision을 --replace-expected로 사용하고 이전 창을 닫아 다시 실행해. 다른 ID의 private data를 자동 이관하지 마.
7. 채팅 연결은 작업을 준비한 원래 thread로만 해. 선택과 요청을 미리 확인한 뒤 복사하거나 내가 누른 채팅에 보내기로만 대기열에 넣어. 열린 창 추정이나 자동 전송을 하지 마. 설치·고정 manifest·작업 키/revision·실제 명령/종료 코드·증거와 남은 일을 한국어로 알려 줘.
```

## B. Computer Use가 없는 환경

```text
현재 figma-flow 클론에서 Figma Flow 0.22.0과 워크숍을 준비해 줘. CLI·파일 작업은 네가 하고 Figma Desktop 버튼은 내가 누를 거야.

1. origin·git status·v0.22.0 커밋·두 manifest 버전과 Codex 설치 위치/활성 상태를 확인해. 기존 작업을 보존하고 설치된 figma-plugin-setup 스킬과 docs/figma-guide.md를 따라 환경·Python 의존성을 준비해. 회사 npm은 실제 URL·범위만 확인하고 인증값을 요청하지 마.
2. 기존 Figma Flow 작업공간의 고정 manifest·ID가 있으면 재사용해. 없으면 내가 최초 한 번 개발 → 새 플러그인 → Figma Design → 사용자 정의 UI로 저장한 manifest 경로를 줄게. 그 ID로 비공개 작업공간을 init하고 고정 WORKSPACE/manifest.json의 최초 등록 경로를 알려 줘.
3. 워크숍과 검토 작업을 prepare --kind review로 준비하고 현재 채팅 UUID를 기록해. 원격이면 숨김 .generations를 포함한 작업공간 전체를 내 PC로 전달해. 개별 작업 manifest를 매번 등록하게 하지 마.
4. 내가 할 조작은 Figma Flow → 준비된 작업 → 해당 프로젝트의 검토 작업 열기 → 검토 시안 만들기 → 완료 확인 → 결과 JSON 저장이야. JSON을 주면 verify-native-review·status로 현재 리뷰를 검증해. 파일을 받기 전 Figma 검증은 pending으로 남겨.
5. 실제 후보를 비교·추천하되 내가 선택하기 전 본제작·선택 기록은 만들지 마. 완료하면 작업 목록으로 돌아가고 다음 작업도 같은 고정 manifest에 준비해. 다른 ID의 기존 페이지·private data는 원래 패키지를 보존하고 명시적 이관 범위를 먼저 확인해.
6. 작업별 원래 채팅 열기·선택 내용 미리 확인·내용 복사 경로를 안내해. 선택적 로컬 relay 없이 직접 전송을 약속하지 마. 실제 명령·종료 코드, 설치와 고정 등록 경로·작업 키/revision·현재 단계·남은 수동 조작을 한국어로 정리해.
```

## 내 기획에 적용할 때 덧붙일 문장

> 워크숍 대신 첨부한 팀 초대 기획서와 디자인 시스템으로 진행해 줘. 자료의 관찰과 내 요구사항을 구분하고 두 시안을 비교·추천해 줘. 검토 목적지는 Figma이며 기존 Figma Flow 작업공간에 새 작업으로 준비해. 명시적으로 Local HTML only라고 요청한 경우에는 로컬 경로를 유지해.
