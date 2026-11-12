# 다음 기능 설계안

상태는 모두 **PROPOSED**다. 이 폴더는 구현·설치·배포 또는 사용자 인수 완료 기록이 아니다. 작성 기준은 2026-11-13의 미커밋 0.27.0 후보 코드다. 실행 시 현재 checkout과 소유 파일을 다시 확인한다.

현재 RD-01~09는 구현된 후보이며 실제 인수 결과는 [최종 인수 기록](../development-roadmap/FINAL_ACCEPTANCE.md)을 따른다. 새 앱의 실제 업무 기능은 앱의 검증 대상이다. 예약·대기·취소 기능을 Figma Flow의 새 제품 기능으로 다시 제안하지 않는다. 전체 suite의 과거 통과나 작은 Figma getter 확인은 전체 화면 인수와 다르다.

## 현재 구현과 후속 제안의 경계

실제 앱 어댑터의 `apps/little-hands/design/source.py`는 `share_control_styles`로 기존 컨트롤 스타일 선언 492개를 desktop/mobile 각 12개, 총 24개 main 선언으로 공유한다. `design/control-reuse.json`의 현재 값은 viewport별 이전 246개와 공유 12개이며, 두 viewport를 함께 고정한 12개 profile 계열이다. signature는 각 viewport의 정확한 visual profile을 함께 비교하고 `maxWidth`만 제외한다. width cap은 해당 profile·viewport에서 관측한 최댓값이다. 이는 선언 재사용 구현 근거이며 실제 Figma main/instance getter 인수와 구분한다. NF-01의 Field/Input/Checkbox/Radio/Table 계열 확장은 여전히 제안이다.

native 제작에서는 화면마다 page 전체 container read를 반복하는 경로와 주석별 semantic key 탐색의 비용이 발견되어 별도 수정 중이다. 현재 `direction_review.js`에는 `indexDeclaredContainerRead`를 공유하는 경로가 보이지만, 이 문서는 전체 성능 수정 완료나 실측 배수를 주장하지 않는다. 이 작업은 fresh 읽기 내 중복 탐색 제거이며 NF-02의 세션 캐시와 다르다. NF-02 실행 전 통합된 현재 소스에서 baseline을 다시 측정한다.

## 선택한 실행 순서

| 순서 | 설계 문서 | 사용자에게 생기는 결과 | 우선순위 근거와 선행 조건 |
| --- | --- | --- | --- |
| 1 | [NF-01 입력·선택·표 컴포넌트 계열](NF-01-component-families.md) | 반복 필드를 실제 Component/Instance로 편집하고 재사용한다. | 현재 실제 앱의 편집 가능한 도형과 계열 인스턴스 사이의 차이를 직접 줄인다. 현재 native 인수가 선행한다. |
| 2 | [NF-02 안전한 증분 네이티브 읽기](NF-02-incremental-native-read.md) | 탐색 시 같은 getter를 반복 읽는 비용을 줄이고 검증 읽기는 최신 상태로 유지한다. | NF-01의 instance·속성 변화 fixture를 재사용한다. 성능 개선은 동일 작업 실측으로 판단한다. |
| 3 | [NF-03 실행 원인과 상세 차이 탐색](NF-03-causal-history.md) | 어떤 입력과 선행 작업이 어떤 변경을 만들었는지 찾아간다. | 기존 journal·dependency graph 위의 새 조회 기능이다. NF-02 없이도 시작 가능하다. |
| 4 | [NF-04 SSR 어댑터와 CSS 내보내기](NF-04-renderer-adapters.md) | graph 값을 서버 렌더링과 외부 CSS에서도 같은 해시로 사용한다. | NF-01 계열 의미를 출력 계약에 연결한다. 현재 앱 어댑터는 기준 사례로 보존한다. |
| 5 | [NF-05 포크 패치·근거 교환과 개선 러너](NF-05-improvement-runner.md) | 다른 checkout의 변경과 근거를 검토하고 중단 지점에서 검사를 재개한다. | NF-03의 근거 식별·redaction 계약을 재사용한다. 공개 업로드 없이 로컬 파일 교환부터 만든다. |
| 6 | [NF-06 도메인 경계와 버전 전환](NF-06-domain-protocol.md) | 오래된 준비 번들과 새 런타임의 충돌을 설명하고 안전하게 재준비한다. | 다른 패킷의 실제 호출 경험 후 경계를 굳힌다. 단순 파일 분리를 반복하지 않는다. |

추천 순서는 비용·실사용 가치에 대한 제안이며 전체 일괄 구현 권한이 아니다. NF-01 이후 NF-03은 NF-02와 독립적으로 진행할 수 있다. NF-04와 NF-06이 함께 `tools/figma_workspace.py`를 변경하면 순차 작업한다. 각 패킷 안에서도 한 파일에는 한 writer만 배정한다.

## 문서를 실행하는 방법

각 문서의 기능 계약과 설계 계약을 먼저 읽고 마지막 Cursor 프롬프트를 별도 작업으로 전달한다. 프롬프트의 파일 목록은 시작 시 재확인할 소유 경계다. 소유 범위 밖 변경이 필요하면 원인과 필요한 파일을 보고하고 해당 변경을 멈춘다. 기존 dirty 파일을 되돌리거나 다른 패킷을 앞당기지 않는다.

명시한 기존 명령은 현재 저장소에서 찾은 회귀 검사다. `새 검사 제안`은 아직 없는 검사이며 통과했다는 뜻이 아니다. 제품 구현 시 각 패킷의 독립 인수 조건을 충족하고 필요한 실제 브라우저·Figma 검증을 추가한다. 공통 기록은 `skills/patch-knowledge/SKILL.md`를 따른다. CHANGELOG와 Wiki를 갱신하고 `python3 tools/patch_knowledge.py verify --ref HEAD`를 실행한다. 실패 기반 개선은 수정하지 않은 독립 기준으로 `python3 tools/patch_knowledge_check.py gate <proposal.json> --execute`를 통과해야 한다. 이 명령은 실제 base/target 커밋을 요구하므로 커밋 권한이 없으면 준비 상태와 미완료 조건을 보고한다.

이 문서 작성 작업은 제품 코드나 검증 기준을 바꾸지 않았다. 기능 구현, 실제 native 인수, 성능 수치, 클라우드 저장·배포 성공을 주장하지 않는다. 원문 API는 각 문서의 공식 링크를 확인한다. API 존재와 현재 호스트 사용 가능 여부는 별도 검증이다.
