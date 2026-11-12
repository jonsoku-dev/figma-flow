# 변경 기록

## 0.26.3 · 2026-11-12

- 가져오기 패널에서 너비와 높이만 읽는 부분 요약을 본다. 요청한 값은 전체 읽기와 같고, 부분 읽기임과 생략한 스타일·변수·사진이 표시된다. 사진 바이트가 필요한 필드는 전체 읽기로 돌아간다. 실제 Figma 문서의 속도와 화면은 아직 확인하지 않았습니다.
- 간접 CSS의 사진과 서체는 목록의 준비 상태와 headless Chrome이 실제로 요청한 파일을 따로 기록한다. 쓰이지 않은 글꼴은 목록에 있어도 요청되지 않는다. 사람이 보는 브라우저 창은 아직 확인하지 않았습니다.
- 작업 목록에서 입력 자산을 상태별로 거르고 상대 출처를 텍스트로 본다. 없는 파일과 외부 주소는 정상으로 바뀌지 않고, 목록을 연다고 다시 받지 않는다. 브라우저에서 사진과 서체가 로드되는지는 아직 확인하지 않았습니다.
- 그래프 변경 행에서 적용할 항목을 고르고, 전체 선택과 선택 수, 영향 대상을 본다. 변경이 있는데 하나도 고르지 않으면 적용하지 않는다. Figma에서 고른 값만 바뀌는 적용은 아직 확인하지 않았습니다.
- 선행 개정이 달라지면 후속 작업을 오래됨으로 보고, 은퇴했거나 없는 대상도 읽기 전용으로 표시한다. 이 조회는 작업을 자동 실행하지 않는다. Figma 패널의 은퇴 목록은 아직 확인하지 않았습니다.
- 작업 목록에서 고른 작업의 선행과 후속을 한 단계와 같은 텍스트 목록으로 본다. 관계만 고르면 작업을 열거나 네이티브 변경을 보내지 않는다. 320px 화면과 Figma 패널은 아직 확인하지 않았습니다.
- Figma 작업 목록과 이력에 현재 revision의 상태 분포, 실행별 요청·진행·결과 연결, 작업별 필터와 키보드 초점 이동을 추가합니다. 옛 이력은 연결을 추정하지 않고 보존하며 다운로드·채팅·이전 revision을 현재 완료 수로 세지 않습니다.
- 관측한 native 실패를 중복 기록하지 않고 자동 제어의 결과 검증 실패도 같은 실행에 보존합니다. 고정 재현 검사로 기준 실패와 수정 후 통과를 대조합니다.
- 패널의 기존 light/dark 디자인 안에서 펼침·상태 feedback과 reduced-motion 처리를 제공합니다. 이력 요약은 전체 제품 인수 완료율이나 클라우드 저장을 뜻하지 않습니다.
- 회귀 디자인 시스템에 선언된 size·state 축은 이미 있는 variant에만 연결됩니다. 선언되지 않은 조합, 입력에 없는 사용 설명, swap target은 만들지 않습니다. 축이 없으면 기존 Variant 축을 유지합니다. 실제 Figma variant 패널은 아직 확인하지 않았습니다.
- 같은 구조의 컴포넌트는 화면 너비만 다르면 하나의 main을 공유하고, 각 사용처의 너비는 원본과 같게 맞춥니다. 자식 위치나 높이가 다르면 별도의 Layout 변형을 유지합니다. 자동 검사는 mock Plugin API이며 실제 Figma 렌더는 아직 확인하지 않았습니다.
- 일반 가져오기에서 같은 컴포넌트의 화면 문구를 main의 텍스트 속성 `문구`로 연결합니다. 각 화면은 Figma가 반환한 key로 다른 문구를 갖고, 같은 패킷을 다시 가져오면 기존 main·instance와 사용자가 고친 문구·override를 유지합니다. 속성 API가 없으면 글자를 직접 씁니다. 자동 검사는 mock Plugin API이며 실제 Figma 속성 패널은 아직 확인하지 않았습니다.
- 신규 기능·Figma 제작·최적화·아키텍처 개선8항목을 개별 기능서·설계서·작업서27문서로 정리합니다. 컴포넌트 속성·재사용과 Frame·Group·Auto Layout의 공식 근거, Cursor 실행 프롬프트와 파일 소유권·이관·인수 조건을 포함합니다. RD-01 외 제안 기능은 아직 구현되지 않았습니다.

[상세 패치 기록](docs/llm-wiki/releases.md#v0.26.3) · [부분 요약](docs/llm-wiki/patches/4cf19fe6d9e8f20e9f256c238fca3f5a072ca9c3.md) · [브라우저 대조](docs/llm-wiki/patches/56839c3af04e0be13fa306bc2f743a4d0bbde87d.md) · [입력 자산](docs/llm-wiki/patches/306f26c7454a310f9f9b61f5ddb8b9f557d71318.md) · [선택 행](docs/llm-wiki/patches/d85d6388ae1c50a853278af33ca790a411b1e59e.md) · [의존성 상태](docs/llm-wiki/patches/1c813e3b05c271f043b1360247864ebd216102ae.md) · [선행과 후속](docs/llm-wiki/patches/ef624aadc2e99029e227c62d57d7b6b56df21c5e.md) · [문구 속성](docs/llm-wiki/patches/1f80e5d9896e85afb865919aad7dad3572be932e.md) · [개발 계획](docs/development-roadmap/README.md) · [Cursor 전달서](docs/development-roadmap/CURSOR_HANDOFF.md).

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
