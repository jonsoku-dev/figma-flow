# 개발 계획의 현재 구현 기준

기준 Git은 `9a6f8ba694666ef5040a296c14b1af49bddcd722`다. 0.26.2의 [릴리스](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.26.2)와 [소스 검증 범위](../llm-wiki/verification.md)를 구분해 읽는다. 과거 실행 결과는 새 브랜치의 현재 성공 증거가 아니다.

## 0.26.3에서 다루는 UI

작업 목록과 이력에 현재 revision의 관측 상태 분포, 실행별 연결과 제한된 애니메이션을 추가한다. 요청과 결과의 연결은 실제 dispatch에서 만든 실행 식별자를 사용한다. 오래된 이력에는 연결을 추정하지 않는다. 이 UI는 실행 기록을 설명하며 제품 품질·클라우드 저장·전체 인수의 완료율을 인증하지 않는다. 정확한 제품 계약은 [이력 시각화 스펙](../../specs/workspace-activity/spec.md)에서 관리한다.

RD-03의 작업 간 `depends_on`과 RD-08의 영속적인 단계 journal은 이 UI와 별개인 후속 기능이다. UI용 실행 ID를 Python 제어 journal의 권한이나 복구 증거로 재사용하지 않는다.

## 컴포넌트 재사용은 두 경로에 이미 존재한다

| 구현 위치 | 현재 동작 | 남은 개선 |
| --- | --- | --- |
| [일반 가져오기](../../figma-bridge/code.js)의 `importDesign` | 정의·변형별 main을 만들고 화면에 instance를 배치 | label을 직접 수정하는 경로에 TEXT 속성 노출이 부족 |
| [의미 컴포넌트](../../figma-bridge/semantic_components.js)의 `ensureSemanticComponents` | 의미 key와 profile이 같으면 main을 재사용 | 크기·transform 차이가 Layout 변형을 늘릴 가능성 |
| [방향 검토](../../figma-bridge/direction_review.js) | 버튼 main/set의 TEXT 속성과 실제 instance를 사용 | 화면 내부 레이어가 평평해 의미 계층이 부족 |
| [기초 요소 팔레트](../../figma-bridge/foundation_palette.js) | main/set과 연결된 instance, 토큰 binding과 설명을 사용 | 다른 생성 경로와 속성·사용 설명의 일관성 보완 |

컴포넌트를 전혀 재사용하지 않는다는 결론은 현재 코드와 맞지 않는다. 재사용이 어느 경우에 분리되는지, instance에서 무엇을 편집할 수 있는지, 레이어 구조가 얼마나 읽기 쉬운지가 이번 개선의 대상이다.

## Frame·Group·Component의 선택 기준

| 노드 | 사용하는 이유 | 이 저장소의 적용 경계 |
| --- | --- | --- |
| Frame | 명시적 크기, 배경, clipping, layout, prototype 화면 | 고정 desktop/mobile 화면과 배치 책임이 있는 영역에 유지 |
| Group | 자식 범위를 따라 움직이는 정적 시각 묶음 | 독립 배치·clipping 책임이 없는 장식·아이콘 묶음에 한정 |
| Component / Instance | 정의를 공유하고 속성·변형·override를 제공 | 반복되는 버튼·카드·제어에 사용하며 instance를 detach하지 않음 |
| Auto Layout Frame | 방향·간격·padding·정렬과 내용 변화에 반응 | 명시적으로 선언한 행·열·카드에 적용. 픽셀 아트 전체에 추정 적용하지 않음 |

Group을 더 많이 만든다는 목표는 두지 않는다. 사용자가 고칠 수 있는 구조와 원본 화면의 재현을 함께 보존한다. 근거는 [공식 조사](RD-01-components/design.md#공식-근거)와 [계층 설계](RD-02-layer-structure/design.md)에 연결한다.

## 기존 경계와 재사용할 코드

- [입력 결과](../../tools/input_effect.py)의 `html_channel`, `project`, `freshness`는 중첩 CSS와 사진·글꼴의 의존성과 부재를 추적한다. RD-05는 이 결과의 표시를 추가하며 새 crawler를 만들지 않는다.
- [네이티브 읽기](../../figma-bridge/native_semantic_read.js)의 `readNativeSemantics`는 현재 전체 snapshot과 읽기 단위 이미지 테이블을 반환한다. RD-06은 이를 대체하는 별도 reader를 만들지 않는다.
- [그래프 동기화](../../tools/graph_sync.py)의 `build_plan`, `verify_readback`, `import_values`는 pairing과 전체 근거를 검사한다. RD-04는 필드 선택 때문에 이 검사를 생략하지 않는다.
- [제어 journal](../../tools/figma_control.py)의 `enqueue`, `poll`, `result`, `recovery_read`는 요청·claim·불확실성·복구를 저장한다. RD-08은 기존 queue와 상태 파일을 확장한다.
- [workspace 발행](../../tools/figma_workspace.py)의 `publish`, `trusted_sources`는 task bundle과 runtime 소스를 묶고 해시를 검사한다. RD-07의 모듈 분리는 이 출처 검사를 보존한다.

## 완료로 간주하지 않는 범위

이 계획은 기존 61개 회귀 사례를 완료로 바꾸지 않는다. 실기기, 데스크톱 원본 첨부 UI, 실제 브라우저 200% 확대, 독립적인 Figma 클라우드 저장, 글꼴 바이너리 동일성은 기존 기록의 미검증 범위다. 새 기능을 구현할 때 필요한 실제 브라우저·Figma 관찰은 해당 작업의 소유자가 별도로 남긴다.
