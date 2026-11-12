# RD-08 기능서 · 실행 수명주기와 충돌 복구 내역

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

어느 단계에서 실행이 끊겼는지, 실제 쓰기가 시작됐는지, 복구 읽기가 원래 요청과 연결되는지 한 화면에서 파악하기 어렵다. 충돌 이후 다시 실행하면 안 되는 이유도 결과 JSON을 열어야 보인다.

## 현재 구현

Python control은 private request·claim·terminal receipt·readback·uncertainty를 이미 저장한다. claimed timeout 뒤 uncertain 쓰기를 차단하고 scoped read로 일부 복구한다. Figma clientStorage history는 제한된 UI 요약이며 이 journal을 대신하지 않는다. native-edit는 rollback_conflicts와 관측 값을 반환하지만 작업 이력에서 구조화된 복구 내용을 찾기 어렵다.

## 첫 구현 범위

기존 journal에 증거가 있는 실행 단계와 safe operation ID를 추가하고, 이력에서 읽기 전용 충돌·복구 상세를 보여준다. 처음에는 서버 journal 조회와 UI 연결을 구현한다.

새 queue·DB·상주 LLM, 불확실 mutation 자동 재시도, 과거 실패 영수증 덮어쓰기, claimed만으로 native-started 추정, 성공 메타데이터 복원, 버튼 한 번으로 강제 rollback은 제외한다.

## 기능 요구사항

- **RD-08-REQ-01** — 서버가 발급한 operation ID와 claim을 task key·revision·file/page에 연결한다. UI가 보낸 ID를 권한으로 믿지 않는다.
- **RD-08-REQ-02** — queued·claimed·native-started·result-received·reconciled·uncertain 중 실제 기록이 있는 단계만 표시한다.
- **RD-08-REQ-03** — 서버 재시작·플러그인 재실행 후에도 기록된 단계와 미확정 쓰기 차단이 유지된다.
- **RD-08-REQ-04** — 충돌 상세는 정확한 target, planned before/after, observed value와 rollback 결과를 원래 plan hash에 연결한다.
- **RD-08-REQ-05** — 안전한 후속 동작은 근거 저장과 현재 scope 읽기로 한정한다. 복구 read는 기존 recovery_read 판정 조건을 유지한다.

## 인수 조건

- **RD-08-AC-01** — claim 전 timeout과 claim 후 timeout이 다르게 표시되며 어느 경우도 native-started를 꾸며내지 않는다.
- **RD-08-AC-02** — native 성공 뒤 HTTP 결과 전달 실패는 uncertain으로 남고 같은 mutation이 자동 재실행되지 않는다.
- **RD-08-AC-03** — 올바른 scope의 read만 원래 uncertainty와 연결되며 다른 file/page/revision의 read는 차단을 해제하지 않는다.
- **RD-08-AC-04** — 중복 결과는 기존 terminal receipt와 정확히 같을 때만 결정적으로 처리하고 상충 결과를 거절한다.
- **RD-08-AC-05** — rollback conflict 각 항목이 정확한 관측 값과 plan hash를 보존하며 legacy history는 phase unknown으로 보인다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. 현재 이 문서의 조건은 통과로 기록되지 않았다.
