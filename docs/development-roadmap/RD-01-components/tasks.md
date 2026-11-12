# RD-01 작업서 · 재사용 컴포넌트와 편집 속성

상태는 0.27 구현 후보의 검증 스냅샷이다. AC 5개는 명시된 범위에서 통과했고 optional BOOLEAN·INSTANCE_SWAP 양성 생성은 후속 범위다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. 일반 가져오기 main과 instance의 실제 TEXT property key 연결을 확인한다.
2. 재실행 뒤 기존 identity와 사용자 override가 보존되는지 확인한다.
3. property API 부재의 직접 문구 보존과 warning을 확인한다.
4. 너비만 다른 사용처의 재사용과 구조 차이의 별도 main을 대조한다.
5. 선언한 축과 default 정의를 모두 작성하고 미선언 조합을 만들지 않는지 확인한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

1–3은 `tests/test_figma_bridge.py`의 mock Plugin API에서 세 문구, 반환 key, 재실행 보존, 속성 API 부재 시 직접 쓰기를 확인했다. 4는 `tests/semantic_component_reuse_oracle.cjs`에서 너비 세 사용처의 같은 main과, 이동·높이 차이의 별도 main, 렌더 너비·토큰 fill을 확인했다. 5는 `examples/regression-program/design-system/axes.json`의 size·state를 기존 variant에만 연결하고, 선언되지 않은 조합·사용 설명·swap target을 만들지 않는다. 후속 실제 근거로 원본 TEXT getter·복사본 main 글자색의 세 instance 반영·sizing 한글 증가·재실행 override 보존·R8 실제 set 정의와 빈 description/link를 확인했다. 각 근거의 범위는 최종 인수 기록에 연결한다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
node --test tests/test_graph_token_sync.cjs tests/test_native_control_icons.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_design_foundations.py'
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

주 세션은 실제 복사본에서 같은 main의 TEXT·글자색·180/240/300 너비와 sizing 한글 증가를 확인하고 임시 label·크기·main·parent를 복원했다. R7 실제 opacity override는 같은 패킷에서 보존됐고 숫자는 복원했지만 보관된 R7의 explicit flag는 남는다. 새 R8의 같은 4,820개 ID·페이지와 opacity override 0개, 두 실제 set의 TEXT/Visual·빈 description/link를 확인했다. 모든 variant의 GUI import를 수행했다는 주장은 하지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.

## 후속으로 남긴 양성 경로

`componentSwapTargets`의 배열 검사는 실제 swap property 생성을 뜻하지 않는다. producer schema의 optional icon·BOOLEAN/INSTANCE_SWAP 생성·설정·readback 양성 경로는 [NF-01](../../next-roadmap/NF-01-component-families.md)의 PROPOSED 작업이다. 이 문서의 AC 통과를 RD-01-REQ-04 전체 구현이나 출시·설치 완료로 바꾸지 않는다.
