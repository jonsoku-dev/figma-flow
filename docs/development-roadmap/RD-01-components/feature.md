# RD-01 기능서 · 재사용 컴포넌트와 편집 속성

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

반복 제어를 Figma에서 수정할 때 레이블 속성이 보이지 않거나, 배치 크기만 다른 제어가 별도 main으로 늘어난다. 디자이너가 정의 하나를 고쳐 여러 화면을 갱신하기 어려워진다.

## 현재 구현

일반 가져오기는 `code.js`의 `importDesign`에서 main과 instance를 만든다. 화면 문구는 이제 main의 TEXT 속성과 반환된 key로 설정한다. 속성 API가 없을 때만 하위 TEXT에 직접 쓴다. 방향 검토는 이미 TEXT property를 연결한다. `ensureSemanticComponents`는 자식 구조와 높이가 같으면 root 너비 차이를 instance resize로 흡수한다. 자식 크기·transform·높이가 다르면 별도 Layout main을 유지한다.

## 첫 구현 범위

첫 단위는 일반 가져오기 label의 TEXT property다. 다음 단위는 supported sizing 차이와 semantic variant의 분리다. 마지막 단위는 선언된 독립 variant 축과 사용 설명을 노출한다. 각 단위는 별도 diff로 끝낸다.

기존 instance detach, 사용자 main 재생성, 전체 library 자동 합치기, 모든 variant 조합 생성, 임의 문자열에서 속성 추정은 제외한다.

## 기능 요구사항

- **RD-01-REQ-01** — 정의에 편집 가능한 label이 있으면 main 또는 set에 TEXT property를 만들고 실제 하위 TEXT와 연결한다.
- **RD-01-REQ-02** — 화면의 문구는 반환된 실제 property key로 instance.setProperties에 전달한다. property 표시 이름에서 내부 key를 추측하지 않는다.
- **RD-01-REQ-03** — 지원하는 instance sizing만 다른 동일 의미 컴포넌트는 main을 공유한다. 구조·상태·의도된 시각 역할이 다르면 분리를 유지한다.
- **RD-01-REQ-04** — 선언된 size/state/tone 축은 이름을 보존한다. optional label/icon은 적합한 TEXT/BOOLEAN/INSTANCE_SWAP 속성으로 표현한다.
- **RD-01-REQ-05** — 사용 설명·문서 링크는 graph에 있는 내용만 옮긴다. 기존 override, 변수 binding과 native ID를 보존한다.

## 인수 조건

- **RD-01-AC-01** — 한 main을 참조하는 세 instance에 서로 다른 문구가 보이고, main의 TEXT 정의와 label.componentPropertyReferences가 실제 getter에서 맞는다.
- **RD-01-AC-02** — 같은 의미·구조에서 지원된 너비만 다른 세 사용처는 같은 main ID를 공유하며 각 렌더 너비는 원본과 같다.
- **RD-01-AC-03** — 구조가 다른 fixture는 별도 main을 유지하고 기존 시각 회귀·token binding을 통과한다.
- **RD-01-AC-04** — 같은 패킷 재실행 후 main/set/instance 수와 ID가 유지된다. 사용자가 바꾼 instance override를 초기화하지 않는다.
- **RD-01-AC-05** — 선언하지 않은 variant 조합·사용 설명·swap target은 만들어지지 않는다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. AC-01과 AC-04는 일반 가져오기 mock에서, AC-02와 AC-03은 semantic component oracle에서 재현했다. 실제 Figma 관찰이 없으므로 이 문서의 조건은 통과로 기록하지 않는다. AC-05는 아직 구현하지 않았다.
