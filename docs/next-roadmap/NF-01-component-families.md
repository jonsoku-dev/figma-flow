# NF-01 입력·선택·표 컴포넌트 계열

상태는 **PROPOSED**다(실제 Figma·브라우저 런타임 인수 전 정본 그래프 상태 유지). RD-01의 선언 축 보존과 TEXT 속성 연결을 여섯 개 정본 계열과 `TEXT`·`BOOLEAN`·`INSTANCE_SWAP` 양방향 검증으로 확장한다.

## 기능 계약

현재 실제 DOM의 입력·선택·표는 시각 원본과 편집 가능한 레이어로 전달할 수 있다. 일반 컨트롤은 이미 정확한 paired viewport profile 기준으로 재사용한다. `control-reuse.json`은 이전 스타일 선언 492개가 12개 계열의 desktop/mobile main 선언 24개로 공유됨을 기록하며 후속 R8 실제 getter는 main 24개·set 2개·instance 494개를 별도로 확인했다. 디자이너는 반복 필드의 레이블·도움말 표시·선택 상태·내장 컨트롤 교체를 계열 인스턴스에서 일관되게 바꾸고, 재적용 후에도 개별 override와 수동 배치를 유지하고 싶다. 결과는 `field`, `input`, `checkbox`, `radio`, `table-row`, `table-cell`(Field, Input, Checkbox, Radio, TableRow, TableCell)의 명시적 재사용 계열과 대표 앱 폼·표 및 독립 예제(`examples/owned-component-families/`) 연결이다.

자동으로 모든 DOM을 컴포넌트화하지 않는다. Figma에서 인증·서버 검증·예약을 실행하지 않는다. 기존 레이어를 동의 없이 교체하거나 instance를 detach하지 않는다. 가변 열 수 표를 거대한 variant 조합으로 만들지 않는다.

## 현재 경로와 확장 위치

- `tools/design_system.py`의 `compile_design`, `_compile_component_families`, `compile_graph_component_families`, `attach_declared_axes`, `components_css`, `render`, `render_svg`가 `componentFamilies` 선언·독립 축·미리보기 상태·`figma-flow-semantic-family-contract-v1` 산출물을 컴파일한다.
- `tools/figma_bridge.py`의 `validate_component_properties`, `compare_declared_component_properties`, `compare_import`가 `TEXT`·`BOOLEAN`·`INSTANCE_SWAP` 스키마 검증, 비밀값/외부 URL 차단, `#suffix` 반환 key 및 중복 표시 이름 readback 대조를 수행한다.
- `figma-bridge/code.js`의 `componentSwapTargets`, `validateDeclaredComponentProperties`, `bindDeclaredComponentProperties`, `applyDeclaredInstanceProperties`, `reapplyDeclaredComponents`, `verifyDeclaredComponentReadback`가 세 속성 타입 생성, 파일 내 허용 Component ID(`swap_targets`) 강제, 동일 owner 재적용 시 개별 override·수동 배치(`x`, `y`, `relativeTransform`) 보존, 부분 실패 시 신규 소유 노드 rollback을 처리한다.
- `figma-bridge/semantic_components.js`의 `ensureSemanticComponents`, `readSemanticComponentFamilies`와 `tools/native_edit.py component-families`가 현재 페이지 소유 workbench 안에서 의미 key·트리 호환성·variant 연결·재실행·실제 getter 읽기를 수행한다. 별도 복제 변환기를 만들지 않는다.
- `apps/little-hands/design/source.py`의 `share_control_styles`는 기존 paired viewport profile 공유를 그대로 유지하고, 입력·선택·표 대표 대상만 명시적 계열 매핑과 `dom_source` 대응표로 연결한다.
- `tools/graph_design_system.py`, `tools/graph_sync.py`의 `commit_component_fields`, `sync_selected_component_fields`, `native_property`와 `figma-bridge/graph_token_sync.js`의 `commitComponentFields`가 `BOOLEAN`(`visible`)·`INSTANCE_SWAP`(`allowed_swap_ids`)·`TEXT`(`characters`) 선택 적용과 CAS 경계를 검증한다.

## 데이터와 인터페이스 설계

디자인 선언(`design.json`) 및 정본 그래프(`graph.json`)는 선택적 `componentFamilies` 배열을 가진다. 선언이 없으면 기존 컴파일러 출력 키(`version`, `tokens`, `components`, `screens`)와 기존 ID가 그대로 유지된다.

```json
{
  "componentFamilies": [
    {
      "id": "field",
      "version": 1,
      "axes": {"state": ["default", "error", "disabled"]},
      "properties": [
        {"id": "label", "name": "Label", "type": "TEXT", "targetKey": "label", "default_value": "Participant name"},
        {"id": "helpText", "name": "Help", "type": "TEXT", "targetKey": "field-help", "default_value": "As shown on roster"},
        {"id": "showHelp", "name": "Show help", "type": "BOOLEAN", "targetKey": "field-help", "default_value": true},
        {"id": "control", "name": "Control", "type": "INSTANCE_SWAP", "targetKey": "field-control", "allowedFamilyIds": ["input", "checkbox", "radio"], "default_value": {"component": "input", "variant": "default"}}
      ]
    }
  ]
}
```

배열 순서나 표시 이름 대신 안정된 `property id`와 `targetKey`를 사용한다. `addComponentProperty`가 반환하는 실제 `#suffix` key는 main별 `declared_property_keys`(`{propId: actualKey}`)와 `declared_property_contracts`에 기록하며, `TableRow`의 복수 `"Cell"`처럼 중복 표시 이름도 반환 key로 정확히 구분한다. `property id → 실제 #suffix key → target semantic key` 대응을 readback으로 대조한다. [공식 속성 정의](https://developers.figma.com/docs/plugins/api/properties/ComponentPropertiesMixin-componentpropertydefinitions/)와 [공식 컴포넌트 속성 절차](https://developers.figma.com/docs/plugins/working-with-component-properties/)를 따른다.

- `TEXT`: `characters`에 연결한다(`targetKey: "label"`은 중복 `"문구"` 속성을 만들지 않고 선언된 `TEXT` 정의 하나에 직접 연결하며, 보조 텍스트 슬롯은 `text:<target>`에 연결).
- `BOOLEAN`: 선언한 대상(`label`, `slot:<target>`, `text:<target>`, `field-help`)의 `visible`에 연결한다.
- `INSTANCE_SWAP`: 선언한 중첩 instance(`slot:<target>`)의 `mainComponent`에 연결하며, 허용 범위(`allowedFamilyIds` → `swap_targets` / `preferredValues`)는 현재 파일 내에서 해석된 정확한 로컬 Component ID로 제한한다. 외부 라이브러리 자동 import나 추가 네트워크 권한은 허용하지 않는다.

`field`는 레이블·컨트롤·도움말의 세로(`VERTICAL`) Auto Layout이고, `checkbox`·`radio`·`table-row`는 가로(`HORIZONTAL`) 묶음이며, `table-row`는 `table-cell` 슬롯을 조합하고 행 데이터는 `TEXT` 값으로 전달한다. 대표 상태 축은 `input` `default/focus/error/disabled`, `checkbox` `unchecked/checked/disabled`, `radio` `unselected/selected/disabled`, `table-row` `default/selected`, `table-cell` `default/header`다(`focus`는 시각 상태이며 실제 브라우저 키보드 포커스 실행과 구분). 선언하지 않은 계열 ID·버전·variant 조합은 쓰기 전에 거절한다.

## 화면·실패·접근성 계약

미리보기(`component_families_preview`)는 계열 이름, 생성되는 main/instance 수, 허용 swap 대상, 보존할 override 키를 요약하며 `unmapped | mapped | ready | applied | conflict | unsupported` 상태를 사용한다. unsupported 입력은 screenshot fallback으로 성공 처리하지 않는다. 실제 key 충돌, 누락 대상, 타입 불일치, 허용 범위 밖 swap, stale digest는 네이티브 쓰기 전에 중단(**no mutation**)하고 영향 semantic key를 보고한다.

원본 DOM 대응(`dom_source`)은 허용된 접근성 메타데이터(`selector`, `tag`, `role`, `input_type`, `button_type`, `name`, `placeholder`, `label_for`, `help_id`, `aria_describedby`, `fieldset_legend`, `table_caption`, `th_scope`, `required`, `disabled`, `checked`, `readonly`)만 유지하며 외부 URL(`http://`, `https://`)과 비밀값 패턴(API 키·토큰·개인키)을 차단한다. 웹은 native `input`/`label`, `fieldset`/`legend`, `table` `caption`·`th`·`scope`를 보존하며, Figma 시각 레이블을 웹 접근성 통과 근거로 대체하지 않는다.

## 호환성·마이그레이션·복구 및 소스 핀 갱신

선언이 없으면 기존 출력과 ID가 유지된다. 동일 owner 재실행은 기존 set/main/instance ID와 사용자 개별 override(`TEXT`, `BOOLEAN`, `INSTANCE_SWAP`) 및 수동 배치(`x`, `y`, `relativeTransform`)를 보존하고 비소유 형제 레이어를 건드리지 않는다. 실행 중 일부 생성 단계가 실패하면 이번 실행에서 새로 만든 소유 노드만 제거(rollback)하고 기존 인스턴스와 override는 보존한다.

통합 시 `figma-bridge/code.js`, `figma-bridge/semantic_components.js`, `figma-bridge/graph_token_sync.js` 변경으로 정적 API 인벤토리 또는 레시피 헬퍼 핀이 바뀌면 최종 통합자가 단일 작업트리에서 아래 명령으로 갱신·검증한다(병렬 작업자 간 충돌 방지):

```sh
python3 -B tools/figma_api_inventory.py coverage --write-baseline --typescript /path/to/node_modules/typescript
python3 -B tools/figma_api_inventory.py coverage --check-baseline --typescript /path/to/node_modules/typescript
python3 -B library/figma-recipes/build.py --typescript /path/to/node_modules/typescript
python3 -B tools/workspace_recipes.py verify-helpers
```

## 실제 Figma·웹 재현 절차 (안전 실행 순서)

공식 Figma MCP나 Computer Use 없이, 등록된 로컬 workspace 플러그인과 CLI만으로 아래 순서대로 실행한다(`FILE_KEY`, `PAGE_ID`, `WORKSPACE`는 로컬 비공개 실행 인자로만 전달하고 저장소에 기록하지 않는다).

1. **오프라인 컴파일·미리보기·스키마 검증**
   ```sh
   python3 -B tools/design_system.py --input examples/owned-component-families/design.json --out /tmp/nf01-preview
   python3 -B tools/figma_bridge.py --input /tmp/nf01-preview/figma-import.json --draft-only --out /tmp/nf01-bridge-draft
   ```
   생산 화면 전체 import(`tools/figma_bridge.py --input ... --reviewed-sha256 ...`)의 인간 디자인 방향 검토 게이트는 우회하거나 변경하지 않는다. 현재 페이지 내 NF-01 계열 추가·검증은 아래 additive `native_edit.py component-families` 경로를 사용한다.
2. **대상 파일·현재 페이지 사전 discovery 캡처**
   ```sh
   python3 -B tools/figma_workspace.py prepare --workspace "$WORKSPACE" --key nf01-discover-before --title "NF-01 page discovery" --kind discover -- --file-key "$FILE_KEY" --page-id "$PAGE_ID"
   python3 -B tools/figma_workspace.py refresh --workspace "$WORKSPACE"
   ```
   플러그인 패널에서 읽기 전용 discovery를 실행해 현재 페이지 스냅샷(`before-readback.json`)을 저장한다.
3. **현재 페이지 소유 workbench 내 6개 계열 초기 생성 및 getter 확인**
   ```sh
   python3 -B tools/native_edit.py component-families --graph examples/owned-component-families/design.json --readback /tmp/nf01/before-readback.json --file-key "$FILE_KEY" --page-id "$PAGE_ID" --owner-key nf01.owned-families --out /tmp/nf01/plan-initial.json
   python3 -B tools/figma_workspace.py prepare --workspace "$WORKSPACE" --key nf01-apply-1 --title "NF-01 provision families" --kind edit -- --plan /tmp/nf01/plan-initial.json
   python3 -B tools/figma_workspace.py refresh --workspace "$WORKSPACE"
   ```
   실행 결과 readback에서 여섯 계열(`field`, `input`, `checkbox`, `radio`, `table-row`, `table-cell`)의 set/main/instance ID와 `#suffix` 반환 key(`TEXT`, `BOOLEAN`, `INSTANCE_SWAP`, 중복 `"Cell"` 포함)를 확인한다.
4. **단일 인스턴스 편집 → 동일 owner 반복 적용 → override·배치 보존 readback 검증**
   - Figma 캔버스에서 `field` 인스턴스 하나를 선택해 `TEXT`(레이블/도움말 문구), `BOOLEAN`(도움말 표시 토글), 중첩 `INSTANCE_SWAP`(`input` → `checkbox` 또는 `radio`), 그리고 인스턴스 `x`/`y` 좌표를 직접 편집하고, `table-row` 인스턴스 한 행의 셀 `TEXT`를 수정한다.
   - 2단계와 동일하게 최신 페이지 discovery(`edited-readback.json`)를 읽은 뒤 같은 `--owner-key`로 재적용 계획을 준비·실행한다:
     ```sh
     python3 -B tools/native_edit.py component-families --graph examples/owned-component-families/design.json --readback /tmp/nf01/edited-readback.json --file-key "$FILE_KEY" --page-id "$PAGE_ID" --owner-key nf01.owned-families --out /tmp/nf01/plan-reapply.json
     python3 -B tools/figma_workspace.py prepare --workspace "$WORKSPACE" --key nf01-apply-2 --title "NF-01 repeat apply preserve overrides" --kind edit -- --plan /tmp/nf01/plan-reapply.json
     python3 -B tools/figma_workspace.py refresh --workspace "$WORKSPACE"
     ```
   - 반환된 readback에서 main/instance ID 동일 재사용, 편집한 인스턴스의 `TEXT`·`BOOLEAN`·`INSTANCE_SWAP` 값과 수동 배치 좌표 유지, 비편집 인스턴스 및 비소유 형제 프레임 무변경을 확인한다.
5. **선택 필드 CAS 역반영(graph·웹) 및 브라우저 접근성 확인**
   - 편집한 필드 하나와 표 한 행에서 반영할 항목만 선택해 `commit_component_fields` / `sync_selected_component_fields`(또는 `tools/graph_sync.py`)로 CAS 검증 후 정본 `graph.json`과 생성 웹 모듈을 갱신하고, 선택하지 않은 필드가 보존되는지 확인한다.
   - 브라우저에서 `label`/`input`, `fieldset`/`legend`, `table` `caption`·`th`·`scope`, 키보드 이동·선택과 좁은 화면 표 가로 탐색을 확인한다.

## 작은 작업과 한 writer 경계

1. `tools/design_system.py`, `tools/figma_bridge.py`, `tests/fixtures/nf01/`, `tests/test_component_families.py` 소유자가 선언 컴파일·검증·미리보기와 readback 대조를 담당한다.
2. `figma-bridge/code.js`, `figma-bridge/semantic_components.js`, `tests/nf01_component_properties.cjs` 소유자가 네이티브 속성 생성·교체 허용 범위·반복 적용 보존·복구를 담당한다.
3. `tools/graph_design_system.py`, `tools/graph_sync.py`, `figma-bridge/graph_token_sync.js` 소유자가 `BOOLEAN`·`INSTANCE_SWAP`·`TEXT` 선택 적용 및 CAS 경계를 담당한다.
4. `apps/little-hands/design/*`, `examples/owned-component-families/*`, `tests/test_nf01_app_mapping.py` 소유자가 대표 폼·표 매핑과 독립 예제를 담당하며, `tools/native_edit.py`, `figma-bridge/native_provision.js`, `tools/figma_workspace.py` 소유자가 현재 페이지 실행 래퍼를 담당한다.
5. 통합 담당자가 단일 통합 트리에서 API/레시피 핀을 갱신하고 실제 Figma·브라우저 런타임 인수를 수행한다.

## 인수와 검증

기존 회귀 명령과 NF-01 독립 검증 명령은 저장소 루트에서 실행한다.

```sh
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_declared_component_properties.py'
python3 -B -m unittest discover -s tests -p 'test_component_families.py'
python3 -B -m unittest discover -s tests -p 'test_rd04_component_fields.py'
node --test tests/test_semantic_component_reuse.cjs tests/test_graph_token_sync.cjs tests/test_declared_component_properties.cjs tests/nf01_component_properties.cjs
```

반환 `#suffix`가 다른 `TEXT`/`BOOLEAN`/`INSTANCE_SWAP`, 중복 표시 이름(`"Cell"`), swap 허용 범위 위반, `disabled` 축, 재실행 동일 ID, 사용자 override 및 수동 배치 보존, stale/누락 대상 무변경 거절, 일부 실패 후 rollback 및 재시도, 선택 필드 CAS 역반영을 검증한다.

## Cursor 구현·테스트 프롬프트

```text
이 문서 NF-01만 구현하라. 현재 AGENTS.md와 skills/patch-knowledge/SKILL.md, 기존 RD-01/RD-04 계약 및 현재 dirty 상태를 먼저 읽어라. 새 기능은 명시적 Field/Input/Checkbox/Radio/TableRow/TableCell 계열과 TEXT/BOOLEAN/INSTANCE_SWAP 연결이다. 문서의 componentFamilies는 실제 schema 소유 경로와 호환성을 확인한 후 최소 변경으로 유지하라. 기존 compile_design/ensureSemanticComponents/선택 CAS와 share_control_styles의 정확한 paired viewport profile 공유를 재사용하라. 이미 끝난 492개 스타일 선언→24개 main 선언 공유를 후속 기능으로 재구현하지 말라. 쓰기 소유 범위는 이 문서의 작업 경계 파일과 필요한 패치 기록이며 각 파일은 한 writer가 수정한다. 현재 다른 작업은 보존하라. 업무 앱 기능 추가, detach, 미선언 variant, 라이브러리 자동 import, 게시·커밋은 금지한다. 범위 밖 파일이 필수면 필요한 계약과 이유를 보고하고 그 수정은 멈춰라. 기존 명령과 새 독립 회귀 검사를 실행하라. 승인된 실제 Figma/브라우저를 사용할 수 없으면 준비한 번들과 정확한 미검증 조건을 보고하라. 반환은 변경 파일, 선언/호환 결정, 명령별 결과, 실제 관측 근거, 남은 위험이다. fixture 성공을 native 인수로 쓰지 말라.
```
