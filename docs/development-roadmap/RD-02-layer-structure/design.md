# RD-02 설계서 · 의미 있는 레이어 계층과 컨테이너

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/direction_review.js](../../../figma-bridge/direction_review.js) | `화면 layers/controls 작성과 prototype 연결` |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `layout, importDesign` |
| [tools/design_bundle.py](../../../tools/design_bundle.py) | `구조화 입력 검증` |
| [tools/design_directions.py](../../../tools/design_directions.py) | `방향 패킷 작성` |
| [figma-bridge/native_semantic_read.js](../../../figma-bridge/native_semantic_read.js) | `부모·geometry 실제 읽기` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

아직 구현되지 않은 선택적 입력 예시다.

```json
{"containers":[{"key":"card","kind":"auto-layout","parent":null,"children":["title","actions"],"layout":{"direction":"VERTICAL","gap":12,"padding":[16,16,16,16],"width":"fixed","height":"hug"}}]}
```

`parent:null`은 기존 화면 Frame을 뜻한다. key는 화면 안에서 유일하다. leaf와 container가 같은 key를 쓰지 않는다. Group에는 layout/fill/clip을 허용하지 않는다. 미지원 grid·absolute hybrid는 첫 단위에서 오류로 알리고 추정하지 않는다.

## 구현 결정

검증기가 트리를 먼저 정상화하고 전위 순서로 container를 만든다. Group은 자식 생성 후 실제 자식으로 묶으며, Frame은 부모 geometry를 기준으로 자식을 재배치한다. 부모 좌표로 바꿀 때 absolute transform과 의도한 화면 기준 geometry를 함께 보존한다.

기존 leaf의 ownership, token binding, main component 관계와 annotations를 옮겨도 key와 target identity는 유지한다. 상위 상태 Frame의 ID·크기·clip·flow start는 고정한다. 실제 prototype target이 내부 Group으로 이동하면 실패로 처리한다.

Auto Layout은 원본이 선언한 관계를 투영한다. linear container에서 지원되는 hug/fill/fixed를 먼저 구현하고, 임의 wrap/grid 추론은 후속으로 남긴다.

## 호환성·이관·복구

containers가 없으면 기존 경로를 그대로 사용한다. 새 트리를 기존 페이지에 적용할 때 소유 leaf만 이동하고 사용자 레이어는 건드리지 않는다. 기존 leaf의 부모와 transform을 복구 계획에 보존한다. 부모 추가가 실패하면 새로 만든 container만 제거하고 기존 노드를 원래 부모와 위치로 되돌린다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.

## 공식 근거

- [Frame과 Group의 차이](https://help.figma.com/hc/en-us/articles/360039832054-The-difference-between-frames-and-groups)는 자식을 따라가는 Group bounds와 명시적인 Frame bounds를 구분한다.
- [Frames](https://help.figma.com/hc/en-us/articles/360041539473-Frames-in-Figma-Design)는 화면·배치·clipping 등 Frame의 역할을 설명한다.
- [Auto Layout](https://help.figma.com/hc/en-us/articles/360040451373-Guide-to-auto-layout-in-Figma)은 방향·간격·padding·정렬·sizing의 근거다.
- [접근 가능한 prototype](https://help.figma.com/hc/en-us/articles/7810391964695-Accessible-prototypes-in-Figma)은 상위 frame/component/instance의 의미 있는 이름을 설명한다.
