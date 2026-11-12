# RD-03 작업서 · 작업 간 의존성과 영향 시각화

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. task·artifact identity와 RD-08의 operation ID/권한 경계가 독립적임을 확인한다. UI 통합은 RD-08과 순차 진행한다.
2. 서명된 catalogue에 선택적 dependency 입력·정규화·DAG 검사를 추가한다.
3. 명시적 edge가 있는 실제 prepared fixture와 edge 없는 legacy fixture를 만든다.
4. 선택 node의 선행/후속 보기와 텍스트 대체 목록을 구현한다.
5. stale·retired·orphan 표시와 읽기 전용 동작을 확인한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

1은 `figma_control.task_operation_boundary`가 준비된 task revision과 서버 operation id가 다르다는 것을 확인한다. operation은 task key를 가리키지만 catalogue에 operation id를 task로 넣지 않고, status 조회는 revision을 바꾸거나 dependency를 만들지 않는다. 요청 파일은 하나다. UI 통합은 아직이다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
python3 -B -m unittest discover -s tests -p 'test_figma_workspace.py'
python3 -B -m unittest discover -s tests -p 'test_workspace_replay.py'
node --test tests/test_workspace_host.cjs tests/test_workspace_activity.cjs
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 브라우저와 Figma 패널에서 동일 catalogue의 관계가 같고, edge 조회로 native mutation 요청이 발생하지 않는지 확인한다. 실제 제작 관계는 입력 artifact와 대조한다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
