# RD-03 기능서 · 작업 간 의존성과 영향 시각화

상태는0.27 첫 구현 범위의 기능 계약이다. 조건별 fixture·실제 관측과 미지원 확장은 [최종 인수 현황](../FINAL_ACCEPTANCE.md)을 따른다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

어떤 입력이나 시안이 후속 가져오기·동기화의 근거인지 작업 목록에서 찾기 어렵다. 이전 작업을 바꿨을 때 어떤 후속 준비물을 다시 만들어야 하는지도 보이지 않는다.

## 현재 구현

workspace task에는 key, project, kind, revision과 대상 범위가 있다. 준비 순서·kind·같은 project는 실제 의존성 증거가 아니다. 0.26.3 이력 UI의 실행 연결은 한 dispatch의 요청과 결과만 설명한다.

## 첫 구현 범위

준비 시 명시한 task dependency를 저장하고, 현재·이전 revision 및 직접 영향 범위를 읽기 전용으로 시각화한다. 실행 권한이나 자동 스케줄러를 추가하지 않는다.

제목 유사도·시간순·같은 프로젝트에서 인과관계 추정, AI 자동 edge 생성, downstream 자동 실행·retire, 외부 graph 서버나 chart 라이브러리는 제외한다.

## 기능 요구사항

- **RD-03-REQ-01** — dependency는 선행 task key와 정확한 revision, 관계 종류와 근거 artifact의 등록된 상대 이름·hash를 가진다.
- **RD-03-REQ-02** — 없는 target·self edge·cycle·중복 edge·과거 revision을 현재로 바꾸는 입력을 거절한다.
- **RD-03-REQ-03** — 같은 project의 시각 그룹과 실제 dependency edge를 서로 다른 표시로 구분한다.
- **RD-03-REQ-04** — edge를 선택하면 선행 근거와 후속 작업, 현재 revision과 pinned revision을 보여준다.
- **RD-03-REQ-05** — revision이 바뀌면 stale dependency와 영향받는 준비물을 표시한다. UI 조회만으로 실행·승인 상태를 바꾸지 않는다.

## 인수 조건

- **RD-03-AC-01** — 선행 입력→검토→가져오기 세 작업의 명시적 두 edge만 보인다. 같은 project의 무관한 작업에는 선이 없다.
- **RD-03-AC-02** — 선행 revision 변경 시 후속 작업은 stale로 표시되며 자동 실행되지 않는다.
- **RD-03-AC-03** — cycle와 없는 artifact/hash는 prepare/publish 전에 거절된다.
- **RD-03-AC-04** — edge 없는 기존 task는 독립 작업으로 보이고 기존 실행·추천 동작이 유지된다.
- **RD-03-AC-05** — 320px에서 목록형 대체 보기, 키보드로 node/edge 이동, 같은 정보의 텍스트 설명을 제공한다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. 현재 조건별 판정과 실제 관측·fixture의 구분, 후속 확장과 출시·설치 근거는 [최종 인수 현황](../FINAL_ACCEPTANCE.md)과 패치 Wiki에서 확인한다.