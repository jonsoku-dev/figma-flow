# RD-08 작업서 · 실행 수명주기와 충돌 복구 내역

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. enqueue, poll, result와 timeout·recovery의 상태 전이를 확인한다.
2. 서버 operation ID와 기존 private 요청의 phase journal을 대조한다.
3. 명시적 native-started의 claim·runtime·scope와 전달 실패 차단을 확인한다.
4. canonical history와 legacy·unknown·unavailable 표시를 확인한다.
5. 충돌의 관측 값과 save/read 동작을 확인한다.
6. 재시작과 결과 전달 실패 뒤 uncertain mutation이 재실행되지 않는지 확인한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

1은 `figma_control.pinned_operation_transitions`가 현재 enqueue·poll·result를 다시 실행한다. claim 전 timeout은 expired, claim 후 timeout은 uncertain이다. 읽기 timeout은 다음 명령을 막지 않고, claim된 mutation timeout은 같은 쓰기를 막는다. 다른 페이지 읽기는 uncertainty를 풀지 않고, 같은 scope의 discovery 읽기만 푼다. 끝난 결과의 재전송은 거절한다. native-started는 어느 전이에서도 만들지 않는다. 2는 새 enqueue의 `operation_id`와 `phase_events`를 기존 요청 파일에 덧붙인다. 단계는 queued, claimed, result-received, reconciled, uncertain만 서버가 기록한다. 클라이언트가 보낸 operation ID는 결과 권한으로 받지 않고, lifecycle 필드가 없는 기존 요청은 단계를 추정하지 않는다. 깨진 lifecycle은 claim하지 않는다. 3은 claim된 요청에만 `note_native_started`가 `native-started`를 한 번 덧붙인다. session, claim, file, page, revision과 현재 runtime이 서버에 저장된 claim과 같아야 한다. claim만으로 만들지 않고, 이 사건은 성공 상태가 아니다. 플러그인은 제어 scope·deadline·handler 검사 뒤 마지막 안전 지점에서 그 경로로만 전달하며 수신 실패 시 실행하지 않는다. 4는 `journal_history`가 서버 요청만 읽어 이력에 붙인다. lifecycle이 없으면 legacy이며 표시 단계는 unknown이다. 필드가 깨졌으면 unknown이고 성공으로 보지 않는다. 기록된 단계만 phase와 time으로 돌려주며 readback과 오류 문장은 포함하지 않는다. clientStorage 이력은 journal이 전달된 경우에만 classification과 phase를 가진다. 5는 `conflict_detail`이 충돌의 target, planned before/after, observed, rollback 이유, plan hash를 그대로 돌려준다. observed를 planned after로 덮어쓰지 않는다. 후속 동작은 save-evidence와 read-scope뿐이며 재실행은 없다. 6은 `restart_delivery_report`가 로컬 HTTP 제어 서버로 claim과 native-started를 보낸 뒤 결과 POST 없이 메모리의 runtime 기록을 지운다. 디스크의 같은 operation은 uncertain으로 남고 단계는 queued, claimed, native-started, uncertain이다. 같은 mutation은 다시 enqueue되지 않고, 새 플러그인 poll은 그 작업을 다시 넘기지 않는다. Figma Desktop은 열지 않는다.

현재 `history` route는 current runtime과 exact file/page scope를 검증한 canonical journal만 최대 80개 반환한다. UI `journalHistory`는 clientStorage event와 구분한다. lookup 불가를 성공 단계로 표시하지 않는다.

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

## 최종 결과 재전달 보완

- [x] 최초 수락 payload 지문과 exact claim/scope를 기록한다.
- [x] 같은 결과는 기존 응답만 돌려주고 활성 작업·단계·불확실성을 보존한다.
- [x] 상충 내용·legacy·서버 생성 terminal과 잘못된 ID를 거절한다.
- [x] 고정7개·관련52개 검사와 실제 인증 HTTP200/상충409를 확인한다.

최종 소스·출시·설치 결과는 [인수 현황](../FINAL_ACCEPTANCE.md)과 후속 패치 Wiki에서 구분한다.
