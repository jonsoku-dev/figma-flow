# Figma Flow Starter 기능명세 — 기획·엔지니어링·디자인

조사 기준일은 2026-11-13이다. 배포 기준은 **v0.27.1**, 검증 기록 기준은 **068eb35**다. 개발 중 기능은 이날 작업 트리에서 확인한 스냅샷이다. 아래 우선순위와 신규 기능은 제품 제안이다. [릴리스](https://github.com/jonsoku-dev/figma-flow/releases/tag/v0.27.1) · [설치·네이티브 검증 기록](llm-wiki/releases.md#v0.27.1)

**목표는 편집자 한 사람이 열린 Design 파일에서 자체 플러그인을 실행하고, 세 직군이 그 결과로 일할 수 있게 하는 것이다.** 무료 기본 경로는 로컬 그래프·에셋, Figma Desktop의 Plugin API, 로컬 파일 출력을 쓴다. Figma MCP, Figma REST 토큰, Dev Mode, 유료 AI 호출과 팀 라이브러리 발행을 필수 단계에서 제외한다. 제품 자체의 구독·호출 횟수 제한 없이 제공할 수 있는 범위다. Figma의 계정 권한, 파일 용량·구조, 실행 세션과 기기 자원은 그대로 적용된다. [플러그인 실행 조건](https://help.figma.com/hc/en-us/articles/360042532714-Use-plugins-in-files) · [플러그인 실행 모델](https://developers.figma.com/docs/plugins/how-plugins-run/)

## 직군별 한눈에 보기

개발 순서는 [SSOT·Graph 우선 실행 계획](#ssot-graph-plan)을 따른다. 첫 시연은 취소 정책 한 건의 영향 추적과 예약 버튼 한 개의 디자인 값 왕복이다.

| 역할과 실제 질문 | 0.27.1에서 쓸 수 있는 기능 | 개발 중 확인한 기능 | 다음에 만들 결과물 |
|---|---|---|---|
| 기획자 — “취소 정책이 바뀌면 어느 화면과 예외 흐름을 검토해야 하나?” | 요구사항·화면·행동·인수 조건을 그래프로 연결하고 화면 명세 Markdown/JSON을 생성한다. Design 설명 보드에서 연결된 화면으로 이동한다. 작업의 선행 관계와 revision 상태를 확인한다. | 한·영 기능 검색과 기능별 실행 경로 안내 | **요구사항 변경 리뷰**. 변경 전후 정책, 영향을 받는 화면·행동, 누락된 예외, 검토자 결정을 한 장에서 확인 |
| 엔지니어 — “버튼의 실제 여백과 토큰은 무엇이고 어느 버전에서 읽었나?” | 허용 페이지의 실제 값을 JSON으로 읽고, 준비된 범위의 토큰·컴포넌트 소비자를 비교·선택 적용한다. 변경 후 웹 값도 검증할 수 있다. | 공식 Plugin API·REST 명세 색인, 로컬 TypeScript SDK 생성·빌드, 컴포넌트 속성 참조 읽기 보강 | **오프라인 핸드오프 팩**. 선택 프레임의 치수·토큰·상태·에셋과 출처 revision을 HTML/JSON으로 받아 Dev Mode 없이 구현 |
| 디자이너 — “페이지를 더 만들 수 없어도 컴포넌트를 수정하고 기존 화면에 미치는 영향을 알 수 있나?” | 재사용 main/instance, TEXT 속성, variant, Auto Layout·Frame·Group, 로컬 변수, 프로토타입 연결과 실제 읽기 검증. 지원 스칼라는 변경 전 값을 확인하고 적용한다. | BOOLEAN 표시·INSTANCE_SWAP 슬롯/선호 대상/개별 override, Design 도형·그리드·Smart Animate 예제 등 | **현재 페이지 안 제작** 및 **컴포넌트 변경 미리보기**. 영향받는 인스턴스·override를 확인하고 같은 프레임을 재사용 |

실제 릴리스 기록에는 프로젝트 한 건의 Figma 44화면, 노드 4,820개, main 24개, set 2개, instance 494개, 변수 69개가 있다. 이는 당시 설치본과 해당 파일에서 관측한 수치다. 세 직군이 서로 다른 신규 Starter 계정으로 전체 흐름을 수행하는 시나리오는 아래 출시 인수 항목이다. [인수 행렬](development-roadmap/FINAL_ACCEPTANCE.md) · [릴리스 영수증](llm-wiki/releases.md#v0.27.1)

## 무료 플랜에서의 실행 조건

| 상황 | 가능한 경로 | 설계에 반영할 조건 |
|---|---|---|
| 편집 가능한 Design 파일 | 데스크톱에서 개발 플러그인의 manifest를 등록하고 해당 파일에서 실행한다. 기존 Flow는 고정 workspace와 localhost 제어 또는 패널·JSON 전달을 제공한다. | 사용자 실행 세션이 필요하다. 플러그인을 닫은 뒤 상시 감시를 약속할 수 없다. 로컬 개발 플러그인 사용자는 각자 설치한다. [Quickstart](https://developers.figma.com/docs/plugins/plugin-quickstart-guide/) · [실행 조건](https://help.figma.com/hc/en-us/articles/360042532714-Use-plugins-in-files) |
| 세 사람의 협업 | 공동 편집할 파일은 Starter 팀의 공유 폴더에서 운영한다. 개인 Draft는 소유자가 가공하고 보기 권한의 동료에게 결과를 전달할 수 있다. | 개인 Draft 수는 무제한이다. Starter Draft 초대는 보기 권한이고, 팀 폴더의 Design·Sites 파일은 합산 3개다. Starter 팀 Design 파일은 파일당 최대 3페이지다. [Starter 구조와 권한](https://help.figma.com/hc/en-us/articles/13838684089751-Starter-plan-overview) · [페이지 한도](https://help.figma.com/hc/en-us/articles/360038511293-Create-and-manage-pages) |
| 보기 권한의 기획자·개발자 | Design 기본 UI로 거리·속성을 확인하고 허용된 내보내기를 사용한다. 편집자가 생성한 명세 파일은 별도 Figma 실행 없이 읽는다. | 플러그인 실행에는 파일 편집 권한이 필요하다. 내보내기·공유 정책을 존중하고 이미 승인한 결과만 전달한다. [기본 검사](https://help.figma.com/hc/en-us/articles/22012921621015-Guide-to-inspecting) · [플러그인 권한](https://help.figma.com/hc/en-us/articles/360042532714-Use-plugins-in-files) |
| Dev Mode·네이티브 주석 | Design 캔버스의 일반 Frame/Text 설명 보드와 로컬 명세를 사용한다. | Starter에는 Dev Mode가 없다. Figma의 네이티브 주석 작성은 공식 플랜·좌석 조건이 있다. 기존 Flow의 일부 엄격한 제작 검사는 실제 주석까지 요구하므로 Starter 보드 전용 검증 계약이 필요하다. [Starter 제품 범위](https://help.figma.com/hc/en-us/articles/13838684089751-Starter-plan-overview) · [주석 권한](https://help.figma.com/hc/en-us/articles/20774752502935-Add-measurements-and-annotate-designs) · [현행 네이티브 검사](../figma-bridge/code.js) |
| 팀 라이브러리·다중 테마 | 같은 파일에서는 로컬 main·instance·변수를 재사용한다. 파일 간 공유는 버전을 붙인 토큰·컴포넌트 원본을 전달하고 수신 파일에서 로컬 객체에 연결하는 방식으로 설계한다. | Starter에는 팀 라이브러리가 없다. 추가 variable mode도 플랜 조건을 따른다. 여러 테마는 로컬 JSON에서 보관하고 선택 테마를 별도 프리뷰에 투영할 수 있다. 파일마다 생성된 main·variable ID는 따로 매핑해야 한다. [플랜 범위](https://help.figma.com/hc/en-us/articles/13838684089751-Starter-plan-overview) · [변수 모드](https://help.figma.com/hc/en-us/articles/15343816063383-Modes-for-variables) |
| 기록과 서버 연동 | 허가된 스냅샷·변경 요약·승인 기록을 로컬이나 팀의 Git에 보관한다. | Starter Figma 버전 내역은 30일이다. 로컬 기록의 보존 기간은 팀이 정하고 Figma 클라우드 버전 복원은 별도로 다룬다. REST는 사용 시 좌석·대상 리소스·endpoint별 호출 한도와 권한을 확인한다. [Starter 버전 내역](https://help.figma.com/hc/en-us/articles/13838684089751-Starter-plan-overview) · [REST 한도](https://developers.figma.com/docs/rest-api/rate-limits/) |
| 배포와 파일 식별 | 현재는 발급된 ID와 로컬 개발 manifest로 동일 workspace를 등록한다. | 현행 manifest는 Design 전용이고 `enablePrivatePluginApi`를 사용한다. 공식 문서는 개발 중 로컬 플러그인에 해당 API를 허용한다. Community 공개판 설계에는 `figma.fileKey` 부재를 포함해야 한다. 파일 식별 실패 시 기존 쓰기 검사를 유지한다. [manifest](https://developers.figma.com/docs/plugins/manifest/) · [fileKey](https://developers.figma.com/docs/plugins/api/figma/) · [현행 workspace](../tools/figma_workspace.py) |

현재 플러그인의 대상은 Figma Design이다. 같은 파일에서 기획 검토, 컴포넌트 편집, 개발자 인계를 수행하며 좌석·파일별 제한은 실제 편집기 결과에 기록한다.

**운영 단위.** 설치 시 Figma가 발급한 ID로 desktop 개발 플러그인을 한 번 등록한다. 편집자가 파일에서 열면 플러그인이 문서 값을 읽고, 로컬 도구가 그래프 대조·명세 생성·기록을 맡는다. 준비된 작업은 패널 버튼과 JSON 저장 경로로도 사용할 수 있다. 선택적으로 붙이는 Codex·외부 모델의 이용 조건은 해당 서비스를 따르며, 무료 인계 시연은 로컬 CLI와 정적 파일만으로 구성한다. v0.27.1의 개인 작업공간은 POSIX 기준이다. 제어 채널의 읽기 결과 상한은 32 MiB로, 큰 파일은 페이지·대상 범위를 나눠 읽어야 한다. [사용 가이드](guide.md) · [0.27.1 전송 구현](https://github.com/jonsoku-dev/figma-flow/blob/v0.27.1/tools/figma_control.py)

## 현재 인벤토리와 사용 시작점

| 상태 | 묶음 | 현재 입력 → 결과 | 근거 |
|---|---|---|---|
| 배포 | 요구사항·화면 명세 | 의미 ID와 주석 구조가 있는 graph → `screen-spec.md`, `specifications.json`, `contract.json` | [명세 도구](../tools/specifications.py) · [읽기 쉬운 명세 계약](../specs/readable-specifications/spec.md) |
| 배포 | 시안 비교·선택·본제작 | 브리프·에셋·선택 기록 → 검토 결과, 구조화된 네이티브 화면·설명 보드·프로토타입 | [설치·검토·본제작 가이드](guide.md) · [인수 범위](development-roadmap/FINAL_ACCEPTANCE.md) |
| 배포 | 읽기·수정·선택 동기화 | `discover/import/review/sync/native-edit` 작업, file/page/revision → 범위가 명시된 실제 값·결과 JSON. 전체 읽기와 일부 필드 요약을 구분 | [로컬 제어](../tools/figma_control.py) · [토큰 왕복](../examples/graph-ssot/README.md) |
| 배포 | 자산·품질·이력 | HTML/CSS·폰트·이미지 목록, 레이아웃 검사, 선행 작업, 실행 단계, 진단 내보내기 | [RD 기능 목록](development-roadmap/README.md) · [작업 이력 계약](../specs/workspace-activity/spec.md) |
| 개발 중 | 속성 제작·읽기 | 선언된 BOOLEAN·INSTANCE_SWAP, 기본값·선호 대상·인스턴스별 값 → 소유 main/set과 실제 하위 레이어 참조를 연결하는 코드 | [작업 트리의 제작 계약](component-property-authoring.md) · [읽기 구현](../figma-bridge/native_semantic_read.js) |
| 개발 중 | 기능 검색·예제 | 한국어/영어 의도 → 기능 또는 준비 경로. 조사 시점의 Plugin API 색인은 멤버 1,382개, REST 색인은 endpoint 59개, 로컬 SDK 예제는 6개. 검색 결과와 예제 컴파일의 범위는 각 문서에 표시 | [기능 검색](../tools/figma_feature.py) · [SDK](figma-sdk-project.md) · [레시피](figma-recipes.md) |

**오늘 쓸 수 있는 기획 인계 예시.** 저장소 루트에서 다음 명령을 실행하면 작은손 커피공방의 구조화된 그래프를 읽어 새 디렉터리에 명세를 만든다. 명세 작성자만 이 명령을 실행해도 된다. 수신자는 전달받은 Markdown을 열어 화면별 동작과 근거를 읽는다. 신규 정적 HTML 팩은 아래 E1 범위다.

```sh
python3 -B tools/specifications.py export \
  --graph apps/little-hands/design/graph.json \
  --out .figma-flow/starter-spec-first
```

출력 경로는 새 경로여야 한다. 재실행할 때는 새 이름을 사용한다. 이 조사에서 같은 그래프에 실제 `export` 명령을 실행해 파일 3개와 명세 268개를 확인했다. 명세와 계약에 기록된 원본 식별자가 일치했다. 이번 시연 범위는 로컬 내보내기이며, 계정별 Starter 네이티브 실행은 후속 인수 항목이다. [예제 그래프](../apps/little-hands/design/graph.json) · [실행 소스](../tools/specifications.py)

## 앞으로 만들 기능과 인수 기준

아래 ID는 직군별 납품 기능을 가리킨다. **우선순위는 G0~G4의 정본 보존·변경 추적·왕복 검증이 가장 높다.** S1·P1·E1은 이 과정을 실제 업무로 검증할 첫 배송 묶음이다. 표의 P0/P1은 직군 기능끼리의 우선순위다.

| ID · 주 사용자 | 입력과 행동 → 산출물 | 실패·재실행 시 동작 | 인수 기준 |
|---|---|---|---|
| **S1 · 공통 · P0** 기존 페이지 작업 | 편집자가 대상 페이지와 빈 위치를 지정 → 미리보기에 예상 크기·생성/갱신 목록을 표시 → Flow 소유 Frame 아래 화면·명세·로컬 라이브러리 생성. 주석 사용 가능 여부와 보드 전용 결과를 기록 | 페이지 추가·삭제 없이 동작. 다른 소유자의 동명 프레임을 보존. 대상 불일치·충돌 시 적용 전 중단. 실패 시 이번 작업의 생성물만 정리 | **이미 3페이지인 Starter 팀 파일**에서 페이지 수 유지, 같은 입력 재실행 시 중복 0개, 수동 추가한 형제 레이어 보존, 보드의 대상 링크 왕복, 주석 권한이 없을 때 보드 전용 상태 표시 |
| **P1 · 기획자 · P0** 요구사항 변경 리뷰 | 이전·현재 graph와 정책 변경 하나 → 영향받는 화면·행동·예외·인수 조건 목록 및 담당자 결정 기록 | 연결 없는 항목은 누락, 의미가 모호한 연결은 확인 필요로 표시. 사람의 선택은 입력 버전과 함께 저장 | 예제 취소 정책의 직접 연결 화면과 각 연결 이유를 표시한다. 운영 화면이 실제 정책 소비자라면 그 근거를 연결한 뒤 포함한다. 무관 화면은 제외하고 관련 근거가 변하면 이전 결정을 재검토 대상으로 표시한다. |
| **E1 · 엔지니어 · P0** 오프라인 인계 팩 | 편집자가 허용된 화면을 전체 읽기 → static HTML, JSON, 허용한 에셋, Figma 노드 링크, 관측 시각·revision·파일별 해시 → 기획자와 엔지니어에게 전달 | 혼합 폰트·지원 밖 속성·누락 에셋을 개별 표시. 원문 문구·이미지 포함 범위를 내보내기 전 확인. 오래된 읽기와 요약 읽기는 출처와 누락을 표시 | 수신자가 Figma 로그인·토큰·로컬 서비스 없이 HTML을 열어 간격, 텍스트 스타일, 인스턴스 출처, 수용 조건 확인. 표본 프레임의 수치가 getter와 일치. 숨긴 예제 고객 문구와 인증값은 팩에 0건 |
| **D1 · 디자이너 · P1** 컴포넌트 영향 미리보기 | 로컬 main과 변경 후보 → 재사용 인스턴스 목록, 텍스트·BOOLEAN·SWAP override, 예상 변경·보존 목록 | main/slot/현재 값 불일치 시 쓰기 중단. 동일 화면에 복제 가능한 시험 프레임 제공 | 서로 다른 너비·문구를 가진 인스턴스에서 main 변경 후 override 보존. 표시/숨김과 swap은 실제 하위 노드 visible·main ID까지 재읽기. 승인된 부분만 적용 |
| **D2 · 디자이너·엔지니어 · P1** 파일 간 로컬 키트 | 버전 있는 토큰·컴포넌트 선언 → 대상 파일 로컬 main/variable 생성 또는 갱신. 사용자가 의미 ID와 대상 매핑 확인 | 파일 복제·이름 충돌은 미해결 매핑으로 표시. 대상 파일의 고유 ID·수동 변경을 덮기 전 diff 제공 | 두 Starter 파일에서 같은 키트 적용. 재실행 시 중복 없음, 사용자 변경 충돌 표시. 각 파일 안의 인스턴스가 그 파일 main을 가리킴. 팀 라이브러리 publish/import가 없어도 통과 |
| **X1 · 세 직군 · P1** 전달 후 변경 추적 | P1 결정, E1 팩 revision, native·웹 관측 → 어떤 변경이 어느 산출물을 무효화했는지 표시 | 부분 동기화·불확실한 쓰기·다른 파일을 별도 상태로 유지. 마지막 성공 버전으로 복구할 때 현재 값부터 대조 | 선택한 색상만 변경, 무관한 값 보존, 웹·native 근거 각각 표시. 이전 팩에 최신 상태를 표시하지 않음. 로컬 기록을 재개해 같은 작업을 중복 실행하지 않음 |

**구현 연결.** S1은 기존 importer·direction producer의 페이지 생성 및 실패 정리 경계를 함께 바꿔야 한다. 현재 importer는 실패하면 그 시도에서 생성한 page를 정리한다. 기존 페이지 재사용 시 정리 대상을 소유 Frame과 이번 실행의 부수 자원으로 좁히는 작업이 선행한다. P1/X1은 기존 요구사항 그래프와 작업 간 revision 관계, E1은 명세 export와 실제 readback, D1/D2는 현재 컴포넌트·토큰 계약을 재사용한다. [importer](../figma-bridge/code.js) · [시안 생성기](../figma-bridge/direction_review.js) · [그래프 계약](../skills/figma-flow/references/graph-contract.md)

**역할 간 전달 계약 제안.** P1 결정에는 요구사항 ID, 원본 graph 해시, 변경 전후 정책, 영향 화면·행동 ID, 결정 상태를 담는다. 디자이너는 선택한 결정과 S1 대상 프레임을 연결한다. E1의 `handoff.json`에는 형식 버전, graph 해시, 작업 revision, 허용된 화면·노드 ID, 관측 시각, 추출 범위, 속성의 단위, 에셋 해시와 제외 사유를 담는다. HTML은 같은 JSON을 읽는다. 엔지니어가 발견한 차이는 해당 revision과 노드 ID를 붙여 돌려준다. 파일·노드 링크는 수신자가 접근해도 되는 범위에서 포함한다.

기존 후속 설계와 연결하면 D1/D2는 **NF-01**, 대형 파일에서 선별적으로 읽는 최적화는 **NF-02**, P1/X1의 원인 추적은 **NF-03**, E1 결과를 실제 SSR 앱·외부 CSS까지 유지하는 확장은 **NF-04**다. 검증 재개·포크 간 근거 교환은 **NF-05**, 오래된 준비 번들의 호환성은 **NF-06**에서 다룬다. [기존 후속 설계 6건](next-roadmap/README.md)

<a id="ssot-graph-plan"></a>

## SSOT·Graph 우선 실행 계획

**첫 완료 조건.** 기획자가 취소 정책을 수정하면 어느 화면·테스트를 다시 검토해야 하는지 근거와 함께 알 수 있어야 한다. 디자이너가 채택된 버튼 색을 바꾸면 엔지니어는 같은 graph 버전에서 생성한 CSS를 받고 실제 브라우저와 Figma에서 같은 값을 확인할 수 있어야 한다. 둘 중 한쪽이 오래됐으면 인계 화면에 그 상태가 보여야 한다. 아래 G0~G5는 구현할 순서이며, 이번 조사에서 실행한 검사는 별도로 표시한다.

### 현재 확인한 기준점

| 읽거나 실행한 대상 | 결과 | 계획에 미치는 영향 |
|---|---|---|
| 작은손 예제의 `graph.json` | 노드 357개, 관계 1,101개. `design_foundations`와 `draft_prototype`이 있고 `design_system`은 없다. | 요구사항 추적과 디자인 값 채택은 별도 상태다. 전체 앱의 디자인 SSOT 채택 범위는 현재 비어 있다. [실제 그래프](../apps/little-hands/design/graph.json) |
| `graph.py validate`와 `validate --strict-local` | 구조 검사는 종료 0, 엄격 검사는 종료 1. 예를 들어 `AC-006`과 `TEST-006`의 상태는 `unverified`다. | 과거 앱 테스트 성공과 특정 그래프 버전의 근거 연결 사이에 차이가 있다. 해당 실행의 입력·대상·결과를 연결해야 상태를 갱신할 수 있다. [검사 계약](../skills/figma-flow/references/graph-contract.md) |
| `REQ-006`의 직접 관계와 전체 `impact` | 직접 연결은 `AC-006`과 화면 네 개(예약 확정·대기 등록·취소 확인·취소된 예약). 모든 방향성 관계를 따라가면 영향 후보 64개. 예제에 명시적 `depends-on` 관계는 0개다. | 직접 추적, 재검토가 필요한 의존 관계, 내비게이션 탐색을 화면에서 구별한다. 영향 후보 수를 재작업 건수로 쓰면 안 된다. [그래프 도구](../skills/figma-flow/scripts/graph.py) · [freshness 계산](../skills/figma-flow/scripts/ssot.py) |
| 작은손의 그래프 생성기 | `REQS`의 순서로 REQ·AC·TEST ID를 만들고 `STATES`의 숫자로 연결한다. `build`가 새 사전을 구성해 `graph.json`을 기록한다. | 목록 중간 삽입과 재생성이 기존 ID의 의미·채택된 필드·검증 근거에 미치는 영향을 먼저 고정한다. 현재 파일에 `design_system`만 손으로 추가하는 방법은 다음 생성에서 사라질 위험이 있다. [생성기](../apps/little-hands/design/source.py) |
| 독립 로컬 회귀 검사 | 동시 CAS 쓰기, 오래된 수정 거부, 웹 출력 실패 후 복구, 다른 범위의 바인딩 거부, 근거 변경의 영향 범위 검사 다섯 건 통과. | 이 동작을 회귀 기준으로 보존한다. 이번 검사 범위는 로컬 fixture이며 작은손의 영속 CSS 및 실제 Figma 왕복은 G3~G4의 인수 대상이다. [정본 쓰기 검사](../tests/test_graph_design_system.py) · [왕복 검사](../tests/test_graph_sync.py) · [근거 검사](../tests/test_ssot.py) |

### 어떤 사실을 어디에서 바꾸는가

| 사실 | 쓰기 책임과 변경 경로 | 소비자가 확인할 근거 |
|---|---|---|
| 제품 의도와 요구사항 | 기획자가 원문 변경을 결정하고 안정적인 의미 ID로 graph의 요구사항·화면·행동·인수 관계를 갱신 | 원문 출처, 변경 전후 graph, 바뀐 ID와 관계 |
| 실제 취소 가능 여부·가격·권한 | Django 서비스·DB가 실행 결과를 소유한다. 정책 변경은 앱 코드·업무 테스트로 입증하고 graph에 해당 구현과 결과를 연결 | 성공·거부 사례, 구현 위치, 테스트 식별자와 실행 근거 |
| 채택된 디자인 값 | 프로젝트 graph의 `design_system.tokens/components`가 소유한다. 디자이너의 직접 편집은 실제 읽기 → 차이 검토 → 이전 SHA가 맞을 때만 graph 반영 | primitive·alias·사용처, graph SHA, binding과 실제 계산값 |
| Figma와 웹의 현재 모습 | Figma getter와 브라우저 computed style이 각각 관측값을 제공한다. 파일별 node ID와 selector는 해당 의미 ID의 매핑으로 관리 | file/page 범위, 대상 ID, 읽은 시각, 전체/부분 범위, 적용한 출력의 해시 |
| 명세·승인·실행 이력 | Markdown·HTML·CSS는 해당 graph 버전에서 생성한다. 승인과 실행 결과는 당시 revision에 연결해 보존한다. | 오래된 문서도 열 수 있어야 하고, 변경 후 현재 상태와 이전 승인 시점을 식별할 수 있어야 한다. |

파일마다 이미 쓰는 식별자를 사용한다. Graph 원본 SHA, 선택·작업 revision, 출력 파일 SHA와 pairing은 서로 다른 질문에 답한다. 하나의 버전 문자열로 합치지 않는다. 원격 링크만 기록된 자료는 실제 내용이 관측될 때까지 확인 대기로 남긴다. [현행 SSOT 계약](../skills/figma-flow/references/graph-contract.md) · [값 쓰기와 잠금](../tools/graph_design_system.py) · [pairing과 복구](../tools/graph_sync.py)

### 구현 순서와 통과 조건

| 순서 | 기존 기능을 어떻게 업데이트할지 | 납품물과 인수 기준 |
|---|---|---|
| **G0 · 기준선과 소유권** | 첫 대상은 작은손의 `REQ-006`과 예약 버튼의 `backgroundColor`로 한정한다. 현재 graph·원문·캡처·CSS와 관련 코드/테스트의 식별자를 보존한다. 앱 고유 정책, 관측된 레이아웃, 사람이 수락한 값을 표시한다. | 기준선 표와 읽기 전용 비교 결과. 두 사람이 같은 입력으로 직접 관계와 토큰의 채택 여부를 재현한다. 근거가 비어 있는 항목은 상태와 이유가 남는다. |
| **G1 · 기존 생성기와 ID 보존** | `STATES`·`REQS`의 위치 참조를 명시적 ID로 옮긴다. 기존 ID를 그대로 이관한다. 생성기는 임시 출력에 변경 후보를 만들고, 제품 graph의 채택 값·사람이 작성한 관계·검토 기록을 소유 범위 밖으로 보존한다. 원본 SHA가 달라지면 저장을 중단한다. | 기존/새 결과 diff, 구버전 입력 fixture, 재생성 검사. 동일 입력 반복·목록 재정렬·중간 요구사항 삽입 후 기존 ID가 같은 의미를 가리킨다. 임시 graph에 채택한 토큰과 근거를 추가하고 재생성해 보존을 확인한다. 삭제된 원본은 고아 후보로 보고하고 이전 근거를 추적할 수 있다. |
| **G2 · 정책 변경과 기존 명세·이력 개선** | `graph_diff.py`의 전후 비교, `graph.py`의 직접 관계, `ssot.py`의 명시된 의존 관계 전파를 P1/X1에 사용한다. 근거가 있는 의존 관계만 추가한다. `specifications.py` 출력과 검토 결정에 해당 원본 해시를 연결한다. | 실제 취소 정책 한 건의 변경 리뷰. 직접 연결된 네 화면을 이유와 함께 표시하고 무관한 로그인 화면을 수정 대상으로 지시하지 않는다. 운영 명단 반영은 실제 서비스·테스트 근거로 판단한다. 영향받은 인수 조건에는 현재 실행 근거를 연결하고 관련 근거가 낡으면 재검토를 표시한다. 엄격 검사 실패 항목은 별도로 남긴다. |
| **G3 · 디자인 값 한 개의 영속 소비** | NF-04의 첫 단위를 앞당긴다. 디자이너가 승인한 버튼 배경색 하나에 primitive·semantic alias·사용처를 명시한다. 기존 `resolve_design_system`과 MJS 출력을 재사용해 외부 CSS와 manifest를 만들고, 실제 Django 템플릿이 해당 CSS를 읽게 한다. G1 재생성 후에도 선언이 남아야 한다. | 동일 입력의 CSS 바이트가 일치한다. 정적 파일 수집 후 실제 웹에서 선택한 버튼의 계산값을 확인한다. 원본 그래프를 재생성하고 서버를 다시 시작해도 같은 값을 읽는다. 다른 의미의 위험 버튼, 모바일 상태, 수동 override가 같이 변하지 않는지 검사한다. [SSR 설계](next-roadmap/NF-04-renderer-adapters.md) |
| **G4 · Starter에서 네이티브 왕복** | 기존 S1 제작 경로에 소유 Frame 재사용과 보드 전용 명세를 연결한다. 승인한 main·instance·변수의 실제 ID를 발견한 뒤 기존 선택 적용·역수입·복구 경로를 쓴다. 기존 `source.py` 재생성, 패키지 재시작, 브라우저 재로딩을 경계에 포함한다. | **정방향**은 graph의 색 수정 → 기존 페이지의 Figma getter와 웹 계산값 확인. **역방향**은 Figma에서 같은 색 수정 → 새 전체 읽기 → dry-run → SHA 확인 후 반영 → 웹 재생성 → 새 pairing 확인. 같은 수정 재실행 시 중복 0개. 오래된 값, 다른 파일, 부분 읽기, alias 묶음 일부, 투영 쓰기 중단에서 관련 없는 값·레이어 보존. 원본 캡처는 보존하고 새 관측을 별도 기록한다. |
| **G5 · 직군별 배송과 확장** | P1 변경 리뷰·S1 작업 결과를 E1 인계 팩에 연결한다. 기획자는 예외와 승인, 엔지니어는 CSS·리비전, 디자이너는 main/instance와 override를 확인한다. D1·D2의 다른 컴포넌트/파일로 범위를 넓힌다. 증분 읽기 최적화는 같은 값·누락 범위를 반환하는 기준선부터 측정한다. | 보기 전용 사용자가 정적 팩을 오프라인으로 읽는다. 이전 팩은 어느 버전인지 표시되고 새 팩은 새 graph·native·web 근거를 가리킨다. 신규 필드나 파일별 매핑마다 지원 범위·충돌·복구 사례를 추가한다. |

G1과 G2의 **상태 보존·영향 판정**이 첫 개발 단위다. 이어서 G3의 **영속 웹 소비**를 입증한다. 첫 직군 기능 릴리스의 완료 조건은 G4 왕복과 G5의 첫 인계 팩 시연이다. D1/D2 전체, 앱 전체의 토큰 전환, 대형 파일 성능 개선은 각각 자기 범위의 증거가 생길 때 확대한다.

### 작업 중 발견하는 하드코딩 처리

| 실제 후보 | 이번 계획의 처리 | 개선을 입증하는 검사 |
|---|---|---|
| `enumerate(REQS, 1)`과 화면별 요구사항 번호 | **G1에서 우선 수정.** 기존 `REQ-006`, `AC-006`, `TEST-006` 의미를 고정하고 명시적 ID로 연결한다. | 목록 재배치 후 취소 정책이 같은 화면·테스트를 가리킨다. |
| `source.py`의 `paddingX == 22`, `radius == 0`, 본문 `15px`·`Hahmlet` | **역할 선언과 실제값 검사를 분리.** 선택한 컨트롤에 의미 역할을 부여하고 숫자는 관측치와의 대조에만 쓴다. | 같은 22px를 쓰는 무관한 컨트롤을 함께 묶지 않고, 채택한 간격만 바꾸면 선언한 소비자만 바뀐다. |
| CSS의 `--rust`와 `--danger`가 현재 같은 색상 | **G3에서 의미를 확인.** 예약 CTA와 위험 동작의 독립성 또는 의도된 공유를 디자이너가 결정한다. 동일 색상이라는 이유만으로 alias를 만들지 않는다. | CTA 원색을 바꿨을 때 위험 색상의 실제 계산값이 결정된 계약과 일치한다. [앱 CSS](../apps/little-hands/static/littlehands/app.css) |
| Python `NODE_FIELDS`와 JS `nativeEditFields` | **계약 불일치 검사 후보.** 두 실행기의 지원 필드·타입·소유자 조건을 비교한다. 반복 변경에서 어긋남이 재현되면 기존 선언에서 정적 허용 목록을 생성한다. graph 전체 속성 목록은 용도가 더 넓다. | 지원 목록·검증 규칙이 다른 필드를 잡고, 임의 필드는 양쪽에서 거부한다. [준비기](../tools/native_edit.py) · [실행기](../figma-bridge/native_edit.js) |
| DB 업무 제약, 전송 상한, 캡처 좌표·폰트 보정, 독립 회귀 기대값 | **기존 소유처에 유지.** 실제 결함이나 변경 요구가 생기면 각각 업무 코드, 프로토콜, 새 측정, 독립 검사로 다룬다. | 디자인 토큰 변경으로 취소 정책·안전 상한·과거 관측을 덮어쓰지 않는다. |

각 작업의 diff에서 바뀌는 값과 그 소비자를 먼저 검색한다. 발견한 후보는 **위치 → 사실 소유자 → 재현되는 불일치 → 이번 수정 또는 보류 이유 → 회귀 검사** 한 줄로 남긴다. 현재 기능과 같은 원인이고 소비자를 확인할 수 있으면 같은 변경에서 원본과 소비자를 함께 수정한다. 의미가 불명확하거나 다른 직군의 결정이 필요하면 해당 기능의 후속 항목에 남긴다. 완료 지표는 제거한 숫자의 개수보다 **한 번의 정본 변경이 올바른 소비자에만 반영되는지**다. 기존 정적 소비자 분석은 관측·후보·동적 코드로 인한 미확인을 구분하므로 Django 적용 범위를 확인해서 재사용한다. [기존 토큰 소비자 분석](../tools/token_code_scope.py)

### 구현자가 재현할 첫 점검

```sh
python3 -B skills/figma-flow/scripts/graph.py validate apps/little-hands/design/graph.json
python3 -B skills/figma-flow/scripts/graph.py validate apps/little-hands/design/graph.json --strict-local
python3 -B skills/figma-flow/scripts/graph.py impact apps/little-hands/design/graph.json --from REQ-006
python3 -B -m unittest tests.test_graph_design_system.GraphDesignSystemTests.test_concurrent_cas_writers_only_one_can_succeed tests.test_graph_design_system.GraphDesignSystemTests.test_invalid_or_stale_updates_never_modify_graph tests.test_graph_sync.GraphSyncTests.test_web_write_failure_is_recoverable_twice_without_graph_rollback tests.test_graph_sync.GraphSyncTests.test_wrong_scope_alias_binding_identity_rejected_without_graph_write tests.test_ssot.SsotTests.test_evidence_mapping_edit_scopes_staleness_to_node_and_dependents
```

기준점에서 두 번째 명령은 종료 1이 예상된다. G1 재생성·실패 주입은 예제 복사본과 임시 출력에서 수행한다. 반영 전에는 graph와 근거 파일을 고정하고, 반영 후에는 변경된 ID·소비자·검증 수준을 남긴다. 복구 시 그래프가 이미 갱신됐고 웹 출력만 지연됐으면 기존 journal로 투영을 복구한다. 다른 작성자가 정본을 다시 바꿨으면 최신 SHA와 새로운 계획이 필요하다. [기존 역수입·복구 경로](../tools/graph_sync.py)

## 출시 판정 시연

1. 편집 가능한 Starter 팀 파일과 보기 권한 계정을 준비한다. 편집자는 기존 3페이지 중 하나에서 Flow를 직접 실행한다. 기본 시연에는 Figma MCP·REST 자격 증명·유료 AI를 설정하지 않는다.
2. 기획자가 취소 정책의 예외 한 건을 변경한다. 기대 영향 목록과 실제 P1 결과를 대조한 뒤 디자이너가 변경 범위를 선택한다.
3. 디자이너가 현재 페이지에 프레임을 생성하고 같은 입력으로 재실행한다. 페이지 수·노드 ID·연결된 main과 변수·수동 수정 보존을 대조한다. 한 건의 충돌을 의도적으로 만들고 부분 생성물과 다른 레이어를 확인한다.
4. 편집자가 E1 팩을 내보내고 보기 전용 동료가 네트워크를 끈 상태에서 읽는다. 화면 하나의 수치·링크·예외·revision을 원본과 대조하고 제외한 민감 문구를 검색한다.
5. 같은 파일의 토큰이 바뀌면 이전 팩에 재검토가 표시되는지 확인한다. 계정 플랜, 편집기, 파일 위치, 역할별 권한, 버전, 실제 읽기, 결과와 미검증 항목을 기록한다. API 선언 수·컴파일 성공과 실제 사용 성공은 각각 집계한다.
