---
name: figma-plugin-setup
description: Install Figma Flow in Codex, connect its generated Figma development plugin, verify actual readback, or update and repair that connection. Handles private repositories, company npm registry setup, and environments with or without Computer Use.
---

# Figma 플러그인 설치·연동·업데이트

## 적용 범위와 입력

Figma Flow의 **Codex 설치**, 프로젝트별 **Figma 개발 플러그인**, 사용 중일 때만 **paired sync**를 구분한다. 디자인 제작·후보 선택은 기존 `figma-flow` 절차를 사용한다. 입력은 원본 URL/태그, 마켓플레이스·설치 경로, 프로젝트/현재 리뷰, 등록 manifest, Computer Use 가능 여부다. 현재 대화와 로컬 파일에서 확인한 값은 재사용한다.

이 파일의 두 단계 위가 동봉된 플러그인 루트다. 경로를 설치 캐시 관례로 추정하지 말고 실제 파일로 확인한다. 첫 설치는 아직 이 스킬이 없으므로 [설치 프롬프트](../../docs/installation-and-updates.md#1-클론-전부터-codex에-맡기기)를 사용하고, 설치 후 이 스킬을 읽는다.

해당 분기의 문서만 읽는다.

- 브라우저에서 설치 자료·사이트·로컬 페이지를 열 때: [허용 대상 등록과 적용 확인](../figma-flow/references/browser-access.md). 실제 작업에 필요한 새 대상은 등록 후 계속한다. Figma Desktop 자체의 접근 승인은 해당 앱 경로를 따른다.
- 최초 설치·읽기 검증: [설치·연동 가이드](../../docs/installation-and-updates.md)의 1~5절.
- private 복제·회사 배포: [private 저장소 가이드](../../docs/private-repository.md). 읽기 권한 확인과 원격 생성·업로드 권한은 별개다.
- Node/npm 설정: [npm 환경 가이드](../../docs/npm-environment.md). 회사 레지스트리 도메인/전체 URL과 전체 미러·`@scope` 적용 여부를 **사용자에게 묻고** 설정한다. 기존에 확인한 설정이면 값을 대조해 재사용한다. 토큰을 대화에 요청하지 않는다.
- 최신화·복구: 설치·연동 가이드의 [6절](../../docs/installation-and-updates.md#6-업데이트와-되돌리기).

## 1. 현재 상태 확인

1. 원본 루트, `git status`, 태그/커밋, 두 plugin manifest 버전, 마켓플레이스 JSON을 읽는다. 현재 CLI의 plugin/marketplace `--help`, `list --json`으로 실제 지원 문법과 설치 소스를 확인한다. 다른 작업이 있는 클론은 보존하고 새 전용 클론에서 진행한다.
2. 최신 요청은 해당 공개/회사 저장소의 최신 **정식 GitHub Release**를 확인한 뒤 정확한 태그·커밋으로 고정한다. 릴리스가 없으면 게시된 안정 버전을 추측하지 말고 사용할 ref를 사용자에게 받는다. 서로 다른 회사/개인 마켓플레이스가 같은 이름이면 덮어쓰기 전에 구분한다.
3. 로컬 파일/CLI와 Figma Desktop의 위치를 확인한다. 원격 Codex가 만든 파일은 Desktop이 있는 머신으로 전체 패키지를 전달한다. Computer Use가 없으면 이후 Figma 조작만 사용자에게 넘긴다. Figma가 목적지인 요청을 HTML로 변경하지 않는다.

완료 기준: 원본·설치·실행 머신과 대상 프로젝트를 구분하고, 변경할 경로와 보존할 경로가 특정된다.

## 2. Codex 플러그인과 환경 준비

1. 최초 설치는 실제 마켓플레이스 이름으로 `codex plugin marketplace add <source> --json`, `codex plugin add figma-flow@<name> --json`을 사용한다. 기존 소스가 맞으면 재사용한다. `add`의 `installedPath`, 목록의 `installed`, `enabled`, `version`, `marketplaceSource`를 읽고 설치 복사본의 두 manifest를 대조한다.
2. 새 스킬이 현재 채팅에 로드되지 않으면 설치 경로·버전·프로젝트·다음 단계를 넣은 이어가기 프롬프트를 제공한다. 사용자가 새 채팅에서 계속할 수 있게 한다. 요청 없이 새 채팅을 생성하거나 사용자의 Codex UI를 자동 조작하지 않는다.
3. `.nvmrc`에 고정된 현재 LTS와 실제 `node --version`을 대조한다. “현재 LTS로 변경” 요청일 때는 공식 Node.js 자료에서 당시 최신 LTS를 확인하고 정확한 버전을 쓴다. 설정 파일만 확인했으면 실제 런타임 검증과 구분한다.
4. npm 문서에 따라 사용자가 지정한 URL·스코프만 프로젝트 `.npmrc`에 반영한다. URL은 HTTPS, 정상 host, userinfo/query/fragment/공백·제어 문자 없음으로 검증하고 서비스 경로를 보존한다. 인증은 사용자별 registry 범위 설정으로 유지한다. 기존 `.npmrc`를 저장소 밖의 전용 위치에 보존하고 필요한 키만 편집한다. `npm config set`이 제거한 주석은 백업과 대조해 복원한다. `package-lock=false`, lockfile ignore와 실제 추적 여부를 확인한다. lockfile을 GitHub에 올리지 않는다.
5. 루트에는 `package.json`이 없으므로 npm 설치를 실행하지 않는다. 저장소 밖의 Python 가상환경에 `requirements-optional.txt`를 설치하고 같은 Python으로 예제·검증 도구를 실행한다. 실제 앱에 npm 설치가 필요할 때만 그 앱의 매니페스트·레지스트리·lockfile 정책을 별도로 확인한다.

6. 브라우저·Playwright 검수까지 맡긴 작업이면 [브라우저 접근 등록](../figma-flow/references/browser-access.md)에 따라 실제 로컬 URL·작업 사이트를 등록한다. 현재 프로젝트 루트에서 도구를 실행하고 반환된 `mcp_server`로 그 프로젝트의 로컬 설정을 만든다. 실행 파일은 PATH에서 확인하며 다른 사용자의 홈·클론·설치 캐시 경로를 복사하지 않는다. 허용 목록을 적용할 수 있는 MCP가 없으면 공식 Playwright MCP를 프로젝트에 설정하고 같은 등록 JSON을 `--config`로 연결한다. 프로젝트 설정·도구 목록·실제 resolved config를 확인하며, 새 연결이 현재 채팅에 로드되지 않으면 설정 경로와 재연결 후 검증할 도구를 명시한다. 브라우저를 쓰지 않는 Figma Design 전용 경로에는 MCP 설치를 요구하지 않는다.

완료 기준: 실제 Codex 설치 경로·버전이 확인되고 환경·의존성이 준비된다. 브라우저 분기는 MCP 설정·실제 연결·허용 목록 적용을 각각 보고한다. 설치 성공은 Figma 연결 성공과 별도로 보고한다.

## 3. 검토 패키지와 실제 Figma 연결

1. 설치된 복사본의 `examples/native-direction-review/demo.py --out <새 폴더>`로 첫 워크숍을 만들고 `tools/design_actions.py status --manifest <review/directions.json>`에서 `NATIVE_REVIEW_PENDING`을 확인한다. 기존 프로젝트를 무단 재생성하지 않는다.
2. 해당 프로젝트의 검토용 개발 ID가 있으면 manifest에서 숫자 문자열을 읽는다. 없으면 Figma Desktop의 **플러그인 → 개발 → 새 플러그인 → Figma Design → 사용자 정의 UI → 전용 폴더에 저장**으로 발급받는다. 계정 로그인·접근 승인은 사용자 단계다. 다른 캠페인의 ID를 빌리지 않는다.
3. `tools/design_actions.py prepare-native-review --manifest <directions.json> --plugin-id <실제 ID> --out <새 폴더>`로 패키지를 만들고 출력의 `prepared.manifest`를 확인한다. `manifest.json`, `code.js`, `ui.html`의 절대 경로를 전달한다.
4. Figma Desktop에서 **개발 → 매니페스트에서 플러그인 가져오기 → 해당 manifest 선택 → 개발 플러그인 실행 → 검토 시안 만들기 → 결과 JSON 저장**을 진행한다. 등록 중복은 프로젝트·ID·전용 폴더를 대조하고 해당 폴더를 백업한 뒤 같은 패키지의 세 파일을 함께 사용한다.
5. 실제 내보낸 JSON을 받은 뒤 `verify-native-review --manifest <현재 directions.json> --readback <실제 파일>`과 `status`를 실행한다. 성공 상태는 `WAIT_SELECTION`이다. 실패 진단은 보존하고 원본 입력에서 수정한다.
6. 실제 크기의 데스크톱·모바일에서 글자 잘림·겹침·버튼 정렬, 주요 프로토타입과 복귀, 주석 링크를 확인한다. 내보낸 PNG를 사용할 수 있다. JSON 비교, 화면 관찰, 사용자 선택의 근거를 구분한다. 실제 선택 전에는 본제작을 시작하거나 선택 영수증을 만들지 않는다.

**Computer Use 없음:** 설치 가이드 4절의 단계별 버튼·예상 파일·다음 프롬프트를 제공하고, 사용자가 manifest 또는 readback 경로/파일을 줄 때 해당 단계부터 계속한다. 파일이 아직 없으면 연결 검증은 pending이며, 생성한 패키지와 실행할 검증 명령을 남긴다. 수동 경로도 같은 JSON 검사와 상태 기준을 사용한다.

**Computer Use 있음:** 지정한 Figma Desktop 파일·메뉴·관련 선택/저장 창만 조작한다. 앱의 접근 승인과 사용자 확인을 준수한다. 도중에 불가능해지면 이미 만든 패키지를 보존하고 같은 수동 경로로 이어간다.

## 4. 업데이트·복구 분기

설치 가이드 6절을 읽고 다음 순서로 진행한다.

1. 이전 설치 버전·원본/ref·재설치 가능한 소스와 Figma 패키지·등록 경로를 보존한다. 삭제될 수 있는 설치 캐시만 롤백 사본으로 삼지 않는다.
2. 새 릴리스를 별도 클론에 준비하고 해당 마켓플레이스만 갱신한다. `marketplace upgrade`는 소스 갱신이며 고정 ref 변경이나 설치 캐시 교체의 증거가 아니다. 현재 CLI가 지원하는 해당 플러그인 재설치 후 실제 새 버전·소스·스킬을 대조한다.
3. 새 설치 도구로 **새 출력 폴더**에 프로젝트의 검토용 또는 본제작용 패키지를 만든다. 같은 프로젝트·용도의 ID는 유지하고 두 용도를 섞지 않는다. 등록된 Figma 경로를 새 패키지에 맞추고 실행 중인 이전 창을 닫는다.
4. 새 코드 실행과 실제 새 readback을 검증한다. 기존 페이지를 보존하는 반복 import는 새 입력이 적용됐다는 증거가 아니다. 원본 변경·선택 무효화는 기존 워크플로의 재검토 절차로 처리한다. 실패하면 새 진단을 남기고 이전 패키지 **전체**와 설치 소스로 되돌린다.
5. paired sync 사용 중일 때만 token-sync와 bridge 문서를 읽는다. 정확한 해당 서버만 종료하고 상태 폴더·비밀값·저널을 보존한다. 기존 컴패니언 변경을 거부하면 새 private 상태 디렉터리에서 준비한다. 일반 업데이트를 위해 `--prior-sync`를 임의 사용하지 않는다. 수동 사용자도 새 컴패니언 등록·baseline·결과 전달을 같은 순서로 진행한다.

## 결과 보고

설치 가이드 8절의 형식으로 원본·버전·실제 설치 경로, 환경, 패키지/등록 경로, 실제 명령과 종료 코드, readback 검증과 상태, 관찰한 화면, 남은 사용자 입력과 복구 경로를 보고한다. 패키지 생성·유닛 테스트만 수행한 경우 실제 Figma 실행은 미확인으로 남긴다. 인증값과 pairing 상태 파일은 보고서·공유 패키지에 넣지 않는다.
