# RD-04 설계서 · 동기화 변경을 골라 적용하기

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/graph_sync.py](../../../tools/graph_sync.py) | `build_plan, graph_panel, import_values, verify_readback` |
| [panel-ui/src/GraphPanel.jsx](../../../panel-ui/src/GraphPanel.jsx) | `diff 검토와 apply 메시지` |
| [figma-bridge/graph_token_sync.js](../../../figma-bridge/graph_token_sync.js) | `선택 scope의 실제 적용` |
| [figma-bridge/graph-panel.html](../../../figma-bridge/graph-panel.html) | `기존 패널 protocol` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

`selection_manifest(plan)`은 정확한 plan의 `plan_sha256`와 stable identity를 가진 `figma-flow-selection-v2` manifest를 만든다. 생성 번들의 `GRAPH_SELECTION_MANIFEST`가 권한 기준이며 UI가 보낸 manifest나 변경 값은 신뢰하지 않는다.

```json
{"type":"apply","protocol":2,"plan_sha256":"64-hex-digest","selected_ids":["stable-change-identity"]}
```

identity는 token root 또는 component와 field로 만들며 표시 index를 쓰지 않는다. 같은 root의 alias와 component field 소비자는 하나의 group이다. `selectedPlan`은 group 전체 선택, 중복·빈 목록·미등록 identity와 plan hash를 검증한다. `selected_changes` 같은 UI 소유 변경 객체는 실행 권한으로 받지 않는다.

## 구현 결정

부분 선택은 선택하지 않은 token의 값을 `before`로 유지한 plan을 기존 실행기로 전달한다. 실행기는 원래의 file, page, collection, main/instance, binding과 compare-and-set 검사를 수행한다. 비동기 font load 뒤와 쓰기 직전에도 scope와 baseline을 다시 확인한다.

부분 적용은 `partial_apply`와 `selected_ids`를 readback에 남기며 전체 graph marker를 진전시키지 않는다. `verify_readback`과 후속 import는 부분 결과를 완전한 pairing이나 native edit intent로 받지 않는다. 새 token 생성 또는 binding repair를 포함한 migration은 전체 선택이 필요하다. fixture helper의 `baseline` 결과는 실제 page marker 갱신과 구분한다.

## 호환성·이관·복구

protocol v1 또는 protocol 생략은 기존 전체 적용 경로를 사용하며 선택 필드를 함께 보내면 거절한다. v2는 `plan_sha256`와 비어 있지 않은 `selected_ids`가 필수다. 알 수 없는 protocol은 쓰기 전에 거절한다. 전체 선택도 manifest의 모든 stable identity를 명시한다. 부분 결과를 전체 성공으로 바꾸거나 pairing baseline을 추정 갱신하지 않는다. 기존 오류·rollback 경로를 유지한다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.


