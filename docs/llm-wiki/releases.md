# 버전과 전체 Git 기록 대조

0.27.1 최초 catalog의 소스 기준은 `aa8b7191405b160d1119c403510152a12e0ae801`이었다. 최신 기준 커밋·수량은 [현재 catalog](catalog.json)에 기록한다. 당시 도달 가능한 canonical 커밋 222개와 별도 보존 계보 39개(저장 head 19개)를 기록한다. 별도 39개 patch와 19개 head는 2026-11-13 원본 Git 객체로 대조했다. 기본 verify의 structural 검사와 source-Git 대조는 별도 근거다. 0.27.0은 기존 태그와 프리릴리스 영수증을 보존하고, 0.27.1의 최종 발행·설치는 해당 절의 실제 결과를 따른다. 제품 소스 뒤 Wiki/CHANGELOG 전용 발행 커밋은 코드 변경과 구분한다.

## 대조 방법

각 버전 절은 명시한 소스·기록 시점의 설명을 보존한다. 과거의 미검증·pending 문구는 그 시점의 상태이며, 최신 발행·설치 결과는 가장 최근 버전의 실제 영수증으로 확인한다.

`catalog.json`과 `patch_knowledge.py inventory`가 실제 커밋·부모·파일·diff 해시·태그·매니페스트를 제공한다. 아래 목록은 본문을 보존하는 사람이 읽는 연결이다. 태그 없는 버전, 겹친 버전, CHANGELOG에만 남은 버전을 명시한다. 과거 테스트 코드의 존재를 당시 성공 실행으로 세지 않는다.

## v0.35.0

[사용 절차](../guide.md#web-disclosure-quickstart) · [FAQ 인수 조건](../../specs/interactive-web/disclosure.md) · [설계 그래프](../../specs/interactive-web/graph.json) · [배포본과 SHA-256](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.35.0).

**편집 가능한 SaaS FAQ.** 실제 SaaS 홈페이지의 다섯 질문 중 두 개를 1440×900 데스크톱에서 측정했다. 일곱 입력에서 전체 닫힘과 답변 두 개, 여섯 종류의 클릭을 관찰했다. 같은 세 프레임을 재적용하고 별도로 읽어 Figma ID 재사용과 현재 상태를 확인했고, 실제 프레젠테이션에서 여섯 방향을 모두 눌렀다. 첫 클릭은 목표를 벗어났고, 좌표를 바로잡은 뒤 검증했다. CSS 높이 애니메이션, 키보드와 동시 열림은 확인 범위 밖이다.

**독립 검수에서 발견한 결함.** 초기점과 분리된 순환을 Python CLI와 Figma 브리지가 잘못 승인했다. 검사를 먼저 커밋하고 같은 검사에서 수정 전 실패와 수정 후 통과를 재현했다. 수정본으로 원 관측을 다시 컴파일한 그래프와 계획은 Figma에서 재생한 바이트와 일치했다. 브라우저 신규 수집은 시간이 달라지므로 새 그래프 해시는 다르다. 대신 클릭 추적과 답변, 상태·입력 PNG 10장을 대조해 모두 같음을 확인했다. [고정 검사](patches/066830a97f7f053e880cdf2a6418aadb3de781ab.md) · [양쪽 구현 수정](patches/43a8b1ba64d276a79e4d6429b9b2b0a9175c5e2f.md).

<a id="g1-source-regeneration"></a>

### G1 소스 재생성

요구사항·상태의 안정 ID와 디자이너가 채택한 토큰을 보존하고, 생성 원본에서 사라진 노드·관계를 검토할 수 있도록 남긴다. REQ-006 삭제를 재현한 후 오래된 CSS 버전으로 차단하고 유효한 입력으로 재시도했다. 세 단계 모두 노드 3개와 관계 10개 전체가 일치했다. [최초 구현](patches/2a8e3adde7b0e2bb8d5baddc72ea2a1800e524f9.md) · [최종 수정 및 인수](patches/bfb5e8f95af859098921f80da3811047a2a75f4d.md). 이 변경은 v0.34.0 태그 이후의 main에 통합됐다.

## v0.34.0

[탭 계약과 실제 사용 장면](../../specs/interactive-web/tabs.md) · [정본 그래프](../../specs/interactive-web/graph.json) · [입력 형식](../web-tabs-input.md) · [사용 절차](../guide.md#web-tabs-quickstart).

1440 × 900 CSS px의 실제 Devtool 홈에서 탭 두 상태와 관찰한 클릭 두 번을 기록했다. 상태 구분은 패널 글자 해시, 전이의 출발점은 출발 화면에서 누른 탭과 같은 상자의 frame 요소다. 처음 구현은 반응을 탭 레이어에 직접 넣었다. Figma Desktop은 이 장면에서 `setReactionsAsync` 연결 시간 초과로 두 번 거절했고, 두 번 모두 새 노드를 롤백했다. 같은 장면에서 최상위 투명 프레임에 같은 반응을 넣으면 성공해, 탭 클릭도 캐러셀 드래그와 같은 최상위 hotspot 경로를 쓴다. Chrome과 Figma 프레젠테이션에서 A→B→A를 같은 클릭으로 대조했다. 그래프에 없는 탭을 누르면 프로토타입은 현재 상태에 머문다.

캐러셀과 탭의 읽기·적용은 하나의 관찰 상태 그래프 경로를 쓰고, 0.33 프레임의 플러그인 데이터 키는 바꾸지 않았다. 홈 요약은 0.33부터 누락되던 이전/다음 버튼 전이를 포함한다. 두 캡처 CLI는 같은 Chromium 파이프 모듈을 사용한다. 탭과 무관하게 바뀌는 로고 띠 같은 주변 애니메이션은 캡처 순간의 모습으로 남는다.

## v0.33.0

[캐러셀 계약과 실제 사용 장면](../../specs/interactive-web/carousel.md) · [정본 그래프](../../specs/interactive-web/graph.json) · [입력 형식](../web-carousel-input.md) · [사용 절차](../guide.md#web-carousel-quickstart).

390 × 844 CSS px의 실제 SaaS 페이지에서 카드 네 개, 입력별 전이 열두 개를 관측했다. 양 끝의 수동 정지 두 개는 Figma에서 같은 프레임으로 이동시키면 거절되므로 해당 방향의 반응을 비워 경계를 보존한다. 나머지는 드래그와 타이머로 연결한다. 마지막 타이머가 첫 카드로 돌아오는 것을 Figma 플레이어에서 직접 확인했다. 드래그는 측정된 레일의 각 절반에서 시작한다. 캡처 당시의 진행 표시와 실제 연속 스크롤 관성에는 표현 차이가 남는다.

공통 이미지는 원본 해시, 크기, 맞춤 방식, 페인트와 조상 레이아웃이 일치할 때 묶는다. 네이티브 읽기에서 이미지 인스턴스 세 개가 같은 메인을 참조했다. 홈 또는 이력에서 사용하는 동작에는 읽었던 작업 버전, 그래프, 파일, 페이지, 시작점 정보가 필요하다. 이전 그래프의 문자열 컴포넌트 키도 재생할 수 있다. 포크는 아래 커밋별 페이지에서 관찰, 재현 기준, 실제 구현과 호환성 변경을 따로 검토할 수 있다.

## v0.32.2

[브라우저·Figma 비교](../web-svg-fidelity-0322.md)와 [편집 가능한 웹 그래프](../../specs/editable-web/graph.json)에서 외부 SVG의 필터와 루트 opacity를 추적한다. 이전 Figma 출력의 로고 6개 중 5개에 남았던 색을 밝기 0 필터가 확정하는 단색 실루엣으로 가져왔다. 이번 표본에 남은 네이티브 경로는 26개다. 지원 범위를 넘어가는 SVG·래스터 필터는 원본 근거와 시각적 한계를 구분한다.

포크는 캡처·SVG 바인딩 기준 3d72453, 루트 투명도 기준 6b448d9, 네이티브 적용 ec9eb9b, 바인딩 구현 09ea462의 순서로 검토할 수 있다. [상호작용 로드맵](../next-roadmap/NF-09-interactive-web-design.md)은 제안 단계다. 현재 버전의 웹 가져오기는 모션이나 스와이퍼의 자동 변환을 제공하지 않는다.

## v0.32.1

웹 화면의 자간과 첫 이미지 미리보기에 관한 패치다. [실측 보고서](../web-fidelity-0321.md)는 브라우저 너비, 자간을 생략한 Figma 대조군, 자간을 복원한 편집 가능 레이어를 같은 입력으로 비교한다. 두 Magic UI 화면에서 본문 글꼴 대체 없이 TEXT 너비를 비교했고, 별도 버튼 표본에서 서로 다른 두 자간과 실제 메인–인스턴스 연결을 검증했다. 한 메인의 자간을 직접 바꿔 충돌을 읽은 뒤 원래 값으로 복원했다.

최초 캔버스 미리보기 비교에서는 동일 RGB 영역이 0개에서 13,500개 픽셀로 바뀌었다. 화면 전체를 두 번째 내보내기와도 대조했다. 이전 그래프는 자간 필드를 추가하지 않고 그대로 읽을 수 있다. 라스터를 포함한 새 화면만 준비 렌더가 하나 추가되며 하나의 45초 제한을 공유한다.

포크에서 검토할 순서는 [재현 기준](https://github.com/jonsoku-dev/figma-flow/commit/925aa87), [구현](https://github.com/jonsoku-dev/figma-flow/commit/abd3af8), [독립적인 네이티브 검증과 정본 그래프](https://github.com/jonsoku-dev/figma-flow/commit/1430fdf), [설치 버전](https://github.com/jonsoku-dev/figma-flow/commit/4de7542)이다. API 정적 커버리지 기준에는 소스 해시만 바뀌었다. 새 API 관측 개수를 주장하지 않는다.

## v0.32.0

최종 제품 소스는 `86b182e0f579206a65586a8ca34db0131f4d0f3a`이며 두 manifest의 버전은 0.32.0이다. [GitHub 배포 페이지와 다운로드](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.32.0)에서 태그, 설치 ZIP, SHA-256을 확인한다.

### Design 범위

프로젝트 헌법, 에이전트 규칙, 활성 라우트와 SDK 생성기를 Figma Design/default에 맞춘다. 독립 FigJam·Slides 생성 레시피와 편집기 전용 테스트를 제거했다. Figma Widget 프로젝트는 Design 파일에서만 등록한다. 이전 릴리스의 API 선언과 역사 기록은 과거 근거로 유지한다.

기존 테스트 소유 FigJam 보드 2개와 Slides 덱 3개는 정리 전에 각각 복구 자료로 저장했다. 실제 plugin-data 소유 marker와 기존 ID 명단을 기준으로 보드 객체 129개와 슬라이드 111개, 행 37개를 정리했다. 원본 파일, 백업, 고정된 과거 release는 보존했다. [정리 근거](../design-runtime-verification.md#이전-제작-경로-정리) · [제품 헌법](../../CONSTITUTION.md).

### CSS masks, filters and canvas

브라우저 CSSOM이 생략한 기본 중심을 복원해 래디얼 배경을 Figma paint로 전달한다. 선형·래디얼 alpha mask의 `intersect`는 중첩 네이티브 마스크로 가져온다. 단색 leaf에서 지원하는 색상 필터는 CSS 순서대로 계산한다. 지원하지 않는 mask operator와 이미지 필터는 limitation으로 남긴다.

| 비교 영역 | 수정 전 중앙 최대 채널 차이 | 수정 후 |
| --- | ---: | ---: |
| 래디얼·선형 mask 교차 | 119 | 2 |
| blur와 drop shadow | 167.5 | 2 |
| 필터 없는 래디얼 원본 | 167 | 1.5 |
| 단색 밝기·채도 | 0 | 0 |

수치는 각 영역 6개 표본에서 RGB 채널별 최대 차이의 중앙값이다. 단색 면 중심에서 브라우저와 Figma가 모두 `#825e3a`를 반환했다. Magic UI SaaS의 800×800 canvas PNG를 읽어 네이티브 이미지 레이어로 옮겼다. 원본 출처가 다른 canvas는 사용자가 제공한 screenshot에서 측정된 crop만 쓴다. 정적인 캔버스 이미지는 animation frame을 보존하지 않는다. [실제 브라우저·Figma 측정](../design-runtime-verification.md#복합-마스크와-필터) · [canvas 입력과 crop 규칙](../web-design-capture.md).

### Design API inspection

Design API 우선순위 row는 Design 적용 범위를 별도로 분류한다. Design review graph의 조사 queue에는 Design 호환 row만 넣고, 고정된 공식 선언 인벤토리의 편집기별 row는 분모와 과거 기록을 위해 보존한다. 0.31 baseline에서 미관측이던 1,193개 중 368개의 새 unique member ID에 관측 근거를 더해 누적 557/1,382개를 확인했고 잔여는 825개다. 중복되는 API 키는 합계에서 제외한다.

비공개 fixture 플러그인은 정확한 member ID와 소유한 receiver만 조사한다. 일반 사용자 페이지를 훑거나 원시 텍스트, 레이어 이름, path, 이미지 바이트를 내보내지 않는다. Service graph는 269개 항목을 시도해 241개 성공, 15개 값 미제공, 13개 런타임 오류를 기록했다. Scene graph는 265회 읽기 시도와 8회 복구된 write, 79개 successful member edge, 9개 deduplicated edge, 5개 attempt-only edge를 기록한다. 마지막 safe property receipt는 23회 성공, 2회 값 미제공을 기록한다.

Native value graph는 exact getter를 통해 정규화한 62개 field를 기록한다. 62는 필드 관측 수이며 62개의 새 API member를 뜻하지 않는다. scene·service graph와 겹치는 member ID는 다시 고유 키로 세지 않는다. Function-valued property는 probe에서 호출하거나 직렬화하지 않는다. 현재 비식별 [scene evidence](../../specs/design-inspection/scene-observations.json), [service evidence](../../specs/design-inspection/service-observations.json), [typed value evidence](../../specs/design-inspection/value-observations.json)에서 원본 receipt의 해시·member edge를 확인한다. [API 우선순위 안내](../api-priority.md) · [native probe 안내](../native-api-probe.md) · [value-path 절차](../design-runtime-verification.md#추가-네이티브-값-경로-실행).

### Native workspace update

Startup에서 오래된 task generator를 찾으면 `HostAdapter.native`가 서명된 workspace snapshot, 소스 revision, task 입력, dependency pin을 확인한다. 오래된 row를 함께 준비하고 generation 하나를 게시한다. Batch 중 실패하면 현재 generation과 이전 task artifact를 유지한다. 실제 79 task 실행에서는 generation 1개를 만들고 이전 generation 1,138개를 보존했다. 15.12초는 이 단일 실행의 receipt 값이며 재현 가능한 성능 비교가 아니다. 개별 task replay API는 직접 task 준비를 위해 남아 있다. [workspace replay 변경](patches/456cb515719974311b0051ac86e7e3d764aa18d4.md).

### Independent Design observations

새 Design frame의 정확한 ID가 Cloud editor에 나타났지만 Desktop에는 미동기화 안내가 남았다. 이는 해당 frame이 브라우저 파일에 도달했다는 근거이며 Desktop 변경 전체가 동기화되었다는 뜻은 아니다. 공개 Figma 예제는 1920×1080, 18.033초로 재생했다. 16.378초, 17.681초, 반복 후 0.863초 표본에서 재생 위치가 진행했다. 무료 초안은 새 source video upload를 거절했으므로 이 영수증은 공개 예제 재생만 다룬다. [Design 런타임 기록](../design-runtime-verification.md#클라우드와-프로토타입).

이 source

최종 소스에서 원본 선택 자료를 연결한 전체 로컬 Python 1,254개, Node 348개, finalize 75개, 디자인 18개, 데모 2개가 통과했다. 건너뜀과 실패는 0건이었다. 복합 CSS 마스크의 개선 전 실패와 후속 성공은 별도 커밋에 보존한 동일 검사로 재실행했다.

## v0.31.0

0.31.0의 최종 제품 소스는 `d44a2a6f2eb4051dc8dceb4f1db1bc1f8336462a`이다. 54개 화면의 근거 그래프는 `f6af842f0420301ee533ac0994f3f9b0fbe21109`에서 등록했다. 배포 ZIP과 SHA-256은 [GitHub 릴리스](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.31.0)에서 확인한다.

0.30.0의 제품 source는 `c1541b8129bdf3e175dd905cddfed39acd52bc2e`이고 `v0.30.0` tag가 가리키는 `f9453da79c5f57aa779096468cbf29286c7fb185`는 CHANGELOG·Wiki/catalog만 발행한 docs-only commit이다. 0.31.0은 그 tag나 installer의 연장이 아니라 새 candidate source다.

### Browser 경로와 화면 인수

공급 ZIP에서 20개 일반 페이지와 7개 source error path를 골라 각 경로를 390×844와 1440×900 CSS pixel에서 읽었다. 각 route/viewport를 연결한 54개 frame receipt를 보관했고, 같은 입력 재적용은 이전 frame ID와 main 연결을 유지했다.

| 템플릿 | ZIP 페이지 | 오류 경로 | Figma 프레임 | 편집 요소 | Instance |
|---|---:|---:|---:|---:|---:|
| Portfolio | 9 | 2 | 22 | 3,306 | 2 |
| Codeforge | 1 | 1 | 4 | 1,138 | 48 |
| Devtool | 5 | 2 | 14 | 1,652 | 22 |
| SaaS | 5 | 2 | 14 | 1,385 | 16 |
| **합계** | **20** | **7** | **54** | **7,481** | **88** |

Instance는 편집 요소 수에 포함되고, 1,435개의 native VECTOR descendant는 별도로 센다. 오류 경로는 4개 app의 일반 404, Portfolio dynamic 404, Devtool·SaaS의 원본 dynamic 500을 포함한다. 각 case는 browser에서 측정한 source 응답이며 성공적인 native import와 동일한 개념이 아니다.

54개의 browser/native rendering 비교에서 채널별 절대 차이 평균은 0.29–24.13 범위였다. 이 수치는 글꼴 래스터화, 줄바꿈, animation frame과 지원하지 않는 CSS를 함께 반영하므로 pixel equality로 해석하지 않는다. 별도 mask fixture의 지정 sample points는 RGB 채널별 차이 최대 1이었다.

### Native 편집과 미디어 경계

실제 readback은 ALPHA mask 72개, DROP_SHADOW 1,978개, INNER_SHADOW 4개, LAYER_BLUR 106개, image fill 155개와 VECTOR descendant 1,435개를 확인했다. 108개 origin/request URL 조합의 asset pin을 hash 기준으로 다시 대조했다. 네 영상 source는 원본과 제한된 derivative 및 첫 frame fallback을 고정했다. 현재 유료 Team Figma 파일은 native VIDEO paint를 거절했으므로 실제 적용은 hash-pinned raster fallback이다. 이 파일에서 native video playback은 확인하지 않았다.

지원 범위는 box/inset shadow, bounded blur/drop-shadow, 90°·180° linear alpha mask, text gradient와 안전하게 정규화한 내부 SVG gradient/clip reference다. 임의 filter·mask, 외부 SVG paint reference, canvas의 시간 변화는 자동 복원을 보장하지 않는다. 외부 media fetch는 redirect를 거부하고 검토한 origin·정확한 request URL·응답 bytes의 hash를 요구한다.

### API 관측

0.30.0 baseline은 1,382개 member 중 150개를 관측하고 1,232개를 미관측으로 남겼다. 네 signed native read batch는 getter 488회를 시도해 473회 success, 10회 unavailable, 5회 unsupported, 0회 blocked였다. 새 exact member 39개를 추가해 누적 189개 관측, 1,193개 미관측이다. API priority score는 조사 순서를 정하고 runtime 지원을 보증하지 않는다. `d44a2a6`은 이미 관측된 exact audit member key 1–16개를 같은 receiver의 static allowlist로 재검사하는 private selection을 추가했다. 일반 작업은 계속 미관측 ranked queue를 사용하고, recheck key가 새 관측 사실을 만들지는 않는다. [sanitized overlay](../../specs/responsive-web/api-observations.json) · [queue guide](../../docs/api-priority.md)

### 검증 상태와 잔여

최종 제품 소스에서 Python 1,231개, Node 338개, finalize 75개·디자인 18개·데모 2개가 모두 통과했다. 원본 자료를 연결한 로컬 실행에서 건너뜀은 없었다. 최종 후보를 실제 Design 파일에서 다시 열어 54개 프레임과 main 연결을 확인했다. 별도로 이전 0.30.0 SaaS 프레임이 그대로 읽혔고, 이미 관측한 멤버의 읽기 39회가 모두 성공했다. 이 39회는 신규 관측 합계에서 제외했다.

브라우저 error state와 native Figma 오류 상태는 각각의 원본 응답·receipt 기준으로 분리한다. 유료 계정이 허용하지 않은 native VIDEO, unsupported CSS·SVG, pixel equality, 1,193개 미관측 API member는 0.31.0이 지원한다고 주장하지 않는다. [screen graph](../../specs/responsive-web/graph.json) · [browser/native verification](../../docs/responsive-web-verification.md) · [screen-scope recovery](patches/9974579407d29dd6072fcb9f1cf515115c954cb6.md)

## v0.30.0

0.30.0의 최종 제품 소스는 `c1541b8129bdf3e175dd905cddfed39acd52bc2e`다. 기능·검증·설치 예제는 두 manifest에 고정한 같은 버전을 사용한다. 태그와 ZIP은 [GitHub 배포 페이지](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.30.0)에서 확인할 수 있다. `v0.30.0` 태그는 문서 전용 발행 커밋 `f9453da79c5f57aa779096468cbf29286c7fb185`를 가리킨다. 이 커밋은 CHANGELOG와 Wiki/catalog를 발행하며 제품 소스 변경은 포함하지 않는다.

기능 간 인수 관계는 [editable web graph](../../specs/editable-web/graph.json)에 있고, 사용 범위와 실제 화면·native 결과는 [editable web verification](../../docs/editable-web-verification.md)에 있다.

| 인수 조건 | 실제 결과와 경계 |
| --- | --- |
| 웹 화면 캡처 | Portfolio·Codeforge·Devtool·SaaS 네 로컬 템플릿의 브라우저 화면을 문서 크기 그래프로 기록했다. 최종 graph에는 각각 508·492·38·20 요소가 있다. Codeforge 문서 높이는 11,677px다. CSS mask·filter·shadow, 외부 media, canvas·video, 복잡한 SVG와 지원하지 않는 배경 paint는 변환 대상이 아니다. |
| Figma 편집 가능한 화면 | 최종 shipping apply/readback 결과는 각각 512·526·41·23 editable node, 합계 1,102개다. 27개는 component instance이며 VECTOR descendant는 합계에서 제외했다. Devtool의 21 GeistSans alias 요청은 실제 Geist Regular·Bold·SemiBold로 해석됐다. Receipt에는 family rename이 fallback으로 기록된다. |
| 이미지와 벡터·그라디언트 | Portfolio 사진 8개(me.png 포함)와 Devtool 썸네일 3개에 대해 byte hash·파일 서명·native IMAGE fill·decode size를 확인했다. 네 개의 최종 Figma PNG 미리보기를 browser 결과와 육안 대조했다. 이는 pixel equality 측정이 아니다. Codeforge의 native radial fill 4개를 확인했고 Portfolio의 외부 SVG 3개는 가져오지 않았다. |
| 같은 그래프 재적용과 충돌 보호 | 네 stable screen ID를 같은 graph로 재적용해 변경 없는 결과를 확인했다. SaaS signup의 실제 메인 버튼 글꼴 크기를 14에서 16으로 바꾼 상태에서 같은 graph를 다시 적용해 사용자 편집 보존을 확인했다. 값을 14로 복원한 다음 재적용은 변경이 없었다. |
| 재적용과 사용자 편집 | 네 stable graph ID를 재적용해 변경 없는 결과를 확인했다. SaaS main 버튼을 14→16으로 바꾸고 같은 graph를 재적용해 편집값 보존을 확인한 뒤 14로 복구했다. 마지막 재적용은 쓰기 없이 끝났다. 네 그래프의 shipping-reused 결과도 변경 없음이다. |
| 컴포넌트 타이포그래피 재사용 | 20·24·20px line-height의 실제 button label을 native import했다. 첫 결과에서 세 번째 값이 20px로 잘못 재사용되는 문제를 재현했다. 수정 후 20/24px 값의 두 main과 첫 main을 재사용한 한 instance를 확인했고, 반복 적용은 변경 없이 끝났다. Instance range style 불일치는 검증에서 실패하고 새 객체를 정리한다. 집중 web-native 테스트 7개가 통과했다. |
| Figma 작업 이력 | 현재 native metadata 읽기에서 활성 task 54개를 확인했다. 이전 16개 test revision은 감사 이력으로 보존했다. 이 읽기는 해당 실제 workspace의 현재 상태만 확인하며 배포 설치 인수를 뜻하지 않는다. |
| Plugin API 관측 | 10개 실제 노드에서 236회 typed probe 호출, Codeforge Vector에서 17회를 수행했다. 253 probe 호출은 50개 고유 member에 대응한다. 추가 typography 실측은 19개 exact member ID를 읽었고, 이 중 10개가 기존 140 관측에 더해졌다. 현재 관측은 150/1,382, 미관측은 1,232다. 8개 전·후 graph audit 검사가 통과했다. |
| API 조사 우선순위 | 1,382개 pinned API audit member를 전체 inventory에 유지하고 관측 그래프의 exact-key 근거만 상태에 반영한다. 현재 기준은 관측 150개와 미관측 1,232개다. 순위 점수는 조사 순서이며 runtime 지원이나 성공 증거가 아니다. [API priority contract](../../docs/api-priority.md) |
| 집중 검증 | Web subsystem의 Python 8개와 native bridge Node 4개 검사가 통과했다. |
| 안정된 local release suite | 전용 stable clone에서 Python 1,215개, Node 326개, finalize 75개, design 18개, demo 2개가 모두 통과했고 건너뛴 검사는 0개다. Node의 마지막 세 검사는 native component identity, instance text readback, line-height mismatch rollback을 확인한다. 이 수치는 local suite 실행이며 원격 CI 성공을 뜻하지 않는다. |
| 이전 skip의 원본 자료 replay | `test_shadow_troupe_light_bars_are_placeholder_bars` 1 pass, `test_supplied_native_evidence_and_tampering` 1 pass, `actual saved initial Moss tint packet is rejected without writes` Node 16 pass. 각 결과의 skip 수는 0이다. 원래 clean checkout에는 Shadow Troupe layout, operator readback, Moss Choir packet이 없어 선택 테스트를 건너뛰었다. 실제 로컬 replay 절차는 [optional evidence tests](../../docs/optional-evidence-tests.md)에 있다. |

최종 브리지에서 줄 높이와 기존 프레임 호환성을 확인했다. 현재 브리지 단위 검사 9개가 통과했고, 전체 로컬 Node 실행은 328개로 늘었다. 올바른 폰트 별칭은 실제로 사용한 글꼴과 대조한다. 이전 버전에서 잘못 만든 레이블은 해당 요소를 보고하며 기존 프레임을 보존한다.

### 개인정보 정정

공개된 중간 commit의 테스트 fixture에 실제 Figma file locator가 들어 있었다. API token은 없었다. `cb392ce`가 그 값을 synthetic test identifier로 바꿔 현재 소스와 일반 archive에서 제거했다. 이전 Git object는 이력을 다시 쓰지 않아 남아 있으며, 이 기록은 locator 문자열을 복사하지 않는다.

이 자료는 네 템플릿과 제공된 native readback의 범위를 다룬다. 임의 웹사이트의 pixel parity, 모든 CSS·media의 변환, 공개 Figma 배포, installer 동작, 전 API의 runtime 지원은 검증하지 않는다. CSS masks·filters·shadows와 외부 media는 변환하지 않으며 외부 SVG 3개는 빠져 있다. GitHub Actions 실행, 배포 ZIP의 SHA-256 파일, 설치된 패키지의 자체 플러그인 읽기 결과를 별도로 확인한다.

## v0.29.0

제품 소스 `b1e4a06ca97450c729c134644f4fb99fc0af80e5`에서 한 graph의 선택된 노드·관계·상태를 세 에디터에 투영한다. 이전 0.28 배포의 세 원격 CI, 설치본 해시와 설치 후 실제 재읽기는 [0.28 발행 영수증](patches/5d3a088c6becc62fef08ecd0fc8fd857ed850957.md)에 기록했다.

| 인수 조건 | 실제 결과 |
| --- | --- |
| Design·FigJam·Slides 간 출처 일치 | 네 Magic UI 앱에서 만든 같은 graph의 20개 노드·16개 관계를 세 편집기에서 확인했다. Design은 역할별 main 4개를 재사용한다. FigJam은 표 1개·스티키 21개·셀 84개·코드 블록 1개·커넥터 16개를, Slides는 7행·21장·텍스트 42개를 반환했다. |
| 사용자 입력과 정본 보존 | 같은 원본 SHA에서 다른 부분 선택을 다시 열고 사용자 변경 충돌과 이전 산출물의 소유권을 확인했다. FigJam은 실제 코드 블록 폰트 오류를 수정했다. Slides는 과거 단일 마커와 기본 숫자 이름을 실제로 재현해 원래 71개 노드만 이관했다. |
| 앱·사진·글꼴 | 네 앱 각각을 프로덕션 빌드해 실제 브라우저에서 경력 아코디언, 월·연 과금 주기, 글 상세 이동, 로그인 → 가입 화면을 확인했다. 각 프로젝트의 같은 출처 캡처 에셋 22·12·5·6개가 정상 input record와 source freshness에 연결됐다. 외부 URL의 원본 바이트는 미확인으로 유지한다. |
| API 근거 | Design에서 9개 실제 노드에 141회 노드–멤버 조회, 고유 멤버 37개. FigJam·Slides 제작에서 추가 12개. 0.28의 78개와 합친 고유 멤버는 127/1,382(9.19%). 나머지 1,255개는 이 관측으로 입증하지 못했다. [관측 그래프](../../specs/graph-review/api-observations.json) |
| 구현·재현 | [정본 기능 그래프](../../specs/graph-review/graph.json), [API 조사 방법](../native-api-probe.md), [계승한 입력 형식](../html-asset-map.md), [고정 검사](patches/3fc3002553ecd2f8a3c35f89e68789938f1b76e3.md), [제품 패치](patches/b1e4a06ca97450c729c134644f4fb99fc0af80e5.md). |

원본 ZIP·제3자 템플릿 소스·로컬 서버 원시 응답·실제 Figma 파일 키는 공유하지 않는다. 제품 소스와 실제 후속 릴리스 설치를 구분하며, 정확한 공개 버전은 해당 GitHub 릴리스의 태그·ZIP 체크섬으로 확인한다.

깨끗한 checkout에서 Python 전체 1,195건 중 2건을 건너뛰고 통과했다. 추가 finalize 75건, 작은손 디자인 18건, 예제 2건도 통과했다. 최초 Node 실행에서 매개변수용 editor harness 두 개가 잘못 수집되어 [경로와 실제 호출자를 이관](patches/1fa5f0dd4386bfd46bd919284b946d39493ae857.md)했다. 수정 후 전체 Node 319건 중 318건 통과·1건 건너뜀을 확인했다. 고정된 재현 gate는 3fc3002의 예상 실패와 b1e4a06에서 동일 테스트의 통과를 확인했다.

## v0.28.0

기존 디자인 파일의 같은 페이지에서 소유 프레임을 재사용하고, 작은손의 예약 버튼 배경색을 그래프·Figma·브라우저 사이에서 왕복했다. 편집기·플랜·권한별 사용 경로, 컴포넌트 속성, 포크에서 실행할 생성기 및 회귀 검사를 공개한다.

| 확인 범위 | 관측과 한계 |
| --- | --- |
| 로컬 플러그인과 실제 Figma | 원래 96노드 중 ID·부모·위치·치수·채움·반응이 달라진 노드 0개. 재사용 프레임의 메인과 두 인스턴스가 같은 main을 가리켰고 반복 적용에서 변경 수가 0이었다. Smart Animate는 프레젠테이션에서 양쪽 점을 클릭해 이동·복귀를 확인했다. |
| 실제 Django 웹 | PostgreSQL 업무·설정 검사 59건 통과. 실제 브라우저에서 시작색 `#8e3e28`, 정방향 `#773925`, Figma 역수입 뒤 `#8e3e28`과 세 graph SHA를 각각 확인했다. 홈페이지에서 1600×900 사진과 Hahmlet WOFF2 요청을 관측하고 제목의 계산 글꼴을 대조했다. |
| 실패와 복구 | 생성 후 TEXT 조회 및 동기 main getter 실패, 이름 정규화 충돌, 오래된 CSS manifest를 재현하고 수정했다. 이전 읽기를 현재 버전으로 재사용하지 않고 새 getter와 브라우저 측정으로 pairing을 재발행했다. |
| 기준 회귀 | 실캡처 graph 유실과 컴포넌트 참조 누락 모두 각 검사 파일이 고정된 Git base/target에서 원래 실패와 수정 후 성공을 실행했다. G4 소스 커밋에서 전체 Python 1,170건 중 2건 건너뜀, finalize 75건 통과, Node 311건 중 310건 통과·1건 건너뜀, 예제 2건 통과. |
| 검증 경계 | 실제 플랫폼은 무료 표시가 있는 Figma 초안 파일의 기존 페이지와 실제 브라우저였다. 별도 Starter 팀 3페이지 제한의 파일, 두 번째 Figma 계정, 실물 모바일 기기, 모든 편집기와 계정 권한은 실측 범위 밖이다. |

상세 변경은 [공개 API와 속성 작성](patches/fad40b21f8fbb14209f50b3029bd656d40bbb1fe.md), [정책 영향·영속 CSS](patches/961f193437e3699a5fed679d14e9c49f7e799a0d.md), [실제 Figma·웹 왕복](patches/4c3b39218e5b214e0e21b762678a23dc55a3cd1f.md)에 기록했다. 동작을 재현할 [사용 안내](../guide.md)와 [Cursor용 후속 설계](../next-roadmap/README.md)를 함께 제공한다.

[오프라인 인계 팩](patches/7f37a138bae2b4c4977405352fab16f658dd03cf.md)에서 같은 임시 문구로 나타난 두 인스턴스를 발견해 [템플릿 기반 문구 교정](patches/42752d575ebe17ca5b10a176a29d6525719685b0.md)을 적용했다. 실제 네이티브 적용 2건, 다시 적용 0건을 확인했다. 최종 인계 HTML에는 JSON과 같은 관측이 들어 있고 자동으로 불러오는 외부 리소스는 0개였다. 로컬 파일 열기는 이 세션의 인앱 브라우저 프로토콜 정책으로 차단됐다. 공개 제품 ZIP에는 비공개 원시 getter·파일 키를 포함하지 않는다.

공개 Plugin API 1.142.0의 멤버 1,382개를 전부 대조했다. 0.28 개발 후보에서 실제 Figma 관측 78개, 소스·자동 검사로 추가 입증한 구현 3개, 컴파일까지 확인한 12개, 해당 내장 편집기 경로에서 미구현 6개, 경로 미지원 1개, 미확인 1,282개였다. v0.27.1에서는 소스·자동 검사로 14개를 입증했다. [공식 선언·실행 경로·미구현 목록](../../library/figma-api/audit/report.md)과 [상세 패치](patches/eeeeae315cca7b193a791969123ce09343c165e1.md)를 연결한다.

릴리스 조합의 깨끗한 별도 checkout에서 Python 전체 1,174건(2건 건너뜀), finalize 75건, Node 312건(311건 통과·1건 건너뜀), 예제 2건을 실행했다. 그 뒤 추가한 인벤토리 분모 검사는 실제 1,382개 재생성과 verify, 배포 fixture 변경은 해당 검사 두 건으로 따로 재검증했다. 로컬 ZIP 검사는 Git 트리의 모든 파일을 대조하고 실제 홈 경로와 비공개 작업 폴더 포함 여부를 검사한다.

배포 직전 ZIP 전수 검사에서 0.27.1부터 들어 있던 실제 Figma 파일 식별자를 보정 입력과 생성 DOM 맵에서 발견했다. [파일 지문으로 교체](patches/4db8c67d0f44f8be50b696ae7dc63d4e7f96a02a.md) 후 같은 캡처 44개와 디자인 검사 18개로 다시 확인했다. 새 아카이브에 대한 실제 비공개 값 7개 검사에서 일치 0건을 확인했다.

## v0.27.1

제품 소스는 `aa8b7191405b160d1119c403510152a12e0ae801`다. 구문·startup 수정은 `25b6f754a4798119defc65c5146d59e0d3f23467`, Intel 실행기는 `ee4f40a0eb3ceef5b87697a13b2768ae0dc1a67e`, CI DB 환경은 `6178905a1f182e5fcfe7b3fdf22fc57116544ea3`, WOFF2 의존성은 최종 소스에 있다.  [패치 상세](patches/25b6f754a4798119defc65c5146d59e0d3f23467.md)와 [고정 재현 검사](patches/23b44e3b3004639e088467bd91d808de24df38d7.md)를 연결한다. 두 manifest와 현재 설치 안내를 0.27.1로 맞췄다.

0.27.0 발행 후 앱 워크플로는 `--only-binary=:all: -r`의 콜론·공백 때문에 YAML 파싱에 실패해 job이 하나도 시작되지 않았다. 명령을 block scalar로 옮겨 실제 pip argv는 유지했다. 별도로 일반 Python 업데이트 명령이 검증할 패키지에 bytecode를 쓰는 실패를 재현했다. CLI 진입부가 local 모듈을 import하기 전에 bytecode 쓰기를 막으며, 파일 무시나 검증 우회 없이 기존 authority·정확한 바이트·rollback 검사를 유지한다.

로컬에서 YAML 파싱과 정확한 설치 명령 보존, startup 검사 27개, 일반 Python CLI 반복 실행의 전체 패키지 바이트 보존 1개, 진단 버전/runtime 검사 6개가 통과했다. 독립 정적 검수에서 지정 diff의 P1/P2를 찾지 못했다. 0.27.0 제품 소스의 깨끗한 전체 검사와 실제 앱·Figma R8 관찰은 영향을 받지 않은 범위의 근거로 재사용하며, 0.27.1 원격 CI·태그·최종 ZIP·설치본 및 native 재읽기는 아래 최종 실행 영수증에서 각각 확인한다.

첫 0.27.1 후보 `e75d60b`의 원격 앱 CI는 app이 읽지 않는 `DATABASE_URL` 때문에 기본 DB 포트로 접속하다 실패했다. [DB 환경 수정](patches/6178905a1f182e5fcfe7b3fdf22fc57116544ea3.md) 후 새 pinned PostgreSQL 17 컨테이너를 실제 CI와 같은 loopback 5432·workflow 환경으로 만들고 check·migration 확인·58개 업무 검사·4개 배포 검사를 모두 통과시킨 뒤 컨테이너를 제거했다. 이 local 리허설의 Python host는 Mac ARM이고 최종 Ubuntu AMD64 원격 결과와 구분한다.

같은 후보의 [전체 CI](https://github.com/jonsoku-dev/figma-flow/actions/runs/43339869559)는 WOFF2 글꼴을 열 때 Brotli 누락으로 중단됐다. 이전 clean Git archive 검사는 기존 Python 환경에 있던 Brotli를 사용했다. [FontTools WOFF extra](patches/aa8b7191405b160d1119c403510152a12e0ae801.md)를 선언하고 새 venv·시스템 site 차단·선언된 optional 의존성만으로 전체 파이프라인을 재실행한다. 새 venv에서 선언한 optional 의존성과 WOFF extra만 설치한 뒤 실제 글꼴 변환·디자인 16개·Python 1,107개(2 skip)·추가 Python 75개·Node 299개(1 skip)·demo 2개가 모두 실패 없이 끝났다. 11개 파이프라인 명령의 exit가 0이고 React·typed runtime 재빌드 파일은 원본과 byte-identical이었다. 이 결과는 `aa8b719`의 clean archive와 새 환경에 대한 local 관찰이며 원격 결과와 별도로 보존한다.

동일한 frozen CLI 검사로 base `23b44e3b3004639e088467bd91d808de24df38d7`의 bytecode 경로 AssertionError와 최종 target `aa8b7191405b160d1119c403510152a12e0ae801`의 통과를 확인했다. 개선 gate는 제품·후속 기록을 포함한 정확히 15개 변경 경로와 원본 불변성을 검사해 통과했다. Wiki는 canonical 222개·보존 39개 기록을 검증했다. 원격 CI·최종 패키지·설치·native 재읽기는 별도 판정한다.

### 최종 발행·설치·Figma 영수증

0.27.1 정식 태그는 `v0.27.1`이며 커밋 `42379a56d677ad29296ae3ae6495742a11fbaf43`를 가리킨다. 제품 소스 `aa8b7191405b160d1119c403510152a12e0ae801` 뒤의 문서 발행을 포함한 스냅샷이다. [정식 릴리스](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.27.1)는 latest stable로 확인했고 0.27.0 프리릴리스와 태그는 덮어쓰지 않았다. 이 영수증은 발행 이후 실행의 기록이므로 ZIP의 문서 스냅샷과 이후 main의 기록 시점을 구분한다. 제품 파일은 추가로 변경하지 않았다.

| 항목 | 실제 확인 결과 |
| --- | --- |
| 원격 전체 도구 CI | [43341749250](https://github.com/jonsoku-dev/figma-flow/actions/runs/43341749250) success. macOS 15 Intel에서 실제 Codex sandbox 검사, 빌드 동일성, design 16·Python 1,107(2 skip)·추가 Python 75·Node 299(1 skip)·demo 2 통과. |
| 원격 앱 CI | [43341749145](https://github.com/jonsoku-dev/figma-flow/actions/runs/43341749145) success. Ubuntu/PostgreSQL 17에서 업무 검사 58·배포 검사 4 및 AMD64 Docker build 통과. |
| 원격 Wiki CI | [43341749039](https://github.com/jonsoku-dev/figma-flow/actions/runs/43341749039) success. 해당 릴리스 소스와 기록 검증. |
| 배포 ZIP | `13,379,910` bytes, 공개 파일 `1,348`개. 실제 다운로드의 sidecar SHA와 원본 archive가 일치. SHA-256 `b063b013f841be59902a3acabab7c5276ea5636d6f4a030ca1303640660c1380`. |
| 배포 개인정보 확인 | 실제 staging 자격 정보·control/chat token·compiler key 8개 값을 ZIP과 대조해 0건 일치. 비공개 workspace·venv·원시 readback은 ZIP에서 제외. |
| Codex 설치 | 정상 업데이트의 반환 installedPath와 CLI 목록에서 0.27.1 installed/enabled 확인. 두 manifest와 공개 파일 1,348개가 ZIP과 일치. 개인 설치 경로는 공개 기록에서 제외. |
| 일반 시작 명령 | `-B` 없이 실제 설치본의 일반 Python `check` 및 `ensure --figma-access allowed --workspace ...` 실행 성공. Codex `current`, native `files-current`. 패키지 바이트·실행 속성과 이미 검증한 generation은 그대로 유지. |
| 기존 Figma 등록·작업 | 같은 등록을 유지. 기존 task key 31개를 보존하고 독립 R8 읽기 1개를 추가해 32개. 정상 replay로 32개 generator 파일을 현 설치본과 일치시킨 뒤 같은 플러그인을 재열었음. |
| 실제 로드 runtime | 설치본 경로에서 control server를 실행한 것을 프로세스 경로로 확인. 실제 HTTP readiness의 expected/observed version·implementation·generation이 모두 0.27.1 현 세대와 일치. 단순 파일 복사 성공으로 로드를 추정하지 않음. |
| 최종 실제 Figma 읽기 | `4,820`개 node ID·24 main·2 set·494 instance·Group 2·69 variable·collection 1 유지. 전체 파일 갱신 뒤 같은 discovery schema의 node·variable·collection 원시 레코드가 앞선 실제 설치본 읽기와 정확히 일치. |
| 최종 readback | `18,787,869` bytes, SHA-256 `c8d242150e1dc2ec90bba9486b8bc155cd5b63a8759e0fc5082e491e184bd4ea`. 보호된 원시 JSON과 운영 경로는 공개하지 않음. |
| 실제 Figma UI | 최신 읽기의 server queued→claimed→native-started→result-received와 같은 실행의 로컬 요청→실행 중→읽기 완료 3단계를 확인. 두 실행을 하나로 합치지 않음. |
| Figma 버전 기록 | `Figma Flow 0.27.1 · 설치본 재검증`을 일반 UI로 저장한 뒤 버전 내역의 제목·설명·저장 시점을 다시 관찰. 독립 원격 API에 의한 cloud save attestation과 구분. |

검증 보고서가 R8 입력 manifest를 갱신해 기존 source pin이 달라진 경우에는 기존 키를 버리거나 pin을 수동 수정하지 않았다. 원래 generator 인수와 현재 revision의 `prepare --replace-expected`에 해당하는 정상 CAS admission으로 현재 입력을 다시 고정한 뒤 준비 파일을 갱신했다. 보존된 과거 revision·영수증은 새 작업의 성공으로 재분류하지 않았다.

이전 direction readback과 discovery readback은 schema가 다르다. 공통 getter 76종의 값은 동일했고, `fontFamily` binding의 `[alias]`와 `alias` 표현 256건만 동일한 단일 alias ID로 엄격히 정규화했다. 새 collection의 `owner` 관찰 metadata는 원본 instance ownership과 맞았으며 기존 공통 값은 같았다. 이후 완전 갱신된 runtime끼리의 재읽기는 정규화 없이 원시 node·variable·collection 레코드가 동일했다. JSON schema 전체가 처음부터 같았다고 주장하지 않는다.

최종 공개 파일의 Figma JS/UI와 독립 앱 소스는 0.27.0 제품 검증 이후 바뀌지 않았다. 따라서 실제 44화면·3171 leaf bbox·550 clip·314 reaction의 기존 검증은 그 동일 소스 범위의 근거로 재사용하고, 설치/입력/환경 변경은 위 별도 실행으로 확인했다. 사용자 창작·production 승인은 생성하지 않았고 기존 NATIVE_REVIEW_PENDING/DRAFT 경계를 유지했다. BOOLEAN·INSTANCE_SWAP 양성 작성, 앱 영속 SSOT, 실기기, 공개 DNS/TLS 운영, 실제 채팅 첨부 전달, 기존 61-case 전체 및 모든 312 prototype link의 GUI 실행은 이 릴리스에서 완료로 승격하지 않는다. [후속 6개 기능·설계·Cursor 작업서](../next-roadmap/README.md)는 PROPOSED다.

## v0.27.0

[상세 patch page](patches/841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988.md)는 제품 소스 `841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988`를 기록한다. `plugin.json`과 `.codex-plugin/plugin.json`은 모두 0.27.0이며 catalog에는 이 버전을 가리키는 제품 커밋이 하나 있다. 이 0.27.0 제품 소스 시점의 catalog에서 도달 가능한 커밋은 215개, 전체 페이지는 215개, 첫 부모 대비 이 변경 경로는 347개다. CHANGELOG는 짧은 기능 요약을 제공하고 상세 변경·근거·미검증 범위는 patch page 및 [최종 인수 행렬](../development-roadmap/FINAL_ACCEPTANCE.md)에 있다.

제품은 실제 TEXT 속성·너비 기반 main 재사용, 선언 variant와 Group/Frame/Auto Layout 작성, revision/hash로 연결된 작업 dependency, 원자 선택 sync, CSS/image 자산 근거, full native read·제한된 transport/진단 export를 제공한다. 독립 Little Hands Django/PostgreSQL 앱은 별도 인증·예약·운영 트랜잭션과 패키징 경계를 둔다. 이 앱의 Figma prototype은 정적 화면이다.

보고된 검증 범위는 clean archive에서 root Python 1,107개 중 1,105개 통과·2개 skip·0개 실패, PostgreSQL backend 58개, packaging 4개, design 16개, finalize Python 74개, native demo 2개 성공과 Node 299개 중 298개 통과·1개 skip·0개 실패다. 14개 local 명령은 모두 exit 0이었다. React build 및 typed runtime의 배포 파일은 원본과 byte-identical이었다. 독립 frozen improvement gate는 정확히 347개 변경 경로에서 baseline AssertionError 재현 및 target diagnostic privacy·Group Python·partial consumer Node를 통과시켰고 checkout 원본을 유지했다. 별도 native 관찰은 44 screens/4,820 nodes, Group 2개, main 24개, component set 2개, instances 494개, variables 69개, 기존 Frame clip 550개, nonempty reaction node 314개(312 product + 2 palette)의 semantic target 보존, leaf geometry 3,171개의 bbox 차이 0이다. 이는 앱·플러그인 전체의 출시 인수나 모든 prototype 링크 실행을 뜻하지 않는다.

45 AC bounded pass는 45 REQ의 전체 긍정 구현이 아니다. BOOLEAN/INSTANCE_SWAP 양성 작성과 앱의 영속 Graph SSOT는 미구현이며 NF-01/NF-04 제안 범위다. 정적 prototype의 14개 실제 GUI 조작은 Django 업무 요청이 아니다. 실기기, 사람의 art/production 승인, 공개 DNS/TLS·상용 배포, 기존 61개 회귀 전체는 검증되지 않았다. 최종 local Python·frozen improvement gate는 통과했다. 원격 release, CI 및 설치 결과는 별도 확인 전까지 pending이다.

### 0.27.0 발행·설치 관찰

`v0.27.0`은 문서 발행 커밋 `e0aeed2ce67caf6570ba37bcf0beda22165cdc32`를 가리키고 제품 소스는 `841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988`다. [발행 기록](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.27.0)은 원격 최종 검사 전 프리릴리스로 전환했다. ZIP 13,356,051 bytes의 SHA-256은 `a937dc8b2eced24868371fbd4ab424efb4fd42e27623063966e960587f66d019`이며 실제 다운로드의 sidecar 검사가 통과했다. `plugin_startup ensure`는 최초 bytecode 변경에 따른 거절 뒤 검증된 기존 캐시 복원과 `-B` 재시도로 0.26.3→0.27.0 업데이트에 성공했다. 반환된 실제 installedPath의 공개 파일 1,340개가 ZIP과 byte-identical이었다. 기존 작업 공간·서버·R8은 유지했지만 이 0.27.0 설치본에서 native 재읽기는 하지 않았다.

[Patch knowledge CI](https://github.com/jonsoku-dev/figma-flow/actions/runs/43327580949)는 성공했다. [앱 워크플로](https://github.com/jonsoku-dev/figma-flow/actions/runs/43327579170)는 YAML 문법으로 job 시작 전에 실패했고 0.27.1에서 수정한다. [전체 도구 CI](https://github.com/jonsoku-dev/figma-flow/actions/runs/43327581031)는 초기 queued 뒤 ARM hosted runner 공급 부족으로 job을 받지 못해 취소됐다. [macOS Intel 실행기 변경](patches/ee4f40a0eb3ceef5b87697a13b2768ae0dc1a67e.md)은 같은 OS 검사와 명령을 보존하며 0.27.1에서 재실행한다. 이 상태를 안정 릴리스 전체 통과로 표시하지 않는다.

## v0.26.3

[이력 UI와 고정 재현 기준](patches/fce49dadaf9600e3c9855046ba48411ee5e581c1.md), [실패 기록 수정](patches/6a50f5c0aea3e8a131e0698151875cd83102ed69.md)을 포함한다. 제품 소스 기준은6a50f5c다. 이 기록 시점에는 실제 Figma의0.26.3 후보 UI를 확인했으며 태그·ZIP·최종 Codex 설치·원격 CI는 발행 이후 실제 릴리스와 호스트 기록으로 확인한다.

작업 목록과 이력에서 현재 task revision의 마지막 상태를 분포와 정확한 수로 보여준다. 같은 dispatch의 요청·진행·결과는 host가 생성한 실행 ID와 task/revision으로 연결한다. legacy는 비연결 시간순 기록으로 남기며 전체 원본 event 요약을 펼칠 수 있다. 필터와 작업 링크는 해당 실행으로 초점을 옮긴다. 짧은 펼침 feedback과 reduced-motion CSS를 기존 테마 안에 포함한다. 다운로드·채팅·옛 revision을 현재 완료 수로 세지 않으며 제품 인수 완료율을 표시하지 않는다.

컴포넌트 속성·재사용, 의미 계층과 Frame/Group/Auto Layout, 작업 dependency, 선택 동기화, 자산 목록, 네이티브 읽기 최적화, runtime 모듈 경계, 실행 수명주기·복구8항목을 [개별 기능서·설계서·작업서27문서](../development-roadmap/README.md)로 제공한다. [Cursor 전달서](../development-roadmap/CURSOR_HANDOFF.md)에 실제 소유 코드·작업 순서·검사·보고 형식을 연결한다.

이후 [세 문구 검사 기준](patches/7260d2995764d65d736aed031ddc63323ecf4e0c.md)과 [일반 가져오기 문구 속성](patches/1f80e5d9896e85afb865919aad7dad3572be932e.md)을 추가했다. 같은 컴포넌트의 화면 문구는 반환된 TEXT 속성 key로 설정되고, 같은 패킷의 재가져오기는 기존 ID와 사용자 수정을 유지한다. 그 종료 게이트는 기준 종료 코드 1, 대상 `tests.test_figma_bridge` 25개 종료 코드 0이다. 실제 Figma 속성 패널은 새 Design 캔버스가 열리지 않아 관찰하지 못했다.

[너비 재사용 기준](patches/76a2d2b73a1d71631abe6f717073d15068c08155.md)과 [너비 공유](patches/640ff8c1a0ae1f185a60be5284558d6e7c914deb.md)는 root 너비만 다른 세 사용처를 한 main에 두고, 자식 transform·높이 차이는 별도 Layout main으로 남긴다. 그 종료 게이트는 기준 종료 코드 1, 대상 oracle 종료 코드 0이다. 실제 Figma 렌더는 관찰하지 않았다.

[선언 축 기준](patches/008c01c64e41b255c43b7e81e4029f4368b1f797.md)과 [축 연결](patches/0ff91654bd6867c816292a9fbac8561d474644d8.md)은 `axes.json`의 size·state를 기존 variant에만 연결한다. 선언되지 않은 조합·사용 설명·swap target은 만들지 않는다. 그 종료 게이트는 기준 종료 코드 1, 대상 종료 코드 0이다. 실제 Figma variant 패널은 관찰하지 않았다.

[진단 기록 기준](patches/015f440ee635d817f033dddabb504acaea69895f.md)과 [진단 기록](patches/73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2.md)은 그래프 패널에서 진단 기록을 마크다운과 JSON으로 복사하거나 저장한다. 비밀값은 가리고 노드 ID·리비전·오류·작업 식별자는 남긴다. 그 종료 게이트는 기준 종료 코드 1, 대상 종료 코드 0이다. 실제 Figma 패널은 관찰하지 않았다. RD-09 상태는 제안으로 남아 있다.

독립 검수에서 발견된 중복 실패와 remote validation 누락은 같은 고정 oracle로 실제 기준 AssertionError 종료1·대상 종료0을 확인했다. 자동 검사와 실제 브라우저320/560/840px, light/dark, 필터·키보드·빈 상태는 별도 확인했다. 실제 Figma에서 새 실행의3단계 연결과127노드·변수·collection·3이미지테이블 보존을 읽었다.15개 task key를 유지하고 UI artifact 변경에 따라 revision을 다시 생성했으므로 기존 이력은 과거 revision으로 남는다.

Python1,072개 중1,070통과·2skip, Node229개 중228통과·1skip, 데모2통과다. OS reduced-motion 설정 전환은 실제 관찰하지 않았고 CSS rule을 확인했다. 기존61개 회귀 전체, 실기기, 데스크톱 원본 첨부 UI, 실제200%확대, 클라우드 저장과 font binary 동일성은 완료로 승격하지 않는다.

## v0.26.2

v0.26.1 태그 뒤 [CSS 간접 의존성 수정](patches/f3ec102c6dbe436495ff15391f599cddfd86a449.md), [이미지 테이블과 중단 보호](patches/bd511d743a228b0a71ea4a0fc5e2a92e8c0920ff.md), [실제 생성 조사 경로 보완](patches/e179df281a870086582ad25cf649931af5a8eaa2.md), [검증 근거 보존](patches/1cfe00b16c17ebeaa4b4cc8bddbede6ecc64222d.md)을 포함한다. 코드 기준은 e179df2, 기록·스펙 근거 기준은1cfe00b이다. 이 소스 시점에는0.26.2의 원격 CI·태그·배포·최종 설치가 아직 실행 전이다. 발행 뒤 `git rev-parse v0.26.2^{commit}`와 `gh release view v0.26.2` 및 호스트의 실제 설치·읽기 기록으로 확인한다.

로컬 HTML/CSS의 중첩·인라인 `@import`, 확장자 없는 CSS, 사진·글꼴 `url()`과 부재를 추적한다. tinycss2를 선택 의존성에 추가했으며 v1/v2 입력 결과는 v3로 재준비한다. 전체 CSS cascade·동적 JS·외부 자산 수집이나 임의 HTML importer로 범위를 넓히지 않는다.

네이티브 페이지 조사마다 실제 `IMAGE.imageHash`로 바이트 읽기를 공유하고 `rasterImages` 테이블과 `rasterImageRef`를 전달한다. 여러 페이지의 테이블을 합칠 때 같은 hash의 다른 바이트는 거절한다. Python 정상화는 원본 JSON을 바꾸지 않고 복사한 행에 바이트를 해석하며 기존 인라인 읽기도 지원한다. paint/ref 일치와 원래 자산의 실제 SHA 비교는 계속 필요하다. 2,000,000바이트 동기화 한도·12MiB 제어 읽기 한도를 올리지 않았다.

실제 동일 페이지의 읽기 전후를 각5회 확인했다. 화면당 사진 수는 두 상태×두 뷰포트이므로 실제 사진 노드 수와 구분한다. 아래 값은 실제 제어 읽기에서 저장한 UTF-8 JSON 크기이며 전체 앱 동기화 완료나 모든 고유 이미지의 한도 충족을 뜻하지 않는다.

| 화면당 사진 | 실제 사진 노드 | 수정 전 바이트 | 수정 후 바이트 | 감소 |
|---|---:|---:|---:|---:|
| 1 | 4 | 947,050 | 484,869 | 48.80% |
| 6 | 24 | 4,105,712 | 560,531 | 86.35% |
| 14 | 56 | 9,157,631 | 679,650 | 92.58% |

시간 측정은 전후 교차 실행이 아니므로 속도 향상으로 판정하지 않는다. 모든 성공 표본에서 실제 사진 SHA를 확인했고, 기존 노드·변수·명세의 현재 값은 전송 표현 외에 유지됐다. 별도의 새0.26.2 패킷은 네 프레임의 정상 생성·최종 메타데이터·전체 검증, 독립56사진/8명세 전달, 같은 페이지의 재실행, 실제 Desktop 프로토타입의 두 뷰포트 왕복을 통과했다.

중단 시점에는 페이지 소유 완료 표시가 없을 수 있어 새 페이지에 논리 패킷 예약을 먼저 기록한다. 같은 미완료 논리 패킷은 렌더러가 바뀌어도 차단한다. 이전 완료 페이지의 호환성과 실제 flow 시작점·후기 메타데이터를 검사하되, 현재 명세·보드의 정상 검증을 대신하지 않는다. 실제 부분 시안의 같은 패킷 요청은 기존 페이지 ID를 포함한 오류로 거절됐고 페이지 수와127개 노드가 유지됐다. 과거 미확인 생성 응답은 성공으로 고치지 않았다. 기존 수정 경로로 빠진8명세만 복구했으며 페이지의 최종 생성 메타데이터를 임의로 복원하지 않았다. 원래 중단의 정확한 유발 원인은 확정하지 않았다.

고정 기준은 [CSS oracle](patches/ab1c8200cd77e2c24a3e322ddde643d80b179239.md), [이미지·부분 페이지 oracle](patches/ce10c8591bda9ad100c5de7a0f5323f20f5827c9.md), [생성 조사 경로 oracle](patches/3932393cfd5cdb40edf38f0ecbc8f997cf7a9bbf.md)에서 먼저 보존했다. 로컬 전체 검사는 Python1,072개 중1,070통과·2건너뜀, Node224개 중223통과·1건너뜀, 데모2통과다. 스펙 근거 변경 뒤의 별도 회귀25개도 통과했다. 중복 집계를 총수에 더하지 않는다. 원격 CI와 최종 설치는 이 제품 소스 기록 이후 별도 실행이다.

회귀61개 전체 인수 상태는 계속 unverified다. 실제 기기 없음, 데스크톱 채팅 원본 첨부 UI, 실제 브라우저200%확대, Figma 클라우드 저장·글꼴 바이너리의 독립 동일성은 이 검증의 통과 범위가 아니다. CLI `--image`는 새 합성 이미지를 실제 전달한 별도 경로이며 HTML/글꼴의 데스크톱 첨부 UX로 계산하지 않는다.

## v0.26.1

태그 `v0.26.1`의 실제 대상은 `25b17f9cc0cd13f73f4545403fbef0f9d6ba1a6c`이다. [0bd8177 자산/사진 수정](patches/0bd817701f3df66673e314007f768a6de404fd78.md), [e3bb050 지식 시스템·검증표·버전 통합](patches/e3bb0505b011f77a656e096b821c7d0d01f2990c.md), [25b17f9 기록 발행](patches/25b17f9cc0cd13f73f4545403fbef0f9d6ba1a6c.md)을 포함한다. 이후 source 문자열0.26.1을 유지한 CSS 수정은 이 태그에 들어 있지 않으며0.26.2에 포함된다.

직접 로컬 의존성 신선도와 안전한 URL 해석, 실제 네이티브 사진 바이트·형식·크기 검사, 정상 사진·글꼴 예제, reactions/clipsContent getter, 바이너리 MIME을 보완한다. 입력 결과 v2로 재준비해야 하며 임의 HTML importer·글꼴 업로드가 아니다.

검증표 `specs/regression-program/cases.json`의61개 케이스는 모두 unverified로 유지하며183개 부분 근거 참조와 연결한다. 참조가 연결됐다는 사실을 각 케이스의 전체 통과나 현재 배포의 실기기·실제 사용자 첨부 성공으로 해석하지 않는다. 해당 증거는 소유자의 로컬 자료이며 배포 Wiki에 원시 자료를 복사하지 않는다. 원시 브라우저/Figma 실행은 이 기록 보완에서 새로 실행한 결과가 아니다. 지식 시스템과 제품 전체의 실행 검사·잔여 한계는 e3bb050 상세 기록에 연결한다.

## v0.26.0

여러 네이티브 시작점·연결 기획·정밀 실측·작업 은퇴·시작 복구를 통합한다. 마지막0bd8177은 매니페스트가0.26.0이지만 v0.26.0 태그 뒤 변경이므로 0.26.1 항목으로 별도 연결한다.

태그 `v0.26.0`의 실제 대상은 `90f9195600dd54131c80a817bebdd88fd63fe52a`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [8f2d51b](patches/8f2d51b5a65d01a5e161a6158e4766934fc28ad0.md) feat: complete connected multi-page native review.

- [6969e5d](patches/6969e5dafccef185256c6f02f42b66b9f3636074.md) fix: isolate native intrinsic text measurements.

- [ad05cd3](patches/ad05cd323ec85de8647e81f1a5f07c1c25df50b3.md) fix: measure fresh text and retain live result readiness.

- [2bc6875](patches/2bc687579e5059cba6702bc5c4a2690c9e34b509.md) feat: archive obsolete prepared tasks by revision.

- [ea574f6](patches/ea574f67f1a2fe1ba75f1ce767829d5b6af591d2.md) fix: measure browser pixels without CSS string loss.

- [e384376](patches/e3843766a60d3356cb1964f633609fbe101fdb83.md) docs: record current native and round-trip verification.

- [a9521a8](patches/a9521a82e965865cac74777b747dd26260532173.md) fix: retain recovered native state during startup checks.

- [90f9195](patches/90f9195600dd54131c80a817bebdd88fd63fe52a.md) docs: reconcile final startup verification count.

- [0bd8177](patches/0bd817701f3df66673e314007f768a6de404fd78.md) fix: verify linked assets and native photo readback.

## v0.25.0

여러 앱 화면의 실측, 투명 제어와 분산 간격, 실행 중 작업공간 게시 차단을 연결한다. 태그 이후61c0b1e도 같은 버전 문자열을 사용하지만 태그에 포함되지 않은 후속 변경이다.

태그 `v0.25.0`의 실제 대상은 `f64d9a9e592343a0910cec236d358cd841b8e207`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [0ee0a24](patches/0ee0a24c5955e52dfb6f8f183bb6ac813252b446.md) Verify component evidence across mounted app screens.

- [0b2ad20](patches/0b2ad20d935fbf2d7e4d5406c806a1e12697c6a5.md) Preserve transparent controls and native distributed spacing.

- [f64d9a9](patches/f64d9a9e592343a0910cec236d358cd841b8e207.md) Keep workspace publication behind active native runs.

- [61c0b1e](patches/61c0b1ea79abda7b258459e245a1187e1ecc0314.md) Keep readable specifications, direct drafts, and panel identity on shared sources so locales, rem, and display name stay one contract. Record the regression program that locks those checks..

## v0.24.1

오래된 pairing 표식의 가져오기를 거절하고 로컬 제어 서버를 사전 확인한다. 이후 동작이나 다른 버전의 준비 상태까지 이 태그로 검증한 것으로 간주하지 않는다.

태그 `v0.24.1`의 실제 대상은 `3d44aa2aae27fc8032c7e0d88ecfa02d124cbc19`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [3d44aa2](patches/3d44aa2aae27fc8032c7e0d88ecfa02d124cbc19.md) Reject stale discovery imports and preflight control servers.

## v0.24.0

선택한 풍부한 디자인의 본제작·대비·native-edit·웹 동기화와 가이드 통합이 함께 들어간다. 태그는 통합 가이드 커밋을 가리키며 앞선 구현도 조상으로 포함한다.

태그 `v0.24.0`의 실제 대상은 `347a1762edc0e6738346f59d34b9a7e749659a71`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [9f67a2b](patches/9f67a2b638697a6a6ccc5a75353b83325bb2c38e.md) Promote selected rich designs and verify native web sync.

- [347a176](patches/347a1762edc0e6738346f59d34b9a7e749659a71.md) Unify the guide and allow the dedicated browser automatically.

## v0.23.1

컴포넌트 속성 키 복구와 앞·뒤 아이콘, 실제 문구·배치 대조를 보완한다. 정적 회귀 검사와 실제 Figma 관찰을 별도 근거로 기록한다.

태그 `v0.23.1`의 실제 대상은 `2233e0af3732229d36e806063973875a043188f5`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [2233e0a](patches/2233e0af3732229d36e806063973875a043188f5.md) Preserve native button icons and verify control labels.

## v0.23.0

React 작업대와 범위가 제한된 제어 relay를 도입한다. 태그 뒤의 글꼴 안내 커밋도 같은 버전을 사용하므로 배포 태그의 포함 범위와 구분한다.

태그 `v0.23.0`의 실제 대상은 `7d2f41d9652ad228d42e9a1aec813c76b4ed204d`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [7d2f41d](patches/7d2f41d9652ad228d42e9a1aec813c76b4ed204d.md) Build the accessible React workbench and scoped Codex control relay.

- [e4e9d5d](patches/e4e9d5d866f8805cc52181cae76b7484e4ade3b3.md) Document font setup without Computer Use.

## v0.22.0

단일 작업공간·채팅 연결·회복 경로와 텍스트 스타일 보존이 태그 없는 여러 커밋에 이어진다. 로컬 통합본이라는 원래 분류를 유지한다.

현재 기준 이 버전의 Git 태그는 없다. 릴리스 커밋을 태그로 확정할 수 없다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [bf04926](patches/bf049266356987b6abbf62533a5d3b0f9c549b8b.md) Unify prepared Figma workflows and link tasks to their Codex chat.

- [3f01ec3](patches/3f01ec317a307f179bacb8b546f3ebeecaab5a0f.md) Integrate unified Figma workspace with pinned skill distribution.

- [b52d107](patches/b52d107dbd5cbabb0524985462f924517dda1a57.md) Align installation guide with the integrated release.

- [93ec9aa](patches/93ec9aae6ed9e16508b8a9b600ec6a1bedc8e779.md) Recover relay receipts without blocking new requests.

- [791378c](patches/791378c941b08d1cd6274b690a756fa3a5c8f45e.md) Document ownership and native checks for workspace tasks.

- [9a7a37f](patches/9a7a37ff3578f0e429e23ba9549f60d40bf71042.md) Load only the existing review page before traversing it.

- [212cb0b](patches/212cb0b57719410694bd369823c679d6a26bdbf8.md) Preserve linked typography through scoped adoption and rollback.

## v0.21.1

0.20.1의 요청 경계 테스트 수정을 보존한 병합 버전이다. 당시 설치 대조 보고와 실제 배포·실행 근거는 구분한다.

현재 기준 이 버전의 Git 태그는 없다. 릴리스 커밋을 태그로 확정할 수 없다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [b1dd1d3](patches/b1dd1d3240435d48cb9f116ca4c1654f210a340c.md) Preserve upstream request-boundary test fix in 0.21.1.

## v0.21.0

Graph SSOT와 동봉 스킬 변경을 병합한 로컬 통합 버전이다. 부모 커밋을 포함한 두 갈래 이력을 대조하며 병합 자체를 별도의 런타임 검증으로 세지 않는다.

현재 기준 이 버전의 Git 태그는 없다. 릴리스 커밋을 태그로 확정할 수 없다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [e30b9a4](patches/e30b9a4ffc64f294d1404498f3c9171c313b5faa.md) Integrate graph SSOT and bundled skill setup for 0.21.0.

## v0.20.1

ad7f9b8에서 plugin.json은0.20.1, .codex-plugin/plugin.json은0.20.0으로 서로 다르다. 당시 두 값을 그대로 보존하며 현재 기록에서 소급 교정하지 않는다. 요청 크기 경계 테스트의 경쟁 제거 패치다.

태그 `v0.20.1`의 실제 대상은 `ad7f9b8604734a64f843179ed9f4f4a00bbfca9b`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [ad7f9b8](patches/ad7f9b8604734a64f843179ed9f4f4a00bbfca9b.md) Verify oversized request rejection before uploading its body.

## v0.20.0

병렬 작업의 매니페스트 버전과 병합 후 버전이 겹친다. Graph SSOT·동봉 스킬·원문 바이트 보존과 병합을 각 커밋으로 기록한다. 태그 대상과 버전 문자열이 같다는 사실은 동일 diff를 뜻하지 않는다.

태그 `v0.20.0`의 실제 대상은 `3c6a0f004ed0a1994a55bc98e59f0efa7647d377`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [b605165](patches/b605165745eee3a4d1f94c3a8677f05a4d7302e3.md) Use pinned bundled skills and remove music taste.

- [0173535](patches/01735351c2d82f1372442192b9bf14fa6f049a74.md) Preserve vendored bytes across Git checkouts.

- [9d10cff](patches/9d10cff7bc1b7287e8eb24e8ad56ff915302cf89.md) Integrate current main without replacing concurrent repository work.

- [8c94145](patches/8c9414594854f99a2d57d00088383f901e465409.md) Document graph-owned component design and synchronization scope.

- [3c6a0f0](patches/3c6a0f004ed0a1994a55bc98e59f0efa7647d377.md) Make canonical graph synchronization the release entry point.

- [ad7f9b8](patches/ad7f9b8604734a64f843179ed9f4f4a00bbfca9b.md) Verify oversized request rejection before uploading its body.

## v0.19.1

태그 없는 로컬 업데이트다. a787647의 브라우저 설정과 b27dffc의 동봉 원문은 같은 매니페스트 버전이지만 별도 변경이다. 기존 CHANGELOG의 설치 경로 수정과 이 커밋 관측을 구분한다.

현재 기준 이 버전의 Git 태그는 없다. 릴리스 커밋을 태그로 확정할 수 없다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [a787647](patches/a787647678eb3d8369bbdc9930a18b90427ed122.md) Add Unslop review and portable browser MCP setup.

- [b27dffc](patches/b27dffc2e923347831d30368faaf8136f2cc3b54.md) Vendor pinned design skill sources and licenses.

## v0.19.0

CHANGELOG는 Unslop·브라우저 설정을 설명하지만 당시 4a6314c의 매니페스트는 Graph SSOT 작업에도 이 버전을 쓴다. 버전만으로 변경 소유 범위를 추정하지 않고 각 커밋의 실제 diff를 확인한다.

현재 기준 이 버전의 Git 태그는 없다. 릴리스 커밋을 태그로 확정할 수 없다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [4a6314c](patches/4a6314c0584daf8ae1615ea73d8e3d79b60a73f6.md) Make graph tokens canonical for scoped native and web component sync.

## v0.18.2

실제 글자 기하·재사용 제어·pluginData 분할과 설치 안내를 보완한다. 버전 이름은 실제 기기 실행 결과의 증거로 쓰지 않는다.

태그 `v0.18.2`의 실제 대상은 `10a379463f5bfa8af845420d3c3936b4b211596d`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [10a3794](patches/10a379463f5bfa8af845420d3c3936b4b211596d.md) Verify real Figma text geometry and preserve design system controls.

- [1f8d203](patches/1f8d203dff972a1c98b8b2a49d5d0d20a838d80e.md) docs: add private setup and Figma onboarding.

## v0.18.1

첫 공개 릴리스로 구현과 설치 가이드·CI를 가져온다. 뒤따르는 CI 실행 환경 수정도 같은 버전 문자열을 쓰며 태그 포함 여부는 커밋 조상 관계로 확인한다.

태그 `v0.18.1`의 실제 대상은 `f18f8f53dfdadd89db0781d13d404ab4b8bc3d0c`이다.

당시 매니페스트에서 이 버전이 관찰된 커밋은 다음과 같다.

- [aa3acdd](patches/aa3acddf626642b7bf0db2f04730cab9cc533a4b.md) Release Figma Flow 0.18.1 with the desktop setup guide.

- [d7b345b](patches/d7b345b57af0ae0ed73b50db0740696fe2bd46b2.md) Install the real Codex sandbox CLI in CI.

- [f18f8f5](patches/f18f8f53dfdadd89db0781d13d404ab4b8bc3d0c.md) Run confinement checks with the native CLI on macOS.

## v0.18.0

CHANGELOG가 보존한 로컬 릴리스다. canonical Git에는 이 버전의 독립 커밋이 없고 다음0.18.1에서 구현이 일괄 반입된다. 삭제 전 bundle의 [0.18.0 구현](legacy/patches/f33249fa960d8666dfda75be5b493de4846bb6a4.md)은 아래 보존 이력에서 정확한 전체 커밋과 대조한다. canonical과 별도 계보를 섞어 버전 태그를 만들지 않는다.

현재 기준 이 버전의 Git 태그는 없다. 릴리스 커밋을 태그로 확정할 수 없다.

매니페스트와 대응하는 원본 커밋은 미상이다. [초기 Git 기준선](patches/07d32a81eb3523babd7d4039cdb6a39857b7517c.md)과 다음 버전의 일괄 반입 기록을 참조한다.

## 전체 커밋 연결

버전 추정과 무관하게 루트·merge·문서 수정까지 모든 도달 가능한 커밋을 연결한다.

- [07d32a8](patches/07d32a81eb3523babd7d4039cdb6a39857b7517c.md) first commit.

- [aa3acdd](patches/aa3acddf626642b7bf0db2f04730cab9cc533a4b.md) Release Figma Flow 0.18.1 with the desktop setup guide.

- [d7b345b](patches/d7b345b57af0ae0ed73b50db0740696fe2bd46b2.md) Install the real Codex sandbox CLI in CI.

- [f18f8f5](patches/f18f8f53dfdadd89db0781d13d404ab4b8bc3d0c.md) Run confinement checks with the native CLI on macOS.

- [10a3794](patches/10a379463f5bfa8af845420d3c3936b4b211596d.md) Verify real Figma text geometry and preserve design system controls.

- [1f8d203](patches/1f8d203dff972a1c98b8b2a49d5d0d20a838d80e.md) docs: add private setup and Figma onboarding.

- [a787647](patches/a787647678eb3d8369bbdc9930a18b90427ed122.md) Add Unslop review and portable browser MCP setup.

- [b27dffc](patches/b27dffc2e923347831d30368faaf8136f2cc3b54.md) Vendor pinned design skill sources and licenses.

- [b605165](patches/b605165745eee3a4d1f94c3a8677f05a4d7302e3.md) Use pinned bundled skills and remove music taste.

- [0173535](patches/01735351c2d82f1372442192b9bf14fa6f049a74.md) Preserve vendored bytes across Git checkouts.

- [4a6314c](patches/4a6314c0584daf8ae1615ea73d8e3d79b60a73f6.md) Make graph tokens canonical for scoped native and web component sync.

- [9d10cff](patches/9d10cff7bc1b7287e8eb24e8ad56ff915302cf89.md) Integrate current main without replacing concurrent repository work.

- [8c94145](patches/8c9414594854f99a2d57d00088383f901e465409.md) Document graph-owned component design and synchronization scope.

- [3c6a0f0](patches/3c6a0f004ed0a1994a55bc98e59f0efa7647d377.md) Make canonical graph synchronization the release entry point.

- [e30b9a4](patches/e30b9a4ffc64f294d1404498f3c9171c313b5faa.md) Integrate graph SSOT and bundled skill setup for 0.21.0.

- [ad7f9b8](patches/ad7f9b8604734a64f843179ed9f4f4a00bbfca9b.md) Verify oversized request rejection before uploading its body.

- [b1dd1d3](patches/b1dd1d3240435d48cb9f116ca4c1654f210a340c.md) Preserve upstream request-boundary test fix in 0.21.1.

- [bf04926](patches/bf049266356987b6abbf62533a5d3b0f9c549b8b.md) Unify prepared Figma workflows and link tasks to their Codex chat.

- [3f01ec3](patches/3f01ec317a307f179bacb8b546f3ebeecaab5a0f.md) Integrate unified Figma workspace with pinned skill distribution.

- [b52d107](patches/b52d107dbd5cbabb0524985462f924517dda1a57.md) Align installation guide with the integrated release.

- [93ec9aa](patches/93ec9aae6ed9e16508b8a9b600ec6a1bedc8e779.md) Recover relay receipts without blocking new requests.

- [791378c](patches/791378c941b08d1cd6274b690a756fa3a5c8f45e.md) Document ownership and native checks for workspace tasks.

- [9a7a37f](patches/9a7a37ff3578f0e429e23ba9549f60d40bf71042.md) Load only the existing review page before traversing it.

- [212cb0b](patches/212cb0b57719410694bd369823c679d6a26bdbf8.md) Preserve linked typography through scoped adoption and rollback.

- [7d2f41d](patches/7d2f41d9652ad228d42e9a1aec813c76b4ed204d.md) Build the accessible React workbench and scoped Codex control relay.

- [e4e9d5d](patches/e4e9d5d866f8805cc52181cae76b7484e4ade3b3.md) Document font setup without Computer Use.

- [2233e0a](patches/2233e0af3732229d36e806063973875a043188f5.md) Preserve native button icons and verify control labels.

- [9f67a2b](patches/9f67a2b638697a6a6ccc5a75353b83325bb2c38e.md) Promote selected rich designs and verify native web sync.

- [347a176](patches/347a1762edc0e6738346f59d34b9a7e749659a71.md) Unify the guide and allow the dedicated browser automatically.

- [3d44aa2](patches/3d44aa2aae27fc8032c7e0d88ecfa02d124cbc19.md) Reject stale discovery imports and preflight control servers.

- [0ee0a24](patches/0ee0a24c5955e52dfb6f8f183bb6ac813252b446.md) Verify component evidence across mounted app screens.

- [0b2ad20](patches/0b2ad20d935fbf2d7e4d5406c806a1e12697c6a5.md) Preserve transparent controls and native distributed spacing.

- [f64d9a9](patches/f64d9a9e592343a0910cec236d358cd841b8e207.md) Keep workspace publication behind active native runs.

- [61c0b1e](patches/61c0b1ea79abda7b258459e245a1187e1ecc0314.md) Keep readable specifications, direct drafts, and panel identity on shared sources so locales, rem, and display name stay one contract. Record the regression program that locks those checks..

- [8f2d51b](patches/8f2d51b5a65d01a5e161a6158e4766934fc28ad0.md) feat: complete connected multi-page native review.

- [6969e5d](patches/6969e5dafccef185256c6f02f42b66b9f3636074.md) fix: isolate native intrinsic text measurements.

- [ad05cd3](patches/ad05cd323ec85de8647e81f1a5f07c1c25df50b3.md) fix: measure fresh text and retain live result readiness.

- [2bc6875](patches/2bc687579e5059cba6702bc5c4a2690c9e34b509.md) feat: archive obsolete prepared tasks by revision.

- [ea574f6](patches/ea574f67f1a2fe1ba75f1ce767829d5b6af591d2.md) fix: measure browser pixels without CSS string loss.

- [e384376](patches/e3843766a60d3356cb1964f633609fbe101fdb83.md) docs: record current native and round-trip verification.

- [a9521a8](patches/a9521a82e965865cac74777b747dd26260532173.md) fix: retain recovered native state during startup checks.

- [90f9195](patches/90f9195600dd54131c80a817bebdd88fd63fe52a.md) docs: reconcile final startup verification count.

- [0bd8177](patches/0bd817701f3df66673e314007f768a6de404fd78.md) fix: verify linked assets and native photo readback.

## 별도 보존 계보

[삭제 전 bundle의 조사와 이식 근거](legacy/README.md), [19개 head와 추가39개 커밋 목록](legacy/index.md)을 연결한다. 이전0.18.1 head와 canonical aa3acdd는 전체 tree가 같지만 서로 다른 커밋이다.
