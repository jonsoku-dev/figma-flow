# RD-06 기능서 · 목적별 네이티브 읽기와 제한된 캐시

상태는0.27 첫 구현 범위의 기능 계약이다. 조건별 fixture·실제 관측과 미지원 확장은 [최종 인수 현황](../FINAL_ACCEPTANCE.md)을 따른다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 사용자 문제

패널의 작은 상태 갱신에도 전체 의미 정보를 읽는 경우가 있다. 사진 중복은 줄었지만 노드·text segment·style getter 비용은 그대로여서 작은 조회의 비용을 더 줄일 여지가 있다.

## 현재 구현

공유 `readNativeSemantics`는 page 전체 노드·속성·스타일·변수와 이미지 바이트를 읽는다. raster 바이트 dedupe는 한 읽기 안에서 동작한다. import/export, graph discovery, draft review, native-edit가 이 reader를 사용하고 전체 snapshot을 기대한다.

## 첫 구현 범위

full을 기본으로 유지하고 패널 요약용 읽기 profile 하나를 선택적으로 추가한다. 첫 단위는 getter 수를 줄이는 projection이며 장기 cache는 이후 별도 단위다.

mutation gate에서 전체 근거 생략, document 간 전역 cache, 영속 clientStorage 이미지 cache, JSON 한도 상향, freshness 추정, 측정하지 않은 속도 향상 주장은 제외한다.

## 기능 요구사항

- **RD-06-REQ-01** — 기존 호출의 기본 동작과 full snapshot schema를 유지한다.
- **RD-06-REQ-02** — 요약 profile은 요청한 node/field 범위를 명시하고 partial임을 반환한다.
- **RD-06-REQ-03** — 스타일·변수·부모·이미지 참조의 필요한 closure를 유지하거나 미포함을 명시한다.
- **RD-06-REQ-04** — cache는 같은 plugin session·file·page·generation 범위에 한정하고 변경 신호가 불확실하면 full로 돌아간다.
- **RD-06-REQ-05** — 쓰기 전 pairing·검증·recovery는 현재 full read를 요구한다. partial 결과를 저장된 full evidence로 바꾸지 않는다.

## 인수 조건

- **RD-06-AC-01** — 변화 없는 fixture에서 partial projection의 요청 필드는 full 결과와 같고, 부분 읽기임이 명시된다.
- **RD-06-AC-02** — getter 호출 수가 의도한 필드 범위만큼 줄어든다. 실제 측정 전 wall-clock 개선율은 표시하지 않는다.
- **RD-06-AC-03** — 추가·삭제·reparent·문구·style·variable·이미지 변경과 file/page 전환에서 stale cache를 재사용하지 않는다.
- **RD-06-AC-04** — partial 결과로 graph import/apply/recovery를 시도하면 거절되거나 fresh full read를 수행한다.
- **RD-06-AC-05** — 기존 inline raster와 raster table 호환·paint/ref·원본 SHA 검사를 유지한다.

인수 조건은 [설계서](design.md)의 경계를 보존하면서 [작업서](tasks.md)에서 구현한다. 현재 조건별 판정과 실제 관측·fixture의 구분, 후속 확장과 출시·설치 근거는 [최종 인수 현황](../FINAL_ACCEPTANCE.md)과 패치 Wiki에서 확인한다.