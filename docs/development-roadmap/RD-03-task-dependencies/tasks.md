# RD-03 작업서 · 작업 간 의존성과 영향 시각화

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. task·artifact identity와 RD-08 operation ID의 권한 경계를 확인한다.
2. prepare와 서명된 catalogue의 dependency 정규화 및 DAG 검사를 확인한다.
3. trusted history의 exact artifact와 legacy fixture를 대조한다.
4. 선택 task의 한 단계 graph와 텍스트 목록을 대조한다.
5. stale·retired·orphan 표시가 자동 실행을 만들지 않는지 확인한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

1은 `figma_control.task_operation_boundary`가 준비된 task revision과 서버 operation id가 다르다는 것을 확인한다. operation은 task key를 가리키지만 catalogue에 operation id를 task로 넣지 않고, status 조회는 revision을 바꾸거나 dependency를 만들지 않는다. 요청 파일은 하나다. 현재 UI는 dependencyView와 dependencyFreshness를 연결한다. 2는 `normalize_task_dependencies`가 선택적 `uses-output` edge만 정규화하고 publish 전에 DAG를 검사한다. 같은 project는 edge가 되지 않는다. 없는 target, self edge, cycle, 중복 edge, 현재 또는 검증된 history에서 찾을 수 없는 revision, 등록되지 않은 artifact와 hash 불일치는 서명 전에 거절한다. 3은 `tests/fixtures/rd03/legacy-tasks.json`과 `declared-edges.json`을 `load_task_dependency_fixtures`로 읽는다. legacy에는 depends_on이 없고, 선언한 fixture는 import-task에서 review의 code.js로 가는 edge 하나만 가진다. notes는 같은 project여도 edge가 없다. 4는 `dependencyView`가 선택 task의 한 단계 선행·후속과 같은 문장의 텍스트 목록을 만든다. 같은 project나 다른 relation은 선이 되지 않는다. 관계 조회는 작업을 열지 않고 native mutation을 보내지 않는다. 5는 `dependencyFreshness`가 개정 불일치를 stale, 은퇴 기록에만 남은 대상을 retired, 어디에도 없는 대상을 orphan으로 표시한다. 조회는 실행 상태를 바꾸지 않고 자동 실행을 하지 않는다.

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
