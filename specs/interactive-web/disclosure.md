# SaaS FAQ 아코디언을 편집 가능한 Figma 프로토타입으로 변환하기

Figma Flow 0.35.0 후보는 단일 열림(`single-collapsible`) FAQ/아코디언 화면을 브라우저에서 관찰하고, 시작 상태(`initialState`)에서 방향 탐색(directed traversal)으로 도달 가능한 상태와 관찰한 클릭 전이만 Figma Design 프로토타입으로 연결한다. 디자이너는 상태별 프레임의 질문 텍스트·답변 텍스트·chevron 벡터 레이어를 편집한다. 기획자는 같은 시작 프레임(`All closed`)에서 열기·닫기·전환 여섯 방향 흐름을 재생한다. 개발자는 그래프에서 상태별 `answerSha256`, `contentSha256`, 출발 화면별 `controlElementId`, `autoClosedItem`과 목적지를 확인한다. [사용 안내](../../docs/guide.md#web-disclosure-quickstart) · [관찰 입력 형식](../../docs/web-disclosure-input.md) · [정본 그래프](graph.json)

## 실행과 인수 경로

1. 사용자가 로컬 Node 명령 `tools/web_disclosure_capture.mjs`를 실행한다. 격리 프로필의 headless Chromium이 페이지를 열고 전체 스크롤과 진입 애니메이션 안정화를 기다린 뒤 지정한 `--click` 순서대로 질문을 누른다. Computer Use, hook, 공식 Figma MCP와 API 토큰 없이 실행한다.
2. `single-collapsible` 불변식을 검사한다. 항목은 2~16개의 고유 라벨(<= 160자)이어야 하고, 상태마다 최대 1개 항목만 열려야 하며, `aria-expanded`·`data-state`와 실제 답변 텍스트 노출 여부가 일치해야 한다. 열린 항목의 trigger 상자는 전체 항목 상자를 덮지 않아야 하며, 각 클릭의 `hitTest`와 스크롤 고정을 확인한다.
3. `native_edit.py web-disclosure`가 관찰 기록을 정본 그래프에 결합한다. 관찰하지 않은 전이, self-loop, 중복 `expandedItem` 상태, `answerSha256` 누락·불일치, `action`/`autoClosedItem` 불일치, frame이 아닌 컨트롤, 화면 밖 대상, 그리고 `initialState`에서 directed traversal로 도달할 수 없는 상태(예: 분리된 순환 그래프)는 거절한다.
4. 자체 플러그인이 상태별 프레임을 만든다. 각 출발 상태의 trigger header 위에는 투명한 최상위 `Open · <질문>`, `Close · <질문>`, `Switch · <질문>` hotspot 프레임을 두고 즉시 `NAVIGATE`하는 `ON_CLICK` 반응을 연결한다. `initialState`가 흐름 시작점(`FAQ`)이 된다. 재적용 시 기존 프레임 ID를 재사용하고 편집된 반응을 덮어쓰지 않는다.
5. 실제 `read`로 프레임·hotspot·흐름 시작점이 `current`인지 확인한 뒤, Figma 프레젠테이션에서 여섯 방향 전이를 재생해 브라우저와 대조한다.

## 실제 SaaS FAQ에서 관찰한 결과

로컬 SaaS FAQ 섹션의 **5개 질문 중 2개 질문**(질문 1, 질문 2)을 1440 × 900 CSS px, DPR 1 데스크톱 레이아웃으로 열었다. 측정 화면 폭은 1425 px(세로 스크롤바 15 px)이고, 화면 요소 수는 `All closed` 51개, 질문 1 열림 52개, 질문 2 열림 52개다.

브라우저 캡처에서는 **7번 브라우저 입력**(질문 1 열기 → 닫기 → 다시 열기 → 질문 2로 전환 → 닫기 → 열기 → 질문 1로 전환)을 실행해 **3개 상태**와 중복 제거된 **6개 방향 전이**(열기 2, 닫기 2, 형제 전환 2)를 기록했다.

| 순서 | 브라우저 입력 및 관찰 결과 | Figma Design 프레젠테이션 (이전 후보 `e92b3ad`) |
| --- | --- | --- |
| 1 | `All closed`에서 질문 1 클릭 (`open`) → 첫 번째 답변 열림 | `Open · <질문 1>` → 질문 1 상태 프레임 이동 |
| 2 | 질문 1 열림 상태에서 같은 질문 클릭 (`close`) → `All closed` 복귀 | `Close · <질문 1>` → `All closed` 시작 프레임 복귀 |
| 3 | `All closed`에서 질문 1 다시 클릭 (전환 출발 상태 복귀) | `Open · <질문 1>`로 다시 첫 번째 답변 상태 이동 |
| 4 | 질문 1 열림 상태에서 질문 2 클릭 (`switch`, 첫 질문 자동 닫힘) | `Switch · <질문 2>` → 세 번째 상태 프레임 이동 |
| 5 | 질문 2 열림 상태에서 같은 질문 클릭 (`close`) → `All closed` 복귀 | `Close · <질문 2>` → `All closed` 시작 프레임 복귀 |
| 6 | `All closed`에서 질문 2 클릭 (`open`) → 두 번째 답변 열림 | `Open · <질문 2>` → 세 번째 상태 프레임 이동 |
| 7 | 질문 2 열림 상태에서 질문 1 클릭 (`switch`, 두 번째 질문 자동 닫힘) | `Switch · <질문 1>` → 두 번째 상태 프레임 이동 |

브라우저 측은 캡처 CLI의 headless Chrome(1440 × 900, DPR 1) 마우스 입력으로 확인했다. Figma 측은 이전 후보(`e92b3ad`)에서 Figma Desktop 적용·재적용(`frame_ids_reused: true`)·실제 `read`(`status: "current"`) 및 프레젠테이션 여섯 방향 클릭 도달을 확인했다.

## 확인한 한계와 수정 후보 구분

- **도달성 검증 보완 및 별도 게이트**: 이전 후보(`e92b3ad`)의 실제 Figma 프레젠테이션 확인 당시에는 네이티브·Python 검증이 `initialState` 또는 임의 전이의 도착 여부(`edge.to`)만 확인해, 시작 상태에서 도달할 수 없는 분리 순환(disconnected cycle)을 허용하는 한계가 있었다. 후속 커밋(`066830a`, `43a8b1b`)에서 `tools/web_design.py`와 `figma-bridge/web_design.js`가 모두 `initialState`에서 directed traversal(BFS)로 모든 상태 도달을 검사하도록 수정했고, Python·Node 공개 진입점 단위 테스트로 분리 순환 거부를 확인했다. 수정된 0.35.0 후보의 최종 게이트와 설치 검증은 별도 검증 절차에서 수행한다.
- **프레젠테이션 좌표**: `e92b3ad` 프레젠테이션 첫 클릭은 CSS 픽셀 좌표가 HiDPI 표시 좌표와 맞지 않아 `All closed`에 머물렀고, 실제 display 픽셀 좌표로 다시 클릭해 여섯 방향 전이 전체를 확인했다.
- **범위 밖 항목**: 5개 FAQ 질문 중 나머지 3개 질문 조합, 키보드(`Enter`·`Space`·화살표)와 스크린리더 의미, 다중 열림(`multi-collapsible`) 아코디언, 웹 CSS 높이 애니메이션 보간은 이번 프로토타입에 포함하지 않는다.
