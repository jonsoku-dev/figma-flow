# RD-09 설계서 · 진단 기록 내보내기

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/audit_log.js](../../../figma-bridge/audit_log.js) | `새 진단 기록. buildAuditRecord, renderAuditExport` |
| [figma-bridge/graph-panel.html](../../../figma-bridge/graph-panel.html) | `같은 스크립트와 읽기 전용 복사·저장 버튼` |
| [tools/graph_sync.py](../../../tools/graph_sync.py) | `기존 graph_panel. 이 항목은 그 함수를 바꾸지 않고 템플릿에 기록을 실음` |

RD-06이 쓰는 `ImportPanel.jsx`, `code.js`, `native_semantic_read.js`, `panels.js`는 이 항목의 작성 대상이 아니다. 그 파일이나 `graph_sync.py`가 다른 작업으로 수정 중이면 진단 기록은 새 스크립트와 그래프 패널 템플릿에만 둔다.

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

기록 스키마는 `figma-flow-audit-log-v1`다. 사람이 읽는 결과는 마크다운이고, 같은 객체의 JSON을 펜스 안에 둔다. 텍스트는 그 마크다운이다. JSON 저장은 같은 객체다.

```json
{"schema":"figma-flow-audit-log-v1","plugin_version":"0.26.3","file_key":"","page":{"id":"","name":""},"task_key":"","revision":"","operation_id":"","pairing":{"state":"","freshness":""},"runtime_freshness":"","lifecycle":[{"phase":"","status":"","error":"","time":""}],"uncertainty":{"blocked_write":true,"reasons":[]},"input_summary":[{"ref":"","kind":"","status":"","source":""}],"dependency_freshness":[{"label":"","freshness":""}],"native_read":{"profile":"summary","node_ids":[],"fields":[],"omitted":[],"complete":false},"unobserved":[{"check":"live-figma-panel","reason":""}]}
```

없는 사실은 `null` 또는 빈 목록으로 두고 `unobserved`에 검사 이름을 남긴다. 실제 Figma 패널 관찰은 이 내보내기가 대신하지 않는다.

## 구현 결정

`buildAuditRecord`가 사실을 고르고 비밀값을 가린다. `renderAuditExport`가 마크다운·JSON·텍스트를 만든다. 입력 객체는 바꾸지 않는다.

가리는 값은 bearer 토큰, `sync_token`·`chat_token`·`capability` 같은 로컬 비밀, 홈 디렉터리로 시작하는 절대 경로, 자격 증명이 든 쿼리다. 페어링 객체에서는 상태와 신선도만 남긴다. 노드 ID, 리비전, 오류 문장, 작업 식별자는 유지한다.

네이티브 읽기는 요약의 `coverage` 또는 전체 읽기의 노드 목록에서 프로파일, 노드 ID, 필드, 빠뜨린 닫힘, 완료 표시를 가져온다. 둘 다 없으면 `native_read`는 `null`이고 검사 이름은 `native-read`다.

그래프 패널 버튼은 복사와 파일 저장만 한다. `postMessage`로 적용을 보내지 않는다. 진단 스크립트는 `graph-panel.html` 안에 두어 기존 `graph_panel`의 config 치환만으로 패널에 실린다.

## 호환성·이관·복구

기존 그래프 읽기·적용 메시지와 pairing plan은 그대로다. 진단 버튼을 빼도 읽기와 적용은 남는다. 플러그인 버전은 기록에 0.26.3으로 적고 매니페스트 버전은 올리지 않는다. 과거 요청 파일의 형식은 바꾸지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 비밀과 설치 경로는 공유 Wiki나 진단 기록의 비밀 칸에 넣지 않는다. 오류 문장 안의 비밀 구간만 가리고 나머지 문장은 남긴다.
