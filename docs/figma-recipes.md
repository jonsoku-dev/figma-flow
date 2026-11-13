# Figma Design Plugin API 예제

Figma Flow bridge에 없는 공개 API를 독립 개발 플러그인으로 검토하고 실행할 때 사용하는 소스 예제다. 카탈로그는 [`manifest.json`](../library/figma-recipes/manifest.json)에 있다. 이 저장소가 작성한 예제이며, Figma가 배포한 공식 샘플은 아니다. 공식 `plugin-typings` 1.142.0 선언과 TypeScript 5.9.3의 strict 검사로 각각 컴파일했다. 선언의 출처·커밋·해시는 [`source.json`](../library/figma-api/source.json)에 고정되어 있다.

| Recipe ID | `--editor` | 생성하거나 반환하는 결과 |
| --- | --- | --- |
| `design-shapes` | `figma` | 현재 페이지의 새 프레임에 union, subtract, intersect, exclude 결과와 alpha mask 그룹 |
| `design-grid` | `figma` | 현재 페이지에 새 2행 × 2열 auto layout `GRID` 프레임 |
| `design-motion` | `figma` | 현재 페이지의 새 section에 두 프레임과 클릭 이동·복귀 Smart Animate 반응 |
| `design-component-properties` | `figma` | 새 프레임에 실제 BOOLEAN·INSTANCE_SWAP 속성과 기본·교체·숨김 인스턴스, getter 검증 결과 |

Design 예제는 현재 페이지에서 실행한다. 글자·도형·컴포넌트는 작업이 소유한 컨테이너에 생성한다.

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


작은손 파일의 기존 컴포넌트 페이지에서 등록된 Figma Flow 개발 플러그인으로 네 Design 예제를 실행했다. 레이어 목록에서 GRID의 셀 네 개, 네 Boolean 결과와 타원 마스크를 확인했다. 컴포넌트 예제는 실제 속성 및 참조 검사에서 PASS를 표시했다. 모션 예제를 프레젠테이션에서 열고 양쪽 점을 클릭해 도착 프레임에서 시작 프레임으로 복귀하고 다시 도착하는 것을 확인했다. 모션의 프레임별 시간은 측정하지 않았다.

## 네이티브 속성 예제와 정적 번들

`design-component-properties`의 button에는 실제 `ShowLabel`·`ShowSymbol` BOOLEAN과 `Symbol` INSTANCE_SWAP 속성이 생긴다. circle/square symbol은 실제 로컬 컴포넌트이며 도형과 텍스트가 달라 교체 결과를 눈으로 구별할 수 있다. 기본 인스턴스, label 숨김 + square 교체 인스턴스, symbol 숨김 인스턴스를 캡션과 함께 만든다. production `applyDeclaredInstanceProperties`가 실제 getter를 검사하며, 추가로 속성 타입·preferred component key·main 기본값 보존을 검사한다. 통과하면 프레임에 PASS 문구와 `componentPropertiesRecipeResult` pluginData를 남긴다. 이는 해당 실행의 기술 검사이며 미적 승인이 아니다.

`component-properties.helpers.js`는 `figma-bridge/code.js`에서 `metadata`, `info`, `bindOwnedLabelProperty`, `validateDeclaredComponentProperties`, `markComponentSlot`, `markImportedInstanceSlots`, `bindDeclaredComponentProperties`, `applyDeclaredInstanceProperties`를 그대로 추출한다. commercial `importDesign`을 호출하거나 그 guard를 바꾸지 않는다. visual master 구성은 이 예제의 최소 fixture이며 production 디자인 제작 전체를 인수한 결과는 아니다.

번들은 로컬에서 재생성한다. 컴파일러는 이미 설치한 신뢰하는 TypeScript 5.9.3을 지정한다.

```sh
python3 library/figma-recipes/build.py --typescript library/figma-api/node_modules/typescript/lib/tsc.js
```

`bundle.json`은 네 Design 소스와 컴파일된 JS, 공유 helper의 SHA256을 고정한다. helper를 바꾸면 production 원문 추출과 실제 fixture 컴파일을 다시 실행하고 결과를 검토한다. 정적 번들 생성은 Figma 문서에 접근하지 않는다. 전체 production 파일 해시는 출처 기록이며 일반 실행 차단 조건이 아니다. 추출한 각 함수의 해시와 helper 소스·번들을 각각 검증한다.

오류 정리 회귀 검사는 `node library/figma-recipes/test-rollback.cjs`로 실행한다. GRID 미지원, boolean API가 새 노드를 다른 부모로 옮긴 뒤 실패하는 경우, production BOOLEAN 미지원, nested instance 생성 후 부모 연결 실패를 주입해 기존 노드와 선택이 보존되는지 검사한다. 이 검사는 모의 API를 사용하며 네이티브 Figma 실행 검증과 구분한다.

## 카탈로그 계약

`schemaVersion`은 `1`이며 `recipes`의 각 항목은 고유한 `id`, 표시용 `name`, `editorType`, `mode`, 디렉터리 안의 TypeScript `entry`, `description`, 예제가 다루는 `api` 문자열 배열을 갖는다. `runtimeHelpers`는 필요한 예제에서만 정적 JavaScript companion 경로를 지정한다. `api`는 검색·설명을 위한 목록이며 실행 허용 목록이나 bridge operation 이름이 아니다. 새 예제는 사용자가 선택한 경우에만 생성기에 복사되며, 에디터·모드가 맞지 않으면 생성기가 거부한다.
