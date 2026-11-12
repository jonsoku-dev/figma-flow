# 여러 페이지와 첨부 자료로 Figma Flow를 검증한다

2026-11-12. 계획과 실제 실행 범위를 함께 관리한다. 세 앱의 기본 웹·네이티브 검사와 정상 사진·글꼴 보조 사례를 실행했으며, 케이스별로 확인한 범위와 남은 조건을 [목록](cases.json)에 연결했다.
사용자의 요청은 단순 접수·좌석 앱에서 벗어나 새 다중 페이지 앱과 여러 입력 조합을 시험하고, 발견한 결함을 플러그인 수정과 재검증으로 연결하는 것이다.
실행 범위와 현황의 정본은 이 계획과 [케이스 목록](cases.json)이다. 새 사용 가이드를 만들지 않고 기존 [통합 가이드](../../docs/guide.md)를 재사용한다.

## 실행 범위와 완료 조건을 고정한다

새 앱 3개, 논리 페이지 40개를 시험한다. 모달·탭·행·viewport를 페이지 수에 더하지 않는다. 실제 URL 파라미터 값의 개수도 세지 않는다.
기본 입력으로 만든 모든 페이지를 모바일·데스크톱에서 확인하므로 기본 viewport 검사는 80개다. 오류·로딩·역할 상태와 보충 입력 검사는 별도다.
입력 실행 계획은 16개, 인수 케이스는 61개다. 현재 케이스 상태는 모두 `unverified`이며, 실제 부분 검증을 `verified_scope`와 해시가 있는 `evidence`에 기록한다. 이는 검사가 전혀 없다는 뜻이 아니며, 해당 케이스의 필수 실행·변형을 모두 충족한 합격 근거는 아직 부족하다는 뜻이다.

제품 의미와 관계는 앱별 graph 한 개가 소유한다. 화면 명세·HTML·Figma 메모·구현·근거는 같은 의미 ID를 참조한다. `cases.json`은 테스트 목록이며 새 제품 SSOT가 아니다.
기존 REQ-SPEC·REQ-QUALITY·REQ-UPDATE와 [graph 계약](../../skills/figma-flow/references/graph-contract.md)을 재사용한다. 미지원 기능이 제품 요구를 충족하지 못하면 구현 스펙과 인수 조건을 추가한다.
완료는 필수 적용 케이스의 최신 근거가 모두 있고, 해결되지 않은 기능 결함·자료 유실·잘못된 연결·심각한 접근성 결함이 없을 때다. `blocked`나 `unverified`를 합격에 넣지 않는다.
확인한 범위를 local/unit, 실제 웹, 실제 Figma getter, 실제 UI 관찰, 시각 비평으로 나눠 보고한다. 전체 화면 자동 양방향 재설계나 운영 서비스 보안을 검증했다고 확대하지 않는다.

## 현재 구현을 출발점으로 삼는다

1. [현재 검증 기록](../verification.md)의 작은 앱·16개 native 대상 결과를 이전 회귀 기준으로 보존한다. 새 앱이나 새로운 입력 유형의 성공으로 재사용하지 않는다.
2. [design_actions.py](../../tools/design_actions.py)의 `draft`는 brief·research·이미 작성된 candidate spec을 받는다. [design_directions.py](../../tools/design_directions.py)의 `Source`, `_candidate`, `_layout_signature`는 준비된 자료를 검사한다. 임의 앱 코드 importer나 URL 수집기로 간주하지 않는다.
3. [design_system.py](../../tools/design_system.py)는 토큰·variant·screen JSON을 컴파일한다. 임의 TSX·CSS 소스를 자동 해석했다고 주장하지 않는다. 코드 분석·컴포넌트 재사용·실제 렌더는 별도로 확인한다.
4. [critique 검사](../../tools/design_critique.py)는 근거의 연결을 검사하며 결과를 `visual_quality=unverified`로 둔다. 실제 시각 비평을 생략하지 않는다.
5. [graph_sync.py](../../tools/graph_sync.py)의 여러 PAGE discovery와 route별 probe를 재사용한다. 지원되는 토큰·컴포넌트 속성 왕복과 전체 화면 레이아웃 변경을 구분한다.

이는 소스에서 확인한 범위와 미검증 영역이다. 아래 후보를 재현 전부터 제품 버그라고 등록하지 않는다.

## 새 앱의 브리프와 실제 흐름을 만든다

| 새 앱 | 논리 페이지 | 복잡성을 만드는 목적 | 기본 입력 |
| --- | --- | --- | --- |
| Atlas Workspace | 14 | 업무·승인 관리 | `html` |
| Morrow Market | 14 | 커머스·주문·반품 | `url` |
| Paper Room | 12 | 독자·작성자·편집자 CMS | `design-system` |

Atlas는 구성원·검토자·관리자 역할과 공유 셸, 데이터 표, 보드, 폼, 승인 상세를 다룬다. 할 일 저장 실패·입력 유지·승인 후 목록 반영·권한 변경을 확인한다.
Morrow는 카탈로그·검색·상품·비교·장바구니·여러 단계 주문·반품을 다룬다. 재고와 가격 변경, 단계 복귀, 중복 제출, 실패 복구를 확인한다.
Paper는 독자·작성자·편집자 역할과 독자 화면·편집기·검토·캘린더를 다룬다. 긴 콘텐츠, 자동 저장 충돌, 반려·재검토, 가상 발행을 확인한다.
데이터·로그인·권한·재고·주문·발행 응답은 재현 가능한 mock 서버/fixture로 만든다. 실제 결제·메일·계정 생성·공개 발행은 연결하지 않는다.
Atlas는 밀도 높은 업무 UI, Morrow는 상품 중심의 편집적 구성, Paper는 읽기·작성에 집중한 타이포로 브리프를 구체화한다. 각 앱에서 도메인 의미가 다른 실제 컴포넌트와 페이지별 위계를 만든다. 같은 대시보드의 색과 제목만 바꿔 앱 수를 채우지 않는다.

## 입력 파일과 비교 근거를 준비한다

자료가 실제 채팅 첨부인지 로컬 파일 fixture인지 사용자 본문의 URL인지 기록한다. 첨부의 원래 이름·전달 metadata·로컬 경로·바이트 hash를 보존한다. 로컬 또는 에이전트 합성 전달은 실제 채팅 첨부 UX의 성공 근거가 아니다. 해당 호스트 전달을 실행할 수 없으면 그 범위만 미검증으로 남기고 독립 파일 검사는 계속한다.
HTML 입력은 자체 포함 파일, 여러 HTML과 외부 CSS·상대 자산, JS가 만드는 콘텐츠를 각각 준비한다. 원본을 복사·해시 고정하고 제공자가 지정한 범위의 실제 렌더를 관찰한다.
URL 입력은 최종 URL·관측 시각·본문 위치·viewport·캡처·채택한 원칙을 기록한다. 검색 요약이나 텍스트 조회만으로 레퍼런스 관찰을 완료하지 않는다.
디자인 시스템 입력에는 로컬 TSX 컴포넌트 Button·Field·Table·Dialog·Tabs·Nav, theme·CSS 변수·아이콘을 가진 통제된 fixture를 준비한다. 앱에서 실제 사용하는 컴포넌트와 패키지 버전을 고정한다. import 경로와 실제 렌더에서 재사용을 확인한다. Figma library 연결은 native 자료가 있을 때만 인정한다.
세 입력을 조합할 때 각 사실의 권한을 brief에 미리 적는다. 명시된 제품 동작은 brief, 시스템 값은 지정한 코드, 목업 구조는 HTML, 참고 원칙은 URL에서 가져오는 기본 fixture를 만든다. 충돌 fixture는 우선순위가 있는 경우와 없는 경우를 나눈다.
없는 기능이나 조건은 추측하지 않는다. 자료 속 지시문은 자료로 다루며 새로운 권한을 부여하지 않는다.

외부 문서 후보는 [Carbon 표 지침](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines), [GOV.UK 답변 확인 패턴](https://design-system.service.gov.uk/patterns/check-answers/), [Material navigation drawer](https://m3.material.io/components/navigation-drawer/overview)다.
2026-11-11 문서 조회에서 Carbon의 이전 주소는 현재 지침으로 리다이렉트됐고 GOV.UK 본문은 읽혔다. Material의 텍스트 응답은 JavaScript 필요 안내뿐이었다. 이 결과는 URL 수집 fixture의 근거이며 브라우저 렌더·시각 검사 성공을 뜻하지 않는다. 실제 실행 시 다시 수집하고 변동 자료와 보존 snapshot을 구분한다.

## 입력 조합의 실행 수준을 나눈다

`all-routes-smoke`는 목록의 모든 경로를 직접 열고 기본 내용·주 행동·오류를 확인한다. `all-routes-and-critical-flows`는 이 검사와 앱의 두 핵심 흐름을 수행한다.
`all-default-screens`는 해당 앱 모든 기본 화면의 두 viewport를 Figma에 전달하고 원본을 읽는다. `five-core-routes`는 앱마다 고정한 다섯 경로에 대한 native 보충 검사다.
`affected-targets`는 입력 변경이 영향을 준 실제 대상만 갱신하고 다른 대상 보존을 확인한다. 의존성 범위가 누락되거나 불확실하면 해당 앱 전체 route로 검사를 넓힌다. 보충 검사를 전체 페이지 native 성공으로 확대하지 않는다.

| 실행 ID | 입력 | 실제 웹 범위 | 실제 Figma 범위 |
| --- | --- | --- | --- |
| `atlas-brief` | `brief` | all-routes-smoke | not-requested |
| `atlas-html` | `html` | all-routes-and-critical-flows | all-default-screens |
| `atlas-url` | `url` | all-routes-and-critical-flows | five-core-routes |
| `atlas-design-system` | `design-system` | all-routes-and-critical-flows | five-core-routes |
| `morrow-brief` | `brief` | all-routes-smoke | not-requested |
| `morrow-html` | `html` | all-routes-and-critical-flows | five-core-routes |
| `morrow-url` | `url` | all-routes-and-critical-flows | all-default-screens |
| `morrow-design-system` | `design-system` | all-routes-and-critical-flows | five-core-routes |
| `paper-brief` | `brief` | all-routes-smoke | not-requested |
| `paper-html` | `html` | all-routes-and-critical-flows | five-core-routes |
| `paper-url` | `url` | all-routes-and-critical-flows | five-core-routes |
| `paper-design-system` | `design-system` | all-routes-and-critical-flows | all-default-screens |
| `atlas-html-url` | `html+url` | changed-routes-and-critical-flows | affected-targets |
| `morrow-html-design-system` | `html+design-system` | changed-routes-and-critical-flows | affected-targets |
| `paper-url-design-system` | `url+design-system` | changed-routes-and-critical-flows | affected-targets |
| `atlas-html-url-design-system` | `html+url+design-system` | changed-routes-and-critical-flows | affected-targets |

입력 실행 16개 외에 mode 권한, 두 PAGE, 왕복·충돌·복구, 규모 검사는 별도 suite로 수행한다. 복합 case는 `variants`의 각 상태에 근거가 있어야 합격한다. 미방문·미지원 상태를 임의로 적용 제외 처리하지 않는다.
BRIEF 대조군에서는 첨부 입력을 뺀다. TC-I01·I04·I08은 HTML·URL·시스템 코드를 각각 포함한 결과와 제거한 결과를 필수 대조한다. 혼합 TC-I11부터 I14까지는 입력을 하나씩 제거하며 구조·참고 원칙·실제 컴포넌트 import·토큰 소비가 의도한 원본에서 왔는지 대조한다. 고유 기대값과 대상 위치는 생성 전에 fixture에서 고정한다.
다른 입력 바이트·seed·소스 revision·환경이 같을 때만 기존 brief/단독 실행을 대조군으로 재사용한다. 다르면 대조용 렌더를 추가한다. 이 대조 렌더는 입력 실행 16개 외의 검사이며 누락하면 해당 입력 case를 닫지 않는다. 겉모습이 같다는 이유만으로 입력 무시를 단정하거나 소비 근거 없이 합격시키지 않는다.
보충 입력의 다섯 경로는 `cases.json`의 `core_routes`로 고정한다. 입력별 재생성을 전체 조합으로 무제한 늘리지 않고, 실패가 나온 축을 중심으로 확장한다.
단일 방향 `direct`를 기본으로 한다. 별도 비교 fixture에서는 두 안의 자료를 만들고 실제 선택 전 `WAIT_SELECTION`에 머무르는지 검사한다. 자동으로 선택하거나 본제작 승인 파일을 만들지 않는다.
테스트용 생성물은 exploratory 범위로 표시한다. 합성 승인 adapter는 local/unit 전용이며 실제 native 본제작 권한으로 사용하지 않는다.

## 단계별 실행과 수정 순서를 따른다

| 단계 | 실행할 일 | 종료 조건과 근거 |
| --- | --- | --- |
| 0. 기준 고정 | 현재 HEAD·dirty 파일·실제 소스 해시·설치/실행 버전·등록 workspace·작업 키·mock seed를 기록한다. 기존 작업을 보존한다. | `run.json`, 입력 해시, 기존 작은 앱 기준 결과가 있다. 버전 고정·개발 변경 예외가 명시돼 있다. |
| 1. 자료와 관측 준비 | 앱별 brief·경로·역할·오류 응답·입력 provenance·graph·명세를 작성한다. 먼저 입력을 무시하면 실패하는 검사를 만든다. | 모든 경로와 핵심 조작에 인수 ID가 있고 원본 입력과 실제 관찰이 연결돼 있다. |
| 2. Atlas 전체 실행 | HTML 기본 입력으로 모든 페이지와 두 핵심 흐름을 웹/Figma에서 확인한다. 가장 먼저 linked CSS·JS 렌더·긴 메모·공유 셸을 시험한다. | 모든 기본 경로/viewport, 실제 getter, UI 캡처와 오류 복구 근거가 있다. |
| 3. 결함 수정 | 재현 → 원인 가설 → 최소 수정 → 실패하던 검사 → 실제 재실행 순서로 고친다. 생성 앱의 임시 수정과 플러그인 수정의 소유권을 구분한다. | 문제 원인을 소유한 공통 경로에 수정이 있고 이전 실패와 수정 후 결과가 같은 조건으로 남는다. |
| 4. 다른 앱·입력 확장 | Morrow URL, Paper 시스템 코드의 전체 실행을 끝낸다. 나머지 단독 입력, 대조군, 혼합 입력을 표의 범위로 수행한다. | 전체 경로 누락 없이 입력 유형별 반영 근거가 있다. Atlas 수정의 미학/기능 회귀를 확인한다. |
| 5. 왕복·복구·규모 | route별 probe 합치기, native 역수입, stale·중복·사용자 주석·중단 복구·여러 PAGE 범위·지연 읽기를 수행한다. | 현재 graph/작업 revision/대상 IDs로 두 방향의 실제 값이 일치하며 미지원 변경과 충돌은 명시돼 있다. |
| 6. 독립 검수 | 입력 반영, 시각 품질, 의미/동작, 근거 최신성을 구현자와 다른 검수자가 확인한다. | 필수 케이스의 최신 결과와 미해결 목록이 있고 이전 근거를 통과로 복사하지 않았다. |
| 7. 인계 | 전체·실패·수정·재검증·미검증 범위를 집계하고 통합 가이드의 해당 기능만 갱신한다. | 결과를 다시 실행할 수 있다. 계획·소스 검사·실제 제품 증거를 구분한다. |

독립적인 fixture 제작과 읽기 전용 검수는 병렬로 진행한다. 플러그인 공통 파일과 Figma workspace/PAGE에는 한 번에 한 writer만 둔다.
이미 실행 중인 서버·다른 앱·다른 사용자의 변경은 중단하거나 초기화하지 않는다. 임시 테스트 데이터만 해당 run 범위에서 관리한다.
이 계획은 PR·병합·릴리스·배포 또는 자동 반복 일정 등록을 승인하지 않는다. 실행 시작마다 현재 사용자 지시와 파일 범위를 다시 고정한다.

## 시각·native·소비자 흐름을 따로 판정한다

모든 기본 페이지를 390×844와 1440×1000에서 확인한다. 320px·768px·200% 확대·키보드·긴 문구는 고정 핵심 경로에 추가한다.
시각 검수는 콘텐츠 위계, 타이포, 간격·밀도, 컴포넌트 일관성, 자산, 반응형, 주 행동을 캡처 위치별로 기록한다. 근거 없는 미적 점수는 만들지 않는다.
기존 불투명 텍스트 배경 문제를 회귀 항목으로 유지한다. 대비는 실제 합성 배경에서 확인하며 경고가 불확실하면 그 이유를 남긴다.
웹 route 수와 Figma `PAGE` 수를 혼동하지 않는다. 기본은 앱별 소유 PAGE에 모든 화면 프레임을 두고, 별도 두 PAGE fixture에서 scope와 다중 페이지 discovery를 시험한다.
Figma 검사는 우리 고정 플러그인만 사용한다. 공식 Figma MCP를 사용하지 않는다. 개발자 대신 앱 열기·초기 실행·시각 관찰에 쓰는 Computer Use는 기록한다.
소비자 경로는 최초 고정 플러그인 실행을 전제 조건으로 기록하고, 이후 생성·읽기·스펙 갱신·지원되는 동기화를 로컬 명령과 플러그인으로 재생한다. 소비자가 GUI 자동화를 써야만 통과하면 기능 결함으로 남긴다.
실제 Figma가 잠기거나 Dev Mode가 요금제로 막히면 해당 UI 관찰만 `blocked`로 남긴다. getter 검증·일반 Design 보드·웹·코드 검사는 독립적으로 진행한다.

## 측정 예산을 기준 실행 뒤 고정한다

Atlas의 1·6·14 경로 범위를 같은 장비·폰트·viewport·데이터로 측정한다. 생성/준비, plugin apply, 독립 read, 의미 검사, 웹 probe를 따로 기록한다.
동일 부하 baseline을 먼저 수집하고 수정본과 교차 실행한다. 외부 URL 로딩 시간은 수집 시간으로 분리한다. 파일 수·실제 노드 수·readback 바이트·오류 수·누락 대상 수와 완료 시간을 남긴다.
제안 회귀 규칙은 동일 부하 반복 실행의 중앙값이 기준의 1.25배를 넘으면 조사하는 것이다. 표본 다섯 번을 기본으로 하고 분산이 크면 원인을 기록한다. 측정 전 성능 합격을 주장하지 않는다.
새 기능에 비교할 기준이 없으면 비율을 만들지 않는다. 실제 첫 측정 뒤 절대 예산을 고정하고 변경 이유를 이력에 남긴다. control 명령의 기본 timeout 120초는 연결 동작 값이며 성능 SLA가 아니다.
부하 때문에 작업을 나누면 전체 누적 범위·원본 해시·부분 실패·재실행 상태를 보존한다. 검증 대상을 줄여 성능 합격으로 만들지 않는다.
현재 `specifications.py`의 갱신 계획은 최대 32개 대상을 받는다. 화면·중요 조작·viewport를 합친 수가 이를 넘으면 32개 이하로 나누고, 각 적용 뒤 새 getter와 검증 결과로 다음 계획을 만든다. 같은 보드의 변경 전 snapshot을 여러 묶음에 미리 재사용하지 않는다.

## 발견한 문제를 자체 개선으로 연결한다

각 finding에는 case ID·app/route/state·입력 hash·재현 절차·실제/기대 결과·분류·원인·수정 파일·수정 전후 근거·회귀 case를 남긴다.
분류는 plugin 결함, 생성 앱 결함, 입력 자료 결함, 환경 제한, 미지원 요구로 나눈다. 환경 실패를 plugin 성공으로 바꾸거나 생성 앱 수작업을 plugin 수정으로 보고하지 않는다.
자료 유실·다른 대상 쓰기·승인/권한 혼용은 해당 쓰기를 중단하고 복구부터 검증한다. 기능·연결·중요 접근성 결함은 통과 전에 고친다. 경미한 시각 차이는 위치와 사유를 남기되 읽기나 조작을 방해하면 필수 수정으로 올린다.
소스 입력과 브라우저/native 출력이 다른 가설을 한 번에 하나씩 시험한다. 같은 전제를 쓴 수정이 두 번 실패하면 그 전제와 관측 방법을 독립적으로 재검토한다.
수정 후에는 해당 case, 같은 입력 축의 대표 case, 다른 앱의 공유 소비자, 기존 Repair Desk/Quiet Seat 핵심 회귀를 실행한다. 광범위 변경일 때만 전체 suite를 넓힌다.
기대값을 실제 오작동에 맞춰 바꾸거나 검사기를 우회하지 않는다. 원본 변경이 정당하면 이유·새 hash·새 기준을 남기고 이전 실패를 보존한다.
발견한 반복 실패는 원인을 소유한 validator·계약·회귀 검사로 고친다. 필요할 때만 guide에 사용자가 알아야 할 제약을 추가한다. 자동 문서 증식이나 임의 릴리스를 하지 않는다.

## 기존 명령과 근거 경로로 재현한다

아래는 저장소에 실제 있는 entry point다. 대문자 값은 실행 때 고정한 입력·ID·새 출력 경로로 채운다. 이 문서 작성 중 실행한 제품 테스트 명령은 아니다.

```sh
python3 -B tools/plugin_startup.py check --figma-access forbidden
python3 -B tools/skill_dependencies.py --check
python3 -B tools/design_actions.py draft --project APP --brief brief.md --research research.md --from-existing candidate-spec.json --mode direct --review-destination figma --out APP/reviews/NEW_REVIEW
python3 -B tools/design_system.py --input APP/design.json --out NEW_SYSTEM_PREVIEW
python3 -B tools/specifications.py export --graph APP/graph.json --out NEW_SPEC_EXPORT
python3 -B tools/graph_sync.py discover --file-key FILE_KEY --page-id MAIN_PAGE_ID --include-page-id SECOND_PAGE_ID --out NEW_DISCOVERY
python3 -B tools/graph_sync.py probe --graph APP/graph.json --component COMPONENT_ID --out NEW_PROBE.js
python3 -B tools/graph_sync.py combine-web --graph APP/graph.json --proof ACTUAL_A.json --proof ACTUAL_B.json --out NEW_WEB_PROOF.json
python3 -B tools/check_project.py --init --brief APP/brief.md --graph APP/graph.json --bindings APP/bindings.json --out NEW_CHECK
```

native 실행은 [workspace/control 가이드](../../docs/guide.md#prepared-native-edit)와 현재 `figma_workspace.py prepare`, `figma_control.py run`을 사용하며 실제 key/operation/file/page/revision을 고정한다. 비교·본제작 승인을 fixture로 대체하지 않는다.
로컬 전용 BRIEF 대조군은 그 범위를 명시한 fixture brief와 `--review-destination local`을 사용한다. 그 packet을 Figma 전달 성공으로 재사용하지 않고, native 실행은 Figma 목적지로 고정한 입력과 별도 검토 기록을 사용한다.
단위 회귀 후보는 `tests/test_design_directions.py`, `test_direct_design.py`, `test_design_system.py`, `test_reference_graph.py`, `test_specification_rendering.py`, `test_graph_sync.py`, `test_scoped_web_proof.py`, `test_figma_control.py`, `test_workspace_replay.py`다. fixture pass와 live 근거를 구분한다.

run 출력은 `outputs/figma-flow-regression-program/RUN_ID/APP_ID/`에 격리한다. 공유 자료는 상대 경로와 필요한 hash만 포함하며 고정 workspace 인증 자료를 복사하지 않는다.
`run.json`은 source fingerprint·버전·입력·대상을 기록한다. `results.json`은 case별 판정과 원본 evidence를 참조한다. `findings.json`은 미해결 문제와 수정 이력을 담는다. 이 저장 형식은 단계 1에서 준비할 계획이며 기존 실행 기능이라고 주장하지 않는다.
각 case는 해당 범위의 `result.json`, 실행 command와 exit code, 전후 캡처, raw getter/probe와 hash, graph 의미 ID, operation revision, 환경 제약을 갖는다. 스크린샷만으로 동작 완료를 증명하지 않는다.

## 논리 페이지 목록을 대조한다

### Atlas Workspace의 경로를 고정한다

- `SCR-ATLAS-01`는 `/sign-in`이다.
- `SCR-ATLAS-02`는 `/workspaces`이다.
- `SCR-ATLAS-03`는 `/dashboard`이다.
- `SCR-ATLAS-04`는 `/projects`이다.
- `SCR-ATLAS-05`는 `/projects/:projectId`이다.
- `SCR-ATLAS-06`는 `/projects/:projectId/board`이다.
- `SCR-ATLAS-07`는 `/tasks/:taskId`이다.
- `SCR-ATLAS-08`는 `/approvals`이다.
- `SCR-ATLAS-09`는 `/approvals/:approvalId`이다.
- `SCR-ATLAS-10`는 `/members`이다.
- `SCR-ATLAS-11`는 `/members/invite`이다.
- `SCR-ATLAS-12`는 `/roles`이다.
- `SCR-ATLAS-13`는 `/roles/:roleId`이다.
- `SCR-ATLAS-14`는 `/settings`이다.

### Morrow Market의 경로를 고정한다

- `SCR-MORROW-01`는 `/`이다.
- `SCR-MORROW-02`는 `/collections/:slug`이다.
- `SCR-MORROW-03`는 `/search`이다.
- `SCR-MORROW-04`는 `/products/:productId`이다.
- `SCR-MORROW-05`는 `/compare`이다.
- `SCR-MORROW-06`는 `/saved`이다.
- `SCR-MORROW-07`는 `/cart`이다.
- `SCR-MORROW-08`는 `/checkout/contact`이다.
- `SCR-MORROW-09`는 `/checkout/delivery`이다.
- `SCR-MORROW-10`는 `/checkout/review`이다.
- `SCR-MORROW-11`는 `/orders/complete/:orderId`이다.
- `SCR-MORROW-12`는 `/orders`이다.
- `SCR-MORROW-13`는 `/orders/:orderId`이다.
- `SCR-MORROW-14`는 `/returns/new/:orderId`이다.

### Paper Room의 경로를 고정한다

- `SCR-PAPER-01`는 `/`이다.
- `SCR-PAPER-02`는 `/search`이다.
- `SCR-PAPER-03`는 `/articles/:slug`이다.
- `SCR-PAPER-04`는 `/collections/:collectionId`이다.
- `SCR-PAPER-05`는 `/saved`이다.
- `SCR-PAPER-06`는 `/studio`이다.
- `SCR-PAPER-07`는 `/studio/articles`이다.
- `SCR-PAPER-08`는 `/studio/articles/new`이다.
- `SCR-PAPER-09`는 `/studio/articles/:articleId/edit`이다.
- `SCR-PAPER-10`는 `/studio/reviews`이다.
- `SCR-PAPER-11`는 `/studio/reviews/:reviewId`이다.
- `SCR-PAPER-12`는 `/studio/calendar`이다.

## 케이스별 합격 조건을 대조한다

이 표는 [cases.json](cases.json)의 내용을 투영한 계획이다. 모두 미실행이며 실행 시작 때 목록과의 일치를 확인한다.

| case ID | 검사 대상 | 근거 종류 | 합격 조건 |
| --- | --- | --- | --- |
| `TC-I01` | 인라인 HTML 목업 | web | 제공한 제목·배치·간격을 위치별로 대조하고 입력을 제거한 대조군과 달라지는 근거를 남긴다. |
| `TC-I02` | 여러 HTML과 상대 경로 자산 | web | 페이지별 외부 CSS·이미지·폰트·SVG를 포함한 실제 렌더가 유지되고 누락 자산과 404를 보고한다. |
| `TC-I03` | JS 렌더와 깊은 경로 | web | JS가 만든 필수 콘텐츠와 라우트가 실제 브라우저에 나타나며 정적 파싱을 실행 증거로 사용하지 않는다. |
| `TC-I04` | 공개 레퍼런스 URL | web | 원래 URL·최종 URL·관측 시각·뷰포트·캡처·채택한 원칙·적용 대상을 연결한다. 입력 포함·제거 대조에서 고정한 reference 원칙의 대상 위치·레이아웃 차이와 source provenance를 확인하고 자료를 무시한 결과는 통과시키지 않는다. |
| `TC-I05` | JS가 필요한 레퍼런스 | web | 문서 텍스트만 보이면 수집 완료로 통과시키지 않고 렌더 확인 또는 명시적 미검증으로 남긴다. |
| `TC-I06` | 리다이렉트·로그인·404·요청 제한 | web | 통제된 URL 상태별로 원인과 미확인 범위를 남기고 접근 실패 내용을 추정하지 않는다. |
| `TC-I07` | 여러 레퍼런스의 충돌 | human | 출처별 채택·제외 이유와 위치를 남기며 어느 화면에 반영했는지 확인한다. |
| `TC-I08` | 디자인 시스템 코드·테마 재사용 | web | 실제 프로젝트 컴포넌트를 import하고 테마 토큰·패키지 버전·파일·실제 렌더를 연결한다. 입력 포함·제거 대조에서 제공 컴포넌트의 실제 import·렌더 소비자와 고유 theme 토큰 값를 확인하고 자료를 무시한 결과는 통과시키지 않는다. |
| `TC-I09` | 크기·상태·브랜드·모드 | web | 선언한 버튼·필드·표의 상태와 별칭·light/dark 매핑을 대조하고 미지원 축을 누락 없이 보고한다. |
| `TC-I10` | 순환 별칭·누락 토큰·버전 불일치 | unit | 잘못된 연결은 거절하고 원본 변경은 이전 투영·검토·읽기를 stale로 만든다. |
| `TC-I11` | HTML과 URL 함께 제공 | human | 브리프의 내용과 HTML 구조를 유지하면서 참고한 시각 원칙의 출처를 특정한다. 입력 포함·제거 대조에서 각 입력을 하나씩 뺀 결과와 비교한 구조·참고 원칙의 분리를 확인하고 자료를 무시한 결과는 통과시키지 않는다. |
| `TC-I12` | HTML과 디자인 시스템 함께 제공 | web | 목업 구조와 시스템 컴포넌트를 연결하고 임의의 유사 컴포넌트 복제를 검출한다. 입력 포함·제거 대조에서 각 입력을 하나씩 뺀 결과와 비교한 목업 구조·실제 시스템 import를 확인하고 자료를 무시한 결과는 통과시키지 않는다. |
| `TC-I13` | URL과 디자인 시스템 함께 제공 | human | 시스템의 컴포넌트·토큰을 지키며 참고 URL에서 가져온 배치 원칙만 반영한다. 입력 포함·제거 대조에서 각 입력을 하나씩 뺀 결과와 비교한 참고 원칙·시스템 토큰 소비를 확인하고 자료를 무시한 결과는 통과시키지 않는다. |
| `TC-I14` | 세 입력의 요구 충돌 | human | 명시된 브리프 우선순위로 해결하거나 영향을 받는 작업을 막고 충돌을 숨기지 않는다. 입력 포함·제거 대조에서 입력 하나씩 제거한 결과 및 미리 정한 우선순위별 상충 값의 채택·거절를 확인하고 자료를 무시한 결과는 통과시키지 않는다. |
| `TC-I15` | 자료의 지시문과 경로 경계 | unit | 자료 속 명령을 사용자 권한으로 취급하지 않고 경로 이탈·심볼릭 링크·입력 덮어쓰기를 거절한다. |
| `TC-W01` | 전체 라우트·직접 진입 | web | 모든 route ID에 페이지·제목·주 행동·직접 새로고침 결과가 있고 누락·빈 화면이 없다. |
| `TC-W02` | 사용자 역할별 경로 | web | 각 역할의 허용·거절·읽기 전용 상태를 mock 정책과 대조하며 운영 인증 보안을 검증했다고 주장하지 않는다. |
| `TC-W03` | 로딩·빈 결과·오류와 재시도 | web | 실패 응답을 주입해 해당 페이지의 안내와 재시도를 확인하고 입력·선택을 보존한다. |
| `TC-W04` | 키보드·포커스·다이얼로그 | web | 탭 순서·필드 이름·오류 포커스·닫기·포커스 복귀가 주요 흐름에서 작동한다. |
| `TC-W05` | 모든 페이지의 반응형 | web | 390×844와 1440×1000에서 콘텐츠 잘림·겹침·의도하지 않은 가로 넘침이 없다. |
| `TC-W06` | 방문 이력과 복원 | web | 뒤로·앞으로·새로고침 뒤 필터·탭·초안·선택 상태가 브리프와 일치한다. |
| `TC-W07` | 긴 한국어·영어·일본어 | web | 제목·오류·버튼을 늘려도 위계와 조작을 유지하고 폰트 누락을 보고한다. |
| `TC-W08` | 많은 목록 데이터 | web | 1,000개 mock 항목의 정렬·필터·페이지 이동을 확인하고 화면에 없는 행의 측정을 꾸며내지 않는다. |
| `TC-W09` | 좁은 폭의 조작 전환 | web | 320px·768px·200% 확대에서 핵심 내비게이션과 양식·표의 대체 표현을 확인한다. |
| `TC-N01` | 대상과 생성 소유권 | native | 실제 file/page/revision과 생성 대상을 고정하고 다른 앱·사용자 디자인을 바꾸지 않는다. |
| `TC-N02` | 실제 편집 가능한 레이어 | native | 제목·본문·버튼·표의 구조가 편집 가능하며 참고 스크린샷을 완성 프레임으로 대체하지 않는다. |
| `TC-N03` | 변수·컴포넌트의 사용처 | native | 선언한 실제 소비자의 변수·메인·인스턴스·변형 연결을 getter로 확인한다. |
| `TC-N04` | 완전한 메모와 왕복 링크 | native | 모든 화면과 중요한 조작의 조건·동작·결과·복구·지원 범위가 graph와 같고 양방향 링크가 정확하다. |
| `TC-N05` | 화면 이동·돌아가기 | native | 선언한 출발·도착·복귀를 실제 프로토타입으로 실행하며 필요한 reactions 읽기가 없으면 검증을 막는다. |
| `TC-N06` | 웹 기능과 Figma 지원 경계 | native | 가짜 네이티브 입력·저장 성공을 주장하지 않고 정적 표현과 실제 웹 동작을 설명한다. |
| `TC-N07` | 같은 입력·변경·충돌·복구 | native | 같은 입력의 중복이 없고 graph 문장 수정은 정확한 대상만 갱신하며 사용자 편집과 다른 주석을 보존한다. |
| `TC-N08` | 여러 Figma PAGE의 범위 | native | 명시한 두 PAGE만 읽고 한 PAGE 누락·다른 파일·다른 앱 component 연결을 거절한다. |
| `TC-N09` | 재실행 후 지연 읽기 | native | 플러그인 재열기와 다음 독립 읽기에도 배치·바인딩·직접 overrides·메모가 유지된다. |
| `TC-S01` | graph에서 Figma와 웹으로 | native | 지원되는 scalar 토큰 변경을 여러 route의 소비자에 반영하고 Figma·웹의 실제 값을 다시 대조한다. |
| `TC-S02` | Figma에서 graph와 웹으로 | native | 허용된 메인·토큰 수정의 역수입 후 graph와 웹을 재생성·재측정하고 다른 필드는 보존한다. |
| `TC-S03` | 조건부 화면의 probe 합치기 | web | 서로 다른 route·viewport에서 수집한 값이 전체 선언을 덮고 하나 빠지면 pairing이 실패한다. |
| `TC-S04` | 미지원 편집의 공개 | native | 임의 전체 레이아웃·개별 인스턴스 변형을 자동 왕복으로 통과시키지 않고 대상과 지원 한계를 보고한다. |
| `TC-S05` | 동시 변경·오래된 근거 | native | 이전 graph·다른 viewport·오래된 readback·편집 충돌을 최신 검증으로 인정하지 않는다. |
| `TC-S06` | 앱 간 같은 이름 격리 | native | 동일한 Button 이름·색·의미 ID를 가진 다른 앱의 값이나 근거를 혼용하지 않는다. |
| `TC-S07` | 변형과 모드 연결의 보존 | native | 지원되는 variant/mode/alias 소비자를 대조하고 지원되지 않는 조합을 조용히 버리지 않는다. |
| `TC-L01` | 시작 버전·출처·예외 | unit | Codex 패키지·Figma 파일·실행본을 구분하고 개발 변경·고정·오프라인 예외를 기록한다. |
| `TC-L02` | 작업 종류 등록과 실행기 | unit | 등록 가능한 종류와 실제 실행기의 허용 종류가 일치하고 직접 수정 작업의 재등록·읽기가 중단되지 않는다. |
| `TC-L03` | 소비자의 Computer Use 없는 실행 | native | 최초 고정 플러그인 실행 뒤 생성·읽기·갱신을 우리 플러그인과 로컬 명령으로 재현한다. |
| `TC-L04` | 실행 중 재연결·불확실한 응답 | native | claimed 작업을 바꾸지 않고 끊긴 쓰기는 실제 상태를 읽기 전 재시도하지 않는다. |
| `TC-L05` | 실패 복구와 사용자 변경 | native | 실패 이전·이후 snapshot과 복구 결과가 있고 그 사이 사용자 변경은 덮어쓰지 않는다. |
| `TC-L06` | 다음 깨끗한 실행의 재현 | web | 새 격리 브라우저·mock 초기 데이터에서도 같은 필수 결과를 얻으며 이전 세션 상태에 의존하지 않는다. |
| `TC-L07` | 단일안·비교·실제 선택 경계 | unit | 구체적인 단일 방향은 한 안으로 준비하고 비교 요청은 선택 전 대기하며 합성 사용자 이벤트를 실제 본제작 권한으로 승격하지 않는다. |
| `TC-Q01` | 페이지별 정보 위계 | human | 목적·주 행동·보조 정보와 빈 공간을 실제 캡처 위치로 비평하고 유틸리티 화면에 장식용 히어로를 강제하지 않는다. |
| `TC-Q02` | 자료·타이포·브랜드 일치 | human | 원본과 결과를 나란히 보고 채택한 구조·폰트·강조가 의도한 위치에 반영됐는지 판단한다. |
| `TC-Q03` | 투명 배경의 실제 대비 | web | 합성 배경 픽셀과 텍스트를 검사하고 경고를 없애려 불투명 텍스트 배경을 추가하지 않는다. |
| `TC-Q04` | 이미지·아이콘과 편집 구조 | human | 목적에 맞는 자산·일관된 아이콘을 쓰고 대체 텍스트와 편집 가능한 구조를 구분한다. |
| `TC-Q05` | 공통 컴포넌트와 앱의 차이 | human | 동일 컴포넌트의 화면 간 일관성을 확인하면서 세 앱을 색만 바꾼 같은 템플릿으로 만들지 않는다. |
| `TC-Q06` | 고정된 근거의 전후 비평 | human | 원본·캡처 해시에 연결된 위치별 문제와 수정 이유를 남기며 구조 검사나 자작 점수를 미적 품질로 대체하지 않는다. |
| `TC-P01` | 규모별 지연·오류·payload | perf | Atlas의 1·6·14 route를 같은 조건에서 측정하고 읽기 누락·메모리 증가·작업 시간·오류 수를 기록한다. |
| `TC-P02` | 수정 전후 같은 부하 비교 | perf | 동일 workload의 baseline과 수정본을 교차 측정하고 정한 예산을 넘으면 성능 회귀로 남긴다. |
| `TC-F01` | 할 일 저장과 복구 | web | 프로젝트 목록에서 상세·보드·할 일로 이동하고 저장 실패 뒤 초안을 보존해 재시도한다. |
| `TC-F02` | 승인과 역할 제한 | web | 구성원 요청을 검토자가 승인하고 역할을 바꾼 뒤 내비게이션과 접근 거절을 확인한다. |
| `TC-F03` | 주문 단계와 재고 충돌 | web | 상품 선택·장바구니·연락처·배송·검토·완료를 이동하고 재고 충돌 시 중복 주문 없이 복구한다. |
| `TC-F04` | 저장 목록과 반품 | web | 새로고침 뒤 저장 목록·주문 상세를 복원하고 반품 실패 뒤 입력을 유지한다. |
| `TC-F05` | 작성·자동 저장·검토 | web | 새 글을 만들고 자동 저장 실패·새로고침 복구·검토 요청을 확인한다. |
| `TC-F06` | 역할별 검토·발행 | web | 편집자가 반려·수정 요청·가상 발행을 수행하고 독자 화면과 캘린더에 반영되는지 확인한다. |

## 미검증 개선 후보부터 착수한다

첫 우선 후보는 linked CSS·JS 생성 내용·여러 route의 입력 반영, 코드 유래 theme/variant 재사용, reference 수집 실패 보고, route를 넘나드는 의미 ID와 probe coverage다.
native는 긴 메모 배치, 기존 사용자 주석, prototype/reactions의 실제 수집, 다시 열었을 때 되돌아가는 instance override, PAGE 범위를 우선한다. 값을 한 번 읽었다고 완료하지 않는다.
이 목록은 소스에서 확인한 관측 공백과 이전 회귀 위험이다. 이번에 재현한 새 버그 목록이 아니며 실제 재현 후 수정할 대상을 고른다.

## 2026-11-12 실행 근거 대조

소스·단위 검사, 실제 브라우저, 실제 native getter, UI 관찰을 구분해 기존 기록을 케이스별로 대조했다. 목록의 `remaining_scope`를 다음 실행의 종료 조건으로 사용한다. 소유자 로컬 원본은 배포에서 제외하며 witness 경로·SHA가 있다고 새 fork에서 같은 실행이 이루어진 것으로 취급하지 않는다. 누락되거나 변경된 근거는 재실행한다. 정상 사진·서체 보조 사례는 브라우저 네 화면·Figma 네 프레임의 실제 검증이며 기존 세 앱/40페이지의 전체 입력 조합 완료 수에 더하지 않는다.
