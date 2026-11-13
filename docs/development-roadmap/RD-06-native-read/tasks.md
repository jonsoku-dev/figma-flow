# RD-06 작업서 · 목적별 네이티브 읽기와 제한된 캐시

상태는 0.27 구현 후보이며 표준 discovery 요약의 실제 관찰은 일부 확인됐다. RD-06 전체 Figma 인수는 대기다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. 동일 fixture의 full 반환과 실제 getter 목록을 대조한다.
2. summary projection과 coverage 및 읽기 전용 UI를 확인한다.
3. full 소비자의 partial 거절 검사를 실행한다.
4. session snapshot을 보관하지 않고 새 값을 다시 읽는지 확인한다.
5. getter와 전송 bytes의 fixture 측정 범위 및 실제 Figma 관찰을 구분한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

1은 `nativeReadGetterLedger`가 같은 fixture의 full `readNativeSemantics` 결과와 실제로 읽은 getter 이름을 함께 남긴다. 기존 호출은 인자 없는 full이다. `rect.width`와 `rect.fills`는 기록되고 `rect.exportAsync`는 호출하지 않는다.

full은 `componentPropertyDefinitions`의 전체 데이터(`preferredValues`의 component/component-set key 포함)와 하위 노드의 `componentPropertyReferences`를 복사한다. 참조가 없는 노드의 관측값 `null`과 지원하지 않거나 getter가 실패한 경우의 `unavailable_fields`·`unavailableFields`를 구분한다. width 등 지원 필드만 요청한 summary는 이 getter들을 읽지 않으며 component 데이터 요청은 full로 돌아간다. [component property fixture](../../../tests/test_native_component_properties.cjs)는 getter ledger, 복사한 값의 보존, 재호출 시 최신 값, summary 생략·fallback을 확인한다. 실제 Figma component property getter 실행 인수는 이 fixture가 보장하지 않는다.

2는 native summary coverage를 공유 reader의 summary profile로 반환한다. schema는 `figma-flow-native-read-summary-v1`이고 `coverage.complete`는 false다. 요청한 `width`는 같은 fixture의 full과 같고, `fills`처럼 이미지 closure가 필요한 필드는 full로 돌아간다. 스타일·변수·raster는 생략 목록에 남긴다. ImportPanel의 `NativeSummary`는 그 결과만 보여주고 보내지 않는다. 표준 discovery의 별도 요약 버튼은 주 페이지의 width/height만 요청하며 full fallback 없이 `coverage.pageIds`·nodeIds·fields·omitted·complete false를 표시한다. `expected_scope`의 전체 허용 범위는 실제 읽은 주 페이지 범위와 구분한다.

3은 `requireFullNativeRead`가 summary coverage를 full evidence로 받지 않는다. full readback·native edit·draft read·graph import/apply/pair는 full 경계를 유지한다. graph discovery의 기본 `read`는 모든 허용 페이지를 full로 읽으며 별도 요약 버튼은 partial을 그대로 보여 준다. React·legacy 패널은 별도 summary 파일명을 사용하고 진단에는 최신 읽기 결과를 연결한다.

4는 공식 documentchange가 원격 편집, 비동기 페이지 로드, 변수 변경까지 이 런타임에서 보장되는 것을 확인하지 못해 session cache를 넣지 않는다. TTL은 coverage가 아니다. 공유 reader는 호출마다 다시 읽고 저장한 snapshot을 돌려주지 않는다.

5는 `compareNativeReadProfiles`가 같은 fixture의 요청 필드 일치, getter 이름, UTF-8 JSON 바이트를 실측한다. 변경 무효화와 wall-clock은 측정하지 않는다. 0.26.2의 사진 크기 결과는 재사용하지 않는다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
node --test tests/test_native_raster_table.cjs tests/test_graph_token_sync.cjs tests/test_readable_spec_native.cjs
node tests/graph_discovery_raster_oracle.cjs
python3 -B -m unittest discover -s tests -p 'test_native_raster_assets.py'
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

주 세션의 실제 R7 요약은 4,818개 노드의 width/height가 이전 full과 모두 일치했다. 진단 JSON에서 summary profile·complete false와 정확한 node ID/field/omission 목록 및 무거운 필드 부재를 확인했다. 일반 graph import `--apply`와 pair는 summary를 거절했으며 출력 없음·graph bytes 보존을 확인했다. 이는 주 세션 관찰이며 문서 작성자가 재실행한 결과가 아니다.

실제 GUI에서 이후 full 읽기로 최신 진단이 교체되는 동작, 편집·페이지 전환별 새 읽기와 나머지 AC·보존 검사 연결은 아직 대기다. fixture getter count와 실제 지연은 따로 보고하며 요약 수치만으로 속도 향상을 주장하지 않는다.

[finalize_discovery_summary.cjs](../../../tests/finalize_discovery_summary.cjs)는 제품 변경 전 기준 커밋 `dca7dfcb4ec97ee52427a40050e815f53880d47e`에 고정됐다. 변경 전 `0 !== 2` 예상 assertion 실패 후 동일 blob의 변경 후 통과가 주 세션 근거다. host의 주 페이지 범위·scope 변경 거절·busy 중복 차단·full 기본값·모든 허용 페이지 읽기·mutation 거절·진단·React/legacy 버튼·번역을 확인한다. 추가 확인의 시작점은 아래 명령이며 이번 문서 갱신에서는 실행하지 않았다.

```sh
node tests/finalize_discovery_summary.cjs
```

session cache는 도입하지 않았다. Codex 설치 0.26.3과 native 0.27 후보를 구분하고 push·후보 설치 후 검증을 별도로 남긴다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
