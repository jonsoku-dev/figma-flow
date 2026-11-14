# 외부 SVG 로고 필터 실측 · 0.32.2

[편집 가능한 웹 그래프](../specs/editable-web/graph.json) · [웹 캡처 가이드](web-design-capture.md)

## 측정 조건

Devtool 모바일 화면을 390 × 844 CSS px, DPR 1에서 Chromium으로 측정했다. 그래프 `evidence-0322-devtool-stable-logo`의 화면 `WEB-devtool-stable-logo`에는 외부 SVG 로고 6개가 있다. 브라우저의 계산된 스타일은 모두 `brightness(0) grayscale(1) invert(1)`과 `opacity: 0.3`이었다.

각 브라우저 관측 상자에서 RGB 채널 최댓값과 최솟값의 차이가 40을 넘는 픽셀 수를 셌다. 이 값은 강한 색 성분이 남았는지 보여 준다. 전체 화면의 픽셀 일치를 뜻하지는 않는다.

| 로고 | Figma `VECTOR` 하위 노드 | 브라우저 색 픽셀 | 0.32.1 첫 적용 | 0.32.2 첫 적용 |
| --- | ---: | ---: | ---: | ---: |
| Google | 6 | 0 | 1,179 | 0 |
| Microsoft | 5 | 0 | 709 | 0 |
| Amazon | 8 | 0 | 236 | 0 |
| Netflix | 2 | 0 | 1,368 | 0 |
| YouTube | 4 | 0 | 816 | 0 |
| Instagram | 1 | 0 | 0 | 0 |
| 합계 | 26 | 0 | 4,308 | 0 |

0.32.2는 `brightness(0)`으로 정해지는 색을 각 SVG의 리터럴 fill과 stroke에 적용했다. 이 6개 원본에는 로컬 clip path가 있는 YouTube와 Netflix를 포함해 지원 가능한 페인트만 있었다. 각 로고는 Figma의 편집 가능한 벡터로 남았다.

이 6개 SVG에는 alpha 색 값이 없었다. 별도 회귀 테스트는 alpha를 포함한 색과 SVG 그룹 opacity가 보존되는지 확인한다. 캡처 그래프는 `<img>` opacity `0.3`을 기록하고 native import는 그 값을 벡터 루트에 할당한다. Figma Design 속성 검사에서 Google 로고 `el-38`의 불투명도는 30%로 읽혔다. 나머지 다섯 로고의 값은 그래프와 픽셀 측정으로 확인했다. 필터 캡처, alpha 보존, 벡터 opacity, 제한된 필터 체인은 [`test_web_design_svg_capture.cjs`](../tests/test_web_design_svg_capture.cjs), [`test_web_design_svg_filter.py`](../tests/test_web_design_svg_filter.py), [`test_web_design_svg_root_opacity.cjs`](../tests/test_web_design_svg_root_opacity.cjs), [`test_web_design_svg_filter_limits.py`](../tests/test_web_design_svg_filter_limits.py)에서 확인한다.

Google 로고의 벡터 루트는 별도 Chrome에서 같은 네이티브 노드 ID로 연 뒤 Figma 속성 패널의 불투명도 30%를 직접 확인했다.

## 네이티브 구성 및 한도

그래프에는 정규화된 SVG 6개와 각 원본 SVG의 경로 및 SHA-256이 남아 있다. 정규화된 파일은 합계 31,922 bytes, 원본은 32,140 bytes였다. 여섯 자산은 모두 `bound_media`에 있었고, 누락 이미지는 없었다. 로고에 래스터 fallback은 사용하지 않았다.

최초 적용과 재적용 영수증은 같은 그래프, 화면, Figma 프레임을 가리켰다. 재적용은 기존 프레임을 재사용했다. 화면에는 편집 가능한 노드 73개가 있었고, 로고 하위 벡터는 26개였다. 미리보기 PNG는 480 × 1,052 px, 504,960 pixels, 73,070 bytes였다. 각 값은 5,000,000-pixel 및 작업당 8 MB 한도보다 작다. 여섯 원본과 정규화 SVG는 각각 합계 32,140 bytes와 31,922 bytes로, 8 MB 미디어 한도보다 작다. Figma는 최초 적용에서 GeistSans 요청 15건을 Geist 글꼴로 대체했고 텍스트 폭 편차 9건을 기록했다. 이 기록은 로고 상자의 색을 검증하며 전체 화면 픽셀 동등성을 주장하지 않는다.

색을 안정적으로 계산할 수 없는 경우 화면 그래프는 원본 벡터를 유지하고 제한을 기록한다. 예를 들어 `currentColor`, SVG paint-server 참조, 또는 `brightness(0)` 없는 필터 체인은 이 실루엣 변환을 쓰지 않는다. 이미지도 그래프에서 제거하지 않는다.

## 과거 프레임 확인

별도 Cloud Chrome 확인에서는 이전 작업의 프레임 54개를 다시 열었다. 54개 모두 프레임 ID가 URL과 일치했고, 관측한 너비와 높이는 예상값에서 0.55 px 이내였다. 이 확인은 기존 54개 프레임의 해당 보기만 다루며 파일 전체의 저장 상태를 보증하지 않는다.
