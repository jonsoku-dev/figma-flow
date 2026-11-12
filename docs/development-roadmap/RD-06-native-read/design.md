# RD-06 설계서 · 목적별 네이티브 읽기와 제한된 캐시

상태는 0.27 구현 후보이며 표준 discovery 요약의 실제 관찰은 일부 확인됐다. RD-06 전체 Figma 인수는 대기다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/native_semantic_read.js](../../../figma-bridge/native_semantic_read.js) | `readNativeSemantics와 rasterImages` |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `readback, exportReadback, syncToApp` |
| [figma-bridge/direction_review.js](../../../figma-bridge/direction_review.js) | `readDraft` |
| [figma-bridge/native_edit.js](../../../figma-bridge/native_edit.js) | `네이티브 읽기` |
| [tools/graph_sync.py](../../../tools/graph_sync.py) | `discovery_bundle`의 생성 host: `discoverGraphSummary`, `discoverGraphNative`; full 소비자: `normalize`, `verify_readback` |
| [panel-ui/src/GraphPanel.jsx](../../../panel-ui/src/GraphPanel.jsx), [legacy 패널](../../../figma-bridge/graph-panel.html), [번역](../../../figma-bridge/locales/graph.json) | discovery 전용 summary 버튼·partial 표시·별도 JSON 저장·최신 읽기 진단 |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

공유 `readNativeSemantics(figma,page)`는 옵션이 없으면 full을 읽는다. 세 번째 인자 `{profile:"summary",nodeIds:[...],fields:[...]}`는 중복 없는 비어 있지 않은 ID와 field 목록을 요구한다. summary 지원 field는 `x`, `y`, `width`, `height`, `visible`이다. 지원 밖 field를 요구하면 full을 읽는다.

summary는 `figma-flow-native-read-summary-v1`과 `coverage:{profile,nodeIds,fields,complete:false,omitted}`를 반환한다. style, variable, collection, raster image, text segment closure는 생략 목록에 남긴다. `requireFullNativeRead`는 summary를 저장·검증용 full evidence로 받지 않는다. full에는 실제 `clipsContent`와 `overflowDirection` getter가 포함된다.

## 구현 결정

같은 reader가 full과 제한된 summary를 담당한다. ImportPanel의 읽기 전용 NativeSummary는 범위를 표시한다. 표준 graph discovery에는 별도 `native-summary` 동작이 있으며 기본 `read`·full export·draft·native-edit와 전체 graph 소비자는 full 경계를 유지한다. summary에 없는 값을 선언 또는 cache로 채워 검증하지 않는다.

표준 discovery의 `discoverGraphSummary`는 승인된 주 페이지를 로드하고 그 페이지와 하위 노드 ID만 열거하여 `width`, `height` 두 필드를 요청한다. 이 고정 경로는 full fallback을 하지 않는다. `coverage.pageIds`는 주 페이지 하나이며 공통 `nodeIds`, `fields`, `omitted`, `complete:false`를 함께 반환한다. `expected_scope`는 전체 허용 페이지 범위를 보존하므로 실제 summary coverage와 구분한다. 기본 `discoverGraphNative`는 허용된 모든 페이지를 fresh full로 읽는다. 읽기 전후 file·주 page scope를 확인하며 busy 중 중복 요청·쓰기는 수용하지 않는다.

React와 legacy 패널은 discovery에만 요약 버튼을 제공하고 `graph-native-summary.json`으로 저장한다. 요약의 실제 범위와 누락을 표시하며 진단은 최신 readback을 사용한다. summary를 full evidence나 pairing 완료로 승격하지 않는다.

session snapshot cache는 구현하지 않는다. `nativeReadSessionSnapshot()`은 null이고 호출마다 native 값을 다시 읽는다. raster image 중복 읽기 제거는 한 full 읽기 안에서만 적용하며 같은 hash의 상충 bytes는 거절한다.

`nativeReadGetterLedger`와 `compareNativeReadProfiles`는 동일 fixture의 getter, 요청 field 일치, UTF-8 JSON bytes를 비교한다. fixture 수치로 실제 Figma 지연 감소, 원격 편집 무효화 또는 모든 문서의 동등성을 주장하지 않는다.

## 호환성·이관·복구

기존 인자 없는 호출은 full을 유지한다. summary의 누락 node는 오류이고 full 소비자에게 partial을 넘기지 않는다. 영속 cache와 cache migration은 없다. 실제 Figma 편집과 페이지 전환 뒤 새 읽기 및 전체 소비자의 결과는 별도 인수 관찰 대상이다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.

## 확인된 실제 범위와 남은 인수

주 세션은 R7 실제 summary 4,818개 노드의 width/height가 이전 full과 정확히 일치함을 확인했다. 진단 JSON의 summary profile·complete false·node ID/field/omission 목록도 일치했고 무거운 필드는 없었다. 일반 graph import `--apply`·pair는 summary를 거절했고 출력 없음·graph bytes 보존을 확인했다. 이는 이 페이지·두 필드의 실제 관찰이며 다른 필드나 모든 편집·페이지 전환의 최신성 보장이 아니다.

[고정 회귀 검사](../../../tests/finalize_discovery_summary.cjs)는 `dca7dfcb4ec97ee52427a40050e815f53880d47e`에서 제품 변경 전에 보존됐다. 변경 전 예상 assertion 실패와 변경 후 동일 blob 통과는 주 세션 근거다. full 기본값·모든 허용 페이지·summary scope·진단·읽기 전용 경계를 검사한다. 실제 GUI에서 후속 full이 요약 진단을 교체하는 관찰과 전체 AC·보존 검사 연결은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 남은 대기 범위다. 설치는 0.26.3, native는 0.27 후보이며 push·후보 설치 후 검증도 별도다.
