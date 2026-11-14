# 다음 기능 설계안

신규 기능과 최적화는 [제품 헌법](../../CONSTITUTION.md)과 [Design 전용 설계](../../specs/design-specialization/spec.md)에 따라 채택한다. 각 작업에 실제 Design 사용 장면과 graph의 인수 근거를 연결한다.

이 문서는 제안의 우선순위와 기존 설계 문서를 잇는다. 각 항목은 제안 당시의 범위다. 구현된 부분과 남은 범위는 아래 현재 기준에서 확인한다. 현재 동작과 인수 결과는 [최종 인수 기록](../development-roadmap/FINAL_ACCEPTANCE.md) 및 각 소스의 독립 검사에서 다시 확인한다.

예약·대기·취소는 Little Hands 앱의 업무 기능이다. 이를 Figma Flow 제품에 다시 제안하지 않는다. 전체 suite의 과거 통과나 일부 Figma getter 확인은 전체 화면 인수가 아니다.

## 0.29의 구현 범위

기존 Design 페이지의 검토 보드, 같은 출처 에셋의 명시적 입력 매핑, 선택한 네이티브 속성의 관측과 재실행 비교가 추가됐다. [정본 기능 그래프](../../specs/graph-review/graph.json)와 [실제 인수 결과](../../specs/graph-review/spec.md)에서 구체적인 범위를 확인한다. NF-07의 임의 웹 화면 전체 변환과 NF-08 공식 플러그인 선택 연동은 후속 작업이다. 다음 구현자는 기존 등록 경로와 현재 지원 범위에서 이어서 작업한다.

## 현재 구현과 제안의 경계

Little Hands의 `apps/little-hands/design/source.py`는 실제 캡처를 그래프와 디자인 파일로 변환한다. `reconcile()`은 graph source와 사람이 편집한 값을 비교한다. baseline이 없는 기존 값은 `retained_legacy_edits`에 보존하고, 양쪽에서 같은 필드를 다르게 바꾸면 충돌로 중단한다. `--expected-sha256`는 오래된 graph 입력을 거절한다. 이 동작은 own-mode의 G1 기준 일부다. 기존 `REQS`·`STATES`의 위치 참조를 안정된 의미 ID로 바꾸는 G1 조건과 G0~G5 전체 인수는 별도로 남아 있다.

`share_control_styles()`는 기존 492개 컨트롤 선언을 12개 profile 계열의 desktop/mobile main 선언 24개로 공유한다. 이는 현재 authored declaration 재사용이다. 입력·선택·표 계열의 완전한 native property 지원은 [NF-01](NF-01-component-families.md) 제안이다. main/instance 실제 getter의 결과는 별도 인수 근거로 다룬다.

Native 제작의 같은 실행 안에서 반복하던 container·annotation 탐색은 공유 index를 사용하는 경로가 있다. 이는 NF-02의 세션 browse cache와 다르다. NF-02를 시작할 때 통합 소스에서 동일 작업의 기준을 다시 잰다. Figma event 전달만으로 모든 main·style 파생 변경의 최신성을 증명하지 않는다.

## 우선순위

own-mode는 Figma Flow를 설계·구현·검증에 직접 쓰는 흐름이다. 먼저 [Starter Role의 G0~G5 계획](../STARTER_ROLE_FEATURE_SPEC.md)을 완료 조건으로 사용하고, 그 다음 일반 제품 기능을 아래 순서로 진행한다.

| 순서 | 작업 | 사용 결과와 완료 방향 | 기존 계약과 새 문서 |
| --- | --- | --- | --- |
| 0 | G0~G5 own-mode | 작은손의 기준값·원문·캡처·검증을 고정하고, 정책 변경 리뷰·영속 웹 출력·Starter native round trip·오프라인 인계까지 실제 한 건으로 입증한다. | G0~G5 전체는 PROPOSED다. G1의 일부 source merge 구현은 끝났지만 안정 ID 이관과 role acceptance는 남아 있다. [Starter Role 기능 계약](../STARTER_ROLE_FEATURE_SPEC.md) |
| 1 | Native read와 기존 코드에 맞춘 디자인 구현 | 현재 Figma 파일의 정확한 node·component·variable 읽기를 실제 프로젝트의 기존 코드 구조와 대조한다. 확인된 component와 상태를 재사용하고, 읽기·생성·검증 결과를 각각 표시한다. | [기능 경로와 readback 제한](../../skills/figma-flow/references/figma-feature-routes.md), [가이드의 native 작업](../guide.md), RD-06/08. 새 일반 SDK scaffold는 이미 지원되는 design context 작업을 대신하지 않는다. |
| 2 | Web import | 실제 브라우저 capture를 제한된 source DTO로 바꾸고, review 뒤 기존 graph와 native importer 경로로 들여온다. SSR/CSS 출력인 G3와 방향이 반대인 입력 경로다. | [NF-07 web import와 editor capability](NF-07-web-import-editor-capabilities.md#web-import) |
| 3 | Component families | Field/Input/Checkbox/Radio/Table 계열을 명시한 TEXT·BOOLEAN·INSTANCE_SWAP 선언과 실측 override 보존으로 편집한다. | [NF-01](NF-01-component-families.md) |
| 4 | Causal history와 accessibility | exact operation·artifact revision의 원인과 필드 차이를 읽기 전용으로 찾고, keyboard/focus/label 상태를 함께 검증한다. | [NF-03](NF-03-causal-history.md). 기존 history 요약과 dependency view를 다시 만들지 않는다. |
| 5 | Large-document optimization과 compatibility | 대형 파일에서 선택적 browse 비용을 줄이되 검증은 fresh getter로 유지한다. 구버전 task/runtime 조합은 정확한 재준비 안내를 받는다. | [NF-02](NF-02-incremental-native-read.md), [NF-06](NF-06-domain-protocol.md) |
| 6 | Editor capability matrix | Figma Design의 기능별로 지원·거절·미확인 경로를 비교한다. API 이름이나 manifest 값만으로 runtime 지원을 단정하지 않는다. | [NF-07 editor capability matrix](NF-07-web-import-editor-capabilities.md#editor-capability-matrix) |
| 7 | 선택적 공식 plugin 연동 | 핵심 own-mode·read·import·component·history·large-document·editor matrix가 인수된 뒤, 정확한 공식 plugin을 선택적으로 연결할지 검토한다. | [NF-08 optional installed-plugin routing](NF-08-optional-plugin-routing.md). 설치, 실행 또는 계정 승인을 자동화하지 않는다. |

G3의 graph-to-web 영속 출력은 [NF-04 SSR adapter와 CSS 내보내기](NF-04-renderer-adapters.md)에서 own-mode의 첫 사용 사례로 수행한다. NF-05의 patch exchange와 improvement runner는 개발자 유지보수 도구다. 첫 own-mode 인수 뒤 독립 과제로 다루며 위 순서를 앞지르지 않는다.

이 순서는 사용 가치에 대한 제안이다. 전체 일괄 구현을 승인하지 않는다. 한 파일은 한 writer가 순차로 수정한다. NF-04와 NF-06이 같은 workspace publisher를 건드리면 분리하거나 순차 작업한다.

## 문서를 실행하는 방법

각 설계의 기능·구현·검증·rollback 조건과 마지막 Cursor prompt를 읽고 한 항목씩 전달한다. 시작할 때 현재 checkout, dirty files, 실제 함수 caller와 파일 소유를 다시 확인한다. 범위 밖 파일이 필요하면 변경을 멈추고 필요한 계약을 보고한다.

기존 명령은 저장소에 있는 회귀 검사다. "새 검사 제안"은 아직 구현되지 않은 검사다. 제품 변경에는 각 설계의 독립 인수 조건과 필요한 실제 browser/Figma 관찰을 추가한다. `skills/patch-knowledge/SKILL.md`에 따라 CHANGELOG와 Wiki를 갱신하고 `python3 tools/patch_knowledge.py verify --ref HEAD`를 실행한다. 실패 기반 개선은 수정하지 않은 기준으로 `python3 tools/patch_knowledge_check.py gate <proposal.json> --execute`를 통과해야 한다. 이 gate에는 실제 base/target commit이 필요하다.

이 문서들은 기능 구현, 실제 native 인수, 성능 수치, 클라우드 저장 또는 배포 성공을 주장하지 않는다. 공식 API 문서는 구현 시 다시 읽고, API 존재와 현재 host/runtime에서 사용할 수 있는지는 각각 검증한다.

[웹 스와이퍼·모션·인터랙션의 Design 변환 설계](NF-09-interactive-web-design.md)는 브라우저 상태 그래프, 네이티브 표현과 실제 프로토타입 인수 절차를 제안한다.
