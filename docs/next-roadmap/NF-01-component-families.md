# NF-01 입력·선택·표 컴포넌트 계열

상태는 **PROPOSED**다. RD-01의 선언 축 보존과 TEXT 속성 연결을 확장하는 새 기능이다.

## 현재 첫 범위와 미구현 경로

RD-01의 5개 AC는 TEXT·독립 축·supported sizing·override 보존·미선언 생성 금지의 명시된 범위에서 통과했다. RD-01-REQ-04의 optional label/icon BOOLEAN·INSTANCE_SWAP 양성 생성은 아직 구현하지 않았다. 현재 `componentSwapTargets`는 배열 형태만 검사하고 반환값은 생성에 쓰지 않으며 producer schema에 optional icon property도 없다. R8 실제 두 set의 TEXT·각 12개 Visual 및 빈 description/link 관찰은 이 제한된 지원 범위와 맞는다. NF-01은 그 양성 경로를 추가할 제안이며 PROPOSED 상태를 유지한다.

## 기능 계약

현재 실제 DOM의 입력·선택·표는 시각 원본과 편집 가능한 레이어로 전달할 수 있다. 일반 컨트롤은 이미 정확한 paired viewport profile 기준으로 재사용한다. `control-reuse.json`은 이전 스타일 선언 492개가 12개 계열의 desktop/mobile main 선언 24개로 공유됨을 기록한다. 이 수치는 authored 선언 비교이며 후속 R8 실제 getter는 main 24개·set 2개·instance 494개를 별도로 확인했다. 입력·선택·표의 optional property 계열을 이미 구현했다는 뜻은 아니다. 디자이너는 반복 필드의 레이블·오류·선택 상태를 계열 인스턴스에서 일관되게 바꾸고 싶다. 결과는 Field, Input, Checkbox, Radio, TableRow, TableCell의 선언된 재사용 계열이다. 첫 납품은 이 여섯 계열의 작은 fixture와 실제 앱의 대표 폼·표 연결이다.

자동으로 모든 DOM을 컴포넌트화하지 않는다. Figma에서 인증·서버 검증·예약을 실행하지 않는다. 기존 레이어를 동의 없이 교체하거나 instance를 detach하지 않는다. 가변 열 수 표를 거대한 variant 조합으로 만들지 않는다.

## 현재 경로와 확장 위치

- `tools/design_system.py`의 `compile_design`, `attach_declared_axes`, `components_css`가 디자인 선언과 축을 처리한다.
- `figma-bridge/code.js`의 `addComponentProperty` 호출부는 TEXT 반환 key를 main·instance에 연결한다. 이번 목표는 BOOLEAN·INSTANCE_SWAP의 같은 수준 연결이다.
- `figma-bridge/semantic_components.js`의 `ensureSemanticComponents`는 의미 key·트리 호환성·정확한 variant 연결과 재실행을 검사한다. 이를 우회하는 변환기를 만들지 않는다.
- `apps/little-hands/design/source.py`의 `layout_for`는 측정된 surface·text·image를 만들고 `share_control_styles`는 기존 컨트롤 profile을 공유한다. signature는 desktop/mobile의 정확한 profile을 함께 비교하고 `maxWidth`만 제외한다. 기존 컨트롤 공유를 다시 구현하지 않고 입력·선택·표의 명시적 계열 매핑을 추가하며 원래 DOM 대응표를 보존한다.
- `tools/graph_sync.py`의 `commit_component_fields`, `component_node_edits`와 `figma-bridge/graph_token_sync.js`의 선택/CAS 경계를 재사용한다.

## 데이터와 인터페이스 설계

제안 입력은 기존 디자인 선언의 선택적 `componentFamilies`다. 예시는 저장 형식을 확정하기 위한 제안이며 현재 지원 문법이 아니다.

```json
{"componentFamilies":[{"id":"field","version":1,"axes":{"state":["default","error","disabled"]},"properties":[{"id":"label","type":"TEXT","targetKey":"field-label"},{"id":"showHelp","type":"BOOLEAN","targetKey":"field-help"},{"id":"control","type":"INSTANCE_SWAP","targetKey":"field-control","allowedFamilyIds":["input","checkbox","radio"]}]}]}
```

배열 순서나 표시 이름 대신 안정된 id와 semantic key를 사용한다. 실제 `addComponentProperty` 반환 key는 main별 매핑에 기록한다. 중복 표시 이름은 반환 key로 구분한다. `property id → 실제 key → target semantic key` 대응을 readback으로 확인한다. Figma는 TEXT·BOOLEAN·INSTANCE_SWAP 속성 key에 고유 suffix를 붙이며 전체 key 사용을 요구한다. [공식 속성 정의](https://developers.figma.com/docs/plugins/api/properties/ComponentPropertiesMixin-componentpropertydefinitions/)를 따른다.

TEXT는 characters, BOOLEAN은 선언한 대상 visibility, INSTANCE_SWAP은 선언한 중첩 instance에 연결한다. swap 대상은 현재 파일에서 해석된 정확한 Component ID로 제한한다. 라이브러리 자동 import나 새 권한은 추가하지 않는다. 생성과 값 변경에는 [공식 컴포넌트 속성 절차](https://developers.figma.com/docs/plugins/working-with-component-properties/)를 적용한다. 선언하지 않은 variant 조합을 보간하지 않는다.

Field는 레이블·컨트롤·도움말의 세로 Auto Layout이다. Checkbox·Radio는 indicator·레이블의 가로 묶음이다. Table은 행/셀 계열을 조합하며 데이터 자체는 TEXT 값이다. 대표 상태는 Input default/focus/error/disabled, Checkbox unchecked/checked/disabled, Radio unselected/selected/disabled, TableRow default/selected다. focus는 시각 상태이며 실제 키보드 포커스 실행과 구분한다. 한 계열의 축 개수는 fixture에 명시하고 미선언 조합은 거절한다.

## 화면·실패·접근성 계약

미리보기는 계열 이름, 생성되는 main/instance 수, 교체 대상, 보존할 override를 보여준다. 상태는 `unmapped → mapped → ready → applied`, 충돌은 `conflict`다. unsupported input은 `unsupported`로 남기며 screenshot fallback으로 성공 처리하지 않는다. 실제 key 충돌, 누락 대상, 타입 불일치, 부분 변환은 쓰기 전에 중단하고 영향 semantic key를 표시한다.

레이블 연결과 오류 문구·required·disabled 의미를 원본 DOM 대응에 남긴다. 웹은 native input/label, fieldset/legend, table caption·th·scope를 보존한다. Figma의 시각 레이블을 웹 접근성 검증 결과로 표시하지 않는다. 비밀번호·토큰·개인 입력값은 fixture와 공유 property 기본값에 넣지 않는다. 샘플 데이터만 사용한다.

## 호환성·마이그레이션·복구

선택 선언이 없으면 기존 출력과 ID가 유지되어야 한다. 최초 전환은 선택한 대상에 한정하며 before ID·main·override·배치와 graph digest를 보존한다. 선언 버전이 다르거나 기존 사용자 구조와 충돌하면 자동 재생성하지 않는다. 실패한 변환을 재시도하기 전에 현재 getter로 부분 상태를 확인한다. 복구는 exact before 범위만 다루고 다른 instance를 제거하지 않는다.

## 작은 작업과 한 writer 경계

1. `tools/design_system.py`, 새 `tests/fixtures/nf01/`, 새 `tests/test_component_families.py` 소유자가 선언 검증과 invalid fixture를 만든다.
2. `figma-bridge/code.js`, `figma-bridge/semantic_components.js`, 새 `tests/nf01_component_properties.cjs` 소유자가 native property 연결과 재실행을 구현한다. 1번 결과가 확정된 뒤 시작한다.
3. `tools/graph_sync.py`, `figma-bridge/graph_token_sync.js`, 관련 기존 선택 검사 파일 소유자가 BOOLEAN·swap 값의 선택 및 CAS를 연결한다. 기존 독립 검사 기준은 바꾸지 않는다.
4. `apps/little-hands/design/source.py`, `apps/little-hands/design/test_source.py` 소유자가 대표 폼·표만 명시 매핑한다. 앱 업무 코드·DB는 소유하지 않는다.
5. 통합 담당자가 실제 Figma에서 레이블·오류 표시·선택·swap 편집 후 같은 파일/페이지의 full getter와 웹 대응을 비교한다.

## 인수와 검증

기존 회귀 명령은 저장소 루트에서 실행한다.

```sh
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_rd04_component_fields.py'
node --test tests/test_semantic_component_reuse.cjs tests/test_graph_token_sync.cjs
```

새 검사 제안은 `python3 -B -m unittest discover -s tests -p 'test_component_families.py'`와 `node --test tests/nf01_component_properties.cjs`다. 반환 suffix가 다른 TEXT/BOOLEAN/swap, 중복 표시 이름, swap 허용 범위 위반, disabled, 재실행 동일 ID, 사용자 override 보존, 일부 실패 후 재시도를 다룬다. 실제 Figma에서는 여섯 계열 각각 main/instance 연결과 프로퍼티 getter를 확인한다. 필드 하나와 표 한 행을 직접 수정해 선택한 값만 graph와 웹으로 돌아오는지 검증한다. 실제 브라우저에서 키보드 선택·레이블·오류 읽기와 모바일 표의 가로 접근을 확인한다.

## Cursor 구현·테스트 프롬프트

```text
이 문서 NF-01만 구현하라. 현재 AGENTS.md와 skills/patch-knowledge/SKILL.md, 기존 RD-01/RD-04 계약 및 현재 dirty 상태를 먼저 읽어라. 새 기능은 명시적 Field/Input/Checkbox/Radio/TableRow/TableCell 계열과 TEXT/BOOLEAN/INSTANCE_SWAP 연결이다. 문서의 componentFamilies는 제안 형식이므로 실제 schema 소유 경로와 호환성을 확인한 후 최소 변경으로 확정하라. 기존 compile_design/ensureSemanticComponents/선택 CAS와 share_control_styles의 정확한 paired viewport profile 공유를 재사용하라. 이미 끝난 492개 스타일 선언→24개 main 선언 공유를 후속 기능으로 재구현하지 말라. 쓰기 소유 범위는 이 문서의 작업 1~4 파일과 필요한 CHANGELOG/Wiki 기록이며 각 파일은 한 writer가 순차 수정한다. 현재 다른 작업은 보존하라. 업무 앱 기능 추가, detach, 무선언 variant, 라이브러리 자동 import, 게시·커밋은 금지한다. 범위 밖 파일이 필수면 필요한 계약과 이유를 보고하고 그 수정은 멈춰라. 기존 명령과 새 독립 회귀 검사를 실행하라. 승인된 실제 Figma/브라우저를 사용할 수 없으면 준비한 번들과 정확한 미검증 조건을 보고하라. 반환은 변경 파일, 선언/호환 결정, 명령별 결과, 실제 관측 근거, 남은 위험이다. fixture 성공을 native 인수로 쓰지 말라.
```
