# RD-09 작업서 · 진단 기록 내보내기

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. 진단 schema, redaction과 없는 사실의 unobserved를 검사한다.
2. 현재 React 진단 표시와 JSON 다운로드가 읽기 전용인지 확인한다.
3. standalone 호환 경로와 실제 React 번들 경로를 구분해 검사한다.
4. 실제 Figma 패널 관찰이 없으면 해당 인수 조건을 대기로 유지한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

`tests/rd09_audit_log.cjs`는 기록 schema, redaction, 식별자 보존, full과 summary coverage 및 unobserved를 검사한다. `audit_log.js`의 `buildAuditRecord`와 `renderAuditExport`가 전달된 사실만 고른다. 없는 pairing, runtime, lifecycle과 blocked-write는 unknown으로 남는다.

현재 React 경로는 `GraphPanel.jsx`에서 `DiagnosticExport.jsx`로 model과 evidence를 전달한다. readOnly textarea와 로컬 JSON 다운로드만 제공하고 네트워크 요청이나 mutation 메시지를 보내지 않는다. plugin version은 현재 model에서 받으며 입력 객체와 pairing plan은 바꾸지 않는다. standalone `graph-panel.html`의 `bindAuditExport`는 별도 호환 경로다. React 생성 자산과 실제 패널 연결은 standalone fixture 결과와 구분해 검증한다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
node tests/rd09_audit_log.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
python3 -B -m unittest discover -s tests -p 'test_panel_components.py'
```

React를 바꾸면 `npm --prefix panel-ui run build`로 생성 자산을 갱신하고 실제 렌더 경로를 확인한다. 진단 export 함수 검사는 React 버튼 상호작용이나 설치된 Figma 패널 관찰을 대신하지 않는다.

## 실제 동작 확인

실제 Figma에서 진단 버튼을 눌러 복사한 기록과 문서가 그대로인지는 따로 본다. 그 관찰이 없으면 RD-09-AC-05를 통과로 적지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
