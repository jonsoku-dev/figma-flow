# 로컬 디자인과 소스·기획 감사

일반 사용자는 Figma **Design 모드**의 로컬 플러그인만 사용한다. Figma Dev Mode·Computer Use·후크·원격 MCP는 필수가 아니다. Figma가 요청된 탐색 단계는 실제 네이티브 화면/주석과 Design 캔버스의 읽을 수 있는 대상 링크 주석 보드·팔레트·토큰·프로토타입 왕복 연결을 검증해야 사용자 선택 대기로 진행한다. 로컬 HTML만 읽고 네이티브 검증 완료라고 하지 않는다. 승인 전 본제작과 승인 전 명시적 탐색용 Figma 리뷰를 구분한다. 개발 검수의 CU는 별도 사용자 허용 시에만 가능하며 일반 실행 경로에는 의존하지 않는다.

0.15에서는 [정상 방향 선택 계약](direction-selection.md)의 실제 시안·사용자 선택이 모든 새 제작보다 먼저다. 후크·Computer Use·Stagehand·브라우저 드라이버·GUI 자동화 없이 동작한다. 선택 전에는 탐색 시안과 읽기/감사만 수행하며, 과거의 네이티브 검사 통과를 새 제작 승인으로 사용하지 않는다.

0.5의 기획·그래프·앱·선택 테스트 흐름에 로컬 디자인 원본과 감사 결과를 더한다. Figma가 요청되어도 기본은 이 문서의 로컬 출력과 개발 플러그인 경로다. 기능별 경로는 `python3 tools/figma_feature.py route FEATURE`와 [기능별 실행 경로](figma-feature-routes.md)에서 찾는다. 기존 등록 Flow의 지원 작업을 우선 사용하고, 추가 기능은 별도 로컬 개발 플러그인 SDK로 작성·검토한다. [네이티브 작업·증거 절차](figma-workflow.md)를 적용하며 Figma MCP를 초기 확인이나 대체 경로로 호출하지 않는다.

## 기준 원본과 증거

| 사실 | 기준 원본 | 별도로 필요한 증거 |
| --- | --- | --- |
| 의도한 동작·정책 | 선택한 현재 기획서와 활성 명세 | 원문 대조, 모순 해결 결정 |
| 관계와 의미 ID | 선택한 제품 graph JSON | strict-local 관계 검사 |
| 색·간격·글꼴·컴포넌트·화면 구성 | 로컬 design JSON | 컴파일·미리보기 검토 |
| 디자인 사용처 | 원본 그래프와 디자인에서 만든 `design-graph.json` | 투영 입력 해시와 연결 검사 |
| 실제 구현과 동작 | 코드와 실제 실행 | 테스트·브라우저 기록 |
| 현재 Figma 상태 | 실제 가져온 파일과 해당 파일의 재읽기 | 파일/노드 식별자, 관찰 시각·범위 |

디자인 토큰은 디자인 값이며 Codex 모델 토큰과 다른 개념이다. Codex의 해석·생성은 모델 사용량을 쓸 수 있다. 이 로컬 컴파일과 키트는 Figma MCP·Figma AI를 호출하지 않지만, Figma 좌석·편집 접근·기능 권한·크레딧을 제공하거나 보장하지 않는다. 원격 계정 상태를 로컬 성공으로 추정하지 않는다.

UI를 새로 제작/리디자인하는 작업은 [기본 디자인 검토](design-review.md)를 함께 수행한다. 로컬 전용 UI도 같은 폰트 우선·실제 창작 검토를 요구하며, Figma 미사용은 창작 게이트의 예외가 아니다.

## 디자인 번들 만들기

1. [예제 원본](../../../examples/review-design/design.json)을 참고해 `version: 1`, `tokens`, `components`, `screens`를 작성한다. 토큰은 `$type`과 `$value`를 가지며 지원 타입은 `color`, `dimension`, `number`, `fontFamily`다. `{color.primary}` 형태의 별칭은 같은 타입의 토큰을 참조한다. 컴포넌트의 각 `variants`는 지원 CSS 속성과 토큰 경로를 연결한다. 지원 범위의 정확한 검사는 `tools/design_system.py`가 수행한다.
2. 화면 `id`는 제품 그래프의 screen ID와 맞추고 `trace`는 해당 화면에 연결된 requirement·acceptance·state·action ID를 사용한다. 요소는 `heading`, `text`, `component`로 작성한다. 버튼에는 해당 화면의 `action_id`를 지정하고 화면 이동에는 그 액션의 `target_screen`을 지정한다. 기획에서 정하지 않은 이동은 추론으로 기록하고 승인된 동작과 구분한다.
3. 플러그인 루트에서 새 출력 폴더를 지정한다.

```sh
python3 tools/design_bundle.py --design /프로젝트/design.json --graph /프로젝트/graph.json --out /작업/디자인-001
```

4. 생성된 번들은 `pending_native_handoff`다. `index.html`에서 `preview/wireframe.html`, `preview/styled.html`, 화면별 SVG를 검토한다. `preview/tokens.css`와 `preview/resolved.json`은 해석된 디자인 값이고, `figma-plugin/`은 가져오기 키트다. `bundle.json`과 `design-graph.json`의 입력·범위도 읽는다. 입력 바이트 변경은 다시 생성할 사유다. 기존 원본이나 출력 폴더를 덮어쓰지 않는다.
5. 투영 그래프에는 토큰 → 별칭/컴포넌트 → 화면/액션 방향의 의존성과 디자인 적용 범위가 담긴다. 화면·컴포넌트의 미사용/미포함 목록을 확인한다. 원본 그래프에 디자인 관계를 역으로 덮어쓰지 않는다. 디자인 파일 전체의 공유 증거 해시는 작은 수정에도 여러 노드를 stale로 만들 수 있으므로 실제 영향 경로와 해시 최신성을 나눠 보고한다.

미리보기는 제한된 선언을 보여 주는 정적 시안이다. 버튼 표시·SVG 생성·그래프 연결은 제품 동작, 전체 반응형 품질이나 실제 Figma 일치의 증거가 아니다.

## Figma에서 가져오고 재읽기

키트를 생성한 뒤에는 그 안의 `figma-plugin/README.md`를 따른다. Figma Desktop의 개발 플러그인 등록에서 생성된 `manifest.json`을 선택한다. 앱이 ID를 요구하면 Figma에서 새 개발 플러그인을 만들어 발급받은 숫자 ID를 사용한다.

```sh
python3 tools/design_bundle.py --design /프로젝트/design.json --graph /프로젝트/graph.json --plugin-id 123456789 --out /프로젝트/design-bundle-002
```

숫자는 예시이며 실제 발급 ID로 바꾼다. 사용자가 허용한 편집 대상에서 플러그인의 검토된 payload를 확인하고 가져오기를 실행한다. 현재 문서에서 변수·컴포넌트·화면·프로토타입 반응을 관찰한 다음 플러그인의 재읽기 JSON을 내보낸다. SVG를 직접 가져오는 경로는 시각적 대안으로 기록하며 변수·컴포넌트·반응 보존까지 주장하지 않는다.

```sh
python3 tools/figma_bridge.py --inspect-readback /프로젝트/evidence/figma-readback.json --input /프로젝트/design-bundle-002/preview/resolved.json --expected /프로젝트/design-bundle-002/figma-plugin/expected-native-handoff.json --require-match
```

이 검사는 현재 네이티브 주석·실제 인스턴스 연결·변수 바인딩과 원본의 지원 필드를 대조하고, 검토된 원본에서 생성한 계약으로 공통 네이티브 전달 검사도 자동 실행한다. 생성된 `figma-plugin/expected-native-handoff.json`은 같은 검증기와 호환되며 직접 작성한 계약/네이티브 ID가 필요하지 않다. 보고서의 `generated_expected_contract`와 페이지별 `native_handoff`에는 관측한 화면 명세가 담긴다. 아래 선언을 프로젝트 bindings에 추가하고 `check_project.py`까지 통과시킨다. 파일이 Figma에서 왔다는 진위를 인증하거나 모든 시각·동작 속성을 대조하지 않는다. 재읽기 내보내기와 실제 파일 관찰을 함께 기록한다. 로컬 키트 생성과 시뮬레이션 Plugin API 테스트는 실제 가져오기·재읽기 성공으로 보고하지 않는다. 앱이 열리지 않거나 권한이 없으면 해당 단계를 미검증으로 남기고 로컬 산출물을 전달한다.

## 필수 네이티브 전달 검사 (0.13.0)

Figma 포함 여부는 그래프의 Figma 노드·URL, 시각 원본 또는 `native_handoff` 선언으로 판정한다. 등록 Flow·맞춤 로컬 SDK 모두 같은 조건을 적용한다. `strict-local`과 `ssot.py --scope local-only` 통과는 이 검사를 면제하지 않는다. 순수 로컬 출력은 Figma 원본을 선언하지 않고 기존 흐름을 유지한다.

1. 현재 기획에서 화면과 중요한 조작마다 실제 액션·상태·토큰·컴포넌트 관계를 정한다. 화면 및 조작 노드의 네이티브 `annotations`에 설명을 작성한다. 조작은 실제 로컬 컴포넌트 세트의 인스턴스로 배치하고 중요한 속성은 실제 변수에 연결한다. 미사용 라이브러리·정적 값·메타데이터 주석은 전달 조건을 채우지 않는다.
2. 실제 선택 파일/페이지를 다시 읽는다. 일반 플러그인은 **현재 디자인 읽기**로 저장한다. 맞춤 Plugin API 제작자는 동봉된 `figma-bridge/native_semantic_read.js`의 `readNativeSemantics(figma, page)`를 실행해 반환값을 저장한다. 반환값에 현재 선택한 실제 Figma 파일 URL의 파일 키를 `fileKey`로 포함하고, 파일 키·페이지 ID·관측 시각·실행 기록·캡처 경로를 함께 기록한다. 맞춤 SDK도 같은 네이티브 노드·컬렉션·변수 필드를 읽어 이 형식에 맞춘다. 공급한 JSON의 검사는 원격 출처 인증이 아니므로 실제 호스트 캡처 기록을 별도로 유지한다.
3. **일반 번들:** `design-bundle-002/figma-plugin/expected-native-handoff.json`을 그대로 사용한다. 화면/요소의 의미 ID, 선언 액션·상태·변형, 컴포넌트 관계와 실제 지원 바인딩에서 자동 생성되며 번들의 `native_handoff_contract`·`native_handoff_command`가 이를 가리킨다. 계약이나 네이티브 ID를 재작성하지 않는다. 실제 파일 키는 개발 플러그인 API로 읽기에 포함되며, 프로젝트 선언의 페이지 ID는 읽기에 기록된 실제 페이지 ID를 사용한다.

   **맞춤 제작:** 기대 계약에는 요구한 모든 화면과 중요한 조작을 넣는다. 아래는 **맞춤 스키마 예시**다. 값은 실제 프로젝트 의미 키/네이티브 ID와 변수 이름으로 바꾸고, 액션·상태는 기획에서 정한 표현을 사용한다. 캡처를 보고 계약에서 실패한 요구를 지우지 않는다.

`evidence/native-contract.json`:

```json
{
  "file_key": "ACTUAL_FILE_KEY",
  "collection_name": "Product tokens",
  "variables": [{"name": "color/brand", "resolved_type": "COLOR"}],
  "screens": [{
    "key": "SCR-HOME",
    "controls": [{
      "key": "home.play",
      "action": "ACT-PLAY",
      "states": ["idle", "playing"],
      "component_key": "components.play/idle",
      "token_bindings": [{"property": "fills.0.color", "variable": "color/brand"}]
    }]
  }]
}
```

`key`와 `component_key`는 현재 캡처의 고유한 `semanticKey` 또는 일반 브리지의 `semantic_id`와 일치해야 한다. 고정한 실제 네이티브 ID를 쓸 때는 화면/조작의 `id`, `component_id`, 바인딩의 `variable_id`로 대신 지정할 수 있다. 인터랙티브 화면에는 중요한 조작 목록이 필요하다. 일반 정적 화면은 `static: true, controls: []`를 사용한다. 정적 컴포넌트 요소는 `static: true`와 실제 컴포넌트/바인딩을 선언하며 동작이나 상태를 만들어 넣지 않는다. 전체 디자인에는 실제로 사용된 재사용 인스턴스와 바인딩이 필요하다. 조작의 실제 주석에는 `action`과 모든 `states` 표현이 있어야 한다. 변수의 모든 캡처된 모드·별칭 값과 실제 속성의 별칭 연결이 검사된다. `fills.0.color`는 실제 페인트의 `boundVariables.color`를 검사하며 숫자 연결은 `paddingTop`처럼 지정한다. 라벨의 글자색·폰트는 `node_key: "home.play/label"`로 해당 조작의 실제 하위 노드를 지정한다.

4. 기존 `bindings.json`에 다음 필드를 **추가**한다. `readback`·`contract`는 bindings 파일 기준 상대 경로이며 심볼릭 링크를 통과하지 않는 실제 로컬 파일이어야 한다. `file_key`와 `page_id`는 현재 선택한 실제 대상과 일치시킨다.

```json
{
  "native_handoff": {
    "file_key": "ACTUAL_FILE_KEY",
    "page_id": "12:34",
    "readback": "evidence/figma-readback.json",
    "contract": "design-bundle-002/figma-plugin/expected-native-handoff.json"
  }
}
```

맞춤 제작의 선언은 `contract`를 직접 작성한 `evidence/native-contract.json`으로 지정한다. 일반 번들은 생성된 파일을 직접 연결한다.

5. 플러그인 루트에서 새 출력 폴더로 실행한다. 읽기에 페이지가 하나면 자동 선택하고, 여러 개면 실제 페이지 ID로 `--page-id 12:34`를 추가한다. 첫 번째 명령은 독립 검사이며, 두 번째 또는 세 번째는 프로젝트의 현재 입력과 캡처·계약 해시까지 연결하는 필수 인수 경로다.

```sh
python3 tools/native_handoff.py --readback /프로젝트/evidence/figma-readback.json --contract /프로젝트/design-bundle-002/figma-plugin/expected-native-handoff.json --out /작업/native-001
python3 tools/check_project.py --init --brief /프로젝트/brief.md --graph /프로젝트/graph.json --bindings /프로젝트/bindings.json --out /작업/check-001
# 이미 기준선이 있으면 기존 검토·재개 절차로 변경된 bindings/캡처를 고정한 현재 매니페스트를 검사한다.
python3 tools/check_project.py /프로젝트/admission/manifest-001.json --out /작업/check-002
```

독립 명령은 `report.json`, `screen-spec.json`, `screen-spec.md`를 생성한다. 프로젝트 검사는 `native-handoff.json`에 현재 brief/graph/bindings와 실제 캡처·계약 경로/SHA-256을 기록하고, 관측한 노드·주석·컴포넌트·바인딩·변수 모드에서 `screen-spec.json`과 `screen-spec.md`를 생성한다. 출력 예시의 `summary.json` 필드는 다음과 같다. 이 예시는 실행 증거가 아니다.

```json
{"native_handoff_status": "passed", "native_handoff_receipt": "native-handoff.json", "runtime_status": "not-checked"}
```

`native_handoff_status: passed`와 네이티브 영수증의 `passed: true`를 확인한다. 주석 API 미지원·누락, 빈 계약, 더미/미사용 컴포넌트, 연결되지 않은 토큰, 다른 파일/페이지와 변경된 캡처는 차단 상태로 남긴다. 실패 시 원인과 대상 노드 ID를 보고하고 같은 범위에서 보완 후 새로 캡처한다. 기존 캡처나 증거를 성공처럼 바꾸지 않는다. 전달 명세는 **현재 네이티브 읽기의 투영**이며 기획의 모든 의미, 프로토타입 재생, 웹 실행·시각 일치를 자동 증명하지 않는다.

Figma 제품의 **Figma Specs** 작성은 별도 선택 사항이다. 외부 `screen-spec.md`·JSON 생성과 네이티브 주석·컴포넌트·변수 검증은 모든 Figma 포함 작업의 필수 전달 조건이므로 Specs 미사용/미지원으로 생략할 수 없다.

## 소스 의존성과 기획을 따로 감사하기

플러그인 루트에서 선택한 프로젝트의 원본과 새 출력 폴더를 지정한다. 입력은 프로젝트 안의 파일이어야 한다. 활성 명세가 더 있으면 `--spec`을 반복한다.

```sh
python3 tools/audit_project.py --project /프로젝트 --graph graph.json --bindings bindings.json --brief brief.md --spec screen-spec.md --out /작업/감사-001
```

`audit.json`과 `audit.md`에서 두 판단을 따로 읽는다.

- **소스 의존성:** 지원되는 로컬 정적 참조와 명시한 코드/테스트 소유권으로 입증한 의존 경로가 그래프에 없으면 `missing`이다. 공유 소유권이나 선언된 `checked by`만 있는 관계는 `candidates`다. 동적/미해석 참조, 모호한 대상, 지원하지 않는 구문·파일 등은 `unknown`이다. 화면 이동, 같은 화면 등장, 같은 파일 공유만으로 의미적 의존성을 확정하지 않는다.
- **기획 일관성:** 지원 패턴에서 주체·범위·조건이 같은 활성 규칙의 충돌을 찾으면 `fail`이다. 명시적 과거 규칙·예시는 따로 보존한다. 조건이 모호하거나 지원하지 않는 자연어는 `unsupported`로 남는다. `review`는 미분석 범위가 남았다는 뜻이며, 모순이 전혀 없다는 증명이 아니다. `pass`도 추출한 규칙 범위에 한정된다.

종합 종료 코드 `0`은 검사한 범위에서 확인된 이상이 없다는 뜻이다. `1`은 확인된 의존 경로 누락 또는 활성 모순, `2`는 검토 필요/불완전 범위나 잘못된 입력이다. 후보와 미해결을 확인된 누락 개수에 합치지 않는다. 감사는 파일을 재작성하거나 그래프 관계·새 기준선을 승인하지 않는다.

## 감사 결과로 테스트와 완료 주장 정하기

`affected_tests.py`는 선택한 매니페스트·매핑·실제 현재 소스를 감사하고 그 보고서를 출력에 남긴다. [변경 테스트 절차](draft-build.md)를 따르며 활성 명세는 `--spec`으로 전달한다.

1. 확인된 누락·후보·미해결 의존성이 있으면 매핑된 전체 테스트를 선택하는 보수적 경로를 사용한다. 기획/기준 원본·바인딩 변경 또는 불완전한 기존 경로의 fallback도 유지한다. 전체 매핑 테스트는 프로젝트의 모든 테스트와 같다고 가정하지 않는다.
2. 활성 기획 모순이 있으면 유용한 테스트 실행은 계속하되 `acceptance_claim: blocked-by-active-contradiction`을 유지한다. 테스트 통과 사실과 인수 완료 차단을 함께 보고한다. `test_result`가 통과해도 모순이 해소되지 않으면 전체 영수증 성공으로 바꾸지 않는다.
3. 미분석 기획 구문은 검토 대상으로 남긴다. 감사에서 활성 모순을 못 찾았다는 이유로 전체 자연어 의미나 제품 인수를 완료로 선언하지 않는다. `acceptance_claim: not-established`는 인수 완료를 뜻하지 않는다.
4. 계획은 실행 증거가 아니다. 실제 `receipt.json`·파일별 TAP·입력 전후 해시를 읽고 실패·변경·미실행을 보존한다. 관계 검사, 내용 최신성, 정적 감사, 실제 테스트, 브라우저와 Figma 결과를 각각 보고한다. 검토 후 재개의 새 기준선은 실제 재검증과 별도 검토 절차를 따른다.

## 개발 플러그인 ID와 토큰 사용처

Figma Desktop에서 이 용도로 새 개발 플러그인을 만든 경우 번들 명령에 `--id-from /경로/manifest.json`을 추가하면 그 파일의 숫자 ID만 읽어 새 키트에 적용한다. 게시나 계정 인증이 수행되지 않는다. 결과의 `tokens.html`에서 별칭, 색상 값, 이를 소비하는 변형과 화면을 열어 볼 수 있다. `preview/components.css`는 동일한 변형을 실제 앱에 적용하는 CSS다. SVG 복사 버튼은 사용자가 누를 때만 동작하며 직접 복사가 허용되지 않으면 원문 선택으로 전환된다.

## 자동 규칙 밖의 기획 검토

`audit_project.py --spec specs/retry.md`처럼 이번 판정에 사용할 활성 문서를 명시한다. `unsupported`가 남으면 Codex 또는 사람이 실제 문장을 읽고 주체·조건·대상이 같은지 확인한다. 구체적인 모순 후보가 있으면 `--review REVIEW.json`으로 제출한다. 검토 파일은 version=1, reviewer, findings 배열을 가지며, 각 후보에는 topic, scope, condition, rationale와 evidence 2개가 필요하다. 각 evidence에 file, line, quote, sha256을 담는다. 이미 지정한 문서의 현재 해시와 실제 줄에 일치하는 두 인용만 받아들인다. 검토 후보는 pending으로 보고하며 인용의 일치는 의미 판단의 정확성을 보증하지 않는다.

기존 기준선으로 한 번에 검사하려면 `python3 tools/check_project.py MANIFEST --audit --project PROJECT --spec specs/retry.md --out NEW_DIRECTORY`를 사용한다. 화면 설계 그래프의 토큰 연결은 `python3 tools/design_graph.py --audit --graph AUGMENTED.json --design DESIGN.json`으로 대조한다.

## 실제 Figma Desktop 재검증

`--check-readback EXPORT.json --input RESOLVED.json --require-match`는 검사 가능한 필드가 원본과 다르면 종료 1을 반환한다. 0.6.1은 기본 SVG 글꼴로 Inter를 사용하고, 네이티브 화면 크기·UI 메시지 전달과 Figma가 개별 모서리로 내보낸 변수 연결을 처리한다. CSS 감사의 무조건부 로컬 `@import`는 증거로, 조건부·해석 불가능한 가져오기는 미확정으로 다룬다.
