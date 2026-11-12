# RD-09 작업서 · 진단 기록 내보내기

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 진단 기록이 없을 때의 실패를 `tests/rd09_audit_log.cjs`로 고정한다.
2. `buildAuditRecord`와 `renderAuditExport`로 마크다운·JSON·텍스트를 만들고, 그래프 패널에서 읽기 전용으로 복사·저장한다.
3. 로컬 게이트로 기준 실패와 구현 통과를 다시 실행한다.
4. 실제 Figma 패널 관찰이 없으면 그 인수 조건을 통과로 바꾸지 않는다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

1은 기록 스키마 `figma-flow-audit-log-v1`과 비밀값 가리기, 노드 ID·리비전·오류·작업 식별자 유지, 요약·전체 읽기 범위, 없는 읽기의 `native-read`, 실제 Figma 패널의 `live-figma-panel`을 검사한다. 2는 `figma-bridge/audit_log.js`가 그 기록을 만들고 `graph-panel.html`이 같은 스크립트를 실어 `bindAuditExport`로 복사·마크다운 저장·JSON 저장만 한다. 이 함수는 적용 메시지를 보내지 않는다. 플러그인 버전은 패널에 적힌 0.26.3이다. 입력 객체와 pairing plan은 바꾸지 않는다. `graph_sync.py`가 다른 작업으로 수정 중이면 그 파일은 건드리지 않는다. 3은 같은 Node 검사를 구현 전과 후에 다시 실행한다. 4는 라이브 Figma를 열지 않은 관찰을 성공으로 적지 않는다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
node tests/rd09_audit_log.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
python3 -B -m unittest discover -s tests -p 'test_panel_components.py'
```

React 번들과 가져오기 패널은 이 단위의 소유 파일이 아니다. 그 파일을 같은 변경에 넣지 않는다.

## 실제 동작 확인

실제 Figma에서 진단 버튼을 눌러 복사한 기록과 문서가 그대로인지는 따로 본다. 그 관찰이 없으면 RD-09-AC-05를 통과로 적지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
