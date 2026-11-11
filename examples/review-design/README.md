# 복습 카드 디자인 예시

`design.json`은 편집 가능한 토큰, 컴포넌트 변형, 두 화면의 명세입니다. 화면과 요구사항, 행동 ID는 `product-graph.json`을 참조합니다. 화면 배치와 예시 문구는 디자인 제안입니다.

```sh
python3 tools/design_system.py --input examples/review-design/design.json --out /tmp/review-design-new
```

새 출력 폴더에 `tokens.css`, 재사용 가능한 `components.css`, 토큰 원본 경로와 별칭을 보존한 `resolved.json`, 두 화면을 함께 보여 주는 `wireframe.html`과 `styled.html`, 화면별 SVG가 생성됩니다. `preview/`는 이 예시를 생성한 정적 결과입니다. 변경을 확인하려면 새 출력 경로를 사용하세요. 기존 폴더를 덮어쓰지 않습니다.

지원 범위는 6/8자리 16진 색상 또는 DTCG 2025 sRGB 색상 객체, px/rem 치수 문자열 또는 `{value, unit}` 객체, 유한한 숫자, 단일 글꼴 이름, 같은 타입 토큰에 대한 전체 값 별칭입니다. 그룹의 `$type` 상속과 `$description`을 허용합니다. sRGB 채널과 alpha는 가장 가까운 8비트 값으로 반올림하므로 최대 1/510의 오차가 생길 수 있습니다. 다른 색 공간과 합성 토큰은 지원하지 않습니다. CSS 별칭은 `var()`로 보존하고 `resolved.json`에는 최종 값을 기록합니다. 컴포넌트 스타일은 제한된 속성과 토큰 참조만 허용합니다. SVG는 Figma에 가져올 수 있는 단순화된 정적 그림이며 네이티브 변수 바인딩이나 실행 가능한 화면은 아닙니다. 고정된 360×640 SVG에 내용이 들어가지 않으면 생성이 실패합니다. HTML 역시 동작하는 앱이 아닌 화면 시안입니다.

## Figma MCP 없는 전체 전달

`product-graph.json`은 함께 제공되는 `cards.md`에서 작성한 화면 초안입니다. 아래 명령은 토큰·변형·시안·SVG·개발 플러그인 소스와 디자인 관계 그래프를 새 폴더에 생성합니다.

```sh
python3 tools/design_bundle.py --design examples/review-design/design.json --graph examples/review-design/product-graph.json --draft-only --out /tmp/review-design-bundle-001
```

`--draft-only`는 탐색용 미리보기만 만들고 설치 가능한 `figma-plugin/` 키트는 만들지 않습니다. `index.html`에서 토큰 사용처와 SVG를 확인하세요. 변수를 생성하는 네이티브 가져오기 키트는 실제 사용자가 시안을 고른 뒤 `--draft-only` 대신 `--selection 선택-기록.json`(에셋이 필요하면 `--batch`·`--asset-receipts`도)을 주고, Figma Desktop에서 발급한 플러그인 ID를 `--plugin-id`로 제공해 만듭니다([시안 검토 및 사용자 선택](../../skills/figma-flow/references/direction-selection.md)). SVG 전송은 별도 ID가 필요하지 않습니다.
