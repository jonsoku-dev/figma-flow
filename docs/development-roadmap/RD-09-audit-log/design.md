# RD-09 설계서 · 진단 기록 내보내기

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 책임 |
| --- | --- |
| [audit_log.js](../../../figma-bridge/audit_log.js) | `buildAuditRecord`, `renderAuditExport`, redaction과 unknown facts |
| [DiagnosticExport.jsx](../../../panel-ui/src/DiagnosticExport.jsx) | React 읽기 전용 기록 표시와 JSON 다운로드 |
| [GraphPanel.jsx](../../../panel-ui/src/GraphPanel.jsx) | 현재 model과 evidence를 DiagnosticExport에 전달 |
| [graph-panel.html](../../../figma-bridge/graph-panel.html) | 기존 standalone 진단 경로 |

React 원본과 생성 `assets/panels.js`가 현재 배포 패널 경로다. 과거 standalone 템플릿만으로 실제 React UI 연결을 증명하지 않는다.

## 현재 데이터와 인터페이스

기록 schema는 `figma-flow-audit-log-v1`다. `renderAuditExport`는 같은 `buildAuditRecord` 결과에서 Markdown, JSON, text를 만든다. plugin version, file·page, task·revision·operation, pairing, runtime freshness, lifecycle, uncertainty, input summary, dependency freshness와 native read coverage 중 전달된 사실만 기록한다.

없는 scalar는 null, 없는 목록은 빈 목록으로 두고 `unobserved`에 검사 이름을 남긴다. `blocked_write`가 없으면 false로 추정하지 않는다. 버전도 실제 model에서 받고 0.26.3 상수로 꾸미지 않는다. full과 summary coverage는 구분하며 `live-figma-panel`은 이 내보내기로 관찰된 사실이 아니다.

## 구현 결정

`buildAuditRecord`는 허용 필드만 골라 입력을 바꾸지 않는다. bearer, 민감 query 값, URL credentials와 개인 home 경로를 가린다. pairing은 상태와 freshness만 보존하고 control·pairing 비밀 원본을 내보내지 않는다. 오류 문장은 redaction 후 남긴다.

`DiagnosticExport`는 React의 readOnly textarea로 text를 표시하고 Blob으로 JSON을 로컬 다운로드한다. 네트워크 요청, 문서 mutation 또는 적용 postMessage를 만들지 않는다. standalone `bindAuditExport`의 복사·Markdown·JSON 저장도 읽기 전용이다. 현재 evidence에 없는 lifecycle이나 pairing 상태를 얻으려고 추가 요청하지 않는다.

## 호환성·이관·복구

기존 graph 읽기·적용 메시지와 pairing plan은 유지한다. 기록 UI를 열거나 파일을 내려받아도 prepared task와 과거 request 파일을 바꾸지 않는다. 입력이 부족하면 unknown과 unobserved로 남으며 성공 사실을 합성하지 않는다. 기록의 redaction 검사는 사용자 파일 전체의 공개 허가를 뜻하지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 비밀과 설치 경로는 공유 Wiki나 진단 기록의 비밀 칸에 넣지 않는다. 오류 문장 안의 비밀 구간만 가리고 나머지 문장은 남긴다.

## 실제 빌드 버전과 전달 범위

공통 `graph_panel`이 정본 `plugin.json`의 버전을 config에 넣고 React·legacy가 같은 값을 사용합니다. 고정 문자열을 제거했으며 version이 없는 독립 config는 null·미관측입니다. 실제 Figma와 독립 브라우저에서0.27.0을 확인했습니다. 실제 클릭으로 복사한2,464자와 표시 마크다운·다운로드 마크다운·동봉 JSON·JSON 파일의 사실이 모두 일치했습니다. 초기 키보드 시도의 빈 관측은 별도 보존하고 클릭 재검증으로 전달을 확인했습니다.
