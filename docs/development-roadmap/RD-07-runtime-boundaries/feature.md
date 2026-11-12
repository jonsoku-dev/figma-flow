# RD-07 기능서 · 제어 전송과 실행 정책의 모듈 경계

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

전송 재시도나 protocol을 수정할 때 task별 실행 증거와 권한 검사까지 한 파일에서 추적해야 한다. 생성 bundle의 결합 범위가 커 작은 변경의 검수 비용이 높다.

## 현재 구현

`figma_workspace.publish`는 task code를 각 run closure에 넣고 공통 chat/control/host runtime을 조립한다. React 자산은 이미 공통으로 포함한다. workspace_control은 HTTP poll/result와 task별 실행·결과 검사를 함께 담당한다. trusted_sources가 실제 배포 소스를 고정한다.

## 첫 구현 범위

HTTP poll/result 전송만 작은 adapter로 분리하고 task별 scope·실행·결과 검사는 기존 domain 경계에 둔다. 생성 bundle은 하나와 서명된 registry를 유지한다.

새 module loader·원격 코드 실행기·plugin entry 추가, LangGraph/LLM 서버 도입, task closure의 무조건 공유화, 큰 파일을 임의 줄 수로 나누기, 측정 없는 bundle 감소 주장은 제외한다.

## 기능 요구사항

- **RD-07-REQ-01** — 전송 adapter는 허용 origin·인증·제한된 payload·timeout을 처리하며 임의 task 코드를 실행하지 않는다.
- **RD-07-REQ-02** — domain executor는 정확한 task kind·scope·revision·허용 operation과 실제 결과를 검사한다.
- **RD-07-REQ-03** — 생성된 runtime의 모든 소스가 trusted_sources와 runtime identity에 포함된다.
- **RD-07-REQ-04** — 한 번의 실행에서 공통 전송 구현은 하나이며 task의 lexical 격리는 유지한다.
- **RD-07-REQ-05** — old/stale runtime, uncertain writes, idle publication 차단과 private config 처리는 유지한다.

## 인수 조건

- **RD-07-AC-01** — 기존 import/read/sync/native-edit/review 메시지 trace와 결과·오류가 구조 변경 전후 같아야 한다.
- **RD-07-AC-02** — 전송 모듈 하나만 바꿔도 runtime digest가 바뀌고 오래된 runtime의 쓰기는 차단된다.
- **RD-07-AC-03** — 어느 task에도 다른 task의 private closure·capability·scope가 노출되지 않는다.
- **RD-07-AC-04** — 실패·timeout·duplicate result·복구 경로가 기존과 동일하게 fail closed한다.
- **RD-07-AC-05** — 실제 생성 bundle을 실행하는 검사와 source/생성 재빌드 비교를 모두 통과한다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. 현재 이 문서의 조건은 통과로 기록되지 않았다.
