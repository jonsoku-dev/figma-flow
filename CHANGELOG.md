# 변경 기록

## 미배포

- NF-01 컴포넌트 계열: 정본 6패밀리를 Figma 컴포넌트 세트·변형·`TEXT`/`BOOLEAN`/`INSTANCE_SWAP` 속성으로 가산 적용하고 다시 읽어 대조합니다. 실기에서 `6`세트·`19`변형·`8`인스턴스를 만들었고, 수동 편집과 이동이 반복 적용 뒤에도 남았으며 기존 컴포넌트는 바뀌지 않았습니다. 첫 적용의 중복 표시명 실패와 롤백, 공개 재현 대응(`578ffc3`→`974b5de`, `node --test tests/test_property_repair_regression.cjs`), Python 비교기 gate checker pin을 기록했습니다. [P1 기록](docs/llm-wiki/releases.md#p1-design-acceptance) · [공개 인수 영수증](docs/next-roadmap/p1-acceptance.md).
- NF-03 원인 이력 상세: History 패널에서 실행별 읽기 전용 필드 diff, 선행 기록 링크, 뒤로가기와 키보드 포커스 복귀를 제공합니다. 상세 조회는 정본 요청·영수증을 쓰지 않으며 인증 누락은 `403`, 범위 밖은 `404`/`409`로 거절합니다.
- P1 최종 제품 소스 `e6f4fd8`의 CI Run `43599181267`이 성공했습니다(비공개·선택 fixture 부재로 skip 3건). 자체 예제 브라우저 접근성은 로컬 화면 범위에서 확인했습니다.
- 배포 검증·CI 경로 가드를 추가하고 로컬 스캔(`paths-only` 및 전체 규칙 검사, 1,682 tracked paths `forbidden_paths=0`, `ephemeral_evidence=0`)과 CI `paths-only` 게이트를 연결했습니다. Linux CI 기본 브랜치 분기 오류(`368db1a9`)를 수정해 `b9495234`에서 통과를 확인했습니다.
- 외부 참고 아카이브 4종과 보존 사본 4종의 변동 0건을 유지한 채 자체 웹·Design 기준 입력(`examples/owned-design-baseline/`)을 도입했습니다. 독립 Chromium 7클릭·3상태·6전이·10/10 바이트 동일 PNG와 `6/6` Figma Present 클릭 및 `85/103/103` 편집 가능 노드 수(초안 `86/104/104` 폐기)를 확인했습니다.
- P0 기준 자료·자체 입력·인수 영수증(`docs/next-roadmap/p0-reference-acceptance.md`)과 로드맵 그래프(`docs/next-roadmap/backlog.graph.json`), API 우선순위 큐(`1,382`행 중 전체 미관측 `825`건, Design 후보 `12`건=`8+4`, 런타임 지원 범위와 구분)를 정리했습니다. [P0 패치 기록](docs/llm-wiki/releases.md#p0-reference-safety) · [공개 인수 영수증](docs/next-roadmap/p0-reference-acceptance.md).

## 0.35.0 · 2026-11-14

- 한 번에 답변 하나만 여는 SaaS FAQ를 Chromium에서 측정해 편집 가능한 Figma Design 프로토타입으로 가져옵니다. 관측한 질문에만 클릭을 연결하며, 시작 상태에서 갈 수 없는 전이는 CLI와 플러그인 양쪽에서 거절합니다. 실제 SaaS 질문 두 개의 열기·닫기·상호 전환을 Figma 프레젠테이션에서 확인했습니다.
- [FAQ 사용 절차](docs/guide.md#web-disclosure-quickstart) · [인수 범위와 한계](specs/interactive-web/disclosure.md) · [포크용 상세 패치 기록](docs/llm-wiki/releases.md#v0.35.0) · [배포본과 체크섬](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.35.0).

- 작은손 디자인을 재생성할 때 생성 원본에서 빠진 노드·관계의 분류와 검토 메모를 보존합니다. CSS 버전 불일치로 생성을 중단한 뒤 다시 실행해도 같은 삭제 후보와 연결 근거를 확인할 수 있습니다. [G1 패치 기록](docs/llm-wiki/releases.md#g1-source-regeneration).

## 0.34.0 · 2026-11-14

- 탭을 누르면 옆 패널이 바뀌는 웹 화면을 로컬 Chromium에서 관찰하고, 실제로 누른 탭과 바뀐 패널만 정본 그래프에 기록합니다. 선택 상태는 CSS 클래스가 아니라 보이는 패널 내용으로 구분합니다.
- 자체 플러그인이 상태별 편집 가능한 Design 프레임을 만들고, 누른 탭 위의 투명한 클릭 영역에서 즉시 이동하도록 연결합니다. 실제 Devtool 홈의 A→B→A를 Chrome과 Figma 프레젠테이션에서 같은 클릭으로 대조했습니다. 관찰하지 않은 탭은 연결하지 않습니다.
- 플러그인 홈이 탭 프로토타입도 같은 목록에서 보여 주고, 캐러셀의 이전/다음 버튼 전이를 빠뜨리던 요약을 고쳤습니다.
- [사용 안내 및 인수 범위](specs/interactive-web/tabs.md) · [포크용 패치 Wiki](docs/llm-wiki/releases.md#v0.34.0) · [배포본과 SHA-256](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.34.0).

## 0.33.0 · 2026-11-14

- 모바일 CSS 스크롤 스냅 캐러셀을 로컬 Chromium에서 측정하고, 상태별 이미지와 입력·시간 전이를 정본 그래프에 기록합니다. Computer Use와 hook 없이 사용할 수 있습니다.
- 자체 플러그인이 편집 가능한 Design 프레임을 만들고 양방향 드래그와 자동재생을 연결합니다. 실제 SaaS 표본은 손으로 밀 때 양 끝에서 멈추고, 5초 타이머로 마지막 카드에서 처음으로 돌아갑니다.
- 동일한 대시보드 이미지를 메인 하나와 인스턴스 세 개로 연결했습니다. 패널의 현재 파일 작업 목록에서 네 카드의 제목과 시작 프레임·재생 동작을 확인할 수 있습니다.
- [사용 안내 및 인수 범위](specs/interactive-web/carousel.md) · [포크용 패치 Wiki](docs/llm-wiki/releases.md#v0.33.0) · [배포본과 SHA-256](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.33.0).

## 0.32.2 · 2026-11-14

- 웹에서 가져온 외부 SVG의 색이 CSS 필터로 단색이 되는 경우, 내부 경로를 편집 가능한 상태로 유지하고 Figma 루트에 불투명도를 적용합니다. 지원하지 않는 색 처리는 원본 자산을 남기고 차이를 표시합니다.
- 실제 Magic UI Devtool 로고 6개에서 벡터 경로 26개와 브라우저의 무채색 표현을 확인했습니다. [실측·지원 범위](docs/web-svg-fidelity-0322.md) · [Wiki](docs/llm-wiki/releases.md#v0.32.2) · [설치본](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.32.2).
- [스와이퍼·웹 모션·상호작용의 Design 변환 설계](docs/next-roadmap/NF-09-interactive-web-design.md)를 추가했습니다. 실제 브라우저의 탭 왕복과 향후 Figma 재생 인수 조건을 구분합니다.

## 0.32.1 · 2026-11-14

- 웹에서 가져온 제목과 버튼에 CSS 자간을 편집 가능한 Figma 텍스트 속성으로 유지합니다. Portfolio·CodeForge 제목 세 줄의 너비 오차가 기존 35.45~59.83 px에서 1.45~2.83 px로 줄었습니다.
- 자간이 같은 버튼은 메인 컴포넌트를 재사용합니다. 디자이너가 자간을 바꾸면 기존 프레임을 보존하고 변경을 보고합니다.
- 이미지 또는 대체 포스터가 포함된 새 화면의 첫 PNG를 준비한 뒤 미리보기를 반환합니다. 캔버스 표본의 첫 출력에서 빠졌던 빨간 영역이 재적용 없이 나타났습니다.
- [실제 브라우저·Figma 비교](docs/web-fidelity-0321.md) · [포크용 패치 Wiki](docs/llm-wiki/releases.md#v0.32.1) · [설치본과 SHA-256](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.32.1).

## 0.32.0 · 2026-11-14

- Design 전용 플러그인 ZIP과 SHA-256 파일을 [0.32.0 배포 페이지](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.32.0)에서 제공합니다.
- Figma Flow의 작성 경로를 Figma Design/default로 좁혔습니다. FigJam·Slides용 레시피와 독립 SDK 생성 경로를 제거했습니다. Widget SDK scaffold도 Design 파일에만 등록합니다.
- 웹 캡처에서 CSSOM이 생략한 래디얼 기본 중심을 복원하고, 선형·래디얼 마스크 교차, 제한된 필터 체인, 캔버스 PNG와 출처가 표시된 스크린샷 crop을 전달합니다. 지원하지 않는 합성은 limitation으로 남깁니다.
- Design API 관측은 1,193개 미관측에서 368개의 새 unique member 근거를 더해 557/1,382개 관측, 825개 잔여를 기록합니다. typed value-path 검사에서 62개 정규화 field를 읽었으며 일부는 기존 member key와 겹칩니다.
- workspace 업데이트는 stale task를 한 번에 재생하고 generation 하나를 발행합니다. 한 실제 79-task 실행은 기존 generation 1,138개를 보존했으며, 한 번의 15.12초 관측은 반복 성능 비교가 아닙니다.
- 실제 Design cloud/playback·CSS effect·canvas 경계와 복구된 원본 보드·덱 수는 [0.32.0 Wiki](docs/llm-wiki/releases.md#v0.32.0)에서 실행 범위별로 구분합니다.

## 0.31.0 · 2026-11-14

- 반응형 route·viewport graph와 signed screen-scope readback을 연결하고, 중단된 가져오기는 동일한 signed 계획의 읽기로만 복구합니다.
- 검증된 로컬 asset bytes로 SVG·raster·video를 기록하고 native mask, 제한된 shadow·blur, text gradient를 편집 레이어로 가져옵니다. native video paint가 거절되면 source hash가 고정된 raster fallback을 사용합니다.
- 27 browser case(20 ZIP pages와 7 source error states)에서 desktop/mobile 54화면을 확인했습니다. 7,481 editable node, 88 instance, 별도 vector descendant 1,435개를 기록합니다.
- 공개 Plugin API 조사에서 0.30.0 baseline 150/1,382와 1,232개 잔여에 39개의 새 exact member를 추가해 189개 관측, 1,193개 잔여를 기록했습니다. 이미 관측한 exact member를 현재 receiver에서 다시 확인하는 bounded recheck도 추가했습니다. [상세 근거와 한계](docs/llm-wiki/releases.md#v0.31.0)
- 설치 ZIP과 SHA-256 확인 파일은 [0.31.0 릴리스](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.31.0)에서 제공합니다.

## 0.30.0 · 2026-11-14

- 열린 웹 화면에서 보이는 텍스트·기하·지원되는 벡터와 컨트롤을 측정해 버전 그래프로 저장하고, 선택한 화면을 검증된 로컬 자산과 함께 편집 가능한 Figma 레이어로 가져옵니다. 지원하지 않는 CSS·미디어는 제한으로 남깁니다.
- 같은 그래프를 다시 적용할 때 변경이 없으면 native 쓰기를 생략하고, 사용자가 수정한 값은 graph conflict 검사로 보존합니다.
- 전체 Plugin API 대상을 역할·실행 가능성·실제 관측 여부로 정렬하는 우선순위 목록을 추가합니다. 점수는 조사 순서만 제안하며 런타임 지원이나 성공을 뜻하지 않습니다.
- [인수 그래프](specs/editable-web/graph.json)와 [검증 기록](docs/editable-web-verification.md)에 실제 브라우저 관찰, native Figma 생성, API 조회 수와 잔여 검증 경계를 연결합니다.

[0.30.0 상세 변경 및 포크 적용 기록](docs/llm-wiki/releases.md#v0.30.0)

## 0.29.0 · 2026-11-14

- 한 제품 그래프에서 선택한 요구사항·화면·컴포넌트·증거로 Design 검토 보드, FigJam의 표·노트·관계선, Slides의 검토 덱을 생성합니다. 같은 graph와 선택으로 재실행하면 기존 산출물을 재사용합니다.
- 실제 디자인 노드에 대한 읽기 전용 API 조사를 추가했습니다. 공식 타입의 소유자와 멤버, 지정한 Figma 노드, 관측 시간과 결과를 그래프로 기록합니다.
- 디자이너·개발자·기획자의 [사용 시나리오](specs/graph-review/spec.md), [검증 및 패치 기록](docs/llm-wiki/releases.md#v0.29.0)을 제공합니다.
- 캡처한 SSR 페이지의 같은 출처 이미지·CSS·글꼴을 실제 응답과 로컬 파일 SHA로 연결합니다. 네 템플릿에서 실제 HTTP 대상 45개를 새 입력 기록에 묶고, 정본 기준의 최신성 검사 경로를 확인했습니다.
- 레시피 메뉴·SDK·기능 검색의 중복된 등록 정보를 한 카탈로그로 통합했습니다. Slides 제작은 현재 Canvas Grid API를 사용합니다. 추가 실측을 합친 공개 API 관측 범위는 [근거 그래프](specs/graph-review/api-observations.json)에서 집계합니다.

## 0.28.0 · 2026-11-13

- 한국어·영어 기능 검색, 공식 Plugin API·REST 색인과 로컬 SDK 프로젝트 생성을 추가했습니다. 편집기별 실행 경로와 권한 조건을 조회할 수 있습니다.
- 등록된 Figma Flow 메뉴에서 현재 페이지에 그리드, 불리언·마스크, Smart Animate, BOOLEAN·INSTANCE_SWAP 예제를 만듭니다. 디자인 시스템 가져오기는 선언된 속성·연결·선호 교체 대상과 인스턴스 값을 검증합니다.
- 기능 안내와 자동 라우팅을 데스크톱 개발 플러그인 중심으로 갱신했습니다. 확인한 실행 범위는 [패치 Wiki](docs/llm-wiki/releases.md#v0.28.0)에 기록합니다.
- 작은손 예약 앱에서 취소 정책의 직접 영향과 근거 변경을 추적합니다. 그래프 재생성은 편집한 값과 관계를 보존하며, 예약 CTA의 배경색을 실제 Figma 컴포넌트와 Django 화면 사이에서 왕복할 수 있습니다. [실제 앱 검증](apps/little-hands/design/VERIFICATION.md)
- 같은 페이지의 작업 프레임을 다시 사용합니다. Figma의 dynamic-page 메인 조회, 점을 포함한 토큰 이름 변환, CSS 생성·배포 시 실제로 발견한 오류를 수정했습니다.
- 컴포넌트 범위 인계 HTML·JSON은 실제 getter·브라우저·정책 근거의 버전을 함께 표시합니다. 회원·비회원 예약 버튼의 문구를 원본 템플릿에서 읽고 기존 인스턴스의 임시 문구를 교정합니다.
- 공개 Plugin API 1.142.0의 1,382개 멤버를 두 릴리스 시점으로 대조합니다. 확인한 실행, 선언, 지원 조건과 미확인 항목을 [API 전수 조사](library/figma-api/audit/report.md)에서 확인할 수 있습니다.
- 배포용 글꼴 보정 자료와 DOM 맵의 Figma 파일 식별자를 해시로 교체했습니다. 기존 보정 입력도 계속 읽을 수 있습니다.

## 0.27.1 · 2026-11-13

- 운영 앱 CI의 패키지 설치 명령을 YAML 블록으로 바꿉니다. `--only-binary=:all:`의 콜론이 문법으로 해석돼 작업 시작 전에 실패하던 문제를 수정합니다.
- 앱이 읽는 `LH_DB_*` 설정으로 CI PostgreSQL 연결을 명시해, 사용하지 않는 `DATABASE_URL` 때문에 잘못된 기본 포트로 접속하던 문제를 수정합니다.
- WOFF2 글꼴을 변환하는 선택 의존성을 `fonttools[woff]`로 선언해, Brotli가 없는 새 환경에서도 실제 Hahmlet 입력을 처리하도록 합니다.
- 업데이트 CLI가 의존 모듈을 읽으면서 검증 대상 패키지에 Python 캐시를 쓰지 않도록 합니다. 일반 Python 명령의 반복 실행에서도 파일 바이트가 유지되며, 기존 출처·복구·바이트 일치 검사는 그대로 적용합니다.
- 설치 안내를 0.27.1 대상으로 갱신합니다. 0.27.0의 기능과 실제 앱·Figma 검증 범위는 유지하며 최종 원격 CI·설치 영수증은 [패치 Wiki](docs/llm-wiki/releases.md#v0.27.1)에 기록합니다.
- GitHub의 macOS ARM 실행기 부족으로 전체 검사가 시작되지 못할 때를 해결하도록 macOS 15 Intel 실행기를 지정합니다. macOS·sandbox·동일 검사 명령은 유지하며 로컬 ARM 검증과 구분합니다.

## 0.27.0 · 2026-11-13

- 반복 컴포넌트의 문구를 실제 TEXT 속성으로 편집하고 너비만 다른 사용처는 main을 공유합니다. 선언한 variant 축과 기존 기본 변형을 함께 보존하며 임의 조합을 만들지 않습니다.
- 원본이 겹치지 않고 위치·한 줄 할당이 정확히 일치할 때만 Figma의 정수 텍스트 치수 올림을 구분합니다. 원시 관측값과 실제 충돌 거절은 유지하며, 앱의 한글 할당과 flex 버튼 문구는 실제 getter·브라우저 관측으로 보정합니다.
- 선언한 Group·Frame·Auto Layout 계층과 명시한 clipped Frame 스크롤 방향을 작성하고 실제 overflow getter로 대조합니다. 실제 배치와 충돌하는 flow, 잘못된 크기·padding, 지원하지 않는 FILL 부모는 쓰기 전에 거절합니다. 기존 노드·main·주석·prototype 연결을 보존합니다. Group/Boolean 조상의 좌표를 중복 누적하던 오류는 실제 Figma 좌표로 재현해 배치·읽기·Python 감사에서 수정했습니다.
- 작업 간 산출물 의존성을 정확한 revision·artifact hash로 연결하고 현재·오래됨·은퇴·확인 불가를 구분합니다. 일반 너비에서는 관계 그래프를 넓게 표시하고320픽셀에서는 텍스트 관계·키보드 초점을 보존합니다. 서버 실행 단계와 로컬 관측 이력을 따로 표시하며 미확정 쓰기를 자동 재실행하지 않습니다. 저장한 결과와 정확히 같은 재전달은 기존 영수증으로 응답하고, 상충 결과·지문 없는 과거 영수증은 거절합니다.
- 선택 동기화가 실제 생성 패널과 Figma 실행기에 연결됩니다. 고정한 선택 manifest와 별도 protocol을 확인하고 alias·공유 consumer 묶음만 원자적으로 적용합니다. 미선택 값·binding과 부분 적용의 기존 marker를 보존하며 부분 결과를 전체 pairing 완료로 인정하지 않습니다.
- 입력 자산의 종류·모든 CSS 출처·부재·외부 미확인을 표시합니다. 목록과 승인된 브라우저의 실제 요청 관찰을 구분하고 별도 Chrome/CDP 실행기와 미선언 의존성을 제거합니다.
- 기존 문서 읽기 화면에도 너비·높이 요약을 연결합니다. 기본 페이지의 부분 범위와 제외 항목을 표시하고 전체 읽기로 대체하며, 동기화 근거로 사용하지 않습니다. session cache 없이 쓰기 전 전체 관측을 유지합니다.
- 로컬 전송을 분리하고 origin·route·payload·timeout을 제한합니다. 실제 React 패널에서 읽기 전용 진단 JSON을 내보내며 URL 자격 정보·토큰·개인 홈 경로를 제거합니다. 진단 버전은 고정 문자열 대신 빌드 매니페스트에서 가져옵니다.
- 보존된 task revision·request·artifact hash가 정확히 같은 bundle을 재사용합니다. 발행 실패 시 manifest가 바뀌지 않았을 때만 미승인 새 산출물을 정리해 기존 작업과 이력을 보존합니다.
- native 제작 중 container 검사는 한 번의 fresh full 읽기를 index로 공유하고 최종 검증은 다시 fresh full로 읽습니다. 주석의 semantic lookup도 제작 실행 안에서 공유하며 세션 cache나 wall-clock 개선 배수를 주장하지 않습니다.
- 독립 Django·PostgreSQL 운영 앱의 실제 인증·예약·대기·취소·회차 변경·운영·감사 트랜잭션과 Docker 패키지를 추가합니다. 22개 상태×2 viewport의 실제 원본 캡처를 디자인 경로에 연결합니다. 실제 Figma getter로44개 화면·24개 main·494개 instance·변수69개를 대조했습니다. Group 두 개를 추가한 정상 제작에서도3,171개 leaf의 절대 bbox 차이0과 기존 clip·prototype 연결 보존을 확인하고, 정적 prototype의14단계를 조작했습니다. 복사한 컴포넌트의3개 스타일을 실제 앱 CSS와 왕복 검증한 뒤 원복했습니다. 전체 링크 실행·창작 승인·공개 상용 배포는 별도 범위입니다.
- 통합 가이드를0.27에 맞추고 현재 RD 구현·최종 인수 행렬·후속 PROPOSED 설계를 분리합니다.


상세 소스·검사·실제 브라우저/Figma 관찰과 남은 범위는 [최종 인수 현황](docs/development-roadmap/FINAL_ACCEPTANCE.md)과 [패치 Wiki](docs/llm-wiki/releases.md#v0.27.0)에서 구분합니다.

## 0.26.3 · 2026-11-12

- Figma 작업 목록과 이력에 현재 revision의 상태 분포, 실행별 요청·진행·결과 연결, 작업별 필터와 키보드 초점 이동을 추가합니다. 옛 이력은 연결을 추정하지 않고 보존하며 다운로드·채팅·이전 revision을 현재 완료 수로 세지 않습니다.
- 관측한 native 실패를 중복 기록하지 않고 자동 제어의 결과 검증 실패도 같은 실행에 보존합니다. 고정 재현 검사로 기준 실패와 수정 후 통과를 대조합니다.
- 패널의 기존 light/dark 디자인 안에서 펼침·상태 feedback과 reduced-motion 처리를 제공합니다. 이력 요약은 전체 제품 인수 완료율이나 클라우드 저장을 뜻하지 않습니다.
- 신규 기능·Figma 제작·최적화·아키텍처 개선8항목을 개별 기능서·설계서·작업서27문서로 정리합니다. 컴포넌트 속성·재사용과 Frame·Group·Auto Layout의 공식 근거, Cursor 실행 프롬프트와 파일 소유권·이관·인수 조건을 포함합니다. 제안 기능은 아직 구현되지 않았습니다.

[상세 패치 기록](docs/llm-wiki/releases.md#v0.26.3) · [개발 계획](docs/development-roadmap/README.md) · [Cursor 전달서](docs/development-roadmap/CURSOR_HANDOFF.md).

## 0.26.2 · 2026-11-12

- 로컬 CSS의 중첩·인라인 `@import`와 사진·글꼴 `url()`을 입력 근거에 포함합니다. 확장자 없는 스타일시트, 문자 인코딩과 안전한 상대 경로를 처리하며, 이전 결과는 v3로 다시 준비해야 합니다. CSS 파서는 선택 의존성 목록에 포함됩니다.
- Figma 페이지를 조사할 때 실제 이미지 바이트를 이미지별로 한 번 읽어 공용 테이블로 전달합니다. 기존 인라인 읽기 결과도 검사하며, 참조·페인트·원본 바이트가 다르면 거절합니다. 기존 전송 크기 제한은 유지합니다. 반복 사진56개 사례의 실제 JSON은 전후 각5회 읽기에서9.16MB에서0.68MB로 줄었습니다.
- 중단된 검토 페이지를 완성본으로 재사용하거나 같은 패킷으로 중복 생성하지 않도록 준비 예약과 부분 생성 검사를 추가합니다. 기존 페이지를 지우지 않고 정확한 읽기·수정 경로로 누락 명세를 복구합니다.

[상세 패치 기록](docs/llm-wiki/releases.md#v0.26.2) · [패치 기록과 검증 절차](docs/llm-wiki/integration.md).

## 0.26.1 · 2026-11-12

- 로컬 HTML에 직접 연결된 CSS·JS·이미지·글꼴이 바뀌거나 사라지면 이전 입력 근거를 무효화합니다. 쿼리·프래그먼트가 붙은 로컬 주소도 추적합니다.
- 실제 Figma 이미지 바이트를 원본과 대조하고, 손상·미지원 형식·4,096px 초과 이미지를 준비 전에 거절합니다. 사진·한글 글꼴 회귀 예제와 바이너리 파일 전송 형식을 보완했습니다.
- 회귀 계획61개 케이스를 부분 관찰 근거183개에 연결합니다. 모든 케이스의 전체 상태는 `unverified`로 유지하며 실기기·사용자 첨부 검증을 통과로 표시하지 않습니다.
- fork에서 이어 갈 수 있도록 CHANGELOG 요약과 내장 LLM Wiki 상세 기록을 함께 제공합니다. 확인 가능한 과거 패치82건을 보완하고, Git 원문·기록 누락 검사와 개선 전 실패/개선 후 통과를 재실행하는 게이트를 추가합니다. 개선 diff에서 검사 파일을 바꿔 기준을 낮추는 시도도 거절합니다.

[상세 패치 기록](docs/llm-wiki/releases.md#v0.26.1) · [연결 자산과 사진 검증](docs/llm-wiki/patches/0bd817701f3df66673e314007f768a6de404fd78.md) · [Wiki 사용과 검증](docs/llm-wiki/README.md).

## 0.26.0 · 2026-11-12

[상세 패치 기록](docs/llm-wiki/releases.md#v0.26.0)

- Support graph-declared multiple prototype entry points and connected human specifications on static product controls without inventing native reactions. Preserve legacy flow defaults.
- Exercise three multi-page regression fixtures with typed component-source consumption, actual input effects and fault recovery. Correct review-submission payloads, pointer targets and reference styling.
- Serve generated web `.mjs` modules with JavaScript MIME so browser round-trip checks execute the real stylesheet module.
- Read fractional browser pixels through Typed OM and accept only exact values or their exact float32 representation, retaining selector, source-hash and coverage checks.
- Keep native vocabulary checks inside shipped fixtures so relocating a checkout does not scan unrelated neighboring projects.
- Reject same-frame native navigation before any page mutation. Preserve current-menu specifications as static controls, and verify actual multiple flow starts rather than inferring them from metadata.
- Restore the regression shell's stable navigation ID and persist Atlas display settings across reloads. Keep Paper review drafts on request failure.
- Measure intrinsic text in an isolated temporary frame so inherited auto-layout constraints cannot masquerade as natural width; always clean up measurement nodes.
- Refresh native readiness only after an authenticated result from the same current runtime, so long operations can be followed by another command without weakening the offline timeout.
- Honor resolved uncertainty records during startup refresh while continuing to block active claims and unresolved mutations.
- Add explicit revision-checked retirement for obsolete prepared tasks, preserving artifacts and receipts while allowing fresh work to be published. Keep source freshness and execution checks intact.

- Attach concise human annotations to exact screen/control nodes, link them to structured full specifications and verify both link directions against actual getters. Include source-backed conditions, recovery and Figma/web scope; preserve technical archives and other annotations. Reflow only owned description boards when their expanded content collides with artwork.

- Preserve bounded finite variable-font settings returned by actual Figma getters when planning description updates; retain the observed font identity.

- Bind new comparison approvals to visible current materials and real question calls. Reject symlink or concurrently changed approval files and preserve external targets during replacement.

- Check the exact registered Codex package and Figma runtime files at each workflow start; safely update with independent recovery snapshots, explicit exceptions and loaded-runtime freshness checks.
- Support one concrete `direct` direction alongside requested `compare` alternatives; retain actual user authority and artifact-linked critique without certifying visual quality from text checks.
- Project graph-owned human specifications into an outside-artwork linked board, retain technical ownership and exact legacy annotations privately, and verify source revision, meaning and actual target/display bindings. Extend the existing bounded native-edit path for updates.
- Register feature requirements/acceptance graphs under `specs/` and keep user instructions in the consolidated guide. Local code/mock verification is separate from real Figma observation.

## 0.25.0 · 2026-11-11

[상세 패치 기록](docs/llm-wiki/releases.md#v0.25.0)

- 여러 화면·뷰포트의 웹 컴포넌트를 범위별로 실측하고 원본 해시와 함께 합칩니다. 최종 pairing은 전체 컴포넌트와 현재 네이티브 값을 계속 요구합니다.
- 아이콘 버튼의 `space-between` 정렬을 실제 끝점·패딩·순서·최소 간격으로 검사합니다. 기존 가운데 정렬은 보존하고 아이콘 없는 미지원 정렬은 준비 단계에서 거절합니다.
- Figma의 HUG 양 끝 정렬에서 최소 간격이 사라지는 문제를 실측 고정 너비로 해결합니다. 명시적 `fill: null`은 투명 버튼을 유지하고 원래 합성 배경의 대비를 검사합니다.
- 같은 HTML을 재사용한 시안의 실제 CSS 배치를 방향 비교에 포함합니다. 동일 이미지·색상만 바꾼 시안의 거절 조건은 유지합니다.
- 새 명령과 제한을 한국어·영어·일본어 통합 가이드에 반영합니다.
- 네이티브 요청이 `claimed`인 동안 작업 목록의 새 게시를 거절해 실행 중 자동 재로드를 방지합니다. 기존 불확실 상태의 읽기 복구와 변경 없는 준비 재시도는 유지합니다.

## 0.24.1 · 2026-11-11

[상세 패치 기록](docs/llm-wiki/releases.md#v0.24.1)

- 로컬 제어 명령을 큐에 넣기 전에 실행 중인 서버의 준비 상태와 지원 작업을 확인합니다. 구버전·연결 실패·인증 실패는 기존 서버를 갱신하는 조치와 함께 표시합니다.
- Figma의 전체 읽기 결과를 그래프로 가져올 때도 현재 pairing 마커를 검증합니다. 오래되거나 충돌하는 마커는 그래프와 웹 파일을 수정하기 전에 거절합니다.

## 0.24.0 · 2026-11-11

[상세 패치 기록](docs/llm-wiki/releases.md#v0.24.0)

- 설치·사용·본제작·동기화·업데이트 가이드를 `docs/guide.md` 한 곳으로 통합하고 중복 문서 7개를 이전했습니다. 한국어 정본과 English·日本語 흐름, 기존 화면 캡처를 함께 관리합니다.
- Figma Flow 전용 격리 브라우저의 `--auto-allow` 설정을 지원합니다. localhost·127.0.0.1의 모든 포트와 작업에 사용하는 외부 페이지를 자동 허용하며, 로컬 MCP 서버는 루프백에서만 수신합니다.

- 실제 사용자 선택과 원본 검토에 연결된 풍부한 본제작 패킷을 지원합니다. 선택한 한 방향의 아트·배치·동작을 보존하고, 요청된 대비·동기화 변경을 경로/해시와 정확한 전후 값으로 검사합니다. 전용 `verify-production`으로 실제 결과를 검증합니다.
- 고정 작업공간에 `native-edit` 작업을 준비할 수 있습니다. 선언된 노드 또는 로컬 변수의 JSON 편집 계획을 실제 Figma API로 실행하며, 파일·페이지·리비전·기존 값과 복구 충돌을 확인합니다. 임의 JavaScript 명령을 받지 않습니다.
- 고정된 이미지와 지원되는 그라디언트 합성의 모든 글자 상자 배경 픽셀에서 최소 대비를 계산합니다. `contrast-unknown`은 판정 불가로 남기며, 불투명 배경판을 기본 수정으로 추가하지 않습니다.
- 본제작 패널은 준비·생성·읽기·검증 문구를 한국어·영어·일본어로 구분합니다. 소비자는 하나의 Figma Flow를 직접 실행한 뒤 localhost 명령 또는 수동 JSON 경로를 사용하며, Computer Use와 공식 Figma MCP가 필요하지 않습니다.

개별 프로젝트의 Figma·웹 완료 여부는 실제 읽기 결과와 실행 보고서로 확인합니다. 이 지원 목록은 모든 실증 검사의 통과를 뜻하지 않습니다.

## 0.23.1 · 2026-11-10

[상세 패치 기록](docs/llm-wiki/releases.md#v0.23.1)

- 자산을 많이 사용하는 캠페인에서 팔레트 인스턴스의 문구를 설정할 때 발생한 오류를 수정했습니다. 새로 만든 컴포넌트 세트의 실제 속성 키를 보관하고, 연결이 사라졌으면 해당 세트에서 복구한 뒤 인스턴스의 표시 문구를 확인합니다.
- 아이콘이 있는 시안 버튼은 앞·뒤 이미지, 레이블과 간격을 같은 Figma 컴포넌트에 담습니다. 가져온 뒤 메인과 인스턴스에서 이미지·순서·실제 배치를 대조합니다.
- 시안 주석에 필요한 본문 글꼴을 생성 전에 검사합니다. Computer Use가 차단된 환경의 설치·글꼴 적용·결과 전달 방법을 한국어·영어·일본어 가이드에 설명했습니다.

## 0.23.0 · 2026-11-10

[상세 패치 기록](docs/llm-wiki/releases.md#v0.23.0)

- 통합 작업대와 모든 작업 패널을 React로 렌더링합니다. 파일별 이력과 실제 준비된 작업으로 다음 행동을 안내합니다. Lucide React 아이콘, 공통 내비게이션·액션·결과·미리보기 컴포넌트, 계층별 CSS를 오프라인으로 번들합니다.
- 한국어·영어·일본어 표시 언어와 실제 후보 썸네일을 제공합니다. 파일별 실행 이력과 현재 작업 리비전에 근거해 다음 행동 또는 최근 결과를 표시합니다.
- 열린 Figma Flow에 Codex가 허용된 작업을 요청하고 로컬 영수증과 실제 읽기 결과를 회수합니다. 정확한 파일·페이지·리비전을 검사하며 수동 패널도 사용할 수 있습니다.
- 본제작에서 텍스트 범위의 변수 바인딩과 실제 글꼴을 확인한 뒤 Figma 텍스트 스타일을 연결합니다.

## 0.22.0 · 2026-11-10 · 로컬 통합본

[상세 패치 기록](docs/llm-wiki/releases.md#v0.22.0)

- 기존 Figma 텍스트 스타일을 사용한 버튼은 선언한 레이블에 전용 스타일을 연결합니다. 원래 스타일과 다른 소비자를 보존하고 실패 시 메인·인스턴스의 스타일 ID까지 확인합니다. 다른 페이지에서 시안을 다시 열 때는 해당 페이지를 먼저 불러옵니다.

- Figma Flow 하나를 등록하면 프로젝트별 작업 목록에서 Codex가 준비한 가져오기·검토·조사·동기화 작업을 열 수 있습니다. 준비된 작업은 개별 Figma 등록 없이 갱신됩니다.
- 작업을 준비한 Codex 채팅을 열고, 요청문과 선택한 노드의 미리보기를 복사하거나 로컬 연결을 통해 해당 채팅 대기열에 보낼 수 있습니다.
- 워크숍 시안의 상태 전환을 본제작 화면으로 가져올 때, 그래프가 선언한 상태와 화면의 연결을 검증합니다.

- Figma의 가져오기, 시안 검토, 그래프 조사·동기화 패널에 공통 스타일을 적용했습니다. 패널은 Figma 테마를 따르고 키보드 포커스와 작업 상태를 표시합니다.
- 그래프 적용 전에 해당 페이지·컴포넌트·변수의 범위와 변경 내용을 확인할 수 있습니다. 가져오기와 시안 검토는 현재 대상, 실행 결과, 저장할 자료를 구분해 표시합니다.
- 그래프 개발 플러그인 매니페스트에 파일 식별에 필요한 설정을 포함하고, 읽기 실패 시 오류와 다시 저장할 수 있는 진단 자료를 표시합니다.
- [Figma 사용 가이드](https://github.com/jonsoku-dev/figma-flow/blob/v0.23.1/docs/figma-guide.md)에 새 패널 화면과 기존 프로젝트 패키지를 갱신하는 절차를 반영했습니다.

## 0.21.1 · 2026-11-10 · 로컬 업데이트

[상세 패치 기록](docs/llm-wiki/releases.md#v0.21.1)

- 동시 배포된 0.20.1의 요청 경계 테스트 안정화를 보존합니다. 완성된 커밋에서 만든 버전별 설치 소스를 사용하고 실제 설치 파일을 소스와 대조합니다.

## 0.21.0 · 2026-11-10 · 로컬 업데이트

[상세 패치 기록](docs/llm-wiki/releases.md#v0.21.0)

- Impeccable 4.0.2, design-taste-frontend와 Unslop의 원문 전체를 명시한 upstream 커밋으로 고정해 참조·스크립트·라이선스와 함께 배포합니다. 개발자 PC의 전역 수정본은 복사하지 않습니다. Unslop 원문과 Figma Flow용 각색 문서를 구분합니다.
- 첫 디자인 실행과 설치 setup에서 동봉 원문·참조·라이선스의 파일별 해시를 검사합니다. 설치 폴더를 수정하거나 최신 스킬을 다운로드하지 않으며, 누락·변조를 전역 스킬로 우회하지 않습니다. 설치 setup 스킬을 플러그인 onboarding 경로로 연결합니다.
- 새 검토 기록은 동봉 원문의 플러그인 기준 경로와 해시를 사용합니다. 과거 전역 원문 영수증은 수정하지 않으며 현재 버전에서 검토할 때 새 기록을 준비합니다.
- 음악·영상 스킬인 정확한 ID `taste`의 자동 배정과 필수 검토 조건을 제거합니다. `prepare_design_review.py`의 `--music-directed` 옵션과 같은 이름의 함수 인자도 제거합니다. `design-taste-frontend`와 일반 모션 제작은 유지합니다.

## 0.20.1 · 2026-11-10

[상세 패치 기록](docs/llm-wiki/releases.md#v0.20.1)

- 요청 크기 경계 테스트는 초과 Content-Length 헤더만 보내고 본문 전송 전의 413 거절을 검증합니다. 큰 본문 전송과 서버 연결 종료의 경쟁으로 macOS CI가 간헐적으로 실패하던 테스트를 안정화합니다. 런타임의 크기 제한과 거절 동작은 유지합니다.

## 0.20.0 · 2026-11-10

[상세 패치 기록](docs/llm-wiki/releases.md#v0.20.0)

- 그래프의 design_system.tokens를 정본으로 삼고, 참조형 컴포넌트 선언에서 Figma 및 웹 스타일을 생성합니다.
- 기존 컴포넌트를 명시적으로 이관해 그래프 소유 변수와 소비자를 고정합니다. 선언 밖의 공유 변수·인스턴스 사용은 적용 전에 차단합니다.
- 디자이너의 직접 편집을 미리 보고 명시한 컴포넌트 범위로 그래프에 반영합니다. 변수 바인딩을 복구하고 실제 웹·네이티브 값을 확인한 뒤 기준선을 갱신합니다.
- 동시 편집 충돌, 조건부 복원, 그래프·웹 발행 잠금과 중단 복구를 추가했습니다.
- [Graph SSOT 스킬](skills/graph-ssot/SKILL.md)과 [사용 절차](examples/graph-ssot/README.md)를 추가했습니다.

## 0.19.1 · 2026-11-10 · 로컬 업데이트

[상세 패치 기록](docs/llm-wiki/releases.md#v0.19.1)

- 브라우저 등록 도구가 실행한 프로젝트 위치에서 MCP 설정 값을 생성합니다. 실행 파일은 PATH의 `npx`를 쓰며, 다른 사람의 홈·클론·캐시 경로를 공유 설정에 복사하지 않습니다.
- 공백·한국어를 포함한 서로 다른 프로젝트 위치에서 실제 CLI를 실행해 설정 경로가 해당 프로젝트로 생성되는지 검사합니다. 생성한 MCP 설정·허용 목록은 로컬 파일로 유지하고 공유 대상에서 제외하도록 설치 절차를 보완합니다.

## 0.19.0 · 2026-11-10 · 로컬 업데이트

[상세 패치 기록](docs/llm-wiki/releases.md#v0.19.0)

- Damir Sokolovsky의 Unslop을 제품 방향·기존 디자인 시스템에 맞춘 내장 비평 절차로 연결합니다. 원문 출처·버전·CC BY 4.0과 변경 사실을 각색 문서에 표시합니다. 기존 시안 선택과 디자인 검토 증거를 재사용하며 외부 Unslop 설치를 요구하지 않습니다.
- 브라우저로 다룰 작업 사이트와 실제 로컬 URL을 프로젝트별 Playwright MCP 오리진 목록에 누적 등록합니다. 새 포트·서브도메인도 사용 전에 등록하고 실제 MCP 적용을 확인합니다. MCP 접속 호스트와 방문 사이트 설정을 구분하며, 허용 목록을 지원하지 않는 도구는 등록 완료로 취급하지 않습니다.
- 브라우저 검수를 사용하는 설치 분기에 Playwright MCP 준비·프로젝트 연결·resolved config 검증을 포함합니다. 현재 채팅에 도구가 아직 로드되지 않은 상태와 실제 브라우저 실행 성공을 구분합니다.

## 0.18.2 · 2026-11-10

[상세 패치 기록](docs/llm-wiki/releases.md#v0.18.2)

- Figma에서 실제 글꼴과 변수 바인딩을 적용한 뒤 텍스트의 높이·줄 수, 화면 밖 배치, 이웃 텍스트 및 버튼과의 겹침을 검사합니다. 재읽기에서도 같은 화면의 실제 노드와 작성한 배치를 대조합니다.
- 한 줄 문구에는 픽셀 단위 자간과 줄 수를 지정할 수 있습니다. 브라우저가 반환한 소수 폭을 Figma 한 줄에 필요한 정수 픽셀로 배정합니다. 실패한 렌더의 레이어와 실제 측정값은 별도 진단 JSON으로 저장합니다.
- 화면별 제품 버튼을 편집 가능한 Figma 컴포넌트 인스턴스로 재사용합니다. 실제 폭·높이, 패딩, 가운데 정렬, 글꼴, 외곽선을 확인합니다. 검토용 상태 이동은 독립적으로 유지합니다. 둥근 도형과 버튼의 CSS 그림자·포커스 링도 편집 가능한 Figma 효과로 재현하고 읽기 결과와 대조합니다.
- 임의의 소수 치수에서 만들던 변수명과 대규모 상태 화면에서의 pluginData 100 kB 한도를 처리합니다. 작은 기존 기록과 여러 조각으로 저장한 기록을 모두 읽습니다.
- 이전 가져오기로 만든 패키지는 당시 버전에서 보존할 수 있습니다. 새 검증을 적용하려면 현재 버전으로 패키지를 다시 만들고 실제 Figma 읽기 결과를 내보내세요.

## 0.18.1 · 2026-11-10

[상세 패치 기록](docs/llm-wiki/releases.md#v0.18.1)

첫 공개 GitHub 릴리스입니다. 로컬에서 검증한 0.18.0의 설계·검사 기능에 설치 경로와 문서를 보완했습니다.

- Figma Desktop의 개발 플러그인 생성, 프로젝트별 ID 발급, 매니페스트 등록, 검토와 본제작, 읽기 결과 대조를 실제 스크린샷과 함께 안내합니다.
- 클론 직후 Codex에 붙여 넣을 설치·예제 실행 프롬프트를 Computer Use 지원 여부에 맞춰 제공합니다.
- shadcn/ui와 MUI의 실제 컴포넌트로 구현한 네 가지 팀원 초대 시안을 브라우저에서 비교했습니다. [비교 결과](docs/design-system-trials.md)
- 일반 클론에서 테스트용 글꼴 의존성까지 설치할 수 있도록 목록을 보완했습니다. 기존 전용 NIGHT 데모를 운영할 때는 환경 변수 `FIGMA_FLOW_NIGHT_FILE_KEY`와 `FIGMA_FLOW_NIGHT_PLUGIN_ID`에 운영자가 소유한 대상만 설정합니다. 휴대용 검토 패키지는 이전처럼 Figma 발급 ID를 사용합니다.
- 두 플러그인 매니페스트와 공개 Git 태그에 같은 버전을 사용합니다. GitHub Actions에서 Python·Node·동봉 예제 테스트를 실행합니다.

## 0.18.0 · 2026-11-10 · 로컬 릴리스

[상세 패치 기록](docs/llm-wiki/releases.md#v0.18.0)

- 선택한 그래프의 주석을 기준으로 본제작 읽기 결과를 대조하고, 복제된 인스턴스 내부 라벨과 실제 중복 의미 ID를 구별합니다.
- `check_project` 요약에 신선도를 확인하지 못한 노드, 사유, 누락 경로를 표시합니다.
- 임베드된 이미지 base64가 4,000,000바이트를 초과하면 경고를 남기고 패키지를 생성합니다.

게임 캠페인의 Figma 생성 스킨 배치, 텍스트 길이 변화 측정과 이를 근거로 하는 최종 디자인 검토는 0.19로 이월했습니다. 네이티브 전달 통과와 프로젝트 전체 디자인 인수는 개별 결과로 확인합니다.
