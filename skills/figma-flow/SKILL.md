---
name: figma-flow
description: Turn any idea or brief into a canonical requirement/screen/acceptance/code/evidence graph, linked screen specifications, and frontend implementation. Use for local-only delivery, local design tokens, a stable Figma workspace with Codex-prepared tasks, one-button local Figma sync, selected-page developer-plugin readback-to-app scalar sync and chained edits, explicit remote Figma MCP work, local source/brief audits, reviewed resumption after changes, mandatory font-first source-resolved Impeccable and applicable web tasteskill authoring/critique, genuine image-generated role assets and same-concept game batches, text-responsive generated skins, automatic prompt-to-design skill routing for logo, icons, raster imagery, typography, collectibles and Figma semantic handoff and SSOT, a curated Korean/Japanese mobile game campaign reference library with category-specific acceptance checklists, a searchable catalog across project manifests, selected draft builds, or pinned affected-test planning and execution; honor narrower requested scope.
---

# Figma Flow

Maintain one canonical JSON graph with stable semantic IDs. The graph owns relationships; explicitly selected sources own each fact. Screen specifications and rendered views refer to graph IDs. A graph or hash check supports review rather than proving product behavior.

## Figma 작업공간 기본 경로

Figma가 작업 목적지이면 하나의 등록된 **Figma Flow 작업공간**을 기본으로 사용한다. [설치·작업 목록 가이드](../../docs/figma-guide.md)를 읽고 기존 workspace manifest·실제 Figma 발급 ID·등록 경로를 먼저 확인한다. 최초 연결·업데이트가 필요하면 `figma-plugin-setup`으로 이어간다. 명시적 Local HTML only 요청은 해당 로컬 경로를 유지한다.

Codex가 검토·본제작·현재 문서 읽기·그래프 동기화 패키지를 준비한 뒤 해당 프로젝트의 실제 작업을 고정 manifest의 목록에 추가하거나 같은 작업 키로 갱신한다. 사용자는 **준비된 작업 → 열기**로 선택하고, 작업 패널의 명시적 실행 버튼을 누른다. **작업 목록으로**는 완료된 작업에서 홈으로 돌아간다. 패널을 여는 것 자체를 생성·적용으로 보고하지 않는다.

작업 목록은 선택·승인 기록이 아니다. 기존 후보 선택, 실제 native/web readback, 해시·페이지·소비자 검증을 그대로 수행한다. 새 작업을 위해 새 Figma ID나 등록 폴더를 반복 요구하지 않는다. 채팅 연결은 기록된 원래 thread의 **보낼 내용 확인 → 내용 복사** 또는 사용자 명시적 큐 전송을 따른다. 앞에 열린 데스크톱 채팅을 추정하거나 자동 전송하지 않는다. 다른 ID로 작성한 페이지의 private plugin data는 현재 ID에서 읽을 수 없으므로, 기존 ID·패키지를 보존하고 명시적인 이관 범위를 확인한다.

## 첨부한 분석 자료 사용

브리프와 함께 받은 전문 분석 플러그인의 보고서, GitHub 링크, 로컬 파일·폴더, HTML, 스크린샷, 실행 기록을 시안의 근거로 쓴다. 분석 보고서가 있으면 먼저 읽고 원본 위치와 적용 범위를 확인한다. 분석 도구나 보고서 형식은 사용자가 쓰던 것을 그대로 쓴다.

프로젝트 안의 텍스트 보고서는 `design_actions.py draft --research`에 전달한다. 첨부가 여러 개이거나 이미지·PDF이면 기존 `research.md`에 시안에 쓸 관찰과 원본 위치(파일·쪽, URL·뷰포트, 커밋·실행 기록 등)를 함께 적는다. 시각적 관찰은 화면 구성·글자 위계·컴포넌트 선택에, 동작 관찰은 그래프의 출발 상태·사용자 행동·결과 상태와 시안 주석에 연결한다. 예를 들어 저장 버튼 캡처는 버튼의 배치 근거이고, 저장 후 목록에 항목이 생긴 실행 기록은 상태 전이의 근거다.

요구사항과 참고 사례를 구분하고 관찰·해석·미확인을 표시한다. 원문과 분석이 충돌하거나 시안 결정에 필요한 근거가 빠지면 그 부분만 HTML·캡처·허용된 로컬 실행 등 알맞은 방법으로 확인한다. 첨부한 분석은 사람의 시안 선택과 Figma 전달 검증을 대신할 수 없다.

### 지정한 디자인 시스템으로 화면 만들기

“이 시스템대로 만들어 줘”와 함께 받은 디자인 시스템 사이트·GitHub 저장소·로컬 코드는 제작 기준으로 쓴다. 기획에서 사용자의 목적·화면·동작을 읽고, 지정한 시스템에서 그 화면에 쓸 컴포넌트·변형·상태와 색·서체·간격 규칙을 찾는다. 예를 들어 초대 양식의 입력 오류와 제출 중 상태가 기획에 있으면, 첨부한 시스템이 각 상태에 제공하는 필드·버튼·오류 표현을 해당 화면에 연결한다. 프로젝트에서 수정한 테마나 컴포넌트가 있으면 적용 중인 버전·경로를 확인하고 공개 문서의 예시와 차이를 남긴다.

앞단 분석 보고서에 대응 관계가 있으면 재사용한다. 부족한 항목만 지정한 소스에서 확인해 `research.md`와 화면 명세에 원본 URL·코드 경로, 사용한 컴포넌트·토큰 이름, 필요한 변형을 기록한다. 같은 시스템으로 만드는 시안들은 기획과 시스템 규칙을 유지한 채 정보 배치와 동선으로 차이를 낸다. 시스템에 없는 요소는 프로젝트 확장 제안으로 표시한다.

웹 구현까지 요청받으면 대상 프로젝트의 실제 컴포넌트와 테마를 재사용한다. Figma 제작에서는 지정한 라이브러리를 열 수 있으면 해당 컴포넌트·변수의 원본을 확인하고, 웹 코드나 문서로 주어졌으면 그 사양에 대응하는 로컬 컴포넌트·변수를 구성한다. 화면 명세에는 코드·문서와의 대응을 적고, 실제 Figma 라이브러리 연결은 네이티브 읽기로 확인한 경우에만 기록한다. 기존 네이티브 전달 검사를 적용한다.

웹 디자인 시스템을 Figma로 옮길 때는 실제 콘텐츠 영역, 사용한 폰트 face, 행간·자간과 상태별 제품 버튼을 [시안 시각 품질 요구사항](references/visual-quality.md)에 따라 작성한다. 실제 읽기 결과에서 줄 수, 겹침, 버튼 외곽 및 라벨 정렬을 검증하고 Figma에서 내보낸 화면과 원본을 비교한다. 실패 진단은 레이아웃 수정의 근거로 쓴다.

## 디자인 제작의 첫 실행

새 UI 후보 작성·기존 화면 리디자인·완성 화면 비평에는 내장 [Unslop 절차](references/unslop.md)를 읽고 적용한다. 브라우저를 열거나 Playwright 호환 API로 확인할 때는 [허용 호스트·오리진 등록](references/browser-access.md)을 먼저 마친다. 작업 대상과 실제 로컬 URL이 늘면 등록·적용 확인 후 계속한다.

새 UI·캠페인 제작과 리디자인은 [시안 검토 및 사용자 선택](references/direction-selection.md)으로 시작한다. 로컬 제작과 Figma 제작에 같은 순서를 적용한다. 원본 스킬을 읽고 참조 사례를 확인한 다음, 같은 목적·문구·주 행동을 가진 비교 시안 2~3개를 제안한다. 각 안에는 데스크톱·모바일 화면, 실제 요소로 연결되는 계획 주석, 제안 토큰과 컴포넌트 샘플을 둔다. 서체 견본은 시안의 일부다.

코드로 후보 파일과 그래프를 검사하고, 에이전트가 시각적 차이·사용성·한계를 실제 결과물에서 평가한다. Figma가 목적지이면 시안 단계부터 Figma 데스크톱의 로컬 플러그인으로 별도 검토 페이지를 만든다. 실제 화면·버튼에 붙은 주석과 같은 내용을 읽고 원본 요소로 이동할 수 있는 일반 디자인 캔버스의 주석 보드, 메인 컴포넌트·가시적인 팔레트·변수 연결, 클릭의 정확한 목적지와 복귀 경로를 원본에서 다시 읽어 검증한 뒤 그 페이지를 제시한다. 비교 이미지와 서버 없이 열 수 있는 검토 HTML도 함께 제공한다. 사용자가 볼 수 없었다면 선택은 성립하지 않는다. 프로그램이 발행한 현재 후보 ID와 버전을 보여준 뒤 실제 사용자 답변을 기다린다. 캠페인 유형 선택이나 “계속해”는 특정 시안에 대한 동의가 아니다.

시안의 `source.py`·`native-layout.json`을 작성할 때는 [시안 시각 품질 요구사항](references/visual-quality.md)을 따른다. 진입 화면마다 시각적 중심(탐색용 이미지 자산, 일러스트, 원·라운드 도형 구성)을 두고, text가 아닌 모든 레이어에 `role`을 선언하며, 의미 없는 장식 막대를 쓰지 않는다. 0.17.0의 `ellipse`·`radius`·`stroke`·`stroke_width`·`opacity`를 사용한다. 검토 패키지를 준비하기 전에 **자기 비평 루프는 필수 단계다.** 미리보기를 렌더해 직접 보고, `python3 tools/design_quality.py --layout ...`(또는 `python3 tools/design_actions.py quality --manifest ...`)와 체크리스트로 확인한 뒤 고친다. 오류는 모두 고치고, 남은 경고는 0개가 되거나 경고마다 사유를 해당 시안의 검토 메모에 적은 다음에만 작업공간의 `prepare --kind review`로 넘어간다. 내부 검토 생성기는 같은 관문 오류가 있으면 패킷을 만들지 않는다. 관문 통과는 결함이 없다는 뜻일 뿐 디자인 품질이나 사용자 선택을 증명하지 않는다.

그 선택을 검증한 후에만 에셋 배치 고정, 이미지 생성 요청, 본 제작용 Figma 번들 제작, UI 구현으로 이동한다. 명령은 입력과 현재 선택을 쓰기 전에 다시 검사한다. 자료 조사·초안 비교·기존 원본 열람은 각 범위의 결과만 보고한다. 정상 이용자는 Figma의 일반 디자인 모드에서 로컬 플러그인을 실행하고 결과를 저장한다. 검토·제작·전달에 Dev Mode, 유료 업그레이드, 훅 또는 Computer Use를 요구하지 않는다. 개발자가 GUI 사용을 승인받아 프레젠테이션을 직접 검증하는 일은 별도이며, 자동 읽기 결과만으로 실제 시연을 했다고 보고하지 않는다.

워크플로 상태·전이·조건의 정본은 `library/workflow.json`이다. `tools/workflow.py`의 `State`·`Event`·`Guard`와 생성된 [워크플로 그림](references/workflow.generated.md)을 사용한다. 제품 상태는 해당 제품의 그래프에서 `tools/app_states.py`로 내보낸 상수를 사용한다.

## Start and choose scope

1. Read the supplied idea/brief and workspace instructions. Inspect the destination repository, working tree, existing components and commands. Preserve unrelated work. Record a fresh run directory, source identity/hash, requested outcome and authorized destinations.
2. **경로를 선택한다.** 새 UI·캠페인·리디자인은 별도 옵션 없이 로컬 Figma 일반 디자인 모드의 시안·주석 보드·팔레트·왕복 프로토타입 검토를 기본으로 계획한다. 사용자가 Figma 제외나 로컬 HTML만 요청하면 로컬 검토를 사용한다. Dev Mode·MCP·Computer Use를 제외하는 지시는 Figma 파일 제외가 아니다. 조사·기술 변경에는 이 기본값을 적용하지 않는다. 실제 파일 작성은 사용자가 지정한 파일 또는 Figma에서 플러그인을 실행한 파일로 한정한다. 디자인 토큰, Figma 출력, 소스/기획 감사 또는 변경 테스트가 필요하면 [local-design-audit.md](references/local-design-audit.md)를 읽는다. MCP 없는 요청에서는 Figma MCP 연결 검사나 호출을 하지 않는다. 사용자가 원격 MCP를 명시했을 때만 [figma-workflow.md](references/figma-workflow.md)를 읽고 필요한 공식 도구/호스트 스킬을 사용한다. Figma를 포함하는 모든 경로는 일반 번들·맞춤 제작·원격 도구와 관계없이 [필수 네이티브 전달 검사](references/local-design-audit.md#필수-네이티브-전달-검사-0130)를 수행한다. 실제 캡처와 기대 계약을 `bindings.native_handoff`에 연결하고 `check_project.py`의 네이티브 게이트가 통과해야 해당 디자인을 완료로 보고한다. Figma 접근·주석·컴포넌트·변수 증거가 없으면 `pending_native_handoff` 또는 `blocked`로 남기고 독립적인 로컬 작업을 계속한다.
3. **Figma 버튼 동기화·재읽기 값을 앱에 반영하거나 이어서 편집할 때** [token-sync.md](references/token-sync.md)를 읽는다. 0.8.0 버튼 방식은 `tools/serve_figma_sync.py`로 앱 밖 비공개 상태 폴더에 페어링 플러그인을 생성한다. 처음에는 원본 그대로 기준선을 저장하거나 정확한 0.7.0 성공 적용 체인을 지정하고, 이후 현재 페이지만 읽어 적용한다. 도우미와 상태 폴더를 유지하고 키를 공유하지 않는다. 작업공간과 ID가 같은 지원 상태는 `prepare --kind import`의 `--paired-state`로 홈에 준비하며, 다른 ID의 standalone 경로를 억지로 합치지 않는다. 수동 JSON 방식은 `tools/apply_figma_change.py`에서 먼저 계획을 검토한 뒤 `--apply`로 적용한다. 두 방식 모두 최초 `resolved.json`을 유지하며 `design.json`과 영향받는 기존 생성 자산만 쓴다. 0.9.0의 별도 읽기 전용 실제 앱 비교는 복습 카드의 네이티브 색과 패딩 네 방향·반경 네 모서리·변수에 연결된 버튼 라벨 글자 크기를 CSS px로 다룬다. 라이브 클릭에 연결된 이전 상태가 있을 때 실제 앱의 전후 값을 수집하며, 누락·혼합 값이나 과거 실측 부재는 `unknown`으로 남긴다. 파일 키·페이지·최초 원본과 보호된 체인을 유지하고 토큰 연결 구조·바인딩 변경은 새 가져오기 페이지로 분리한다. 그래프 선언, 정적 코드 후보, 실제 브라우저 결과와 미검증 범위를 구분하고 테스트만으로 Figma·런타임 성공을 주장하지 않는다.
4. Read [graph-contract.md](references/graph-contract.md) for exact schemas/CLIs and [run-record.md](references/run-record.md) for evidence and resumption. For a runnable bundled example or self-study, read [live-example.md](references/live-example.md). For a selected catalog draft, workbench build, prepared promotion, per-rule specification/test evidence, or affected-test run, read [draft-build.md](references/draft-build.md). Resolve scripts relative to this installed skill, never a remembered project path.

## UI 제작·리디자인의 기본 완료 조건

새 UI·웹·게임 캠페인 제작/리디자인은 [정상 제작·디자인 검토](references/design-review.md)를 반드시 읽고 실행한다. 실제 Impeccable과 적용 가능한 design-taste-frontend 원문에서 방향을 정하고, 대상 언어의 실제 폰트 후보·데스크톱/모바일 표본을 먼저 만든다. 음악/박자 중심 작업은 실제 taste 원문을 리듬·모션에 한정해 사용한다. 라이브러리 아이콘을 권하는 원문보다 현재 사용자의 **로고·아이콘 이미지 생성 의무**가 우선한다.

게임 자산은 UI 시각 제작 전에 정확한 콘셉트/참조/역할 배치를 `asset_batch.py`로 고정하고, 공통 프롬프트의 역할별 요청을 실제 호스트 image_gen 도구로 실행한다. 로고·아이콘·캐릭터·키아트·제목/버튼 장식과 필요한 인장/장식을 같은 게임 문맥에서 계획한다. 제목·버튼 그림은 실제 TEXT를 감싸는 nine-slice/HUG 구조로 만들고 titleFor·내용 래핑·아래 섹션 흐름을 보존한다. 같은 의미의 행동은 폭마다 기존 그림을 재사용하되 다른 목적의 조작 전체를 한 범용 프레임으로 덮지 않는다.

제작 후 구체적인 창작 비평과 필요한 수정을 수행하고 실제 완성 화면과 별도의 긴 문구/모바일 resize probe를 저장한다. 깨끗한 검토는 실제 기준별 관측으로 입증하며 가짜 결함을 만들지 않는다. `prepare_design_review.py`로 실제 관측의 해시·원문 위치를 고정한 뒤 기본 `check_project.py --intent create` 게이트를 통과시킨다. 영수증/해시 자체가 스킬 준수·플랫폼 실행·미적 완성도를 인증한다고 주장하지 않는다. Figma 네이티브 전달은 별도 필수 게이트다. 순수 기술/열람은 해당 의도를 명시하고 `design_completion: not-claimed`로 남긴다.

## 디자인 프롬프트 자동 라우팅

디자인·리디자인·로고·아이콘·이미지·폰트·모션·스킬 조사 요청에서는 [자동 라우팅](references/design-routing.md)에 따라 현재 프롬프트로 `tools/route_design.py`를 먼저 실행한다. 짧은 후속 요청(예: “모두”)은 이전 대화의 대상·제약을 `--context`에 넣어 함께 판단한다. 스타일을 하나 고르는 질문으로 시작하지 않는다. 명시한 제외·기존 자산 재사용·조사 전용 범위와 Figma 원본 요구가 우선한다.

출력의 각 표면·경로·실제 사용 가능 스킬을 확인한다. 요청된 산출물이 있으면 필요한 경로를 같은 작업 안에서 수행하고, 근거 자료와 실제 산출물·검사 결과를 연결한다. 로고·아이콘·다국어 활자에는 [캠페인 아이덴티티](../campaign-identity/SKILL.md)를 사용한다. 시안 이미지는 생성하고 열어서 검토한 뒤 납품 형식에 맞게 정리한다. 라우터의 추천 자체를 제작·설치·인수 완료로 처리하지 않는다.

## 모든 Figma 디자인의 전달 조건

실제 화면과 중요한 조작에 네이티브 주석을 붙이고, 선언한 액션·상태를 주석에서 읽을 수 있게 한다. 중요한 조작은 실제 로컬 컴포넌트 세트의 인스턴스이고 토큰은 사용 중인 속성에 실제 변수로 연결되어야 한다. 맞춤 제작자는 동봉된 `figma-bridge/native_annotations.js`, `semantic_components.js`, `semantic_tokens.js`, `native_semantic_read.js`를 허가된 Plugin API 실행 문맥에서 재사용하거나 같은 네이티브 구조를 직접 작성한다. 모든 제작자는 읽기 결과와 기대 계약(일반 번들의 자동 생성 `expected-native-handoff.json`, 맞춤 제작의 명시 계약)을 고정해 [필수 명령·선언 스키마](references/local-design-audit.md#필수-네이티브-전달-검사-0130)를 실행하고, 관측값에서 생성한 `screen-spec.json`·`screen-spec.md`를 전달한다.

이 외부 화면 명세는 필수 네이티브 증거의 투영이다. 별도 Figma 제품인 **Figma Specs** 작성 여부가 선택 사항이어도 이 게이트·주석·화면 명세는 생략할 수 없다. SSOT라는 단어, MCP 사용 여부, `local-only` 매니페스트는 Figma 포함 작업의 예외가 아니다. 순수 로컬 작업만 Figma를 `not_requested`로 기록한다.

## Figma 원본을 그대로 구현하는 경우

사용자가 Figma를 디자인 SSOT로 지정하면 실제 Figma 파일의 지정 페이지·프레임을 시각 디자인 원본으로 사용한다. 편집 가능한 최종 화면과 사용자에게 보이는 상태를 Figma에서 확인한 뒤 구현을 시작한다. 프레임 ID, 화면 크기, 텍스트·폰트·좌표·채우기·이미지·컴포넌트 및 실제 내보내기의 해시를 기록한다. 프레임을 만든 스크립트나 중간 시안의 값은 네이티브 읽기를 대체하지 않는다.

웹은 해당 원본에서 읽은 레이아웃과 에셋을 소비하고, 구현 코드에는 데이터·키보드·저장처럼 실행 환경이 담당하는 동작을 연결한다. 다른 언어와 반응형 화면도 원본 프레임과 대응시킨다. 변경이 필요하면 Figma에 먼저 반영하고 새 읽기를 고정한다. 같은 크기·언어·상태에서 원본 내보내기와 브라우저를 비교해 관찰한 일치와 차이를 구체적으로 남긴다.

원문을 채택한 이유는 그래프의 `reference → informs → requirement` 관계로 기록한다. 해당 요구를 구현한 화면과 실제 Figma 노드, 코드, 검사를 연결한다. 편집할 디자인 값의 권위는 Figma, 관계 탐색은 그래프, 실행 결과는 실제 테스트 증거가 담당한다.

## 모바일게임 캠페인

기념·행사형(`commemorative-event`), 출시·공개형(`launch-reveal`), 참여·프로모션형(`participation-promotion`)은 독립적인 기본 제작 형태다. [형태별 콘텐츠·자산·CTA](../../library/campaign-forms.json)를 `tools/campaign_forms.py` 또는 정상 라우터에서 읽고, 사용자가 요청한 형태를 모두 같은 작업 안에서 각각 제작한다. “1,2,3 모두”는 이전 선택 맥락을 넘겨 세 형태 모두 선택한다. 행사 프로그램·음악·갤러리, 세계관·캐릭터·실제 티저·등록/설치, 혜택/규칙 우선·참여·획득 결과·공유/저장의 서로 다른 목적을 한 미니게임이나 하나의 만능 페이지 틀로 합치지 않는다. 복수 형태의 실제 섹션/자산 역할을 생성 전 공통 게임 배치에 함께 계획한다.

캠페인 기획·수정·테스트에서는 [캠페인 레퍼런스](references/campaign-library.md)를 사용한다. 기획에 해당하는 카테고리를 하나 이상 고르고, 해당 시장과 카테고리의 `list`와 `plan`을 실행한다. 참고한 패턴 ID, 출처 ID, 적용할 화면·수용 기준을 프로젝트에 남긴다. 여러 카테고리가 겹치면 검사 항목을 중복 제거하고, 전제 조건이 다른 항목은 그 이유를 기록한다. 원문 본문·검색 색인·실제 화면 관찰의 근거 수준을 유지하며, 타 카테고리에서 빌린 아이디어는 유추로 표시한다. 이미지·서체·모션은 현재 프로젝트에 맞게 제작하거나 허용된 라이선스로 확보한다. 브라우저에서 실제 판정한 범위만 검증 결과로 기록한다.

## Execute a local run from any brief

1. **Extract the contract.** Assign requirement, screen, state, action and acceptance IDs. Record original source sections and distinguish specified, inferred and unknown facts. Include relevant validation, failure, keyboard and responsive behavior. Finish when every in-scope requirement has a screen and checkable acceptance criterion; unresolved policy blocks only dependent work.
2. **Author the canonical graph and linked screen spec.** Use the graph contract's canonical edges. Write a screen specification keyed by the same IDs, with controls, states, action outcomes, acceptance links and source references. Connect implementations and actual verification activities as they exist. Finish when action metadata matches edges and graph/spec meaning has been compared to the brief. Generated projections cannot replace that comparison.
3. **Implement admitted behavior.** For new UI, first validate the user's exact selected direction and any required generated-assets/native evidence through the canonical workflow. Reuse repository components, storage and tooling. Preserve user input and existing data on errors. If persistent concurrent writers matter, use the project's transactional/coordination capability and verify that behavior; a fresh localStorage read before a write is not atomic. Finish the requested code and inspect its diff.
4. **Collect scoped evidence.** Run relevant project checks and exercise affected flows in an approved real browser when practical, including important error, keyboard and narrow viewport states. Save command/flow, environment, pinned inputs, actual results and limitations. Mark graph nodes `verified` only for the fact their evidence supports; failed or unrun checks remain explicit. Finish when each in-scope acceptance criterion has evidence or a concrete blocker.
5. **Run the local gates.** Execute `graph.py validate GRAPH --strict-local`; resolve its errors rather than treating warnings from ordinary validation as a completion gate. Use the same flag with `graph.py render GRAPH --strict-local --out-dir NEW_DIRECTORY`. Bind the actual brief/spec/code/evidence files. For a project without a baseline, use the plugin-root `tools/check_project.py --init --brief BRIEF --graph GRAPH --bindings BINDINGS --out NEW_DIRECTORY` to validate declared coverage and create a local-only manifest, reports and `baseline-graph.json`. Otherwise use `ssot.py snapshot ... --scope local-only` followed by `ssot.py check MANIFEST` as appropriate for the existing chain. Save the check JSON and generate the offline viewer with `trace_report.py GRAPH --check CHECK_JSON --out NEW_FILE.html`. Read results and record exit codes. For frontend creation/redesign, bind actual design_review evidence and run the creative gate; missing whole review is blocked by default. For every Figma-backed graph or visual authority, include bindings.native_handoff and use tools/check_project.py for both initialization and subsequent checks; direct ssot.py freshness alone cannot close the native gate. Finish when declared coverage and freshness pass and required native_handoff_status is passed, or report specific remaining blockers. A source reference alone does not prove evidence content.

디자인이 포함되면 같은 의미 ID를 원본 디자인·그래프·화면 명세와 가져오기 결과에 유지한다. `design_bundle.py --design FILE --graph GRAPH --selection VERIFIED_SELECTION --out NEW_DIR`는 미리보기·SVG·개발 플러그인과 `design-graph.json`을 생성한다. 원본 입력은 보존하고 투영 그래프에서 토큰 → 컴포넌트 → 화면/액션 의존성을 읽는다. 번들은 `pending_native_handoff`이며 실제 가져오기·현재 파일 재읽기와 필수 네이티브 전달 게이트 통과가 있어야 해당 범위의 Figma 전달을 완료로 주장한다. 키트 생성과 시뮬레이션 테스트만 있으면 로컬 산출물로 보고한다. Codex 모델 토큰 사용과 Figma MCP 사용을 구분하고, Figma 좌석·편집 권한·AI 크레딧을 보장하지 않는다.

## Authority and changes

Record authority per fact, source/version, competing observations and resolution in the run record. Typical facts are intended behavior from the brief, observed layout from a local spec or Figma, and execution from actual code/runtime. On contradiction, retain both observations and block their dependents until an authorized decision exists.

For an existing local project with a baseline, run the packaged `tools/check_project.py MANIFEST --out NEW_DIR` (resolve it at the plugin root). Use the baseline explicitly selected for this project. When its exact graph bytes were preserved, add `--previous-graph OLD_GRAPH`; accept field/edge before-and-after claims only after the tool verifies those bytes against the manifest. Without an old graph, retain hash/evidence explanations and report precise graph differences as unavailable. Inspect the current graph, recorded evidence and change explanation before deciding which actual tests to rerun. Keep the inspection output separate from the source project. Report an inherited stale state as unresolved history, and a reported dependency path as one reason to recheck the target. Never promote inspection to a fresh test result or new baseline.

Before resuming, check the previous manifest against current files. Preserve stale evidence and old manifests. Review affected IDs and explicit propagation candidates, update graph/spec/code and rerun the affected checks. Use the SSOT contract's exact pinned review JSON and `snapshot --previous ... --review ...` to acknowledge the reviewed state; include actual local revalidation evidence. Check the new manifest. A snapshot alone never clears staleness; review records a decision rather than proving its quality. Inspect an uncertain write's target before retrying.

## Catalog existing projects

For a cross-project idea overview, collect explicitly selected manifests or idea briefs and unique project labels. For two or more new textual briefs, read each separately, write one structurally valid graph per idea with stable IDs, proposed requirements, proposed screens and explicit `appears on` links. Record inferred decisions as proposals; retain `planned`/`unverified` status and author only evidence that actually exists. Finish normalization when each brief has its own graph and the brief-to-screen interpretation has been inspected. Run `tools/idea_catalog.py --idea LABEL GRAPH_JSON --idea LABEL GRAPH_JSON --out NEW_DIRECTORY` for these drafts; a manifest and strict-local completion are unnecessary for browsing proposed ideas. Run the plugin-root `tools/idea_catalog.py --project LABEL MANIFEST --project LABEL MANIFEST --out NEW_DIRECTORY`. Open `index.html` and inspect search, project/type filters, requirement and screen entries, and links to the separate project reports. Preserve `(project label, semantic ID)` identity and report each project's declared graph status, coverage and freshness separately. Invalid or stale projects remain visible; catalog generation runs content checks rather than project tests. See [the two-project exercise](references/live-example.md#5-두-프로젝트의-기능과-화면-모아-보기).

## Build a selected draft and validate changes

Read [draft-build.md](references/draft-build.md) before using `serve_ideas.py`, `promote_idea.py` or `affected_tests.py` at the plugin root. Keep catalog, selected draft and brief pinned to their actual bytes, preserve draft semantic IDs and screen scope, and create a fresh isolated output. An original draft-only brief remains historical product data; record the current user's later implementation authorization separately. Existing code, authorities and baseline must come from inspection and explicit project selection, never inferred from a nearby filename or the newest manifest.

Materialize each independent rule as a linked specification and actual implementation/test bindings. Keep per-file execution evidence and a complete graph-test-ID mapping, including shared test harness/import files as declared inputs. 변경 테스트 전 로컬 소스/기획 감사를 읽는다. 확인된 누락, 후보와 미해결은 별도로 유지하고 자동으로 의미 관계를 추가하지 않는다. 의존성 누락·후보·미해결은 매핑된 전체 테스트로 범위를 넓힌다. 활성 기획 모순은 유용한 테스트 실행을 유지하면서 인수 완료 주장을 차단한다. 지원하지 않는 구문은 검토 필요로 남기며 전체 의미 분석 성공으로 바꾸지 않는다. Inspect dependency branches and conservative fallback in the plan before trusting exclusions. Planning does not run tests; a run receipt does not change graph status or approve a review. Complete the pinned review and chained snapshot procedure only after actual revalidation, keeping failures, unavailable checks and browser limits explicit. Finish when the requested build or change scope has real evidence or concrete blockers; leave Figma `not_requested` for local-only work.

## Deliver and stop

Return actual artifact links, graph and linked screen spec, implementation paths, gate results and separate test/browser/Figma evidence. For Figma-backed work include native-handoff.json, its pinned readback/contract inputs and generated screen-spec.json/screen-spec.md; report blocked or pending when that gate has not passed. State the completed requested scope, assumptions, unresolved blockers and first runnable next action. If the requested acceptance depends on browser behavior, obtain that evidence or report partial completion. Distinguish declared coverage, registered file freshness and actual runtime checks. Do not publish, deploy or expand access without authority.

For unparsed acceptance-critical requirements, inspect the actual source sentences. When the reviewer finds a concrete same-scope conflict outside the deterministic rules, record two current line quotes and their source hashes using the optional semantic review format, then run the audit with `--review`. Describe the resulting candidate as reviewer-reported. Do not infer the absence of conflict from a pass or from the count of matched rules.
