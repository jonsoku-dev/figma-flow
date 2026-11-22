# Figma Design Plugin API 예제

이 문서는 Figma Plugin API 예제의 소스·검증 범위를 설명한다. 예제는 Figma 공식 샘플이 아니다. 현재 `design-grid` 예제는 고정 workspace의 `native-edit` 작업으로 Codex에서 준비·실행한다. 나머지 소스를 별도 SDK 프로젝트로 빌드할 수 있지만, 해당 플러그인은 Figma Flow 패널과 별개다. 카탈로그는 [`manifest.json`](../library/figma-recipes/manifest.json)에 있다. 각 recipe의 시각 값과 component payload는 [`design-examples.graph.json`](../library/figma-recipes/design-examples.graph.json)이 정본이다. 공식 `plugin-typings` 1.142.0 선언과 TypeScript 5.9.3의 strict 검사로 각각 컴파일했다. 선언의 출처·커밋·해시는 [`source.json`](../library/figma-api/source.json)에 고정되어 있다.

| Recipe ID | `--editor` | 생성하거나 반환하는 결과 |
| --- | --- | --- |
| `design-shapes` | `figma` | 현재 페이지의 새 프레임에 네 Boolean 연산과 alpha mask 그룹 |
| `design-grid` | `figma` | 현재 페이지에 authored auto-layout `GRID` 프레임 |
| `design-motion` | `figma` | 현재 페이지에 Smart Animate 클릭 이동·복귀 prototype |
| `design-component-properties` | `figma` | 새 프레임에 실제 BOOLEAN·INSTANCE_SWAP 속성과 기본·교체·숨김 인스턴스, getter 검증 결과 |
| `design-type-review` | `figma` | 기존 Design lab 페이지에 재사용 가능한 타이포그래피 specimen component와 실제 텍스트 스타일 readback을 추가 |

`manifest.json`의 각 recipe는 `designGraph`로 시각 값 그래프를 가리킨다. 그래프의 `recipe:<id>` 노드는 `owns-visual-values` edge로 해당 `visual:<id>` 노드를 소유한다. `design-component-properties`는 `owns-design-payload` edge로 component payload도 소유한다. 새 배치·색상·타입 값을 만들거나 바꿀 때는 그래프를 수정한다. TypeScript 예제와 bundle은 생성 결과다.

`build.py`는 그래프를 검증해 `RECIPE_VISUALS` TypeScript projection, component-properties payload와 bundle hash를 다시 만든다. `bundle.json`은 graph source SHA-256, 전체 projection SHA-256, payload source와 SHA-256을 기록한다. 각 menu recipe는 source, compiled JavaScript와 recipe별 visual projection의 SHA-256을 기록한다. Scoped SDK recipe에는 API review graph, graph projection, visual projection, 선택된 member hash와 compiled output을 별도로 기록한다. `tests/test_library_release_witness.py`는 이 hash, recipe별 생성값과 rollback 동작을 검증한다. 정적 빌드는 실제 Figma 실행 결과를 입증하지 않는다.

`figma_sdk_project.py init --recipe ...`은 선택된 recipe의 그래프를 `vendor/design-examples.graph.json`에 복사하고 선택된 값만 `src/recipe-visuals.ts`로 생성한다. `sdk-project.json`은 두 파일의 hashes를 고정하며 `check`와 `build`에서 다시 대조한다. 컴파일 결과만 편집해도 정본 값은 바뀌지 않는다.

Design 예제는 현재 페이지에서 실행한다. 글자·도형·컴포넌트는 작업이 소유한 컨테이너에 생성한다. `design-grid`는 Codex가 등록된 Figma Flow workspace에서 준비하고 실행한다. `design-type-review`는 별도 Design lab graph로 API 범위를 좁힌 뒤 SDK 프로젝트에서 실행한다. 이 lab graph는 시각 값 graph와 역할이 다르다. 후보값과 typography layout은 시각 값 graph가 계속 소유한다.

## Run design-grid through Figma Flow

Codex에서 현재 파일·페이지와 선택을 읽고 사용자의 요청과 적용 범위를 확인한다. 패널은 문맥과 상태만 표시한다. 대상 파일에서 Figma Flow를 실행 세션마다 한 번 열고, 같은 컴퓨터에서 control `serve`가 실행 중인지 확인한다.

```sh
python3 -B tools/figma_control.py context --workspace WORKSPACE
python3 -B tools/figma_workspace.py prepare --workspace WORKSPACE \\
  --key design-grid --title 'Grid' --kind native-edit -- \\
  --recipe design-grid --file-key FILE --page-id PAGE
python3 -B tools/figma_workspace.py list --workspace WORKSPACE
python3 -B tools/figma_control.py run --workspace WORKSPACE --key design-grid \\
  --operation apply --file-key FILE --page-id PAGE \\
  --expected-revision CURRENT_REVISION --timeout 120
```

`FILE`, `PAGE`와 revision은 현재 `context`와 `list` 출력에서 가져온다. Codex는 실제 `readback`을 확인해 적용 결과를 보고한다. 결과가 불확실하면 적용을 재시도하기 전에 현재 Figma 값을 읽는다. 이 recipe는 기존 페이지에 시각 값 graph가 정의한 auto-layout `GRID` 프레임을 추가한다.

## 검토 가능한 프로젝트 생성

저장소 루트에서 아직 존재하지 않는 목적지를 지정한다. 이 명령은 로컬 소스 프로젝트만 만들며 Figma에서 실행하지 않는다.

```sh
mkdir -p .figma-flow/recipe-projects
python3 tools/figma_sdk_project.py init .figma-flow/recipe-projects/shapes --editor figma --recipe design-shapes
python3 tools/figma_sdk_project.py init .figma-flow/recipe-projects/grid --editor figma --recipe design-grid
python3 tools/figma_sdk_project.py init .figma-flow/recipe-projects/motion --editor figma --recipe design-motion
python3 tools/figma_sdk_project.py init .figma-flow/recipe-projects/properties --editor figma --recipe design-component-properties
```

필요한 예제 하나만 생성해도 된다. 생성기는 선택한 `.ts`를 `src/code.ts`로 복사한다. `design-component-properties`는 `runtimeHelpers`에 지정한 정적 JavaScript도 복사하고 TypeScript `allowJs` + `outFile`로 함께 빌드한다. 이 helper에는 실제 `compile_design` 결과와 production 속성 함수의 원문이 들어 있다. 이후 원본 예제를 수정해도 이미 생성한 프로젝트에는 반영되지 않는다. 카탈로그를 읽거나 검색하는 행위만으로 산출물·Figma 노드가 생성되지 않는다.

생성한 프로젝트에서 검사·빌드한다.

```sh
cd .figma-flow/recipe-projects/shapes
npm install --ignore-scripts --no-audit --no-fund
npm run check
npm run build
```

Figma에서 발급한 새 플러그인 ID로 manifest를 완성하고 해당 에디터의 개발 플러그인으로 가져오는 절차는 [SDK 프로젝트 안내](figma-sdk-project.md)를 따른다. Dev Mode 예제는 코드 생성 위치에서 실행하며 `generate` 이벤트를 기다리므로 즉시 `closePlugin`을 호출하지 않는다.

## 모션과 실행 검증의 범위

`design-motion`은 `setReactionsAsync`의 `SMART_ANIMATE`를 사용하는 Design 프로토타입 예제다. 실행 후 선택된 Start 프레임을 Present에서 열고 점을 클릭하면 이동하며, 도착한 점을 클릭하면 복귀한다. 이름을 유지한 clone 자식이 두 프레임 사이의 매칭 대상이다. 타임라인·키프레임·Motion 에디터 제작 예제가 아니다.


**Historical execution record:** an earlier Figma Flow build ran these four Design recipes in a small business file. The layer list showed the GRID cells, Boolean results and ellipse mask. The component recipe passed its property and reference checks. Figma Present played the motion example in both directions. Frame timing was not measured. This record does not describe the current passive viewer.

## 네이티브 속성 예제와 정적 번들

`design-component-properties`의 button에는 실제 `ShowLabel`·`ShowSymbol` BOOLEAN과 `Symbol` INSTANCE_SWAP 속성이 생긴다. circle/square symbol은 실제 로컬 컴포넌트이며 도형과 텍스트가 달라 교체 결과를 눈으로 구별할 수 있다. 기본 인스턴스, label 숨김 + square 교체 인스턴스, symbol 숨김 인스턴스를 캡션과 함께 만든다. production `applyDeclaredInstanceProperties`가 실제 getter를 검사하며, 추가로 속성 타입·preferred component key·main 기본값 보존을 검사한다. 통과하면 프레임에 PASS 문구와 `componentPropertiesRecipeResult` pluginData를 남긴다. 이는 해당 실행의 기술 검사이며 미적 승인이 아니다.

`component-properties.helpers.js`는 `figma-bridge/code.js`에서 `metadata`, `info`, `bindOwnedLabelProperty`, `validateDeclaredComponentProperties`, `markComponentSlot`, `markImportedInstanceSlots`, `bindDeclaredComponentProperties`, `applyDeclaredInstanceProperties`를 그대로 추출한다. commercial `importDesign`을 호출하거나 그 guard를 바꾸지 않는다. visual master 구성은 이 예제의 최소 fixture이며 production 디자인 제작 전체를 인수한 결과는 아니다.

번들은 로컬에서 재생성한다. 컴파일러는 이미 설치한 신뢰하는 TypeScript 5.9.3을 지정한다.

```sh
python3 library/figma-recipes/build.py --typescript library/figma-api/node_modules/typescript/lib/tsc.js
```

`bundle.json`은 Design recipe 소스, 컴파일된 JS, 공유 helper와 visual graph projection의 SHA-256을 고정한다. helper를 바꾸면 production 원문 추출과 실제 fixture 컴파일을 다시 실행하고 결과를 검토한다. 정적 번들 생성은 Figma 문서에 접근하지 않는다. 전체 production 파일 해시는 출처 기록이며 일반 실행 차단 조건이 아니다. 추출한 각 함수의 해시와 helper 소스·번들을 각각 검증한다.

오류 정리 회귀 검사는 `node library/figma-recipes/test-rollback.cjs`로 실행한다. GRID 미지원, boolean API가 새 노드를 다른 부모로 옮긴 뒤 실패하는 경우, production BOOLEAN 미지원, nested instance 생성 후 부모 연결 실패를 주입해 기존 노드와 선택이 보존되는지 검사한다. 이 검사는 모의 API를 사용하며 네이티브 Figma 실행 검증과 구분한다.

## 카탈로그 계약

`schemaVersion`은 `1`이며 `recipes`의 각 항목은 고유한 `id`, 표시용 `name`, `editorType`, `mode`, 디렉터리 안의 TypeScript `entry`, `description`, 예제가 다루는 `api` 문자열 배열을 갖는다. `runtimeHelpers`는 필요한 예제에서만 정적 JavaScript companion 경로를 지정한다. `api`는 검색·설명을 위한 목록이며 실행 허용 목록이나 bridge operation 이름이 아니다. 새 예제는 사용자가 선택한 경우에만 생성기에 복사되며, 에디터·모드가 맞지 않으면 생성기가 거부한다.
