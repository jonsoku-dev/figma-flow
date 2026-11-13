# NF-07 웹 가져오기와 에디터 기능 범위

0.30.0에서 웹 캡처 → 그래프 → 편집 가능한 Design 프레임 경로를 구현했다. Portfolio·Codeforge 홈, DevTool 블로그, SaaS 가입 화면의 실제 브라우저와 Figma 읽기를 확인했다. 아래 설계 중 디자인 시스템의 기존 컴포넌트와 자동 매핑, CSS 마스크·필터 복원, 편집기별 전체 기능표는 후속 범위다. [현재 사용법](../web-design-capture.md) · [실측과 제한](../editable-web-verification.md) · [API 우선순위 재생](../api-priority.md)

## Web import

### 기능 계약

사용자는 접근 권한이 있는 페이지를 캡처하고, 보이는 구조를 검토한 뒤 지원되는 요소를 기존 디자인 소스로 매핑하고 일반 native import를 준비할 수 있다. 입력은 사용자가 승인한 브라우저 캡처 파일이다. 서버에서 임의 URL을 가져오거나 플러그인 안에서 페이지 script를 실행하지 않는다.

첫 범위는 보이는 제목·텍스트·이미지·링크·폼 레이블·컨트롤·제한된 컨테이너다. source 순서, 지원하는 계산 스타일, 의미 role, 안정된 capture ID를 보존한다. 지원하지 않는 속성과 모호한 구조는 검토 결과에 남긴다. mapper는 component family, 접근성 의미, 상호작용, native 값을 추측하지 않는다.

### 데이터와 구현 경로

버전이 지정된 `web-observation-v1` JSON artifact를 받는다. 각 node는 capture ID, 부모 ID, tag와 role, 표시 여부, bbox, 검토된 텍스트, 허용된 계산 스타일 일부, 선택적인 hash 고정 asset reference를 갖는다. artifact에는 page origin, viewport, capture 시각과 coverage를 기록한다. Cookie, 인증 헤더, 폼 값, 숨겨진 텍스트, password 필드, script 내용, 임의 HTML attribute는 넣지 않는다.

초기 상한 제안은 node 5,000개, JSON 2 MiB, asset 100개, asset 합계 10 MiB다. output을 만들기 전에 초과를 거절한다. asset은 capture artifact나 사용자가 선택한 local directory에서만 읽는다. symlink, 경로 탈출, 원격 asset URL, hash 불일치는 거절한다.

순수 adapter의 흐름은 다음과 같다.

```text
web-observation-v1 -> 검토된 매핑 -> 기존 디자인 소스 -> 일반 importer
```

adapter는 mapping plan과 unsupported 목록을 반환한다. Figma에는 쓰지 않는다. 별도 CLI는 정확한 source artifact, target graph SHA, 새 출력 디렉터리를 받는다. 사용자가 plan을 검토한 뒤 기존 `tools/figma_bridge.py` 경로로 native plugin을 준비한다. `tools/design_system.py`, `tools/figma_bridge.py`, `tools/native_handoff.py`를 재사용한다. 두 번째 native writer를 만들거나 `figma-bridge/code.js` 안에 범용 HTML parser를 넣지 않는다.

Web capture ID와 native node ID는 다른 식별자로 저장한다. 검토된 graph mapping에 capture ID와 source origin을 기록한다. 일반 importer는 실제 ID와 readback을 반환한다. Screenshot이나 생성 graph는 native 인수 증거가 아니다.

### 검토와 실패 상태

준비 전에 source origin, viewport, capture 시각, 지원 node 수, 제외한 내용 수와 unsupported field를 보여준다. Mapping 충돌, 부모 누락, asset 오류, 미지원 layout, 접근성 공백을 나눠 표시한다. 상태는 `ready`, `partial`, `stale-source`, `conflict`, `unsupported`를 쓴다. `partial`은 전체 import 성공이 아니다.

Capture가 제공한 web label, button 이름, heading level, link destination, table header, native control 의미를 보존한다. Capture에 의미 정보가 없으면 `unknown`으로 남긴다. Web 접근성을 픽셀 유사성에서 추정하지 않는다.

### 검증과 rollback

Deterministic conversion, node order, parent identity, 지원 style 값, escaped text, 민감 필드 제외, unsupported input, 과대 입력, asset hash 오류, symlink/경로 거절, 오래된 graph SHA, 재실행 준비를 검사한다. 복사한 source artifact와 임시 output 디렉터리에서 테스트한다.

기존 source 및 importer 검사도 실행한다.

```sh
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_native_handoff.py'
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
```

새 `tests/test_web_import.py`와 작은 `tests/fixtures/web-import/` fixture를 추가한다. End-to-end 검사는 생성한 source artifact가 기존 bridge preflight를 통과하는지 확인하고 격리 API fixture에서 importer readback을 대조한다. 기존 verifier 파일은 느슨하게 바꾸지 않는다.

Native importer가 쓰기와 rollback을 맡는다. Mutation 전에 정확한 file/page, graph SHA, 대상 node ID와 before 값을 고정한다. 실패하면 이번 import가 만든 node만 제거한다. 현재 값이 이번 import가 쓴 값과 같을 때만 원래 값으로 돌린다. 동시 편집은 보존하고 복구 충돌을 보고한다. 재실행은 ownership과 source identity가 일치하는 node만 재사용한다.

Cursor 구현 프롬프트:

```text
NF-07 web import만 구현하라. 현재 디자인 source, native bridge, handoff verifier와 저장소 규칙을 먼저 읽어라. 제한된 사용자 승인 web-observation-v1 artifact만 받는다. Adapter는 순수 함수로 유지하고 기존 디자인 source와 native importer를 재사용하라. 임의 URL fetch, page script 실행, 숨겨진 폼 값 가져오기, 의미 추측, adapter 직접 쓰기, package 설치, 사용자 지정 file/page 범위 없는 Figma 호출은 금지한다. 결정적 변환, 보안·크기 거절, 오래된 SHA, 임시 source end-to-end 검사를 추가하라. 기존 독립 verifier를 보존하라. before 값과 ownership을 고정하고 실제 readback을 대조하라. 이번 import node와 변경값만 rollback하라. readback 또는 rollback이 충돌하면 실제 상태를 보고하고 중단하라. mapping 계약, 변경 파일, 명령별 결과, native 근거와 미검증 에디터를 반환하라.
```

## Editor capability matrix

### 기능 계약

Feature route는 에디터·mode·operation별로 버전이 있는 지원 상태가 필요하다. Matrix는 `supported`, `unsupported`, `unknown`을 구분한다. `unknown`은 닫힌 상태로 두고 local 대안을 안내한다. API declaration, `editorType` 문자열, manifest 하나만으로 runtime 지원을 확정하지 않는다.

첫 표는 Figma Design에서 관측한 기능을 다룬다. 각 기능을 따로 기록한다. 예를 들면 문서 읽기, node 쓰기, variable, component property, reaction, widget runtime, page access다. 최소 API/manifest 요건, 공식 문서 출처, 마지막 문서 확인, runtime 증거 ID를 보존한다. 한 기능이 동작한다고 에디터 전체를 지원으로 표시하지 않는다.

### 구현과 검증

고정된 `editor-capabilities-v1` JSON source와 read-only lookup을 만들고 `tools/figma_feature.py`에서 사용한다. Matrix를 route prerequisite에 손으로 복사하지 않는다. 사용자용 reference는 이 data에서 생성한다. 모든 `supported` 항목은 공식 출처와 같은 에디터/mode의 실제 검사를 요구한다. 둘 다 생기기 전에는 `unknown`이다. Matrix는 file access, plugin permission, 설치, 쓰기 승인을 부여하지 않는다.

각 row의 schema, source reference, 오래된 검토일, status 동작을 검사한다. `unknown`과 `unsupported`는 이유가 있는 non-executed route를 반환한다. `supported` route에도 현재 범위와 사용자 승인이 필요하다. 지원한다고 기록한 에디터/mode에서 최소 한 번 실제 read와 write를 확인한다. Mock이나 build로 이 관찰을 대체하지 않는다.

Rollback은 matrix entry나 생성 reference를 제거하는 것이다. Router 상태는 다시 `unknown`이 된다. 오래된 support claim을 재사용하지 않는다. Lookup을 추가하면서 기존 route 검사나 실행 권한은 바꾸지 않는다.

Cursor 구현 프롬프트:

```text
NF-07 editor capability matrix를 구현하라. 각 후보 editor와 operation을 현재 공식 문서와 일치하는 runtime에서 먼저 확인하라. versioned data file, pure lookup, 생성 reference와 테스트를 추가하라. 기본은 unknown이다. API 이름이나 editorType으로 runtime을 추정하지 않는다. tools/figma_feature.py의 모든 기존 scope, permission, confirmation gate를 유지하라. 설치, account 변경, Figma 쓰기 또는 network discovery를 추가하지 않는다. source와 runtime 증거를 분리해 기록한다. stale, missing, unsupported, supported entry를 검사한다. Rollback은 data entry를 제거하고 router가 unknown을 반환하는지 검증한다.
```
