# RD-07 작업서 · 제어 전송과 실행 정책의 모듈 경계

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 현재 protocol trace와 source pin 범위를 고정하고 모듈 책임을 표로 적는다.
2. 순수 전송 함수만 이동하고 domain validator 호출 위치를 유지한다.
3. publisher 조립과 trusted_sources를 같은 변경에서 이관한다.
4. 실제 generated bundle의 모든 task kind를 실행하고 오류·uncertainty도 비교한다.
5. 구 경로를 지우고 필요한 공개 심볼만 남긴다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

1은 `load_runtime_boundary_trace`가 현재 전송 경로 poll, native-started, result와 source pin 범위 tools, figma-bridge, library를 고정한다.

| 모듈 | 책임 |
| --- | --- |
| workspace_transport | 제안된 순수 전송이다. 이 단위에서는 분리하지 않는다. 후보는 poll, native-started, result이다. |
| workspace_control | 도메인 검사는 workspace_control에 남긴다. kind와 operation, scope, revision을 검사한다. |
| figma_workspace.py | publisher 조립과 trusted_sources는 이 단위에서 옮기지 않는다. source pin은 tools, figma-bridge, library이다. |

2는 controlRequest만 figma-bridge/workspace_transport.js로 옮긴다. kind, operation, scope, revision 검사는 workspace_control.js에 남긴다.

3은 runtime_module_names와 assemble_shared_runtime이 발행 조립과 trusted_sources의 같은 모듈 목록이다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
python3 -B -m unittest discover -s tests -p 'test_figma_workspace.py'
python3 -B -m unittest discover -s tests -p 'test_workspace_publish_guard.py'
node --test tests/test_workspace_control.cjs tests/test_workspace_host.cjs tests/test_native_runtime_version.cjs
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 Figma에서 기존 고정 plugin을 재개하고 runtime identity를 확인한 뒤 read와 승인된 fixture write를 수행한다. source unit test만으로 생성된 runtime 동작을 인증하지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
