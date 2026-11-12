# RD-04 작업서 · 동기화 변경을 골라 적용하기

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. 독립 token과 alias 묶음 fixture의 부분 적용 조건을 확인한다.
2. host manifest의 stable identity와 plan hash를 검증한다.
3. UI 선택·전체 선택·선택 수·영향 target을 확인한다.
4. protocol 2의 atomic group, CAS와 실제 readback을 대조한다.
5. 부분 결과가 전체 marker와 pairing을 진전시키지 않는지 확인한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

다음은 fixture helper의 검증 범위다. 실제 실행 권한은 아래 host manifest 경로에 있다.

1은 `tests/fixtures/rd04/partial-apply.json`을 `load_selective_sync_fixture`로 읽는다. 독립 token 셋 중 color/action과 color/quiet만 after가 적용되고 space/gap은 before 8이 남는다. alias 묶음 type/body·type/size는 반만 고를 수 없고 button.font·text.font가 함께 보인다. 이 조건 조회는 값을 쓰지 않는다. 2는 `serialize_selection`이 kind와 key의 stable identity와 alias bundle id를 만들고, 선택과 분리된 plan_sha256를 직렬화한다. 같은 선택의 순서가 바뀌어도 직렬 결과는 같다. 3은 `graphSelection`이 기존 변경 행에 선택, 전체 선택, 선택 수, 영향 target을 붙인다. 변경이 있는데 하나도 고르지 않으면 적용을 열지 않는다. 4는 `commit_selective_apply`와 `commitGraphSelection`이 같은 선택을 검증한다. 고른 token만 새 값이 되고 나머지는 readback에 남는다. baseline은 적용한 값만 기록하며, 관측값이 before와 다르면 아무것도 쓰지 않는다. 5는 `commit_component_fields`가 같은 token을 쓰는 padding 필드를 함께만 적용한다. `node_id`와 `main_component_id`는 유지되고, 고르지 않은 fontSize는 baseline에 들어가지 않는다.

현재 실행 경로는 `selection_manifest`의 `figma-flow-selection-v2`를 번들에 pin하고 `selectedPlan`이 protocol 2의 `selected_ids`, `plan_sha256`와 공유 root group 전체를 검증한다. 부분 readback은 `partial_apply`를 남기고 전체 page marker를 갱신하지 않는다. 생성·binding repair migration은 전체 선택만 허용한다.

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
