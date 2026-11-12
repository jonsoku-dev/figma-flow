# RD-06 작업서 · 목적별 네이티브 읽기와 제한된 캐시

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 동일 fixture의 full 반환과 실제 getter 목록을 먼저 고정한다.
2. summary projection과 coverage를 추가하고 한 읽기 전용 UI에 연결한다.
3. full 소비자들이 partial을 받지 않는 negative test를 추가한다.
4. 실제 문서 변경 이벤트 coverage를 확인한 경우에만 session cache를 추가한다.
5. 동일 결과·변경 무효화·getters·전송 크기를 대조하고 실측한 범위만 보고한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

1은 `nativeReadGetterLedger`가 같은 fixture의 full `readNativeSemantics` 결과와 실제로 읽은 getter 이름을 함께 남긴다. 기존 호출은 인자 없는 full이다. `rect.width`와 `rect.fills`는 기록되고 `rect.exportAsync`는 호출하지 않는다.

2는 native summary coverage를 공유 reader의 summary profile로 반환한다. schema는 `figma-flow-native-read-summary-v1`이고 `coverage.complete`는 false다. 요청한 `width`는 같은 fixture의 full과 같고, `fills`처럼 이미지 closure가 필요한 필드는 full로 돌아간다. 스타일·변수·raster는 생략 목록에 남긴다. ImportPanel의 `NativeSummary`는 그 결과만 보여주고 보내지 않는다.

3은 `requireFullNativeRead`가 summary coverage를 full evidence로 받지 않는다. readback, native edit, draft read, graph discovery는 그 검사를 통과한 읽기만 저장한다. 요약 버튼은 partial을 그대로 보여 준다.

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

실제 Figma에서 요약·전체 읽기 비교와 편집·페이지 전환 후 무효화를 확인한다. fixture의 getter count 감소와 실사용 지연 감소는 따로 보고한다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.
