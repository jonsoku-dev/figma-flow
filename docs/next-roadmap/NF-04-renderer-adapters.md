# NF-04 SSR 어댑터와 CSS 내보내기

상태는 **PROPOSED**다. app별 실제 관측 경로를 유지하면서 graph SSOT의 출력 대상을 확장한다.

## 기능 계약

현재 graph 값은 생성된 웹 모듈과 연결할 수 있다. Django 같은 서버 렌더링 프로젝트는 앱별 추출·변환 코드가 필요하다. 사용자는 graph의 token/component 값을 JavaScript 실행 없이 외부 CSS에서 쓰고, 실제 SSR 원본을 공통 관측 형식으로 연결하고 싶다.

첫 버전은 deterministic CSS 파일과 JSON manifest 출력, 그리고 명시적 Django 5.2 관측 adapter 하나다. 범용 HTML-to-Figma 자동 추정기, Django 업무 코드 생성기, 모든 프레임워크 지원, 런타임 플러그인 로더는 제외한다. 현재 CSP 문제가 있다는 진단은 이 문서의 근거가 아니다.

## 현재 경로와 확장 위치

`tools/graph_design_system.py`의 `resolve_design_system`은 CSS와 component projection을 만든다. `emit_web_module`·`update_graph_values`는 lock·graph digest·atomic write를 처리한다. `tools/graph_sync.py`의 `export_bundle`, `import_values`, `verify_web_proof`, `recover_projection`은 웹 모듈·pairing·복구를 연결한다. 기존 MJS 출력은 폐기하지 않는다.

`apps/little-hands/design/source.py`의 `load_captures`, `layout_for`, `build`와 `measure.js`, `dom-map.json`은 실제 측정으로 native layout을 만든다. `design/export.py`의 `Sanitizer`와 SSR GET 경로는 실제 HTML 보조 자료이며 geometry나 인증 인수 증거가 아니다. 앱의 STATES·업무 의미·권한 조건은 앱에 남기고 공통화하지 않는다. 현재 `share_control_styles`의 exact profile·paired viewport signature 재사용은 구현되어 있다. `maxWidth`만 identity에서 제외하고 관측 최대 cap을 유지한다. `control-reuse.json`의 492개 기존 스타일 선언→24개 main 선언, 12개 계열을 공통 adapter로 옮길 때도 보존하며 새로운 필드 계열 지원과 구분한다.

현재 실제 앱의 `design/graph.json`에는 `design_system`이 없다. 12개 컨트롤 계열과 candidate foundations는 관측 profile이며 수락된 Graph SSOT binding이 아니다. 앱 template·외부 CSS에 graph SHA와 typed value를 영속적으로 연결한 출력 경로도 아직 없다. 임시 외부 CSS verification overlay로 기존 selective protocol을 별도 검증할 수 있지만, 이는 출시할 영속 adapter 기능의 구현·인수 증거가 아니다.

Django 5.2는 template loading/rendering API를 제공한다. 임의 template은 신뢰할 수 있는 실행 설정이 아니다. [공식 template 문서](https://docs.djangoproject.com/en/5.2/topics/templates/)의 경계를 따른다. 정적 자산 URL은 실제 storage와 template static tag를 통해 해석하며 앱 namespace를 유지한다. [공식 staticfiles 문서](https://docs.djangoproject.com/en/5.2/howto/static-files/)를 따른다. `runserver`의 정적 제공 성공을 production 배포 성공으로 기록하지 않는다.

## 데이터와 인터페이스 설계

내부 출력 함수 제안은 `emit_web_artifacts(graph_path, out_dir, *, expected_sha256, formats)`다. 첫 formats는 `mjs`, `css` 두 값만 허용한다. 사용자가 임의 Python/JS module 경로를 주입하는 registry는 없다. 기존 `emit_web_module` 호출자는 유지하고 새 공통 emitter를 사용하도록 내부만 연결한다.

manifest 제안은 다음과 같다.

```json
{"schema":"figma-flow-web-artifacts-v1","graphSha256":"sha256","renderer":"portable-css-v1","artifacts":[{"path":"design.css","sha256":"sha256","mediaType":"text/css"}],"selectors":[{"componentId":"field","selector":".ff-field","properties":["color","fontSize"]}]}
```

CSS는 기존 `_stylesheet`의 검증된 선언과 정해진 selector만 직렬화한다. token 이름·값·URL·selector를 그대로 문자열 삽입하지 않는다. 지원하지 않는 property·단위는 명시적 오류다. 출력 순서·개행·숫자 표현을 고정하여 같은 graph bytes와 renderer 버전은 같은 산출물 bytes를 만든다. graph와 출력 경로 동일·symlink·상위 경로 탈출은 거절한다.

공통 관측 DTO 제안은 `source-adapter-v1`이며 adapter id/version, source graph/CSS digest, route/state id, viewport, capturedAt, source kind `ssr-html` 또는 `browser-dom`, sanitized HTML digest, assets, domMap, geometry coverage를 포함한다. SSR은 geometry complete false다. 앱이 승인된 실제 staging GET와 브라우저 관측을 제공하고 adapter는 이를 순수 변환한다. 비밀번호·hidden/CSRF·cookie·session을 입력/manifest에 넣지 않는다. adapter가 계정 생성·권한 부여·POST 상태 생성을 하지 않는다.

영속 SSOT 통합은 정상 discover 경로로 실제 main/instance identity를 먼저 읽고, 지원하는 값을 typed design-system 선언으로 고정한 뒤 pairing과 연결한다. 외부 CSS는 현재 CSP와 호환되게 제공하고 template의 graph SHA·artifact hash가 실제 출력과 일치하도록 연결한다. 이 변경에는 새 CSS epoch에서44개 화면 원본을 다시 캡처하고 관련 source hash·pins를 갱신하는 검증이 필요하다. 기존44개 불변 캡처는 과거 관측으로 보존하며 미래 adapter가 반영된 것처럼 덮어쓰거나 재해석하지 않는다.

## 기능·화면·오류 상태

CLI 출력은 생성 형식·graph hash·자산 hash·관측 coverage와 unsupported 목록이다. `ready`, `partial-observation`, `stale-css`, `unsupported`, `conflict`를 구분한다. 부분 관측으로 native 전체 성공을 만들지 않는다. 첫 버전은 새 설정 화면 없이 명시적 CLI 인자로 시작한다.

웹 출력의 focus·label·role·table 의미와 escape는 기존 template이 소유한다. adapter는 이를 삭제·변조하지 않는다. screenshot은 접근성 의미를 대신하지 않는다. 브라우저에서 JavaScript 없이 CSS를 로드한 대표 폼·표·다국어 텍스트와 mobile 레이아웃을 확인한다. 배포·계정 설정·CSP 변경은 이번 작업의 대상이 아니다.

## 마이그레이션·호환성·복구

기존 MJS 호출과 파일 bytes가 바뀌면 이유와 기존 소비자 영향 검사를 먼저 추가한다. CSS는 선택 출력이며 기존 pairing receipt를 CSS 검증 완료로 읽지 않는다. 새 proof는 artifact mediaType/hash와 renderer version을 pin한다. 기존 proof는 기존 방식으로만 검증한다.

여러 파일 출력은 sibling staging에 전부 작성·검증한 뒤 manifest를 마지막에 atomic 교체한다. 중간 실패 시 기존 manifest와 산출물 조합을 계속 읽는다. 오래된 파일 삭제는 자동으로 하지 않는다. `recover_projection`은 기존 MJS 복구를 유지하고 CSS manifest 복구는 별도 버전을 갖는다. rollback은 이전 graph/artifact manifest를 정확한 digest로 복원하며 앱 template·DB에는 손대지 않는다.

## 작은 작업과 한 writer 경계

1. `tools/graph_design_system.py`, `tests/test_graph_design_system.py`, 새 `tests/fixtures/nf04/` 소유자가 CSS/manifest emitter와 순수 golden 검사를 만든다.
2. `tools/graph_sync.py`, `tests/test_graph_sync.py` 소유자가 새 proof/mediaType와 atomic bundle 복구를 연결한다. 기존 독립 인수 파일은 수정하지 않는다.
3. 새 `tools/source_adapters.py`, 새 `tests/test_source_adapters.py` 소유자가 고정 adapter id와 순수 DTO 검증을 구현한다. 신규 runtime/dependency는 추가하지 않는다.
4. `apps/little-hands/design/source.py`, `apps/little-hands/design/test_source.py`, `apps/little-hands/design/README.md` 소유자가 공통 부분만 사용한다. 앱별 state/의미/계정 경로는 보존한다.
5. 통합 담당자가 실제 SSR GET·브라우저 관측을 재사용해 CSS와 DOM/native 대응을 확인한다. 외부 사이트에 publish하지 않는다.

## 인수와 검증

```sh
python3 -B -m unittest discover -s tests -p 'test_graph_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
python3 -B -m unittest discover -s apps/little-hands/design -p 'test_source.py'
```

새 검사 제안 `python3 -B -m unittest discover -s tests -p 'test_source_adapters.py'`는 SSR partial, geometry 위조 거절, static digest drift, hidden/password 제거, path 탈출, unsupported 값, multi-file 중단 복구를 다룬다. CSS bytes 결정성, MJS 회귀, 동일 token을 CSS와 native에서 관측한 대응을 검증한다. 실제 staging은 기존 허용 계정과 준비된 데이터를 쓰고 새 권한·거래를 만들지 않는다. 테스트 source와 실제 브라우저 측정의 차이는 결과에 남긴다.

## Cursor 구현·테스트 프롬프트

```text
NF-04만 구현하라. 먼저 graph_design_system emitter/graph_sync proof·복구와 Little Hands source/export/measure 경로를 읽어라. portable CSS+manifest, 순수 source adapter DTO, 명시적인 Django 5.2 adapter만 범위다. 소유 파일은 작업 1~4와 필요한 패치 기록이며 한 파일에 한 writer를 유지한다. 다른 dirty 변경을 보존하라. 기존 CSS 생성·lock·atomic·digest helper를 재사용하고 MJS 호환성을 입증하라. 현재 앱 graph에는 design_system이 없고 관측12개 계열은 수락된 SSOT binding이 아님을 전제로 하라. 영속 통합에는 정상 discover의 실제 main/instance identity, typed 선언, CSP 호환 외부 CSS와 template graph SHA 연결, 새44개 캡처 epoch/pins가 필요하다. 기존 캡처를 덮어쓰지 말고 임시 verification overlay를 영속 구현으로 보고하지 말라. 앱별 업무 state와 인증은 일반화하지 말라. SSR HTML은 geometry/업무 인수 증거가 아니며 hidden/password/CSRF를 공유하지 말라. 임의 코드 로더, 새 framework/runtime/dependency, CSP 변경·결함 주장, 배포·커밋은 금지한다. 기존 명령과 새 독립 검사를 실행하고 multi-file 실패 복구·CSS 결정성·브라우저 접근성을 확인하라. 새 경로가 필수면 수정 전에 필요한 소유 확장을 보고하라. 반환은 파일, manifest/adapter 계약, 호환·복구 근거, 검사/실제 관측과 미검증 범위다.
```
