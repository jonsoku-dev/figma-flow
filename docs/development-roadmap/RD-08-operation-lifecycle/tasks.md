# RD-08 작업서 · 실행 수명주기와 충돌 복구 내역

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 현재 enqueue/poll/result와 timeout·recovery의 상태 전이를 fixture로 고정한다.
2. 서버 operation ID와 additive phase journal을 기존 상태 저장에 통합한다.
3. claim/runtime 검사를 포함한 명시적 native-started 전달을 별도 단위로 추가한다.
4. 실행 이력에 서버 journal 조회를 연결하고 legacy/unknown을 구분한다.
5. 충돌 상세와 save/read 동작을 추가하고 재실행 버튼은 제공하지 않는다.
6. 서버·플러그인 재시작과 결과 전달 실패를 실제 경로에서 확인한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

1은 `figma_control.pinned_operation_transitions`가 현재 enqueue·poll·result를 다시 실행한다. claim 전 timeout은 expired, claim 후 timeout은 uncertain이다. 읽기 timeout은 다음 명령을 막지 않고, claim된 mutation timeout은 같은 쓰기를 막는다. 다른 페이지 읽기는 uncertainty를 풀지 않고, 같은 scope의 discovery 읽기만 푼다. 끝난 결과의 재전송은 거절한다. native-started는 어느 전이에서도 만들지 않는다. 2는 새 enqueue의 `operation_id`와 `phase_events`를 기존 요청 파일에 덧붙인다. 단계는 queued, claimed, result-received, reconciled, uncertain만 서버가 기록한다. 클라이언트가 보낸 operation ID는 결과 권한으로 받지 않고, lifecycle 필드가 없는 기존 요청은 단계를 추정하지 않는다. 깨진 lifecycle은 claim하지 않는다. 3은 claim된 요청에만 `note_native_started`가 `native-started`를 한 번 덧붙인다. session, claim, file, page, revision과 현재 runtime이 서버에 저장된 claim과 같아야 한다. claim만으로 만들지 않고, 이 사건은 성공 상태가 아니다. 플러그인은 실행 전에 그 경로로만 전달한다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
python3 -B -m unittest discover -s tests -p 'test_figma_control.py'
python3 -B -m unittest discover -s tests -p 'test_workspace_publish_guard.py'
python3 -B -m unittest discover -s tests -p 'test_native_edit.py'
node --test tests/test_workspace_control.cjs tests/test_workspace_host.cjs tests/test_native_edit.cjs
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 fixture에서 하나의 읽기와 충돌 복구 흐름을 실행하고 journal·패널·실제 값이 맞는지 확인한다. timeout 재현 중 원래 페이지를 지우거나 미확정 요청을 성공으로 고치지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
