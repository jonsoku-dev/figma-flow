# 시안 시각 품질 요구사항

플러그인은 시안을 직접 디자인하지 않는다. 캠페인의 `<letter>/source.py`와 `native-layout.json`은 에이전트가 작성하고, 플러그인은 검증·Figma 작성·읽기 검증을 한다. 그래서 시안의 품질은 이 문서의 요구사항을 작성 단계에서 지키는지, 그리고 [품질 관문](#3-품질-관문-design_qualitypy)이 그 결과를 확인하는지에 달려 있다. 이 문서는 [시안 검토 및 사용자 선택](direction-selection.md)의 검토 패키지를 준비하기 **전에** 적용한다. 각 항목은 숫자나 레이어 속성으로 확인할 수 있게 적었다. "보기 좋게" 같은 판단은 요구사항으로 쓰지 않는다.

## 웹 화면을 편집 가능한 Figma 레이어로 옮길 때

텍스트 레이어의 `w`는 문구를 선택했을 때의 글자 경계가 아니라, 그 문구가 차지할 수 있는 **실제 콘텐츠 영역**이다. CSS의 패딩, 같은 행의 아이콘·배지·다른 열, 행간과 자간을 함께 측정한다. 독립된 한 줄 조각을 재현하는 경우 `max_lines: 1`과 정확한 `leading`, 픽셀 단위 `letter_spacing`을 둔다. 문단은 실제 줄바꿈을 허용할 폭과 높이를 배정한다. Figma의 자동 높이는 절대 좌표의 다음 텍스트나 버튼을 밀어 주지 않는다. 원본에서 생략된 항목(외곽선, 노치, 선택 표시, 오류 설명, 로딩 문구)은 가져오기 검사가 되살려 주지 않는다. 상태별로 원본의 보이는 요소와 결과를 맞춰 본다.

브라우저와 Figma에서 사용하는 글꼴의 실제 family/style과 굵기를 확인한다. 측정 가능한 글꼴은 레이아웃 옆 `fonts/sources.json`의 family 레코드에 `file`로 지정한다. 별도 face 파일이나 TTC는 `styles` 안에 스타일별 `file`과 `index`를 지정할 수 있다. 예를 들어 `{"Example Sans":{"styles":{"Bold":{"file":"fonts/bold.ttf","index":0}}}}`이다. 배포할 수 없는 시스템 글꼴은 사용자의 로컬 설치 위치에서 읽는다. 예상 폭 경고는 실제 글꼴에서 맞는지 확인해야 한다.

`state_layouts` 각 상태의 `product_buttons`는 재사용 가능한 실제 제품 버튼 인스턴스를 선언한다. 아래는 단일 상태의 예로, `Primary`는 해당 후보·뷰포트의 `control_styles`에 정의한다.

```json
{
  "product_buttons": {
    "invite-submit": {
      "box": [24, 260, 342, 44],
      "variant": "Primary",
      "label": "초대 보내기"
    }
  }
}
```

입력 필드의 모서리와 포커스 링도 상태의 일부다. 불투명한 단색 바탕의 둥근 외곽선은 해당 바탕색을 채운 사각형에 실제 radius와 stroke를 준다. 사각형·타원과 버튼 스타일의 선택적 `shadows` 배열에는 CSS에서 확인한 그림자를 순서대로 적는다. 예를 들어 `[{"x":0,"y":0,"blur":0,"spread":3,"color":"#b91c1c","opacity":0.2}]`는 오류 포커스 링 한 겹이다. Figma 읽기 검사는 효과 순서, 좌표·번짐·확장, 색·알파를 실제 노드와 대조한다.

제품 인스턴스에는 실제 레이블, 중심 정렬, 패딩, 채우기와 필요한 테두리를 적용한다. 로딩 상태의 버튼에는 로딩 변형과 해당 문구를 쓴다. 사용자가 상태를 체험하는 검토용 이동은 별도의 `control_boxes`와 프로토타입 연결로 선언한다. 버튼 본문을 독립된 사각형과 텍스트로 다시 겹쳐 그리지 않는다.

가져오기와 `verify-native-review`는 실제 native 텍스트 상자의 폭·높이·줄 수·겹침, 컨트롤과 라벨의 위치·크기를 검사한다. `max_lines: 1`인 소수 폭은 다음 정수 픽셀에 배정한다. 실제 글자가 여전히 넘치면 패키지가 실패한다. 실패 시 **실패 진단 JSON 저장**에서 레이어 키와 작성·실측 좌표를 확인한다. 한 줄이 넘친 경우 자연 폭 측정값도 확인할 수 있다. 원본에서 배정 공간이나 줄바꿈과 주변 배치를 고치고 새 리뷰를 만든다. 출력 PNG에서 각 뷰포트·상태를 실제 웹 화면과 비교하고, 측정 검사와 육안 판정을 각각 기록한다.

## 1. 필수 요구사항 체크리스트

시안마다, 뷰포트(desktop·mobile)마다, 상태마다 확인한다. 관문이 자동으로 판정하는 항목은 코드를 함께 적었다. 코드가 없는 항목은 에이전트가 직접 확인하고 결과를 검토 메모에 남긴다.

| # | 요구사항 | 확인 방법 | 관문 코드 |
| --- | --- | --- | --- |
| R1 | **진입 화면의 시각적 중심.** 진입(cover/entry) 상태마다 다음 중 하나 이상을 둔다. 탐색용(non-reference) 이미지 자산 레이어, `role: "illustration"` 도형 구성(원·라운드 도형 2개 이상으로 사물·인물·빛을 표현), `gradient`. 크기는 프레임 짧은 변의 30% 이상이다. | 진입 상태 레이어 목록에 `image`/`ellipse`/`gradient` 또는 illustration 구성이 있는지 본다. | `no-visual-anchor` |
| R2 | **의미 없는 막대 금지.** text가 아닌 모든 레이어에 `role`을 선언하고, 그 도형이 화면에서 무엇인지(커튼, 무대 바닥선, 조명 웅덩이 등) 한 문장으로 말할 수 있어야 한다. 텍스트 줄처럼 생긴 가로 막대(두께 ≤ 64px, 길이/두께 ≥ 6)를 장식으로 쓰지 않는다. 구분선은 `role: "divider"`로 선언하고 실제로 두 영역을 나누는 위치에만 둔다. | 레이어마다 `role`이 있는지, 막대 모양 도형이 divider·frame·illustration 중 하나로 설명되는지 본다. | `placeholder-bar`, `missing-role` |
| R3 | **장식 비중.** role이 없거나 `ornament`인 도형은 8개 이하, 면적 합은 프레임의 25% 이하. 화면 테두리처럼 구조를 이루는 도형은 `frame`으로 선언한다. | 도형 개수와 면적 합을 계산한다. | `ornament-heavy` |
| R4 | **타입 스케일 3–5단계.** 한 상태 안의 서로 다른 글자 크기는 3개 이상 5개 이하. 인접 단계의 비율은 1.25 이상으로 둔다(예: 16 / 24 / 40 / 88). | text 레이어의 `size` 값을 모은다. | `type-scale` |
| R5 | **최소 글자 크기.** 모든 text `size` ≥ 12. 본문은 데스크톱 16 이상, 모바일 14 이상을 권장한다. | `size` 값. | `tiny-text` |
| R6 | **8px 격자.** 레이어와 control box의 `x, y, w, h`는 8의 배수로 둔다. 1–4px 두께의 divider와 글줄 `leading`만 예외다. 어긋나면 이유를 검토 메모에 적는다. | 좌표를 8로 나눈 나머지를 본다. | (에이전트 확인) |
| R7 | **비대칭 구성.** 한 비교에 포함된 2~3개 시안 중 하나 이상은 좌우 비대칭 구성이어야 한다. 예를 들어 텍스트 열은 왼쪽 정렬, 시각적 중심은 오른쪽에 둔다. 한 상태에서 텍스트 3개 이상이 모두 `align: "center"`이고 x 중심이 같으면 단조로운 대칭으로 본다. | text의 `align`과 `x + w/2`. | `all-centered` |
| R8 | **시안 간 차이.** 시안끼리 다음 세 가지가 모두 달라야 한다. 구성(시각적 중심의 위치와 텍스트 열 배치), 타이포그래피(display 서체 family 또는 크기 단계), 색(`bg` 역할의 HEX와 accent HEX). 색 이름만 바꾸고 같은 배치를 쓰면 다른 시안으로 보지 않는다. | `native-layout.json`의 후보별 `fonts`, `colors`, 진입 상태 레이어 좌표를 나란히 비교한다. | (에이전트 확인) |
| R9 | **WCAG 대비.** 텍스트 ink와 바로 아래 배경의 대비는 4.5:1 이상, `size` ≥ 24이면 3.0:1 이상이다. 배경은 텍스트 영역 중심을 덮는 가장 위의 불투명 rect/ellipse fill이고, 없으면 상태의 `bg`다. 이미지·그라디언트 위 텍스트는 자동 판정이 불가능하므로 렌더 결과를 보고 직접 확인한다. | 색상 역할 HEX로 대비를 계산한다. | `contrast`, `contrast-unknown` |
| R10 | **터치 영역.** control box는 모바일에서 높이 44 이상, 데스크톱에서 높이 36 이상, 너비는 항상 44 이상. control box는 text 레이어와 겹치지 않는다(버튼 라벨은 control이 직접 그린다). 버튼은 눈에 보여야 한다: `control_styles`의 `fill`은 버튼이 놓인 자리의 배경과 1.25:1 이상 달라야 하고, `ink`와 `fill`의 대비는 4.5:1 이상(`fontSize` ≥ 24이면 3.0:1)이다. 바탕과 같은 색의 「돌아가기」 버튼은 글자만 떠 있는 것처럼 보인다. | `control_boxes` 값 `[x, y, w, h]`, `control_styles`의 `fill`·`ink` HEX. | `control-size`, `control-text-overlap`, `control-invisible`, `control-label-contrast` |
| R11 | **텍스트 박스.** 텍스트끼리 겹치지 않는다. 줄 수 × `leading` ≤ `h`이고, 가장 긴 줄이 `w` 안에 들어가야 한다. 글꼴 파일이 없을 때는 관문이 CJK 1.0em, 그 외 0.56em으로 추정한다. | 박스 교차 면적, 줄 폭. | `text-overlap`, `text-overflow`, `text-overflow-estimated` |
| R12 | **프레임 안에 둔다.** 레이어가 프레임 밖으로 4px 넘게 나가지 않는다. 배경·장식·일러스트·이미지를 의도적으로 잘라 보이게(bleed) 할 때만 예외이고, 이 경우 해당 `role`을 선언한다. | 좌표와 프레임 크기. | `off-canvas` |
| R13 | **내용 밀도.** 텍스트와 시각 요소(role이 illustration·image인 도형, image, gradient)의 면적 합이 프레임의 12% 이상. 빈 무대에 문장 두 줄만 남기지 않는다. | 면적 합 / 프레임 면적. | `low-density` |

추가 규칙:

- 탐색용 이미지 자산은 레이어로 이미 쓸 수 있다. 브라우저 스크린샷 같은 reference 자산(`"reference": true`)은 레이어로 쓸 수 없고 별도 참조로만 표시된다. 시각적 중심이 필요하면 탐색용 이미지 자산이나 도형 구성을 쓴다.
- 색상 역할은 실제 화면 사용처가 있어야 한다. 0.16.1부터 미사용 역할은 Figma 쓰기 전에 차단된다. 0.17.0부터 `stroke`도 색상 사용처로 집계된다.
- HEX가 같아도 다른 역할의 사용처를 빌리지 않는다. 같은 색이 두 의미로 쓰이면 역할 두 개를 선언하고 각각 실제 사용처를 둔다.

## 2. 0.17.0 레이어 어휘

`state_layouts[viewport][state].layers[]`에 쓸 수 있는 속성이 늘었다. 모두 선택 속성이며 기존 0.16.1 layout은 그대로 검증·작성·읽기 검증을 통과한다.

| 속성 | 적용 대상 | 값 | Figma 기록 |
| --- | --- | --- | --- |
| `role` | text가 아닌 모든 레이어 | `background`, `surface`, `illustration`, `image`, `divider`, `ornament`, `frame` 중 하나. 없으면 `missing-role` 경고, 목록에 없는 값은 Figma 쓰기 전에 거부 | Figma에는 기록하지 않음(검증·품질 관문용) |
| `opacity` | text가 아닌 모든 레이어 | 0 < opacity ≤ 1, 기본 1 | `node.opacity` |
| `radius` | `rect` | 0 이상, min(w, h)/2 이하 | `cornerRadius` |
| `stroke` | `rect`, `ellipse` | `colors`에 선언된 색상 역할 이름. fill과 같은 이름 공간 | `strokes` 변수 바인딩, `strokeAlign = INSIDE` |
| `stroke_width` | `rect`, `ellipse` | `stroke`가 있으면 필수, 없으면 금지. 0 초과, min(w, h)/2 이하 | `strokeWeight` |

새 kind `ellipse`는 `{id, kind: "ellipse", x, y, w, h, fill, stroke?, stroke_width?, opacity?, role?}` 형식이며 `figma.createEllipse()`로 작성된다. 숫자는 유한수여야 하고 `w`, `h`는 0보다 커야 한다. `fill`과 `stroke`는 선언된 색상 역할이어야 한다. 알 수 없는 kind는 `Only declared native draft layer kinds allowed`, 그 kind에 없는 속성은 `Undeclared native draft layer property …`로 Figma 쓰기 전에 거부된다. 레이아웃의 문제는 첫 오류에서 멈추지 않고 `Authored layout invalid (N)` 아래에 모두 나열된다. 읽기 검증은 rect가 RECTANGLE, ellipse가 ELLIPSE로 존재하는지 확인하고, `cornerRadius`, `strokeWeight`, `opacity`를 작성 값과 ±0.001 범위에서 대조한다.

아래 예시는 rect의 radius·stroke·opacity와 ellipse를 함께 쓴 일부 레이어다.

```json
[
  {"id": "spot-halo", "kind": "ellipse", "x": 704, "y": 64, "w": 496, "h": 496, "fill": "paper", "opacity": 0.08, "role": "illustration"},
  {"id": "stage-pool", "kind": "ellipse", "x": 664, "y": 528, "w": 448, "h": 80, "fill": "paper", "opacity": 0.24, "stroke": "line", "stroke_width": 2, "role": "illustration"},
  {"id": "stage-mark", "kind": "rect", "x": 544, "y": 488, "w": 192, "h": 64, "fill": "ink", "radius": 8, "stroke": "accent", "stroke_width": 3, "role": "illustration"},
  {"id": "stage-lip", "kind": "rect", "x": 112, "y": 640, "w": 1056, "h": 8, "fill": "accent", "role": "divider"},
  {"id": "mark-caption", "kind": "text", "value": "그림자가 머무를 무대 표식", "x": 192, "y": 576, "w": 896, "h": 32, "size": 16, "leading": 24, "ink": "muted", "font": "body", "align": "center"}
]
```

`stage-mark` 하나가 0.16.1에서 3px 막대 네 개(`stage-mark-top/bottom/left/right`)로 그리던 무대 표식을 대신한다. 레이어 순서가 쌓임 순서이므로 시각적 중심 도형을 먼저 두고, 그 위에 무대 틀과 텍스트를 둔다.

## 3. 품질 관문 `design_quality.py`

### 쓰기 전 사전 점검

Figma 플러그인은 검토 페이지를 만들기 전에 글꼴(family와 style)이 설치되어 있는지, 이미지 자산 키, 텍스트의 font 역할, control box(유한수 4개, w·h > 0), 상태 layout을 모두 확인한다. 문제가 하나라도 있으면 페이지·변수·스타일을 만들지 않고 모든 문제를 한 메시지에 모아 보여 준다.

```text
검토 초안을 만들기 전에 확인이 필요합니다 (파일은 변경되지 않았습니다):
- ...
```

이 메시지가 나오면 Figma 파일은 바뀌지 않은 상태다. 항목마다 글꼴을 설치하거나 layout을 고친 뒤 플러그인을 다시 실행한다. 글꼴 이름을 임의로 바꿔 통과시키지 않는다. 바꿔야 하면 시안의 `fonts`와 서체 견본을 함께 고친다.

### 실행

플러그인 루트에서 실행한다.

```sh
python3 tools/design_quality.py --layout reviews/r1/native-layout.json --out reviews/r1/quality.json
python3 tools/design_quality.py --layout reviews/r1/native-layout.json --strict
python3 tools/design_actions.py quality --manifest reviews/r1/directions.json
```

- 입력은 schema `figma-flow-authored-native-layout-v1`의 authored native layout이다. `quality --manifest`는 매니페스트에 선언된 native layout 경로를 찾아 같은 검사를 실행한다.
- 보고서는 `{schema: "figma-flow-design-quality-v1", passed, errors, warnings, metrics}` 형식이다. 각 항목에 `code, severity, candidate, viewport, state, layer, message, fix`가 있고 `message`와 `fix`는 한국어다. `metrics`는 후보·뷰포트·상태별 수치다.
- 종료 코드 `0`은 통과, `1`은 오류가 있다는 뜻이다. **오류는 막고 경고는 막지 않는다.** `--strict`를 주면 경고도 실패로 처리한다.
- `design_actions.py prepare-native-review`는 패킷을 만들기 **전에** 이 관문을 실행한다. 오류가 있으면 패킷을 만들지 않고 실패하며, 보고서 경로와 한국어 요약을 출력한다. 경고는 출력에 요약된다.

### 오류 코드 (검토 패키지 준비를 막음)

| 코드 | 뜻 | 고치는 방법 |
| --- | --- | --- |
| `contrast` | 텍스트와 바로 아래 배경의 WCAG 대비가 4.5:1 미만(24px 이상은 3.0:1 미만) | ink 또는 배경 역할의 HEX를 조정하거나, 텍스트를 대비가 충분한 면 위로 옮긴다. |
| `off-canvas` | 레이어가 프레임 밖으로 4px 넘게 나감 | 좌표·크기를 프레임 안으로 줄인다. 의도한 bleed라면 `background`·`ornament`·`illustration`·`image` 역할을 선언한다(이 경우 경고로 낮아짐). |
| `text-overlap` | 두 텍스트 박스의 교차 면적이 작은 박스의 5%를 넘음 | 텍스트 박스를 세로로 분리하거나 한쪽 문장을 줄인다. |
| `text-overflow` | 텍스트가 박스를 넘침(글꼴 파일로 실측) | 박스 `w`/`h`를 늘리거나, 줄바꿈을 넣거나, `size`를 한 단계 낮춘다. |
| `tiny-text` | 글자 크기가 12 미만 | `size`를 12 이상으로 올린다. |
| `control-size` | control box 높이가 모바일 44 미만, 데스크톱 36 미만, 또는 너비가 44 미만 | control box를 최소 크기 이상으로 키운다. |
| `control-text-overlap` | control box와 text 레이어가 겹침 | control 주변의 텍스트를 옮긴다. 버튼 라벨은 control이 직접 그리므로 text 레이어로 따로 두지 않는다. |
| `control-invisible` | 버튼 `fill`이 버튼 아래 배경(가장 위의 불투명 도형 또는 상태 `bg`)과 1.25:1 미만으로 거의 같음. 이미지·그라디언트 위의 버튼은 판정하지 않는다 | 해당 변형의 `fill`을 배경과 구분되는 색상 역할로 바꾼다. 배경이 화면마다 다르면 변형을 나눈다. |
| `control-label-contrast` | 버튼 `ink`와 `fill`의 대비가 4.5:1(24px 이상은 3.0:1) 미만 | `ink`를 `fill`과 대비되는 역할로 바꾼다. |

### 경고 코드 (막지 않지만 해소하거나 사유를 기록)

| 코드 | 뜻 | 고치는 방법 |
| --- | --- | --- |
| `placeholder-bar` | role이 없거나 ornament인 단색 rect가 두께 64px 이하, 길이/두께 6 이상이고 텍스트·이미지와 겹치지 않음. 의미 없는 장식 막대라서 placeholder처럼 보임 | 막대를 지우거나, 실제 의미가 있는 형태(ellipse 조명, 라운드 도형, 이미지)로 바꾸거나, 진짜 구분선이면 `role: "divider"`로 선언한다. |
| `missing-role` | text가 아닌 레이어에 `role`이 없음 | 7개 역할 중 하나를 선언한다. 고를 역할이 없으면 그 레이어가 필요한지부터 다시 본다. |
| `ornament-heavy` | ornament·role 없는 도형의 면적 합이 프레임의 25% 초과 또는 개수 8개 초과 | 장식을 줄이고, 구조를 이루는 도형은 `frame`·`surface`로 선언한다. |
| `no-visual-anchor` | 진입 상태에 image·illustration·ellipse·gradient 레이어가 없음 | R1에 따라 탐색용 이미지 자산이나 illustration 도형 구성을 추가한다. |
| `all-centered` | 텍스트 3개 이상이 모두 가운데 정렬이고 x 중심이 같음 | 텍스트 열을 한쪽으로 정렬하거나 시각적 중심과 비대칭으로 배치한다(R7). |
| `type-scale` | 서로 다른 글자 크기가 2개 이하(위계 부족) 또는 6개 초과(난잡) | 3–5단계로 정리한다(R4). |
| `low-density` | 텍스트와 시각 요소의 면적이 프레임의 12% 미만 | 시각적 중심을 키우거나 내용을 보강한다(R13). |
| `contrast-unknown` | 이미지·그라디언트 위의 텍스트라서 대비를 자동으로 판정할 수 없음 | 렌더한 미리보기에서 대비를 직접 확인하고 결과를 검토 메모에 적는다. 확실하지 않으면 텍스트 뒤에 불투명 `surface`를 깐다. |
| `text-overflow-estimated` | 글꼴 파일이 없어 넘침 여부를 추정치로 판단함 | 글꼴 파일과 Pillow가 있는 환경에서 다시 실행하거나, 박스에 여유를 둔다. |

## 4. 자기 비평 루프 (검토 패키지 준비 전 필수)

검토 패키지(`prepare-native-review`, `figma_draft.py prepare`)를 준비하기 전에 다음 순서를 반드시 거친다. 한 바퀴로 끝나지 않으면 반복한다.

1. **렌더한다.** 시안마다 데스크톱·모바일, 모든 상태의 미리보기 이미지를 만들고 직접 연다. 코드만 읽고 넘어가지 않는다.
2. **관문을 실행한다.** `python3 tools/design_quality.py --layout ... --out ...`를 실행하고 보고서를 읽는다.
3. **체크리스트를 확인한다.** 1절의 R1–R13을 이미지와 보고서로 하나씩 확인한다. 특히 관문이 판정하지 않는 R6(8px 격자), R8(시안 간 차이)과 `contrast-unknown` 대상은 직접 본다.
4. **고친다.** 오류는 모두 고친다. 경고는 고치는 것이 기본이다. `source.py`를 고치고 `native-layout.json`을 다시 생성한 뒤 1단계부터 다시 한다.
5. **남은 경고에 사유를 적는다.** 경고가 0개가 될 때까지 고치거나, 남은 경고마다 코드·레이어·유지하는 이유를 해당 시안의 검토 메모(`agent-review.json`의 그 후보 항목)에 적는다. "의도함"처럼 이유가 없는 문장은 사유로 보지 않는다.
6. 그다음에만 검토 패키지를 준비한다.

관문 통과는 객관적인 결함이 없다는 뜻이다. 디자인이 좋다는 증명이 아니며 사용자의 선택을 대신하지도 않는다.

## 5. 사례 비평: 그림자 극단 A "막이 오르는 밤"

작업공간의 `shadow-troupe/a/source.py`(0.16.1 형식)와 미리보기 `shadow-troupe/previews/a-desktop.png`를 기준으로 한 비평이다. 데스크톱 cover 상태(1280×800, `bg: ink` `#151013`)를 다룬다.

### 무엇이 문제인가

무대 가운데에 가로 막대 세 개와 1px 선 하나가 있다. 모두 `spot` `#3C2C31` 단색이다.

| 레이어 | 크기 | 길이/두께 | 배경 `ink` 대비 |
| --- | --- | --- | --- |
| `upper-light` | 512×18 | 28 | 1.43:1 |
| `main-light` | 736×46 | 16 | 1.43:1 |
| `lower-light` | 448×14 | 32 | 1.43:1 |
| `light-edge` | 608×1 | 608 | `line` `#573B40`, 1.89:1 |

작성 의도는 무대 조명이다. 하지만 화면에서는 조명으로 읽히지 않고 placeholder로 읽힌다. 이유는 다음과 같다.

1. **형태가 글줄과 같다.** 길이/두께 16–32의 가로 막대가 텍스트 열과 같은 가운데 축에서 제목·본문 줄 위치에 쌓여 있다. 로딩 중 스켈레톤 UI나 가려진 문장과 같은 모양이다.
2. **빛이 어둡다.** 조명이라면 주변보다 밝아야 하는데 `spot`은 배경보다 1.43배 밝을 뿐이고 `accent`보다도 어둡다. 빛의 퍼짐도, 가장자리 감쇠도, 비추는 대상도 없다.
3. **관계가 없다.** 막대가 아무것도 비추지 않는다. 그림자 극단의 핵심인 "빛 → 대상 → 그림자"가 cover에 하나도 없다. 그래서 시각적 중심이 없고(`no-visual-anchor`), 텍스트 네 개(`edition`, `headline`, `opening-copy`, `invitation`)가 모두 x 중심 640에 가운데 정렬되어 있다(`all-centered`).
4. **이름 없는 도형이 많다.** 13개 rect 모두 `role`이 없다. 면적 합은 314,144px²로 프레임의 30.7%다. 개수(13 > 8)와 면적(> 25%) 모두 `ornament-heavy` 기준을 넘는다. 커튼 주름(`curtain-*-fold`, 32×800), `valance`, `proscenium-rule`, `stage-lip`, `stage-front`도 막대 기준에 걸린다.

0.17.0 관문에서 이 상태는 오류 없이 경고만 받는다(대비·박스·control은 통과). 하지만 경고 내용이 바로 "회색 막대가 placeholder처럼 보인다"는 문제이므로 자기 비평 루프에서 고쳐야 한다. 예상 경고는 `placeholder-bar`(조명 막대·주름·규칙선), `missing-role`(모든 도형), `ornament-heavy`, `no-visual-anchor`, `all-centered`다. 정확한 목록은 관문 보고서로 확인한다.

### 받아들일 수 있는 버전

조명을 막대가 아니라 **빛이 떨어지는 형태**로 만들고, 그 빛이 실제로 무언가를 비추고 그림자를 만들게 한다. 텍스트는 왼쪽 열로 옮겨 비대칭으로 둔다.

```json
{
  "width": 1280, "height": 800, "bg": "ink",
  "layers": [
    {"id": "spot-halo", "kind": "ellipse", "x": 704, "y": 64, "w": 496, "h": 496, "fill": "paper", "opacity": 0.08, "role": "illustration"},
    {"id": "spot-core", "kind": "ellipse", "x": 784, "y": 144, "w": 336, "h": 336, "fill": "paper", "opacity": 0.16, "role": "illustration"},
    {"id": "stage-pool", "kind": "ellipse", "x": 664, "y": 528, "w": 448, "h": 80, "fill": "paper", "opacity": 0.24, "stroke": "line", "stroke_width": 2, "role": "illustration"},
    {"id": "shadow-actor", "kind": "rect", "x": 848, "y": 336, "w": 80, "h": 224, "radius": 40, "fill": "velvet", "role": "illustration"},
    {"id": "curtain-left", "kind": "rect", "x": 0, "y": 0, "w": 112, "h": 800, "fill": "accent", "role": "frame"},
    {"id": "curtain-right", "kind": "rect", "x": 1168, "y": 0, "w": 112, "h": 800, "fill": "accent", "role": "frame"},
    {"id": "stage-lip", "kind": "rect", "x": 112, "y": 640, "w": 1056, "h": 8, "fill": "accent", "role": "divider"},
    {"id": "edition", "kind": "text", "value": "그림자 극단  /  첫 번째 공연", "x": 176, "y": 136, "w": 432, "h": 24, "size": 16, "leading": 24, "ink": "muted", "font": "body", "align": "left"},
    {"id": "headline", "kind": "text", "value": "그림자 극단", "x": 176, "y": 200, "w": 528, "h": 128, "size": 88, "leading": 120, "ink": "paper", "font": "display", "align": "left"},
    {"id": "opening-copy", "kind": "text", "value": "빛의 위치를 바꾸면,\n그림자의 배역이 달라집니다.", "x": 176, "y": 352, "w": 432, "h": 80, "size": 24, "leading": 40, "ink": "paper", "font": "body", "align": "left"}
  ],
  "control_boxes": {"a-open": [176, 688, 288, 56]}
}
```

바뀐 점과 확인 결과:

- **시각적 중심(R1).** 오른쪽 위에서 떨어지는 빛(`spot-halo`, `spot-core`, 불투명도 0.08 → 0.16)이 바닥의 빛 웅덩이(`stage-pool`)에 닿고, 그 위에 선 배우의 그림자(`shadow-actor`, radius 40의 세로 라운드 도형)가 생긴다. "빛을 옮기면 그림자의 배역이 바뀐다"는 문구를 그림으로 보여 준다. halo 지름 496은 프레임 짧은 변 800의 62%다.
- **막대 제거(R2, R3).** 조명 막대 세 개와 1px 선을 지웠다. 남은 도형은 모두 역할이 있다. 커튼은 `frame`, 무대 앞선은 `divider`, 빛과 그림자는 `illustration`이다. 커튼이 halo보다 뒤에 선언되어 빛의 오른쪽이 커튼에 가려지고, 빛이 무대 안에 있는 것처럼 보인다.
- **비대칭(R7).** 텍스트 열은 x 176에서 왼쪽 정렬, 시각적 중심은 x 704–1200의 오른쪽에 둔다.
- **타입 스케일(R4).** 88 / 24 / 16의 3단계, 인접 비율 3.7과 1.5.
- **대비(R9).** `paper` 대 `ink` 15.47:1, `muted` 대 `ink` 7.55:1. 불투명도가 1보다 작은 빛 도형은 배경으로 계산되지 않으므로 텍스트를 빛 바깥(x < 704)에 두었다.
- **8px 격자(R6)와 control(R10).** 모든 좌표와 크기가 8의 배수다. control box 288×56은 데스크톱 기준(높이 36, 너비 44)을 넘고 텍스트와 겹치지 않는다.
- **색상 사용처.** 이 예시는 `paper`, `ink`, `muted`, `accent`, `velvet`, `line`(stroke)을 쓴다. 원래 계획의 `spot`은 사용처가 없어지므로 색상 계획에서 지우거나 실제 사용처를 다시 둔다. 그대로 두면 0.16.1의 미사용 색상 검사에서 Figma 쓰기 전에 차단된다.

모바일(390×844)도 같은 원리로 다시 구성한다. 빛과 그림자를 위쪽 절반에 두고 텍스트 열을 아래에 왼쪽 정렬로 둔다. control box는 높이 44 이상으로 유지한다. 실제 수정은 해당 캠페인의 `source.py`에서 하고, 생성한 layout을 관문과 미리보기로 다시 확인한다.


## 버튼이 어느 변형을 쓰는지

관문은 `native-layout.json` 옆 후보 폴더의 `annotations.json`에서 control id별 `visual_variant`를 읽어 그 변형의 색으로 판정한다. 주석 파일이 없으면 선언된 모든 변형이 똑같이 결함일 때만 오류로 본다(확실한 경우만 막는다).
