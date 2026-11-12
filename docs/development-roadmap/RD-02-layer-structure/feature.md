# RD-02 기능서 · 의미 있는 레이어 계층과 컨테이너

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

화면 내부에 카드·행·섹션이 있어도 레이어 목록이 평평하다. 디자이너가 관련 요소를 함께 이동하거나 내용 변화에 맞춰 배치를 조정하기 어렵다.

## 현재 구현

방향 검토는 `direction_review.js`에서 authored layers와 controls를 상태 Frame 바로 아래에 배치한다. 상태 Frame은 고정 뷰포트, clipping과 prototype 시작점이다. 일반 가져오기의 `layout`은 세로 Auto Layout을 설정한다. 컨트롤 자체의 Auto Layout은 이미 사용한다.

## 첫 구현 범위

입력이 명시한 컨테이너 트리만 표현한다. 정적 묶음에는 Group, 크기·배경·clip·배치 책임이 있는 영역에는 Frame, 선형 배치에는 Auto Layout Frame을 쓴다.

화면 Frame을 Group으로 일괄 변환하거나, 좌표가 비슷하다는 이유로 임의 그룹을 추정하거나, 모든 픽셀 배치를 Auto Layout으로 바꾸지 않는다. 상위 화면의 prototype target과 flow start를 바꾸지 않는다.

## 기능 요구사항

- **RD-02-REQ-01** — 각 자식은 선언된 부모 하나를 가진다. 중복 소유·cycle·없는 target을 생성 전에 거절한다.
- **RD-02-REQ-02** — Group은 자체 fill·clipping·layout 책임이 없는 정적 cluster에만 허용한다.
- **RD-02-REQ-03** — Frame은 명시적인 크기·배경·clip·constraints를 가지며 Auto Layout은 방향·padding·gap·alignment·sizing을 선언한다.
- **RD-02-REQ-04** — 부모를 추가해도 기존 노드의 화면 기준 위치·사진 바이트·semantic key·명세 링크를 보존한다.
- **RD-02-REQ-05** — layer 이름은 card/header/body/actions처럼 원본 역할을 사용한다. 숨겨진 기술 소유권은 plugin data에 둔다.

## 인수 조건

- **RD-02-AC-01** — 선언한 카드·행·장식 묶음이 각각 Frame·Auto Layout Frame·Group으로 실제 트리에 나타난다.
- **RD-02-AC-02** — 부모 추가 전후 모든 leaf의 absolute bounding box, 원래 화면 clipping과 prototype 왕복이 유지된다.
- **RD-02-AC-03** — 문구 증가와 부모 resize에서 선언된 hug/fill/fixed 관계가 유지되며 사용자 instance가 detach되지 않는다.
- **RD-02-AC-04** — cycle·중복 부모·지원하지 않는 Group 속성은 쓰기 전에 거절된다.
- **RD-02-AC-05** — 기존 container 없는 패킷은 동일한 트리와 geometry로 동작한다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. 현재 이 문서의 조건은 통과로 기록되지 않았다.
