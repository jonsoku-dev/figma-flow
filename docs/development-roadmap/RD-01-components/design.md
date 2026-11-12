# RD-01 설계서 · 재사용 컴포넌트와 편집 속성

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `importDesign, layout, applyProps` |
| [figma-bridge/semantic_components.js](../../../figma-bridge/semantic_components.js) | `ensureSemanticComponents` |
| [figma-bridge/direction_review.js](../../../figma-bridge/direction_review.js) | `기존 TEXT property 생성·linkDraftLabel` |
| [figma-bridge/foundation_palette.js](../../../figma-bridge/foundation_palette.js) | `main/set 팔레트 instance` |
| [tools/design_system.py](../../../tools/design_system.py) | `variant 입력 정규화` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

제안하는 추가 입력은 선택적 `properties`와 `variant_axes`다. 첫 단위는 기존 단일 label로 구현하므로 입력 schema를 늘릴 필요가 없다.

| 값 | 제안 의미 | 검증 |
| --- | --- | --- |
| properties.label | TEXT 속성의 표시 이름·기본값·label 대상 | 실제 label 하나, 중복 이름 금지 |
| variant_axes | 축 이름과 선언한 값 목록 | 독립 축, 조합 unique, 존재하는 정의만 연결 |
| usage | 기존 스펙의 사용 설명과 문서 참조 | 로컬 출처·해시 유지, 외부 설명 생성 금지 |

`variant_axes`는 회귀 디자인 시스템의 `axes.json`에 선언된 값만 기존 variant에 연결한다. 선언되지 않은 조합은 만들지 않는다. 사용 설명은 입력에 있는 문장만 description으로 옮긴다. 축 선언이 없으면 기존 평면 variant map을 단일 `Variant` 축으로 해석한다. 런타임 identity와 시각 profile을 분리하되, 기존 semantic key를 버리지 않는다.

## 구현 결정

TEXT property를 만드는 책임은 main 작성 경로 한 곳에 둔다. Figma가 반환한 key를 실제 컴포넌트 메타데이터에 보존하고 instance 작성자가 사용한다. 방향 검토에서 이미 사용하는 API 패턴을 재사용한다.

재사용 분류는 구조 fingerprint와 지원된 instance 조정값을 나눈다. 임의로 width/height/transform 전체를 fingerprint에서 제거하지 않는다. Auto Layout으로 재현할 수 없는 위치·크기 차이는 기존 분리를 유지한다. 실제 수정 전후 렌더와 main identity를 함께 검사한다.

원문 근거가 있는 사용 설명은 main/set의 description과 지원되는 문서 링크에 투영한다. 화면·instance 이름은 사람이 읽는 의미 이름을 유지한다. semantic key는 별도 plugin data로 보존한다.

## 호환성·이관·복구

기존 패킷은 기존 평면 variant 입력을 계속 받는다. 새 property를 기존 소유 main에 더할 때 현재 정의·참조를 먼저 읽는다. 충돌하면 자동 rename이나 재생성 대신 진단한다. main identity 분류의 변경은 기존 소유 데이터에 한정하고, 합치기가 안전하지 않으면 기존 Layout 변형을 보존한다. 되돌릴 때 새 property·메타데이터만 제거할 수 있어야 하며 사용자 instance를 detach하지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.

## 공식 근거

- [Component properties API](https://developers.figma.com/docs/plugins/working-with-component-properties/)는 property 생성과 실제 sublayer 참조를 설명한다.
- [Component properties](https://help.figma.com/hc/en-us/articles/5579474826519-Explore-component-properties)는 TEXT·BOOLEAN·INSTANCE_SWAP과 variant의 역할을 구분한다.
- [Variants](https://help.figma.com/hc/en-us/articles/360056440594-Create-and-use-variants)는 의미 있는 축 이름과 유일한 조합을 설명한다. 가능한 모든 조합을 만들 필요는 없다.
- [컴포넌트 관리](https://help.figma.com/hc/en-us/articles/39747637290263-Components-collection-Tips-for-component-management)는 사용 설명과 관리 관행의 근거다.

조사일은 2026-11-12다. API를 구현할 때 현재 공식 문서와 실제 getter를 다시 대조한다.
