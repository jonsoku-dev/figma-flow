# NF-09 · 웹 상호작용을 편집 가능한 Figma 프로토타입으로 가져오기

**0.33.0은 모바일 CSS 스크롤 스냅 캐러셀, 0.34.0은 클릭으로 패널을 바꾸는 탭, 0.35.0 후보는 단일 열림(`single-collapsible`) SaaS FAQ 아코디언을 구현했다.** 캐러셀은 2~16개의 카드 상태와 드래그·타이머 전이를, 탭은 관찰한 클릭 전이만, 아코디언은 `initialState`에서 directed traversal로 도달 가능한 2~16개 열림/닫힘 상태와 `open`·`close`·`switch` 클릭 전이를 정본 그래프로 묶어 편집 가능한 Figma Design 프레임으로 가져온다. [캐러셀 인수 기록](../../specs/interactive-web/carousel.md) · [탭 인수 기록](../../specs/interactive-web/tabs.md) · [SaaS FAQ 아코디언 인수 기록](../../specs/interactive-web/disclosure.md). overlay·다중 열림 아코디언·hover와 자유 모션은 후속 설계다. Figma Flow에는 이미 클릭으로 두 네이티브 프레임을 연결하는 [Smart Animate 레시피](../../library/figma-recipes/design-motion.ts)가 있다. 현재 [웹 캡처](../web-design-capture.md)는 측정 시점의 보이는 화면을 읽는다.

실제 Devtool 홈에서 두 번째 탭 카드를 클릭하면 표시 코드가 두 번째 패널 본문으로, 첫 번째 탭 카드를 다시 클릭하면 초기 패널 본문으로 바뀌었다. 0.34.0에서 이 A→B→A를 Figma 프레임과 클릭 hotspot으로 만들고, Chrome과 Figma 프레젠테이션에서 같은 클릭으로 대조했다.

0.35.0 후보에서는 실제 SaaS FAQ의 5개 질문 중 2개 질문에 7번 브라우저 입력을 수행해 `All closed`와 두 열림 상태(3개 상태) 및 6방향 전이를 기록했다. 이전 후보(`e92b3ad`)에서 Figma Desktop 적용·재적용·readback과 프레젠테이션 여섯 방향 도달을 확인했고, 후속 수정(`066830a`·`43a8b1b`)에서 `initialState` directed traversal 도달성 검사와 분리 순환 거부를 반영했다. 수정 후보의 최종 게이트와 설치 검증은 별도로 수행한다.

[관찰 상태·이벤트·미검증 인수를 연결한 정본 그래프](../../specs/interactive-web/graph.json)

## 정본 그래프와 매핑

상태 노드는 화면·뷰포트·요소 키와 활성 항목·열림 여부를 소유한다. 전이 엣지는 출발 상태·실제 입력·대상 요소·도착 상태와 브라우저 전후 근거를 연결한다. 시간·easing·반복·스크롤 위치는 측정한 경우에만 기록한다. 공통 레이어와 메인 컴포넌트는 한 번 정의한다.

| 웹에서 관측한 동작 | Figma Design 표현 후보 | 인수 시 구분할 것 |
| --- | --- | --- |
| 가로로 밀어 보는 카드 목록 | 콘텐츠보다 좁은 클리핑 프레임과 가로 스크롤 | 자유 스크롤과 카드 스냅은 다르다. 처음·중간·끝 위치를 검사한다. |
| 이전/다음, 페이지 점, 자동재생이 있는 캐러셀 | 카드 상태를 variants 또는 프레임으로 연결하고 클릭·드래그·타이머를 지정 | 루프 경계, 역방향, 정지/재시작, 모션 줄이기를 따로 검증한다. 실제 관성과 같다고 가정하지 않는다. |
| 탭·아코디언·호버·메뉴·모달 | interactive component, 상태 간 전환, overlay | 열기·닫기·복귀·내용 변경을 검증한다. 키보드 포커스와 스크린리더 의미는 브라우저에서 별도로 검증한다. |
| 이동·크기·투명도 변화 | 일치하는 레이어를 둔 전후 상태와 Smart Animate | 같은 시작/종료값이라도 중간 궤적은 다를 수 있다. 시작·중간·끝을 비교한다. |
| 영상·Canvas·WebGL·셰이더·물리 시뮬레이션 | 주요 상태 프레임과 실제 동작 영상·원본 코드 참조 | 영상 재생을 편집 가능한 타임라인이나 입력에 반응하는 엔진으로 보고하지 않는다. |

## Cursor 구현 순서와 통과 기준

1. 선택한 요소에서 **관찰한 전이만** 그래프로 묶는다. 우선 Devtool 탭 A→B→A를 사용한다. 이벤트 이름이나 CSS 클래스만으로 도착 상태를 추측하지 않는다.
2. 서로 다른 상태에서 같은 요소를 안정된 키로 연결한다. 스크롤 이동과 내용 변경, 숨김과 제거를 구분한다. 반복 애니메이션은 관찰 시간과 상태 수를 제한한다.
3. 기존 자체 플러그인의 native reaction 경로로 편집 가능한 메인·인스턴스 또는 프레임을 생성한다. 디자이너가 편집한 프레임을 보존한다. 자유 스크롤 목록, 유한 상태 캐러셀, 미디어 참조는 서로 다른 매핑으로 표시한다.
4. 전이마다 브라우저와 Figma **프레젠테이션 모드**에서 같은 입력을 수행한다. 표시 텍스트·활성 인덱스·목표 프레임·복귀를 대조하고 viewport와 입력 장치(실기기 또는 에뮬레이션)를 명시한다. reaction을 읽은 것만으로 재생 검증을 대체하지 않는다.
5. 디자이너에게는 편집할 레이어·variants, 개발자에게는 원본 이벤트와 웹 실행이 필요한 기능, 기획자에게는 통과/근사/미지원 전이 목록을 제공한다. 제작 대상은 Figma Design이다.

설계 근거: [Figma 가로 스크롤 조건](https://help.figma.com/hc/en-us/articles/360039818734-Prototype-scroll-and-overflow-behavior), [Plugin API 트리거](https://developers.figma.com/docs/plugins/api/Trigger/), [Smart Animate의 보간 대상](https://help.figma.com/hc/en-us/articles/360039818874-Smart-animate-layers-between-frames).
