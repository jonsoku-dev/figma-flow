# NF-02 안전한 증분 네이티브 읽기

상태는 **PROPOSED**다. RD-06은 full/summary 분리이며 session cache는 의도적으로 없다. 이 제안은 탐색 성능을 위한 별도 기능이다.

## 기능 계약

큰 페이지에서 선택한 노드의 위치·크기·표시 여부만 다시 보는 탐색은 반복 getter 비용을 줄일 수 있다. 사용자는 최근 탐색 결과와 최신 검증 결과를 구분해서 본다. 최초 범위는 summary의 기존 다섯 필드에 한정한 세션 메모리 캐시다. full 읽기와 apply 전후 검증은 매번 실제 getter를 사용한다.

디스크·clientStorage 영속 캐시, full 검증 캐시, TTL만으로 최신임을 주장하는 방식, 전체 문서 선로딩을 기본값으로 하는 방식은 제외한다. 캐시 hit 비율 자체를 사용자 가치나 정확성으로 취급하지 않는다.

## 현재 경로와 근거

`figma-bridge/native_semantic_read.js`의 `summaryProjectable`, `projectNativeSummary`, `readNativeSemantics`, `requireFullNativeRead`가 공통 경로다. `nativeReadSessionSnapshot()`은 null을 반환한다. full snapshot을 그 함수에 저장하는 변경은 목표가 아니다. `figma-bridge/graph_token_sync.js`와 `tools/graph_sync.py`는 coverage와 full 검증 경계를 유지해야 한다. 기존 `tests/rd06_fresh_read.cjs`, `tests/rd06_summary_coverage.cjs`, `tests/rd06_reject_partial.cjs`는 독립 기준이다. 표준 discovery의 요약 동작도 캐시가 아니라 매번 getter를 읽는 현재 구현이다.

현재 소스에는 native 제작의 batch container 읽기와 annotation index가 구현되어 있다. `direction_review.js`는 fresh full 결과를 `indexDeclaredContainerRead`로 묶어 `readDeclaredContainerLinks`에 공유하고 최종 `readDraft`는 다시 fresh full로 읽는다. `native_annotations.js`의 `indexAnnotationNodes`는 주석의 semantic lookup을 묶는다. 주 세션은 수정하지 않은 oracle 5개 통과를 보고했다. 이는 한 fresh 실행 안의 중복 탐색 제거이며 NF-02의 세션 browse 캐시는 여전히 제안이다.

실제 R5 제작은 geometry 실패로 446초에 끝났다. R6은 native build와 full reader를 약 452초에 마쳤지만 raw 29,991,516바이트·envelope 33,417,636바이트가 당시 12/16 MiB 전송 상한을 넘어 결과 전달에 실패했다. 이후 정상 discovery로 복구했다. R6을 아직 실행 중이거나 전체 제품 인수 성공으로 표시하지 않는다.

R7은 gap binding 22개 보정·부모 oracle 확인과 raw 32 MiB/request 40 MiB 상한 이후 native 생성이 463.698초에 ok로 완료됐다. 현재 실제 full getter는 4,818개 노드·30,103,016바이트이며 44개 화면·prototype getter 312개·복귀 getter 110개·설명 보드 target 536개를 검증했다. 같은 패킷 재실행 14.985초는 기존 페이지를 재사용한 작업으로 최초 생성의 같은 작업량 benchmark가 아니다. getter 수의 80→14 같은 감소도 실제 wall-clock 속도 향상 근거로 바꾸지 않는다. 이 실행 결과는 주 세션 근거이며 문서 작성자의 재실행 결과가 아니다. 새 캐시 실험은 통합된 소스의 같은 조건·같은 성공 기준으로 baseline을 다시 측정한다.

[표준 discovery host](../../tools/graph_sync.py)의 `discoverGraphSummary`와 [React 패널](../../panel-ui/src/GraphPanel.jsx)·[legacy 패널](../../figma-bridge/graph-panel.html)은 주 페이지의 width/height만 읽는 별도 summary 동작을 제공한다. full fallback·cache·쓰기는 없으며 기본 full은 허용된 모든 페이지를 읽는다. `coverage.pageIds`·nodeIds·fields·omitted·complete false를 실제 범위로 표시하고 `expected_scope`의 전체 허용 범위와 구분한다. 진단은 최신 읽기를 사용한다.

주 세션은 실제 R7 summary 4,818개 노드의 width/height가 이전 full과 불일치 0개이며 진단 JSON의 summary·complete false·node ID/field/omission 목록이 정확히 일치하고 무거운 필드가 없음을 확인했다. 일반 graph import `--apply`와 pair는 거절됐고 출력 없음·graph bytes 보존을 확인했다. 후속 full이 최신 진단을 교체하는 실제 GUI 관찰은 대기다. [고정 회귀 검사](../../tests/finalize_discovery_summary.cjs)는 `dca7dfcb4ec97ee52427a40050e815f53880d47e`에서 제품 변경 전에 보존됐고 예상 assertion 실패 후 같은 blob 통과가 주 세션 근거다. 이 summary 경로는 NF-02 cache 구현이나 RD-06 전체 AC 통과가 아니다. 현재 Codex 설치 0.26.3·native 0.27 후보이며 push·후보 설치 후 검증, 사람의 품질 승인은 별도 대기다.

Figma 이벤트는 비동기·배치 전달이다. dynamic-page의 documentchange는 `loadAllPagesAsync()`가 선행해야 하며 main component 변화로 파생된 instance sublayer 변화와 style 파생 변화는 개별 노드 알림이 없을 수 있다. [공식 on 문서](https://developers.figma.com/docs/plugins/api/properties/figma-on/)를 근거로 노드 이벤트 하나만 보고 전체 최신성을 추정하지 않는다. 초기 구현은 이 제약을 수용해 검증 캐시를 도입하지 않는다.

## 데이터와 인터페이스 설계

제안 요청은 기존 summary 요청에 `freshness: "browse" | "fresh"`를 선택적으로 추가한다. 미지정은 `fresh`다. full 요청에는 `browse`를 허용하지 않는다. 기존 호출 signature와 출력 coverage를 유지하며 선택적 `observation`에 `source: "getter" | "session-cache"`, `sessionEpoch`, `observedAt`, `possiblyStale`를 추가한다. 이는 서버 revision이나 native 저장 revision이 아니다.

키는 plugin session identity, 확인된 문서 identity, page ID, reader schema/build, profile, 정렬한 nodeIds와 fields, 현재 epoch의 조합이다. 반환 순서는 요청 nodeIds 순서를 복원한다. fileKey가 없는 호스트에서는 안정된 세션 문서 identity를 확인할 수 없으면 캐시를 끈다. 파일 키 API 접근 권한을 새로 가정하거나 manifest 권한을 자동 확장하지 않는다. [fileKey 제약](https://developers.figma.com/docs/plugins/api/figma/#filekey)을 따른다.

한 페이지에 최대 64개 요청 엔트리, 직렬화 합계 최대 4 MiB를 초기 제안 상한으로 둔다. 크기를 넘는 결과는 저장하지 않는다. LRU를 쓰되 이를 위해 외부 의존성을 추가하지 않는다. 캐시에는 기존 summary 다섯 필드와 최소 식별 정보만 넣는다. 텍스트·이미지 바이트·스타일·변수 snapshot을 넣지 않는다.

## 무효화와 동시성 설계

- page change, plugin close/reopen, reader build/profile/fields/coverage 변화는 기존 엔트리를 폐기한다. summary를 full로 승격하지 않는다.
- 도구가 시작하는 native mutation 직전에 epoch를 올리고 캐시를 비운다. 성공/실패/불확실 종료 때도 다시 비운다. callback 안 쓰기도 같은 경로를 통과한다.
- 현재 페이지 nodechange 또는 이용 가능한 documentchange에서 CREATE/DELETE/reparent/PROPERTY_CHANGE는 페이지 전체 summary를 무효화한다. 개별 필드 최적화는 다음 단계로 미룬다.
- main component와 style/variable 전파, 알 수 없는 이벤트는 전체 엔트리를 무효화한다. 감시하지 못하는 전파는 `possiblyStale: true`로 유지하고 다음 명시적 새로고침에서 getter를 강제한다.
- 읽기 시작 epoch와 끝 epoch가 다르면 결과를 저장하지 않는다. 새로고침은 캐시를 우회한다. 이벤트가 아직 배달되지 않은 동일 tick에서도 browse hit은 최신 증명이 아니다.
- 필요한 이벤트를 관찰할 수 없으면 캐시를 끄고 getter로 fallback한다. 전 페이지 로딩이나 scope 확대가 필요한 경로는 기본값으로 켜지 않는다.

## 화면·오류·개인정보·접근성

탐색 결과에 "세션 탐색 결과, 최신 검증 아님"과 수동 새로고침을 표시한다. 새로고침은 `loading → fresh` 또는 `error`로 끝난다. 오류가 나면 이전 캐시를 최신으로 표시하지 않는다. 선택 노드 삭제는 `missing`으로 표시하고 cache hit으로 숨기지 않는다. 로딩·오류 상태는 live region으로 알리되 캐시 hit마다 음성 알림을 반복하지 않는다. 캐시는 프로세스 메모리에만 있고 공유 진단에는 hit/miss·크기·시간만 기록한다.

## 호환성과 복구

기존 fresh/full 경로는 동일하다. feature 경로를 제거해도 기존 저장 파일 마이그레이션이 없다. 캐시를 끄면 모든 summary가 getter로 돌아간다. 기존 RD-06 독립 검사 파일의 blob·모드를 바꿔 통과 기준을 낮추지 않는다. 변경된 cache 전용 동작은 새 검사에 둔다.

## 작은 작업과 한 writer 경계

1. `figma-bridge/native_semantic_read.js`, 새 `tests/nf02_summary_cache.cjs` 소유자가 browse/fresh와 bounded cache를 구현한다. full 경로는 보존한다.
2. `figma-bridge/workspace_host.js`, `figma-bridge/workspace_control.js`, `figma-bridge/graph_token_sync.js` 소유자가 mutation·page·종료 무효화와 요청 전달을 연결한다. 1번과 겹치는 파일은 없다.
3. 실제 표시 경로를 확인한 뒤 `panel-ui/src/GraphPanel.jsx`, `panel-ui/src/styles/graph.css`, `figma-bridge/locales/graph.json` 소유자가 provenance·새로고침을 연결한다. 실제 경로가 다르면 먼저 소유 변경을 보고한다.
4. 통합 담당자가 같은 page/node/fields를 반복하는 fresh와 browse를 교차 측정한다. 노드 수·getter 호출 수·elapsed·payload bytes·오답 여부를 기록한다. 별도 중복 탐색 최적화가 통합된 현재 소스에서 먼저 동일 작업의 기준을 측정하고 수치를 보고한다. 이전 비효율과 비교해 캐시만의 개선으로 보고하지 않는다.

## 인수와 검증

```sh
node --test tests/test_native_raster_table.cjs tests/test_graph_token_sync.cjs tests/test_readable_spec_native.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
npm --prefix panel-ui run build
```

새 검사 제안 `node --test tests/nf02_summary_cache.cjs`는 profile/fields/page/build 경계, 순서 복원, 상한, page 변경, 삭제·재부모화, 읽기 도중 epoch 변화, main/style 전파, mutation 실패, 이벤트 미지원, 새로고침을 다룬다. full 요청의 getter 카운트가 기존과 동일하고 cached summary가 `requireFullNativeRead`에 항상 거절되어야 한다. 실제 Figma에서 다른 instance 편집과 style 변경을 포함해 stale 표시와 fresh 결과를 비교한다. 정확성 불일치가 하나라도 있으면 해당 browse 경로를 비활성화한다. 캐시 반복 시 getter 호출 감소가 없어도 성능 성공으로 보고하지 않는다.

## Cursor 구현·테스트 프롬프트

```text
NF-02의 summary browse 전용 메모리 캐시만 구현하라. AGENTS.md, 패치 기록 계약, RD-06과 현재 native reader/모든 호출자를 먼저 읽어라. 소유 파일은 작업 1~3 목록과 필요한 패치 기록이다. 다른 dirty 변경은 보존하고 한 파일은 한 writer만 다뤄라. fresh가 기본이고 full/apply 검증은 실제 getter를 유지한다. Figma event는 배치되며 dynamic-page documentchange와 main/style 전파에 제약이 있다는 공식 문서를 재확인하라. 관찰 범위가 부족하면 cache disable 또는 possiblyStale이지 완전 최신 증명이 아니다. 영속 저장, 전체 페이지 자동 load, 새 권한/의존성, 기존 독립 검사 수정, 게시·커밋을 하지 말라. 새 회귀 검사와 기존 명령을 실행하고 동일 작업 기준·변경 후 getter 수/시간/bytes를 실측하라. 실제 native 권한이 없으면 그 인수만 미검증으로 보고하라. 반환은 변경 파일, 무효화 표, 정확성 검사, 측정 조건/결과, 미검증 범위와 rollback 방법이다.
```
