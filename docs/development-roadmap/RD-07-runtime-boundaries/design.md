# RD-07 설계서 · 제어 전송과 실행 정책의 모듈 경계

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/figma_workspace.py](../../../tools/figma_workspace.py) | `publish, trusted_sources, runtime_info` |
| [figma-bridge/workspace_control.js](../../../figma-bridge/workspace_control.js) | `HTTP poll/result와 task별 실행` |
| [figma-bridge/workspace_host.js](../../../figma-bridge/workspace_host.js) | `task run closure·UI 전환` |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `import/export domain 실행` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

`workspace_transport.js`의 `controlRequest(route,body)`는 HTTP 전송만 담당한다. `workspace_control.js`가 kind, operation, scope, revision, claim과 domain 실행·검증을 맡는다. transport의 HTTP 성공은 native 성공 증거가 아니다.

endpoint는 port 1~65535의 `http://localhost` 또는 `http://127.0.0.1` loopback origin만 받는다. route는 `poll`, `result`, `readiness`, `native-started`, `history`로 제한한다. body는 객체이고 readback JSON은 32 MiB, 전체 request는 40 MiB, response JSON은 16 MiB 이내다. readiness는 별도 64 KiB 제한을 유지한다. 요청은 15초 deadline을 가진다. deadline 경과는 native 실행 취소나 결과 미발생을 증명하지 않는다.

실제 앱 44개 화면의 전체 getter 결과는 compact UTF-8 29,991,516바이트였고, 전송 envelope는 약 33.4 MB였다. 기존 12/16 MiB 제한에서 전달이 확정되지 않아 요청 경계만 확장했다. 응답·인증·origin·route·nonce·timeout 검사는 유지하며, 용량 수용은 native 내용 검증이나 전체 인수 통과를 뜻하지 않는다.

## 구현 결정

`controlRequest` 정의는 transport 한 곳에 있고 domain 정책은 control에 남긴다. `runtime_module_names`와 `assemble_shared_runtime`이 runtime 조립과 trusted source 검사의 같은 모듈 목록을 사용한다. task별 closure를 유지하며 동적 import나 외부 eval을 추가하지 않는다.

bundle 검사는 discover, import, native-edit, review, sync를 대상으로 하며 공개 심볼과 source digest를 검사한다. 이 fixture 검사는 설치된 Figma runtime의 재개·쓰기 성공과 구분한다. transport는 token과 private 설정을 추가 저장하거나 진단 UI에 노출하지 않는다.

## 호환성·이관·복구

wire format과 prepared task 입력을 유지하는 구조 변경부터 수행한다. 새 adapter가 private config를 추가 저장하지 않는다. 구 조립 경로와 새 경로를 검사용 fixture에서 비교한 뒤 실제 publisher를 한 번 전환한다. 장기 이중 runtime은 남기지 않는다. 문제가 있으면 기존 concatenation을 복구하고 새 서명 generation을 정상 발행한다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.


