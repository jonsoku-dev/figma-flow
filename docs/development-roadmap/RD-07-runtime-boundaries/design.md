# RD-07 설계서 · 제어 전송과 실행 정책의 모듈 경계

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/figma_workspace.py](../../../tools/figma_workspace.py) | `publish, trusted_sources, runtime_info` |
| [figma-bridge/workspace_control.js](../../../figma-bridge/workspace_control.js) | `HTTP poll/result와 task별 실행` |
| [figma-bridge/workspace_host.js](../../../figma-bridge/workspace_host.js) | `task run closure·UI 전환` |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `import/export domain 실행` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

새 파일 이름 `workspace_transport.js`는 제안이다. 역할은 `poll(runtimeIdentity)`와 `submit(claim,result)`에 한정한다. 실제 envelope는 기존 wire schema를 유지하며 새로운 operation 권한을 추가하지 않는다.

domain executor가 검증된 `{operation,scope,revision,claim}`을 받고 기존 domain 경로를 실행한다. 반환 결과는 해당 domain validator가 검사한다. transport adapter가 성공 문자열만 보고 native evidence를 인증하지 않는다.

생성 모듈 목록과 source digest를 deterministic하게 조립한다. 실행 시 동적 import·외부 eval로 연결하지 않는다.

## 구현 결정

먼저 현재 control의 전송 입출력을 fixture로 고정한다. HTTP 로직을 함수 단위로 이동하고 기존 실행 정책을 호출자로 남긴다. shared runtime의 source 목록은 publisher의 단일 선언에서 읽되 trusted_sources에 모든 새 파일을 포함한다.

task code를 각각 closure에 넣는 것은 lexical 격리를 위한 현재 계약이다. 그 안에 동일 helper가 있다는 이유로 전부 합치지 않는다. 공유해도 상태·상수·scope가 섞이지 않는 코드만 후속 측정과 함께 옮긴다.

이 변경의 성공은 파일 수 감소가 아니라 책임과 검사 경로의 명료화다. 재시도·결과 전달 오류 수정이 domain 검사 기준을 바꾸지 않고 가능해야 한다. RD-08과 같은 파일을 동시에 편집하지 않는다.

## 호환성·이관·복구

wire format과 prepared task 입력을 유지하는 구조 변경부터 수행한다. 새 adapter가 private config를 추가 저장하지 않는다. 구 조립 경로와 새 경로를 검사용 fixture에서 비교한 뒤 실제 publisher를 한 번 전환한다. 장기 이중 runtime은 남기지 않는다. 문제가 있으면 기존 concatenation을 복구하고 새 서명 generation을 정상 발행한다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.


