# Public Plugin API로 독립 개발 플러그인 만들기

Figma Flow 어댑터에 없는 공개 API는 독립적인 개발 플러그인의 검토 가능한 TypeScript 소스로 작성한다. 이 도구는 프로젝트를 생성하고 로컬 컴파일만 수행한다. Figma Flow에 임의 JavaScript 실행기나 원격 코드 실행 경로를 추가하지 않는다.

```sh
python3 tools/figma_sdk_project.py init my-sdk-plugin --editor figma
```

목적지는 **아직 존재하지 않는 새 폴더**여야 하고 부모 폴더는 존재해야 한다. 기존 Figma Flow 등록 작업 공간은 대상이 아니다. 심볼릭 링크와 `..` 경로도 거부한다. macOS의 `/tmp` 같은 시스템 링크 경로는 실제 경로(`/private/tmp`)를 사용한다.

`--editor`는 `figma`, `figjam`, `slides`, `buzz`, `dev` 중 정확히 하나를 지정한다. 앞의 네 에디터는 `default` 모드, `dev`는 `codegen` 모드를 생성한다. 필요하면 `--mode default` 또는 `--mode codegen`을 명시할 수 있으며 호환되지 않는 조합은 거부한다. `dev`에는 codegen capability와 JSON 언어를 선언한다. 다른 모드와 권한은 프로젝트 작성자가 공식 문서를 확인해 직접 설계한다. 파트너·비공개·proposed API에 대한 접근을 부여하지 않는다.

기본 예제는 현재 페이지의 선택 노드 이름·타입·ID를 플러그인 종료 메시지로 표시한다. Dev Mode 예제는 요청받은 노드의 이름·타입·ID를 JSON 코드 생성 결과로 반환한다. 둘 다 문서를 변경하지 않는다. 작성한 소스는 이후 문서 변경 API도 호출할 수 있으므로 실행 전에 실제 소스를 검토한다. TypeScript는 읽기 전용 보안 경계가 아니다.

공식 API 타입으로 검사한 예제를 선택하려면 레시피 카탈로그의 ID를 사용한다. 레시피의 editor/mode와 선택한 editor/mode가 일치해야 한다. 예제에 문서 변경이 포함될 수 있으므로 파일과 레시피 설명을 확인한다.

```sh
python3 tools/figma_sdk_project.py init my-shapes-plugin --editor figma --recipe design-shapes
```

## 등록된 Figma Flow에서 Design 예제 실행

Design의 도형·마스크, Auto layout grid, Smart Animate, 컴포넌트 속성·인스턴스 교체 예제는 별도 ID 없이 등록된 Figma Flow 플러그인의 메뉴에서 실행할 수 있다. 기존 작업 공간을 갱신한 뒤 Figma 데스크톱에서 같은 개발 플러그인을 다시 연다.

```sh
python3 tools/figma_workspace.py refresh --workspace WORKSPACE
```

개발 플러그인의 `Figma Flow → Examples · add to current page`에서 예제를 선택한다. 확인 창의 `Add example to current page`를 직접 눌러야 현재 Design 페이지에 이름 붙인 새 프레임·섹션을 만든다. `Cancel`은 문서를 바꾸지 않는다. 기존 페이지·노드를 수정하지 않지만 현재 페이지를 유지하며 새 컨테이너로 선택이 바뀐다. UI는 준비된 Codex 작업과 분리되어 있으며 이 실행에서 채팅·로컬 제어 서비스를 시작하지 않는다. 메뉴가 갱신되지 않으면 같은 `manifest.json`의 개발 플러그인 등록을 다시 불러온다. 새 ID나 다른 manifest로 바꾸지 않는다.

메뉴 명령은 `flow-recipe:design-shapes`, `flow-recipe:design-grid`, `flow-recipe:design-motion`, `flow-recipe:design-component-properties`로 고정한다. 작성 가능한 명령 문자열이나 JavaScript를 받아 실행하는 브리지가 아니다. 배포된 네 예제의 소스·컴파일 결과 해시를 검사하고 Design/default 문맥을 확인한다. 기존 manifest의 editor·네트워크·권한 범위를 늘리지 않는다. FigJam·Slides·Dev Mode 예제는 아래의 독립 SDK 프로젝트를 사용한다. 컴파일 검사와 실제 Figma API·화면 결과 인수는 별개다.

## 실제 ID와 Figma 가져오기

Figma에서 발급받은 개발 플러그인 ID가 있으면 `--plugin-id`로 전달한다. 발급 여부·소유권은 이 로컬 도구가 인증하지 않는다. ID를 생략하면 ID가 없는 `manifest.template.json`만 생성한다. 가짜 ID와 가져오기 가능한 manifest를 만들지 않는다.

1. Figma의 새 개발 플러그인 생성 기능에서 **새로운** ID를 발급받는다.
2. 해당 ID를 템플릿의 `id`에 넣고 `manifest.json`으로 저장한다. 기존 Figma Flow manifest나 등록 작업 공간을 덮어쓰지 않는다.
3. 아래 설치·검사·빌드를 수행하고 해당 에디터의 개발 플러그인 메뉴에서 새 `manifest.json`을 가져온다. Dev Mode에서는 코드 생성 위치에서 실행한다.
4. 실제 결과·문서 변경 여부·에디터별 API 지원은 Figma에서 따로 검증한다. 생성 및 컴파일 성공은 실제 인수가 아니다.

ID, 에디터, capability와 네트워크 선언은 [공식 manifest 문서](https://developers.figma.com/docs/plugins/manifest/)를 따른다. 기본 네트워크는 `allowedDomains: ["none"]`이며 추가 permissions, 원격 코드 가져오기, 자동 실행·게시·계정 변경은 생성하지 않는다. 필요한 네트워크와 권한은 작성자가 목적에 맞게 manifest와 소스를 검토해 직접 변경한다.

## 설치와 오프라인 검사·빌드

공개 API 선언은 API inventory와 동일한 `library/figma-api/source.json` 버전·커밋·SHA256 및 라이선스를 `vendor/`에 복사한다. TypeScript는 `5.9.3`으로 고정한다. `src/code.ts`가 실행 소스이며, 별도 번들러나 런타임 의존성은 없다.

생성한 프로젝트 폴더에서 실행한다. 첫 설치에는 npm 레지스트리 연결 또는 미리 채운 npm 캐시가 필요하다.

```sh
npm install --ignore-scripts --no-audit --no-fund
npm run check
npm run build
```

생성된 `package-lock.json`을 보존한다. 캐시를 준비한 다른 설치에서는 `npm ci --offline --ignore-scripts --no-audit --no-fund`를 사용할 수 있다. 설치 이후 검사와 빌드는 네트워크를 사용하지 않는다. 출력은 `dist/code.js`이다. 컴포넌트 속성 예제는 실제 제품에서 추출한 로컬 JavaScript helper를 함께 복사하고 TypeScript의 `allowJs`와 `outFile`로 합친다. 호출 소스의 타입을 검사하며 helper 본문은 JavaScript 구문 검사·출처 해시 검사 대상이다. 임의 원격 코드를 가져오지 않는다.

저장소에서도 같은 진입점으로 선언 해시와 컴파일러 버전을 검사한 뒤 컴파일할 수 있다.

```sh
python3 tools/figma_sdk_project.py check my-sdk-plugin
python3 tools/figma_sdk_project.py build my-sdk-plugin
```

이미 설치된 신뢰하는 TypeScript 5.9.3을 오프라인에서 재사용하려면 `--typescript /actual/path/to/typescript/lib/tsc.js`를 지정한다. 이 경로는 호출자가 선택한 **로컬 컴파일러 코드**이며 도구가 다운로드하거나 Figma에서 실행하지 않는다. 프로젝트 자체의 `npm run`은 작성자가 수정한 npm scripts와 tsconfig를 사용한다. 저장소 진입점은 고정된 입력·컴파일 옵션·출력 경로를 사용한다. ES 모듈 import가 필요한 확장은 작성자가 별도의 번들링을 설계해야 한다.

선언의 타입 검사 성공은 API의 에디터·계정·권한·런타임 지원을 보장하지 않는다. [공식 API 문서](https://developers.figma.com/docs/plugins/api/)와 inventory의 개별 소스 링크를 확인한다.

## 번들 유지와 CI

일반 작업 공간 갱신은 승인된 예제 소스·helper·컴파일 결과의 고정 해시를 검사한다. importer 전체 파일이 바뀌었다는 이유로 기존 예제 실행이나 작업 공간 갱신을 막지 않는다. 실제로 공유하는 production 함수의 변경은 별도 CI 검사에서 확인한다.

```sh
python3 tools/workspace_recipes.py verify-helpers
FIGMA_SDK_TEST_TYPESCRIPT=/trusted/typescript/lib/tsc.js python3 -m unittest discover -s tests -p test_workspace_recipes.py
```

함수 의존성이 변경되면 검토 후 `python3 library/figma-recipes/build.py --typescript /trusted/typescript/lib/tsc.js`로 번들을 다시 생성한다. `verify-helpers`는 해당 함수 본문만 비교하고, 위 테스트는 실제 컴파일 결과와 승인된 번들의 바이트 일치도 검사한다. inventory용 로컬 `npm install`의 `node_modules`, 생성된 lockfile과 도구 캐시는 native 런타임 소스 정체성에 포함하지 않는다.
