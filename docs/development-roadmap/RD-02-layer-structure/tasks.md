# RD-02 작업서 · 의미 있는 레이어 계층과 컨테이너

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. flat fixture와 선언한 Group/Frame/Auto Layout fixture를 별도로 고정한다.
2. Python 경계에서 트리·key·속성 조합을 검증하고 정규화한다.
3. 기존 JS leaf 작성 경로를 재사용해 부모 배치만 추가한다.
4. 명세·주석·prototype과 geometry의 연결을 실제 reader로 대조한다.
5. resize와 긴 한글 문구를 확인하고 지원 범위를 문서화한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

1은 `tests/fixtures/rd02/flat-layers.json`과 `declared-containers.json`을 `tests/test_rd02_layer_fixtures.py`로 고정했다. 2는 `design_directions.normalize_layer_containers`가 그 트리를 검증한다. 평평한 패킷은 빈 containers를 유지하고, cycle·중복 부모·없는 target·Group의 fill은 쓰기 전에 거절한다. 3은 기존 leaf 작성 뒤에 `placeDeclaredLayerParents`가 선언한 부모만 붙인다. 화면 Frame의 ID·크기·clip은 유지하고, 실패하면 새 컨테이너만 제거한 뒤 leaf를 원래 부모와 위치로 되돌린다. 4는 `readDeclaredContainerLinks`가 같은 트리를 `readNativeSemantics`로 읽어 부모, 화면 기준 geometry, 주석, 명세 상태, prototype destination을 대조한다. destination이 새 컨테이너이면 실패다. 5는 `refreshDeclaredContainerSizing`이 긴 한글 문구의 현재 상자에 맞춰 hug만 다시 계산하고, fixed는 배치 때 기록한 크기를 유지하며, fill은 부모 Frame 크기를 따른다. 사용자 instance의 type과 main id는 바꾸지 않는다. 실제 글꼴 측정과 Figma reflow는 아직 관찰하지 않았다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
node --test tests/test_readable_spec_native.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_directions.py'
python3 -B -m unittest discover -s tests -p 'test_design_bundle.py'
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 Figma 레이어 트리에서 Group/Frame 유형과 Auto Layout 속성을 읽고, 화면 prototype의 전진·복귀와 resize를 관찰한다. geometry 일치만으로 편집 사용성까지 승인하지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
