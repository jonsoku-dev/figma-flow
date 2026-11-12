# RD-04 설계서 · 동기화 변경을 골라 적용하기

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/graph_sync.py](../../../tools/graph_sync.py) | `build_plan, graph_panel, import_values, verify_readback` |
| [panel-ui/src/GraphPanel.jsx](../../../panel-ui/src/GraphPanel.jsx) | `diff 검토와 apply 메시지` |
| [figma-bridge/graph_token_sync.js](../../../figma-bridge/graph_token_sync.js) | `선택 scope의 실제 적용` |
| [figma-bridge/graph-panel.html](../../../figma-bridge/graph-panel.html) | `기존 패널 protocol` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

아래는 아직 구현되지 않은 메시지 제안이다.

```json
{"selected_changes":[{"kind":"token","key":"color/action"},{"kind":"component","id":"button","field":"paddingLeft"}],"plan_sha256":"64-hex-digest"}
```

표시 index를 identity로 쓰지 않는다. 실행기는 pinned plan에 선택이 속하는지 확인하고, 적용 가능한 closure를 계산한다. plan revision과 선택을 함께 결과에 남긴다. UI 메시지만으로 허용 범위를 늘릴 수 없다.

## 구현 결정

선택 가능한 변경 집합은 Python 계획 단계에서 만든다. UI는 선택 집합을 전달하며 JS 실행기는 같은 pinned identity를 검사한다. 선택 filtering 전후 모두 기존 scope 검사를 유지한다.

부분 적용 후 pairing baseline을 전체가 적용된 것처럼 갱신하면 안 된다. 선택된 값은 실제 읽기로 확정하고 미선택 값은 기존 관측/미해결 차이를 유지한다. 결과 report는 applied와 skipped를 구분하며 후속 import의 scope 근거로 사용한다.

첫 단위는 독립 token roots다. component field 선택은 alias/shared consumer closure와 baseline 갱신 정책을 고정한 뒤 추가한다. 같은 검토 화면 안에서 단계적으로 제공한다.

## 호환성·이관·복구

기존 protocol v1은 selected_changes 필드를 받지 않으며 기존 전체 적용 동작을 유지한다. 선택 기능은 새 protocol v2로 구분하고, v2에서는 selected_changes와 plan_sha256가 반드시 있어야 한다. 누락·빈 목록·알 수 없는 버전은 쓰기 전에 거절한다. v2의 전체 선택도 현재 plan의 모든 stable change identity를 명시한다. v1 메시지에 선택 필드를 보내면 조용히 무시하지 말고 거절한다. 새 selection 기능을 제거해도 원래 전체 적용 경로와 기록을 읽을 수 있어야 한다. 부분 성공 영수증을 전체 적용 성공으로 바꾸지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.


