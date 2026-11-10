---
name: figma-plugin-setup
description: Install Figma Flow in Codex, connect its stable Figma workspace and Codex-prepared task list, verify actual readback, or update and repair that connection. Handles private repositories, company npm registry setup, and environments with or without Computer Use.
---

# Figma 플러그인 설치·연동·업데이트

## 적용 범위와 입력

Figma Flow의 **Codex 설치**, 한 번 등록하는 **Figma Flow 작업공간과 프로젝트별 작업 목록**, 사용 중일 때만 **paired sync**를 구분한다. 디자인 제작·후보 선택은 기존 `figma-flow` 절차를 사용한다. 입력은 원본 URL/태그, 마켓플레이스·설치 경로, 프로젝트/현재 리뷰, 고정 workspace manifest·Figma 발급 ID·작업 키, Computer Use 가능 여부다. 현재 대화와 로컬 파일에서 확인한 값은 재사용한다.

이 파일의 두 단계 위가 동봉된 플러그인 루트다. 경로를 설치 캐시 관례로 추정하지 말고 실제 파일로 확인한다. 첫 설치는 아직 이 스킬이 없으므로 [설치 프롬프트](../../docs/installation-and-updates.md#1-클론-전부터-codex에-맡기기)를 사용하고, 설치 후 이 스킬을 읽는다.

해당 분기의 문서만 읽는다.

- 브라우저에서 설치 자료·사이트·로컬 페이지를 열 때: [허용 대상 등록과 적용 확인](../figma-flow/references/browser-access.md). 실제 작업에 필요한 새 대상은 등록 후 계속한다. Figma Desktop 자체의 접근 승인은 해당 앱 경로를 따른다.
- 동봉된 외부 스킬 확인: [의존성 계약](../figma-flow/references/skill-dependencies.md). 실제 설치본의 `tools/skill_dependencies.py --check`로 고정된 원문·참조·라이선스를 검증한다. 전역 스킬 설치나 최신본 다운로드로 대체하지 않는다.
- 최초 설치·읽기 검증: [설치·연동 가이드](../../docs/installation-and-updates.md)의 1~5절.
- private 복제·회사 배포: [private 저장소 가이드](../../docs/private-repository.md). 읽기 권한 확인과 원격 생성·업로드 권한은 별개다.
- Node/npm 설정: [npm 환경 가이드](../../docs/npm-environment.md). 회사 레지스트리 도메인/전체 URL과 전체 미러·`@scope` 적용 여부를 **사용자에게 묻고** 설정한다. 기존에 확인한 설정이면 값을 대조해 재사용한다. 토큰을 대화에 요청하지 않는다.
- 최신화·복구: 설치·연동 가이드의 [6절](../../docs/installation-and-updates.md#6-업데이트와-되돌리기).

## 1. 현재 상태 확인

1. 원본 루트, `git status`, 태그/커밋, 두 plugin manifest 버전, 마켓플레이스 JSON을 읽는다. 현재 CLI의 plugin/marketplace `--help`, `list --json`으로 실제 지원 문법과 설치 소스를 확인한다. 다른 작업이 있는 클론은 보존하고 새 전용 클론에서 진행한다.
2. 최신 요청은 해당 공개/회사 저장소의 최신 **정식 GitHub Release**를 확인한 뒤 정확한 태그·커밋으로 고정한다. 릴리스가 없으면 게시된 안정 버전을 추측하지 말고 사용할 ref를 사용자에게 받는다. 서로 다른 회사/개인 마켓플레이스가 같은 이름이면 덮어쓰기 전에 구분한다.
3. 기존 작업공간의 고정 manifest와 실제 등록된 폴더·ID를 확인하고 재사용한다. 새 작업은 그 목록에 추가하며, standalone manifest는 기존 호환 경로가 필요한 경우에만 등록한다. 로컬 파일/CLI와 Figma Desktop의 위치를 확인한다. 원격 Codex가 만든 파일은 Desktop이 있는 머신으로 전체 패키지를 전달한다. Computer Use가 없으면 이후 Figma 조작만 사용자에게 넘긴다. Figma가 목적지인 요청을 HTML로 변경하지 않는다.

완료 기준: 원본·설치·실행 머신과 대상 프로젝트를 구분하고, 변경할 경로와 보존할 경로가 특정된다.

## 2. Codex 플러그인과 환경 준비

1. 최초 설치는 실제 마켓플레이스 이름으로 `codex plugin marketplace add <source> --json`, `codex plugin add figma-flow@<name> --json`을 사용한다. 기존 소스가 맞으면 재사용한다. `add`의 `installedPath`, 목록의 `installed`, `enabled`, `version`, `marketplaceSource`를 읽고 설치 복사본의 두 manifest를 대조한다.
   그 실제 설치본에서 `python3 tools/skill_dependencies.py --check`를 실행한다. 동봉한 원문·참조·라이선스가 준비되면 디자인 작업으로 진행하고, 실패하면 해당 설치본의 누락·변조를 복구한다. 다른 PC의 전역 스킬 폴더를 요구하지 않는다.
2. 새 스킬이 현재 채팅에 로드되지 않으면 설치 경로·버전·프로젝트·다음 단계를 넣은 이어가기 프롬프트를 제공한다. 사용자가 새 채팅에서 계속할 수 있게 한다. 요청 없이 새 채팅을 생성하거나 사용자의 Codex UI를 자동 조작하지 않는다.
3. `.nvmrc`에 고정된 현재 LTS와 실제 `node --version`을 대조한다. “현재 LTS로 변경” 요청일 때는 공식 Node.js 자료에서 당시 최신 LTS를 확인하고 정확한 버전을 쓴다. 설정 파일만 확인했으면 실제 런타임 검증과 구분한다.
4. npm 문서에 따라 사용자가 지정한 URL·스코프만 프로젝트 `.npmrc`에 반영한다. URL은 HTTPS, 정상 host, userinfo/query/fragment/공백·제어 문자 없음으로 검증하고 서비스 경로를 보존한다. 인증은 사용자별 registry 범위 설정으로 유지한다. 기존 `.npmrc`를 저장소 밖의 전용 위치에 보존하고 필요한 키만 편집한다. `npm config set`이 제거한 주석은 백업과 대조해 복원한다. `package-lock=false`, lockfile ignore와 실제 추적 여부를 확인한다. lockfile을 GitHub에 올리지 않는다.
5. 루트에는 `package.json`이 없으므로 npm 설치를 실행하지 않는다. 저장소 밖의 Python 가상환경에 `requirements-optional.txt`를 설치하고 같은 Python으로 예제·검증 도구를 실행한다. 실제 앱에 npm 설치가 필요할 때만 그 앱의 매니페스트·레지스트리·lockfile 정책을 별도로 확인한다.

6. 브라우저·Playwright 검수까지 맡긴 작업이면 [브라우저 접근 등록](../figma-flow/references/browser-access.md)에 따라 실제 로컬 URL·작업 사이트를 등록한다. 현재 프로젝트 루트에서 도구를 실행하고 반환된 `mcp_server`로 그 프로젝트의 로컬 설정을 만든다. 실행 파일은 PATH에서 확인하며 다른 사용자의 홈·클론·설치 캐시 경로를 복사하지 않는다. 허용 목록을 적용할 수 있는 MCP가 없으면 공식 Playwright MCP를 프로젝트에 설정하고 같은 등록 JSON을 `--config`로 연결한다. 프로젝트 설정·도구 목록·실제 resolved config를 확인하며, 새 연결이 현재 채팅에 로드되지 않으면 설정 경로와 재연결 후 검증할 도구를 명시한다. 브라우저를 쓰지 않는 Figma Design 전용 경로에는 MCP 설치를 요구하지 않는다.

완료 기준: 실제 Codex 설치 경로·버전이 확인되고 환경·의존성이 준비된다. 브라우저 분기는 MCP 설정·실제 연결·허용 목록 적용을 각각 보고한다. 설치 성공은 Figma 연결 성공과 별도로 보고한다.

## 3. 한 번 등록·실행하고 Codex 로컬 제어

1. 설치된 복사본의 `examples/native-direction-review/demo.py --out <새 폴더>`로 첫 워크숍을 만들고 `design_actions.py status`에서 `NATIVE_REVIEW_PENDING`을 확인한다. 기존 프로젝트를 무단 재생성하지 않는다.
2. 기존 작업공간 ID가 있으면 고정 manifest에서 숫자 문자열을 읽는다. 최초 한 번만 Figma Desktop의 **플러그인 → 개발 → 새 플러그인 → Figma Design → 사용자 정의 UI → 전용 폴더에 저장**으로 사용자 소유 ID를 발급받는다. 계정 로그인·접근 승인은 사용자 단계다.
3. [작업공간 명령과 등록 절차](../../docs/figma-guide.md)에 따라 고정 manifest를 준비하고 Desktop에 한 번 등록한다. 실제 ID와 등록 경로를 기록한다. 작업공간 CLI의 현재 POSIX 지원 범위를 확인한다. Windows 로컬은 standalone 호환 경로를 유지한다. 원격 생성했다면 숨김 generation을 포함한 작업공간 전체를 Desktop 머신에 전달하고 실제 실행 범위를 구분한다.
4. 현재 `CODEX_THREAD_ID` 또는 명시적인 실제 `--thread-id`로 `prepare --kind review`를 실행한다. 둘 다 없으면 오프라인 작업으로 두고 채팅 ID를 만들지 않는다.
5. `figma_control.py enable --workspace DIR --port PORT` 후 workspace `refresh`와 control `serve`를 준비한다. 사용자가 대상 파일에서 플러그인을 한 번 직접 실행하면 Codex가 정확한 키·operation·파일·페이지·현재 revision으로 `run`한다. 반환 readback을 보존하며 실제 성공은 정상 검사기로 대조한다. 제어가 없으면 수동 대체 경로로 **준비된 작업 → 열기 → 검토 시안 만들기 → 완료 확인 → 결과 JSON 저장**을 사용한다. 실행 중에는 완료·오류를 기다린다.
6. 실제 JSON을 받은 뒤 현재 `directions.json`과 `verify-native-review`·`status`로 대조한다. 성공 상태는 `WAIT_SELECTION`이다. 오류 자료는 보존하고 원본 입력에서 수정해 같은 작업 키를 갱신한다. 갱신 후 실제 실행 revision을 확인하고, 이전 코드가 남아 있으면 같은 고정 플러그인을 다시 실행한다.
7. 실제 화면·프로토타입·주석을 확인하고 현재 후보를 비교·추천한다. 실제 사용자 선택 전에는 선택 기록이나 본제작을 만들지 않는다. 다음 본제작·문서 읽기·동기화도 같은 작업공간에 별도 작업 키로 준비한다.

다른 ID의 standalone 패키지를 그대로 끼워 넣지 않는다. Figma private plugin data는 ID에 묶인다. 원래 ID가 만든 기존 페이지를 계속 다룰 때는 그 ID로 작업공간을 구성하거나 원래 패키지를 유지한다. 통합 ID로 옮길 필요가 있으면 기존 자료를 먼저 읽고 사용자가 지정한 범위의 명시적 이관을 준비한다. ID 문자열 교체로 소유권이 이전됐다고 판단하지 않는다.

**Computer Use 없음:** 사용자가 고정 manifest를 최초 등록하고 Figma Flow를 한 번 실행한다. 열린 플러그인의 로컬 제어로 이후 실행·읽기·검사를 Codex가 수행한다. 제어를 사용할 수 없을 때만 사용자가 수동 버튼과 JSON 전달을 담당한다. 실제 파일이 오기 전까지 연결 검증은 pending이다.

**Computer Use 있음:** 지정한 Figma Desktop 파일·메뉴·관련 선택/저장 창만 조작한다. 앱의 접근 승인과 사용자 확인을 준수한다. 불가능해지면 만든 작업공간과 작업 키를 보존하고 같은 수동 경로로 이어간다.


## 4. 업데이트·복구 분기

설치 가이드 6절을 읽고 다음 순서로 진행한다.

1. 이전 설치 버전·원본/ref·재설치 가능한 소스와 Figma 패키지·등록 경로를 보존한다. 삭제될 수 있는 설치 캐시만 롤백 사본으로 삼지 않는다.
2. 새 릴리스를 별도 클론에 준비하고 해당 마켓플레이스만 갱신한다. `marketplace upgrade`는 소스 갱신이며 고정 ref 변경이나 설치 캐시 교체의 증거가 아니다. 현재 CLI가 지원하는 해당 플러그인 재설치 후 실제 새 버전·소스·스킬을 대조한다.
3. 새 설치 도구의 `prepare`로 기존 작업공간의 같은 ID·작업 키를 갱신한다. 바뀐 입력은 `list`의 현재 revision을 `--replace-expected`로 고정한다. 등록 manifest 경로는 유지하고 이전 실행 창을 닫아 다시 연다. 업데이트 전 작업공간 전체를 복구 가능하게 보존한다. enable 직후 refresh_required를 확인해 refresh하고, prepare/refresh 뒤 실제 실행 revision을 대조해 필요할 때만 같은 플러그인을 다시 연다. 자동 재로드·무재시작을 보장하지 않는다. standalone 호환 패키지는 해당 ID·등록 경로를 별도로 유지한다. 검토 수신기를 사용하던 프로젝트는 가이드의 `review --pair-dir/--receiver-port` 분기로 영수증과 서버 중단 시 수동 저장까지 확인한다.
4. 새 코드 실행과 실제 새 readback을 검증한다. 기존 페이지를 보존하는 반복 import는 새 입력이 적용됐다는 증거가 아니다. 원본 변경·선택 무효화는 기존 워크플로의 재검토 절차로 처리한다. 실패하면 새 진단을 남기고 이전 패키지 **전체**와 설치 소스로 되돌린다.
5. paired sync 사용 중일 때만 token-sync와 bridge 문서를 읽는다. 정확한 해당 서버만 종료하고 상태 폴더·비밀값·저널을 보존한다. 기존 컴패니언 변경을 거부하면 새 private 상태 디렉터리에서 준비한다. 일반 업데이트를 위해 `--prior-sync`를 임의 사용하지 않는다. 동일 ID의 지원되는 private paired state는 `prepare --kind import`의 `--paired-state`로 홈에 준비한다. 다른 ID는 원래 standalone 경로를 보존한다. 사용자는 해당 작업 열기·baseline·실제 결과 전달을 진행한다.

## 원래 채팅으로 연결

[채팅 가이드](../../docs/figma-guide.md#11-작업을-준비한-codex-채팅으로-연결)를 따른다. 홈이나 작업 상단의 **Codex 연결**은 기록된 thread에만 연결한다. **보낼 내용 확인** 후 복사·명시적 링크 열기가 기본이며 `init --chat-port`·`workspace_chat.py --workspace`로 구성한 relay가 있을 때만 사용자의 **채팅에 보내기**를 큐에 넣는다. 자동 전송·데스크톱 앞창 추정을 하지 않는다. 큐 접수, 실제 소비·실행과 불확실한 접수는 각각 보고한다.

예전 등록 퇴역을 요청받으면 가이드 6-7절에 따라 새 프로젝트의 실제 작업·읽기 검증을 마친 뒤 지정된 ID·경로만 해제한다. 원래 패키지·등록 목록·증거를 보관하고 현재 고정 manifest와 문서 데이터는 유지하며 원래 ID로 복원할 수 있게 한다.

## 결과 보고

설치 가이드 8절의 형식으로 원본·버전·실제 설치 경로, 환경, 고정 manifest/등록 경로·작업 키, 실제 명령과 종료 코드, readback 검증과 상태, 관찰한 화면, 남은 사용자 입력과 복구 경로를 보고한다. 패키지 생성·유닛 테스트만 수행한 경우 실제 Figma 실행은 미확인으로 남긴다. 인증값과 pairing 상태 파일은 보고서·공유 패키지에 넣지 않는다.
