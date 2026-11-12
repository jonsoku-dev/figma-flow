# RD-04 작업서 · 동기화 변경을 골라 적용하기

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 독립 token 두 개와 alias 묶음 fixture에 관찰 가능한 부분 적용 조건을 고정한다.
2. 계획에서 stable change identity와 선택 묶음을 만들고 직렬화한다.
3. UI 선택·전체 선택·선택 수·영향 target을 기존 행에 추가한다.
4. Python/JS 양쪽에서 선택을 검증하고 transaction 적용·readback·baseline 갱신을 연결한다.
5. component field 단위는 첫 단위의 실제 왕복이 끝난 뒤 추가한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
node --test tests/test_graph_token_sync.cjs tests/test_graph_panel.cjs
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 Figma에서 선택 두 값과 미선택 한 값을 읽고 웹 projection·pairing 결과를 대조한다. UI 체크만 바뀌고 실행 범위가 그대로인 구현은 완료가 아니다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
