# RD-04 기능서 · 동기화 변경을 골라 적용하기

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

한 토큰은 적용하고 다른 컴포넌트 필드는 보류하려 해도 전체 변경을 한 번에 승인해야 한다. 검토 의도와 실제 변경 범위를 맞추기 어렵다.

## 현재 구현

`build_plan`과 `verify_readback`은 전체 token/component 범위를 검사한다. `graph_panel`과 GraphPanel은 차이 목록을 보여주지만 적용 선택은 전체 단위다. alias와 shared consumer 경계는 이미 검사한다.

## 첫 구현 범위

현재 pinned plan 안의 변경을 선택하고 선택 범위만 적용한다. alias root와 공유 consumer는 원자적 선택 묶음으로 유지한다.

새 token 자동 채택, 임의 native-edit, per-instance variant 생성, 오래된 readback 적용, 숨겨진 영향이 있는 필드 강제 분리는 제외한다.

## 기능 요구사항

- **RD-04-REQ-01** — 선택 항목은 현재 plan의 token root 또는 component field를 정확히 식별한다.
- **RD-04-REQ-02** — alias와 shared consumer의 결합된 영향은 같은 선택 묶음으로 표시한다.
- **RD-04-REQ-03** — 알 수 없는·중복·빈 선택, graph/plan/readback drift는 쓰기 전에 거절한다.
- **RD-04-REQ-04** — 미선택 항목은 적용하지 않는다. 결과는 selected/applied/skipped identity를 각각 남긴다.
- **RD-04-REQ-05** — 전체 선택의 기존 결과와 rollback·pairing·native marker 검사는 유지한다.

## 인수 조건

- **RD-04-AC-01** — 서로 독립적인 세 변경 중 두 개를 고르면 실제 해당 두 값만 바뀌고 나머지 값은 보존된다.
- **RD-04-AC-02** — 선택 없음은 Apply를 비활성화하고 서버에서도 거절한다.
- **RD-04-AC-03** — alias 종속을 반만 고를 수 없고 묶음의 실제 영향 대상이 보인다.
- **RD-04-AC-04** — 승인 뒤 graph/readback이 바뀌면 기존 before-value와 pin 검사에서 실패한다.
- **RD-04-AC-05** — 취소·키보드 선택·선택 변경·실패 복구와 JSON 결과의 범위가 일치한다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. 현재 이 문서의 조건은 통과로 기록되지 않았다.
