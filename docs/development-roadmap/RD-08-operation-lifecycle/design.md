# RD-08 설계서 · 실행 수명주기와 충돌 복구 내역

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/figma_control.py](../../../tools/figma_control.py) | `save, enqueue, poll, result, status, recovery_read` |
| [figma-bridge/workspace_control.js](../../../figma-bridge/workspace_control.js) | `claim 수신·domain 실행·결과 전달` |
| [figma-bridge/workspace_host.js](../../../figma-bridge/workspace_host.js) | `안전한 이력 projection` |
| [figma-bridge/native_edit.js](../../../figma-bridge/native_edit.js) | `rollback_conflicts와 실제 관측` |
| [panel-ui/src/Workspace.jsx](../../../panel-ui/src/Workspace.jsx) | `실행과 복구 상세` |
| [panel-ui/src/GraphPanel.jsx](../../../panel-ui/src/GraphPanel.jsx) | `native-edit 결과 표시` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

현재 lifecycle record는 기존 private request 파일에 붙는 versioned 필드다.

```json
{"lifecycle_version":1,"operation_id":"server-issued","phase_events":[{"phase":"queued","time":"ISO8601","source":"server"}],"recovery_of":null}
```

시간은 표시 값이고 사건의 원인 식별은 operation_id/claim/recovery_of다. native-started는 인증된 해당 runtime의 명시적 event가 있어야 기록한다. UI-only executionId와 자동 제어 operation_id는 출처가 다르다. 연결할 때 원본과 종류를 보존한다.

UI summary에는 safe ID·단계·시각·진단 코드만 보낸다. 실제 전후 값·원시 충돌 readback은 기존 private bounded 경로로 저장하고 명시적인 상세 조회에만 최소 필드를 반환한다.

## 구현 결정

기존 save/poll/result 경계에서 사건을 기록한다. 서로 독립적인 상태 파일이나 queue를 추가하지 않는다. journal이 canonical이며 clientStorage는 표시 cache다. legacy request는 저장된 사실 이상을 역으로 추론하지 않는다.

`note_native_started`는 exact claim/runtime/scope를 서버에서 검사한다. `controlExecute`가 제어 scope·deadline·handler 검사를 마친 마지막 안전 지점에서 전달하고, 수신 실패 시 domain 실행을 진행하지 않는다. 이 event 자체는 성공이나 완료 증거가 아니다. terminal result의 기존 native 데이터 검증과 최대 payload/readback 한도는 유지한다.

`history`는 인증된 current runtime과 exact file/page scope의 canonical 요청 이력을 최대 80개 조회한다. host는 clientStorage telemetry와 구분한 `journalHistory`를 UI에 전달한다. unavailable과 legacy/unknown은 성공으로 추정하지 않는다.

복구 상세는 현재 계획과 관측의 차이를 표로 보여주고 기존 읽기 명령으로 이동한다. 과거 요청과 새 read를 recovery_of로 연결한다. 사용자가 바꾼 값을 원래 planned value로 자동 덮어쓰지 않는다.

## 호환성·이관·복구

새 lifecycle 필드가 없는 request는 legacy로 읽는다. 기존 status와 uncertainty marker의 의미를 유지한다. malformed 신규 필드를 무시하고 성공 처리하지 않는다. 단계 UI를 제거해도 기존 uncertainty blocking이 작동해야 한다. 충돌 상세를 보관하는 정책은 기존 private 파일의 cap·보존 범위를 유지하며 자동 삭제 범위를 넓히지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.



## 정확히 같은 결과의 재전달

`result()`는 operation·claim ID, session·file/page·revision과 본문 경계를 검증합니다. 최초 수락한 외부 payload의 정렬된 SHA256을 private terminal 영수증의 `result_payload_sha256`에 저장합니다. `readback_json`은 공백·Unicode·개행까지 비교하며 생략한 optional 필드와 null도 다릅니다.

재전달은 active 작업보다 먼저 해당 private 영수증을 읽고 fingerprint·claim·scope·상태가 같을 때 기존 acknowledgment만 반환합니다. 읽기 결과·단계·후속 uncertainty·native readiness를 다시 쓰거나 작업을 재실행하지 않습니다. 상충 결과와 지문 없는 legacy·서버 생성 terminal은 거절합니다. 여러 파일의 crash 원자성을 새로 보장하지는 않습니다.

[고정 회귀](../../../tests/finalize_terminal_result.py)7개와 관련 제어·RD07·RD08·lifecycle 검사52개가 통과했습니다. 새 서버가 실제 Figma에서 읽은4,818개 노드의 결과를 같은 인증 HTTP 경로로 재전달해200, 개행이 추가된 상충 결과는409를 확인했습니다. 영수증·readback·uncertainty의 바이트와 mtime은 유지됐습니다.
