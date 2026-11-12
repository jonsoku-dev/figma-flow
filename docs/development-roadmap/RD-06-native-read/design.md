# RD-06 설계서 · 목적별 네이티브 읽기와 제한된 캐시

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/native_semantic_read.js](../../../figma-bridge/native_semantic_read.js) | `readNativeSemantics와 rasterImages` |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `readback, exportReadback, syncToApp` |
| [figma-bridge/direction_review.js](../../../figma-bridge/direction_review.js) | `readDraft` |
| [figma-bridge/native_edit.js](../../../figma-bridge/native_edit.js) | `네이티브 읽기` |
| [tools/graph_sync.py](../../../tools/graph_sync.py) | `discovery_bundle, normalize, verify_readback` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

제안 reader 옵션은 `{profile:"full"|"summary",nodeIds:[...],fields:[...]}`다. 기존 호출은 인자가 없어 full이다. 실제 옵션과 허용 field 목록은 boundary에서 고정한다.

partial 반환은 `coverage:{profile,nodeIds,fields,complete:false}`를 가진 별도 명시적 결과다. 기존 full schema를 `complete:false`로 축소해 조용히 전달하지 않는다. 첫 적용 소비자는 패널 요약 한 곳이며 discovery/import/export/native-edit는 full로 유지한다.

cache key는 fileKey/pageId/runtime generation/profile/정규화 요청 범위다. 바이트와 현재 native 값의 출처를 혼동하지 않는다. 같은 hash의 상충 바이트 거절은 유지한다.

## 구현 결정

한 공유 reader 안에서 property 수집을 profile별로 선택한다. 요약 consumer와 full verifier를 다른 함수 이름이나 별도 reader로 복제하지 않는다. 필요한 closure가 profile보다 크면 full로 fallback한다.

cache는 Figma의 실제 document 변경 이벤트가 보장하는 범위 안에서만 쓴다. remote edit·async page load·변수 변경을 관찰할 수 있는지 공식 API와 실제 런타임에서 먼저 확인한다. 보장할 수 없는 종류는 항상 재조회한다. 현재 값을 읽었다는 증거에 TTL만 붙여 새 근거로 쓰지 않는다.

성능 비교는 동일 fixture·동일 요청 범위·같은 native runtime에서 전후 교차 순서로 실행한다. getter 수, 고유 image read 수, UTF-8 JSON 바이트와 지연 분포를 별도로 남긴다. 0.26.2의 반복 사진 결과를 이 개선의 성능 결과로 재사용하지 않는다.

## 호환성·이관·복구

옵션 부재는 full로 유지하므로 기존 소비자는 이관하지 않는다. 요약 opt-in 한 곳부터 시작한다. cache를 끄는 fallback이 full과 동일하게 작동해야 한다. 불확실한 invalidation이 발견되면 cache 단위를 제거하고 projection만 유지한다. 영속 cache migration은 만들지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.


