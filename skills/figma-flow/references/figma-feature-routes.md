# Figma 기능별 실행 경로

공식 문서 확인일: 2026-11-13. 이 문서는 제품 기능군에서 실제 작업 경로를 고르는 안내다. Figma 전체 기능의 자동화·왕복·인수 보증이 아니다. 공식 문서의 지원 범위, 현재 Flow 구현, 대상 계정의 권한을 각각 확인한다. 실행 경로는 등록된 Flow → 필요할 때 별도 로컬 개발 플러그인 SDK → 해당 REST 또는 제품 UI로 고른다. 플랜·좌석·베타·호출 한도는 변경될 수 있다.

## 먼저 경로를 고른다

| 경로 | 적합한 작업 | 시작 조건과 완료 증거 |
| --- | --- | --- |
| **Flow 로컬 bridge** | 이 저장소가 정의한 Design 가져오기, 검토, discover, 제한된 수정·토큰 동기화 | 고정 workspace에 준비된 작업, 실행 중인 플러그인, 정확한 file/page/revision. 실제 readback과 해당 검사 결과가 필요하다. [로컬 bridge 계약](../../../figma-bridge/README.md) |
| **로컬 개발 플러그인 SDK** | 등록된 Flow의 지원 범위를 넘는 문서 노드·속성·변수·반응을 별도 플러그인에서 조작 | manifest의 editorType·permissions·documentAccess와 실제 API 존재 여부. 쓰기 뒤 getter로 결과를 다시 읽는다. [Plugin API](https://developers.figma.com/docs/plugins/api/figma/) |
| **REST** | 파일 JSON·렌더·댓글·버전·이벤트·관리 데이터, 허용된 변수 변경 | 토큰 scope·파일 접근·플랜·rate limit. 일반적인 캔버스 노드 CRUD 경로로 취급하지 않는다. [REST 시작점](https://developers.figma.com/docs/rest-api/) |
| **제품 UI** | 라이브러리 활성화·발행, 브랜치 병합, 발표, 사이트 발행, 계정 관리 | 해당 제품과 권한으로 직접 연다. 저장소의 브라우저/Computer Use 규칙 및 현재 사용자 작업 범위를 따른다. |

**실행 전 기록:** 요청 기능, 제품/편집기, 대상 URL·node ID, 현재 경로, 읽기/쓰기 구분, 권한·비용 제약, 변경 뒤 확인할 실제 값. 문서에 있는 API가 Flow의 지원 입력 형식에 자동으로 추가되지는 않는다.

## Design: 구조·레이아웃·벡터·미디어

| 기능군 | 구체적인 실행 경로 | 제약과 확인점 |
| --- | --- | --- |
| 페이지·섹션·프레임·텍스트·도형 | Plugin `createPage`, `createFrame`, `createText`, 노드 append/resize. Flow에 없는 기능은 별도 SDK 프로젝트에서 구현·빌드·수동 실행 | 텍스트 편집 전에 필요한 font를 `loadFontAsync`로 로드한다. dynamic-page 문서는 async 조회/페이지 로딩을 사용한다. [API](https://developers.figma.com/docs/plugins/api/figma/) |
| Auto layout·사이즈·constraints | `FrameNode`의 layout/sizing/padding/constraints. 읽은 기존 구조와 자식 순서를 유지하며 필요한 값만 바꾼다 | auto layout 전환은 자식 위치와 프레임 크기를 바꿀 수 있다. 값을 되돌린다고 원래 배치가 복원되는 것은 아니다. [FrameNode](https://developers.figma.com/docs/plugins/api/FrameNode/) |
| **Auto layout grid** | `layoutMode = 'GRID'` 및 grid 전용 행·열·track 속성/API | 현재 공식 API에 GRID가 있다. HORIZONTAL/VERTICAL 전용 spacing·alignment 속성을 그대로 대입하지 않는다. Slot에는 GRID 불가. [layoutMode](https://developers.figma.com/docs/plugins/api/properties/nodes-layoutmode/) |
| 레이아웃 가이드 grid | `layoutGrids`와 layout grid style | 위의 Auto layout grid와 별개다. `layoutMode`만 읽어 가이드 grid 유무를 판단하지 않는다. [FrameNode](https://developers.figma.com/docs/plugins/api/FrameNode/) |
| 컴포넌트·variants·instances | `createComponent`, `combineAsVariants`, component properties, instance 생성·속성 변경 | 원본 component와 instance override를 구분한다. 일반 Frame을 만들었다고 component 재사용이 성립하지 않는다. [ComponentNode](https://developers.figma.com/docs/plugins/api/ComponentNode/) |
| 벡터·boolean·Draw | Design에서 벡터 네트워크/paths와 boolean API, Draw UI의 pencil/brush 또는 별도 SDK 프로젝트 | Draw는 Design 내부 도구다. `editorType: 'draw'`를 가정하지 않는다. 붓 질감·stroke·effect의 결과를 실제 이미지로 확인한다. [Draw 제품](https://www.figma.com/draw/), [그리기 UI](https://help.figma.com/hc/en-us/articles/31440438150935-Draw-with-illustration-tools) |
| 이미지·SVG·비디오·내보내기 | 로컬 플러그인의 `createImage`/`createImageAsync`, `createNodeFromSvg`, `exportAsync`; 제품 UI의 import/export | byte 입력·URL fetch·network permission·포맷과 크기 제약을 API별로 확인한다. 네트워크를 허용하지 않는 SDK 기본 manifest에서 URL 로딩을 가정하지 않는다. 이미지 paint/hash와 실제 export를 확인한다. [이미지 생성](https://developers.figma.com/docs/plugins/api/properties/figma-createimageasync/), [API](https://developers.figma.com/docs/plugins/api/figma/) |

## 변수·라이브러리·프로토타입·Motion

| 기능군 | 구체적인 실행 경로 | 제약과 확인점 |
| --- | --- | --- |
| 로컬 variables·collections·modes·aliases·bindings | Plugin `figma.variables`의 async 조회, collection/variable 생성, `setValueForMode`, alias·bound variable 설정 | variable type, collection mode ID, 실제 bound field를 함께 읽는다. JSON 토큰 정의만으로 native binding을 증명하지 않는다. [Variables API](https://developers.figma.com/docs/plugins/api/figma-variables/) |
| 서버에서 변수 동기화 | REST `GET /v1/files/:file_key/variables/local`, published 조회, `POST /v1/files/:file_key/variables` | Enterprise·조직 멤버/좌석·GET/POST별 파일 권한과 `file_variables:read/write` scope 확인. 공식 페이지는 Full seat/게스트 제한과 GET/POST 표를 함께 안내하므로 현재 계정 eligibility를 확인한다. 변경 후 다른 파일 사용에는 발행 필요. [REST Variables](https://developers.figma.com/docs/rest-api/variables/) |
| 팀 라이브러리 변수 발견·가져오기 | `figma.teamLibrary.getAvailableLibraryVariableCollectionsAsync`, `getVariablesInLibraryCollectionAsync`; `variables.importVariableByKeyAsync` | manifest `permissions: ['teamlibrary']`가 필요하다. 라이브러리는 사용자가 UI에서 먼저 활성화해야 한다. Plugin API로 활성화할 수 없다. [TeamLibrary](https://developers.figma.com/docs/plugins/api/figma-teamlibrary/) |
| 팀 component/style 재사용·발행 | published key를 확인한 뒤 Plugin `importComponentByKeyAsync`/`importComponentSetByKeyAsync`/`importStyleByKeyAsync`; 발행은 UI | key와 현재 사용자 접근권을 확인한다. Flow가 만든 로컬 component를 팀 라이브러리에 발행했다고 기록하지 않는다. [API](https://developers.figma.com/docs/plugins/api/figma/) |
| 클릭·overlay·navigate·interactive component·변수 기반 prototype | `reactions` 읽기와 `setReactionsAsync`, trigger/action/destination 검사; 실제 Present UI에서 흐름 실행 | native reaction 설정과 앱의 실제 업무 동작은 별개다. 시작점, 복귀 링크, overlay dismiss, 조건·변수값을 시나리오로 확인한다. [Reaction](https://developers.figma.com/docs/plugins/api/Reaction/), [Action](https://developers.figma.com/docs/plugins/api/Action/) |
| Motion timeline·keyframe·animation style | **Beta** `figma.motion`, node `applyAnimationStyle`, `applyManualKeyframeTrack`, `timelines`, `setTimelineDuration`; 로컬 readback과 제품 Motion UI 재생/내보내기 | prototype transition과 Motion timeline을 구분한다. playhead가 undefined일 수 있다. API는 변경 가능하며 실행 환경·대상 node 지원을 확인한다. 저장된 keyframe뿐 아니라 재생/내보낸 결과를 검토한다. [Motion API](https://developers.figma.com/docs/plugins/api/figma-motion/) |

## 개발 전달·Dev Mode·Code Connect

Design 구현 입력은 Flow의 실제 native readback·화면 명세·export와 변수/컴포넌트 정보를 조합한다. 별도 SDK에서 필요한 getter·`getCSSAsync`·`exportAsync`를 사용할 수 있으나 생성 코드가 제품 동작·접근성·반응형을 만족한다는 증거는 아니다. 정확한 node ID, 실제 라이브러리 매핑, 대상 코드의 기존 component를 먼저 확인한다. [노드 API](https://developers.figma.com/docs/plugins/api/FrameNode/).

- **Code Connect:** 디자인 component를 저장소 component/snippet에 연결한다. Code Connect UI 또는 CLI template으로 매핑하고 Dev Mode에서 실제 snippet을 확인한다. 현재 Professional/Organization/Enterprise의 Full 또는 Dev seat 조건이 있으며 Professional은 active library/framework 각각 하나로 제한된다. CLI 매핑 발행과 component library 발행은 별도 작업이다. [Code Connect](https://developers.figma.com/docs/code-connect/).
- **일반 Design 검토:** 읽기 쉬운 화면·주석 보드는 Design 캔버스에서 제공한다. Dev Mode annotation·측정·codegen 제공 여부를 일반 Design 검토의 전제 조건으로 만들지 않는다. [Flow native 검토](design-review.md).

## 다른 제품의 작업 경로

| 제품·목적 | 우선 경로와 실제 진입점 | 현재 경계 |
| --- | --- | --- |
| **Make**: 실행 가능한 코드/앱 prototype | Make UI에서 디자인/context를 넣고 prompt·코드·preview를 검토한다 | 공식 Plugin editorType에 make 없음. Flow가 Make project/code layer를 생성·수정한다고 주장하지 않는다. AI 기능·team library context·배포는 계정/플랜/credit 조건을 확인한다. code layer는 editable design layer가 아니다. [Make FAQ](https://help.figma.com/hc/en-us/articles/31722591905559-Figma-Make-FAQs) |
| **Sites**: responsive website·CMS·publish | Sites UI에서 webpage/breakpoint/preview·site settings·publish. 원본 Design 캔버스와 Sites 파일을 구분한다 | 공식 Plugin editorType 목록에 sites 없음. 이 문서는 Sites용 범용 Plugin 쓰기 지원을 확인하지 못했다. 현재 Sites는 open beta; 발행은 플랜/edit 권한 필요. 모든 canvas webpage가 발행 대상이며 외부 발행용 사이트 코드 export는 현재 불가. [Sites 발행 계약](https://help.figma.com/hc/en-us/articles/31242845959703-Publish-update-or-unpublish-a-site) |
| **Weave**: 재사용 이미지·영상 generation workflow | Weave UI에서 node 연결·tool 구성·실행. 별도 Weave Enterprise 통합은 공식 Weave API 문서를 사용한다 | Plugin editorType에 weave 없음. API는 Weave Enterprise 전용이며 workspace admin이 발급한 해당 workspace token이 필요하다. 실행은 Weave credits를 소비하므로 현재 사용자의 비용·실행 권한을 확인한다. Workflow를 Flow의 native graph sync로 취급하지 않는다. [Weave API 조건](https://help.weavy.ai/en/articles/17239354-weave-api), [workflow 제품 설명](https://www.figma.com/blog/the-tldr-on-figma-weave/) |
| **Widget**: 파일 안 공동 상호작용 객체 | Widget API의 JSX·synced state와 Design용 widget manifest | 일반 Plugin과 수명·공유 상태가 다르다. Flow 패널을 widget이라 부르지 않는다. 별도 widget 구현·상태 검증이 필요하다. [Widget API](https://developers.figma.com/docs/widgets/) |

## 버전·브랜치·댓글·관리·REST

| 목적 | 구체적인 경로 | 제약 |
| --- | --- | --- |
| 현재 파일/노드/이미지 읽기 | REST `GET /v1/files/:key`, `/nodes`, `GET /v1/images/:key` | token scope·depth·대상 ID·rate limit 확인. 일반 node 쓰기 endpoint로 추정하지 않는다. [File endpoints](https://developers.figma.com/docs/rest-api/file-endpoints/) |
| 버전 목록·과거 상태 | `GET /v1/files/:key/versions`; file 조회의 version 지정. Plugin `saveVersionHistoryAsync`는 이름 있는 버전 저장 용도 | 버전 목록 조회는 복원·merge API가 아니다. restore는 제품 UI와 권한을 확인한다. [Version endpoints](https://developers.figma.com/docs/rest-api/version-history-endpoints/) |
| branch 읽기·비교·merge | REST file 조회의 `branch_data`와 branch key, 실제 편집은 branch URL. 생성·review·merge·conflict 해결은 제품 UI | branch와 main의 대상 key를 혼용하지 않는다. 이 문서는 공개 REST의 branch 생성/merge 경로를 확인하지 못했다. 플랜·파일별 가용성 확인. [Branching 안내](https://www.figma.com/best-practices/branching-in-figma/), [File endpoints](https://developers.figma.com/docs/rest-api/file-endpoints/) |
| 댓글·답글·해결 상태 | 제품 Comments UI 또는 REST comments·reactions endpoint | 캔버스 annotation/note board와 별개다. 댓글 전송은 현재 사용자 요청의 명시적 범위에서만 한다. [Comments API](https://developers.figma.com/docs/rest-api/comments-types/) |
| 문서 변경 이벤트 | Plugin document/page/selection change 이벤트; 서버 알림은 REST webhooks | Plugin 세션 이벤트와 서버 webhook delivery를 구분한다. webhook 생성 권한·보안·재전송 처리는 endpoint 계약을 따른다. [Webhooks](https://developers.figma.com/docs/rest-api/webhooks/) |
| 조직·멤버·좌석·SSO·보안 | Admin UI; 권한 있는 관리 통합에서 SCIM, activity logs, library analytics 등 목적별 API | SCIM은 일반 REST와 base URL·인증이 다른 계정 lifecycle API다. 디자인 파일 편집 권한이 조직 관리 권한은 아니다. [SCIM](https://developers.figma.com/docs/rest-api/scim/), [REST API 분류](https://developers.figma.com/docs/rest-api/) |

REST는 OAuth/PAT/plan access token 등 현재 지원 인증과 최소 scope를 선택한다. `401/403`을 “기능 없음”으로 처리하지 말고 계정·scope·파일 권한·플랜을 분리한다. `429`는 문서의 limit/재시도 안내를 따른다. [인증](https://developers.figma.com/docs/rest-api/authentication/), [REST rate limits](https://developers.figma.com/docs/rest-api/rate-limits/).

## 로컬 SDK·제품 게이트를 판단하는 방법

1. 기존 Flow의 준비된 작업으로 해결되는지 먼저 확인한다. 지원되지 않는 필드를 기존 controller에 임의로 보내지 않는다.
2. 별도 Design 개발 플러그인이 필요하면 `python3 tools/figma_sdk_project.py init NEW_DIR --editor figma`로 생성한다.
3. 고정된 API declaration·recipe로 구현하고 SDK의 `check`/`build`를 실행한다. 생성 manifest의 기본 network는 비활성이다. 필요한 permission만 명시하고 Figma가 발급한 실제 plugin ID로 등록한다. 생성·typecheck·build가 실제 editor 실행은 아니다.
4. 사용자가 대상 편집기에서 개발 플러그인을 직접 등록·실행한다. 실제 file/page/node에서 getter·이미지·동작을 검증한다. SDK 프로젝트는 Flow localhost controller에 연결되지 않는 별도 플러그인이다.
5. API가 없거나 플랜·좌석·편집권·beta에 막히면 `gated`/`unsupported-by-flow`/`unverified`를 구분하고 해당 REST 또는 제품 UI 경로를 제시한다. “미확인”을 제품 전체의 “미지원”으로 바꾸지 않는다. API 명세에 있는 기능만으로 모든 제품 UI의 자동화를 보증하지 않는다.

## Flow 현재 구현과의 경계

이 표는 위의 공식 제품 가용성과 별도로 **이 저장소의 실제 구현**을 확인한 결과다. 구현 변경 후 다시 대조한다.

| 저장소 근거 | 현재 읽히는 범위 | 확대 해석하면 안 되는 부분 |
| --- | --- | --- |
| `tools/figma_sdk_project.py` | 고정 declaration을 사용하는 편집기별 standalone SDK 프로젝트 생성·check·build | 생성 결과는 별도 개발 플러그인이며 실제 Figma 실행과 인수는 미검증 |
| `tools/figma_bridge.py` 생성 manifest | `editorType: ['figma']`인 Design 플러그인 | 기존 파일과 페이지 범위를 확인하고 등록된 플러그인에서 실행 |
| `figma-bridge/README.md`, `tools/figma_control.py` | 준비된 workspace의 bounded review/discover/sync/import operation | 임의 Plugin API JS 실행·닫힌 플러그인 무인 실행·다른 파일 선택 API 아님 |
| `figma-bridge/code.js` | local variables/collections, component·variant·화면 생성, `setReactionsAsync` 기반 native 클릭 연결, readback | 전체 prototype action, Motion timeline, team library 발행, 모든 node 속성 왕복을 보증하지 않음 |
| `figma-bridge/code.js`·`semantic_components.js`의 layout/readback 필드 | 현재 선언된 sizing·padding·일부 layout 필드와 semantic component 처리 | 일반 Plugin API의 GRID 지원만으로 Flow grid track 완전 import/export가 생기지 않음 |
| `figma-bridge/native_edit.js`, `tools/native_edit.py` | 계획과 현재 관측값에 고정된 허용 field·기존 local variable 수정, 충돌·rollback 처리 | arbitrary field setter·remote variable 직접 변경 아님 |
| `skills/figma-flow/references/token-sync.md` | 문서에 명시된 제한된 토큰·binding 및 실제 비교 경로 | 임의 파일·전체 페이지·asset·반응·스타일의 양방향 동기화 아님 |

**완료 보고:** 사용한 경로, 대상 제품/파일/페이지/노드, 변경 전후 getter·실제 이미지/재생·웹 동작 증거, 남은 권한/미검증 범위를 적는다. “공식 경로를 찾음”, “로컬 테스트 통과”, “실제 계정에서 실행”, “제품 인수 통과”를 별도로 보고한다.

## 그래프 기반 에디터 경로

`graph-review`는 기존 Design 페이지에 선택된 요구사항, 컴포넌트와 검증 근거를 연결한 편집 가능한 검토 보드를 만든다.
