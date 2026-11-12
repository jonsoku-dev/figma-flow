# 버전과 전체 Git 기록 대조

카탈로그의 제품 소스 기준은 `1cfe00b16c17ebeaa4b4cc8bddbede6ecc64222d`이다. canonical 조상52개와 보존 계보39개를 별도 기록한다. 태그·매니페스트·CHANGELOG의 버전 대조는 `catalog.json`의 해당 소스 시점 관측이다. 릴리스 태그는 이후 Wiki/CHANGELOG 전용 발행 커밋을 가리킬 수 있으며, 그 문서 접미사는 제품 코드와 구분해 검증한다.

## 대조 방법

`catalog.json`과 `patch_knowledge.py inventory`가 실제 커밋·부모·파일·diff 해시·태그·매니페스트를 제공한다. 아래 목록은 본문을 보존하는 사람이 읽는 연결이다. 태그 없는 버전, 겹친 버전, CHANGELOG에만 남은 버전을 명시한다. 과거 테스트 코드의 존재를 당시 성공 실행으로 세지 않는다.

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
