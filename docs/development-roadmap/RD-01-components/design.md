# RD-01 설계서 · 재사용 컴포넌트와 편집 속성

상태는 0.27 구현 후보의 검증 스냅샷이다. RD-01 AC 5개는 명시된 fixture/runtime 범위에서 통과했으며 모든 REQ의 양성 경로 완료를 뜻하지 않는다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [figma-bridge/code.js](../../../figma-bridge/code.js) | `importDesign, layout, applyProps` |
| [figma-bridge/semantic_components.js](../../../figma-bridge/semantic_components.js) | `ensureSemanticComponents` |
| [figma-bridge/direction_review.js](../../../figma-bridge/direction_review.js) | `기존 TEXT property 생성·linkDraftLabel` |
| [figma-bridge/foundation_palette.js](../../../figma-bridge/foundation_palette.js) | `main/set 팔레트 instance` |
| [tools/design_system.py](../../../tools/design_system.py) | `variant 입력 정규화` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

`code.js`의 `componentVariantGroups`는 `definition.variants`와 선택적 `variant_axes`를 읽는다. 축 값은 기존 variant 이름에 대응한다. 하나의 정의가 여러 축에 속하면 거절하며 축 선언이 없으면 `Variant`를 사용한다. 축에 배정되지 않은 `default` 같은 기존 정의도 `Variant` 그룹에 보존한다. 누락 조합을 Cartesian product로 만들지 않는다.

`usage`는 입력의 비어 있지 않은 문자열만 사용한다. `componentSwapTargets`는 `swap_targets`가 선언된 배열인지 검사하지만 반환값은 생성에 사용하지 않는다. 선언된 swap target의 실제 property 생성은 구현하지 않았다. 별도 `properties.label` 입력 schema를 추가한 구현은 아니다. `bindOwnedLabelProperty`는 실제 TEXT label과 Figma가 반환한 TEXT property key를 연결하고, instance가 그 key로 문구를 설정한다. API가 없으면 직접 label 문구를 보존하며 warning을 반환한다.

## 첫 구현과 남은 REQ 범위

현재 지원은 실제 TEXT key 연결·supported sizing 재사용·선언된 독립 축·원문 usage다. RD-01-REQ-04의 optional label/icon BOOLEAN·INSTANCE_SWAP 양성 생성은 첫 범위에 없다. producer schema에도 optional icon property가 없다. AC-05의 미선언 생성 금지 통과는 이 양성 기능 구현을 증명하지 않는다. 후속 [NF-01](../../next-roadmap/NF-01-component-families.md)은 PROPOSED다.

R8 실제 두 set은 TEXT·Visual만 가지며 Visual 각 12개가 control_styles와 일치했다. 실제 Component Configuration의 description·link는 원문 선언과 같이 비어 있었다. 모든 variant 가져오기를 GUI에서 실행했다거나 임의 optional 속성이 지원된다고 표시하지 않는다.

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

## 검증 스냅샷

R7 원본 TEXT getter·세 복사 instance의 같은 main/180·240·300 너비·구조 분리 oracle을 확인했다. R7 실제 opacity 0.9 편집은 재실행 후 보존됐고 숫자 복원 뒤 정상 검증이 통과했으나 explicit flag는 보관된 R7에 남는다. 새 R8은 main 24개·set 2개·instance 494개와 전체 4,820개 ID를 재사용하고 opacity override 0개였다. 상세 범위는 [최종 인수 기록](../FINAL_ACCEPTANCE.md)·[실제 검증 요약](../../../apps/little-hands/design/VERIFICATION.md)을 따른다. 향후 release 소스·설치 영수증은 Wiki release 기록에서 확인한다.
