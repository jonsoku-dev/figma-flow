# RD-02 설계서 · 의미 있는 레이어 계층과 컨테이너

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/direction_review.js](../../../figma-bridge/direction_review.js) | `화면 layers/controls 작성과 prototype 연결` |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `layout, importDesign` |
| [tools/design_bundle.py](../../../tools/design_bundle.py) | `구조화 입력 검증` |
| [tools/design_directions.py](../../../tools/design_directions.py) | `방향 패킷 작성` |
| [figma-bridge/native_semantic_read.js](../../../figma-bridge/native_semantic_read.js) | `부모·geometry 실제 읽기` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

선택적 `containers`는 `key`, `kind`, `parent`, `children`과 종류별 geometry, layout, fill, clip을 선언한다. `kind`는 `frame`, `group`, `auto-layout`이다. `parent:null`은 기존 화면 Frame이다. `normalize_layer_containers`와 `validateDeclaredContainers`가 중복 key, 잘못된 부모·자식, cycle, 지원하지 않는 layout을 거절한다.

Auto Layout의 방향은 `HORIZONTAL` 또는 `VERTICAL`이고 gap, padding, width와 height의 `fixed`, `hug`, `fill`을 사용한다. Group에는 layout, fill, clip을 넣지 않는다. `scroll`은 `kind:"frame"`과 `clip:true`를 함께 선언한 경우에만 `none`, `horizontal`, `vertical`, `both`를 받는다. 생략하면 스크롤을 추론하지 않는다. 작성 뒤 `clipsContent`와 실제 `overflowDirection` getter를 읽고 선언과 다르면 실패한다.

## 구현 결정

`placeDeclaredLayerParents`는 선언한 Frame과 Auto Layout Frame을 만들고 정적 묶음은 실제 자식으로 Group을 만든다. 화면 기준 geometry를 부모 좌표로 바꾸고 실패 시 변경을 복구한다. semantic key와 main/instance 관계, 화면 Frame과 prototype target은 유지한다.

Auto Layout 부모에 붙인 뒤 `layoutSizingHorizontal`과 `layoutSizingVertical`을 설정한다. `fill`은 Auto Layout 부모에서만 `FILL`이 되고 그 밖에서는 `FIXED`다. 재사용 경로도 `refreshDeclaredContainerSizing`으로 다시 맞춘다. `readDeclaredContainerLinks`는 실제 부모, 순서, geometry, sizing과 선언된 스크롤을 읽는다. 일반 getter에 없는 값을 선언으로 채워 넣어 성공시키지 않는다.

## 호환성·이관·복구

containers가 없으면 기존 경로를 그대로 사용한다. 새 트리를 기존 페이지에 적용할 때 소유 leaf만 이동하고 사용자 레이어는 건드리지 않는다. 기존 leaf의 부모와 transform을 복구 계획에 보존한다. 부모 추가가 실패하면 새로 만든 container만 제거하고 기존 노드를 원래 부모와 위치로 되돌린다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.

## 공식 근거

- [Frame과 Group의 차이](https://help.figma.com/hc/en-us/articles/360039832054-The-difference-between-frames-and-groups)는 자식을 따라가는 Group bounds와 명시적인 Frame bounds를 구분한다.
- [Frames](https://help.figma.com/hc/en-us/articles/360041539473-Frames-in-Figma-Design)는 화면·배치·clipping 등 Frame의 역할을 설명한다.
- [Auto Layout](https://help.figma.com/hc/en-us/articles/360040451373-Guide-to-auto-layout-in-Figma)은 방향·간격·padding·정렬·sizing의 근거다.
- [접근 가능한 prototype](https://help.figma.com/hc/en-us/articles/7810391964695-Accessible-prototypes-in-Figma)은 상위 frame/component/instance의 의미 있는 이름을 설명한다.

## Figma Group의 실제 좌표계

Group과 boolean operation은 자식의 좌표 원점을 만들지 않습니다. 자식의 `x/y`·`relativeTransform`은 가장 가까운 page·frame·component·instance를 기준으로 하므로, 절대 좌표를 계산할 때 Group의 위치를 다시 더하면 안 됩니다. `figma.group(nodes, parent)`는 자식의 절대 위치를 보존하며 Group의 bounds는 자식으로부터 파생됩니다. 실제 Group getter에서도 부모와 첫 자식의 x/y가 같은 값인 경우와 동일한 absolute bounding box를 확인했습니다. [공식 좌표 기준](https://developers.figma.com/docs/plugins/api/properties/nodes-relativetransform/) · [공식 group 계약](https://developers.figma.com/docs/plugins/api/properties/figma-group/).

Frame은 크기·clip의 기준이고 Auto Layout Frame은 자식 배치·Hug/Fill을 소유합니다. Group은 clip·padding·layout 부모의 대체물이 아닙니다. 정적 장식 묶음에 Group을 선언하되 native 배치·읽기·Python 감사와 fixture 모두 같은 containing-parent 좌표 규칙을 사용해야 합니다. 최종 실제 인수와 수정 여부는 [인수 현황](../FINAL_ACCEPTANCE.md)에 연결합니다.
