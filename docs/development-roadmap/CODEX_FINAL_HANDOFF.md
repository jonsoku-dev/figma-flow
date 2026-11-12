# Codex 최종 검수 인계

사용자는 Codex에서 이 트리를 직접 검수하고 고친 뒤, 최종 버전만 직접 푸시한다. 이 세션은 푸시, 태그, 배포, 버전 bump를 하지 않았다. `plugin.json`과 `.codex-plugin/plugin.json`은 `0.26.3`이다. `origin/main..HEAD`에서 두 파일을 바꾼 커밋은 없다.

이전 인계 커밋 `4c49dc395ec0f6f8a3bfbc1137da714f1f2b92f8`은 RD-07 단위 2의 기록과 단위 3–5가 커밋되기 전에 쓰였다. 이 문서가 그 내용을 대체한다. 부모는 `199683f8c221fcac718991dd91ad96b6a50ab144`다.

이 개정 직전 HEAD는 `df65b64205ed85644acf075f0acab8f37f2ac371`이다. 그 커밋의 제목은 `docs: record the public runtime boundary symbols`다. 브랜치는 `main`이고 `origin/main`은 `3a3d68e64d178d1ca37c3ff275d97d41bc92274d`다. ahead 121, behind 0. porcelain은 비어 있었다. 이 파일을 고친 커밋의 부모는 그 HEAD여야 한다. 새 SHA는 `git log -1 --format='%H %P %s'`로 확인한다.

읽기 전에 `git status --porcelain`과 `git rev-parse HEAD`를 다시 실행한다. 위 HEAD보다 새 제품 커밋이 있으면 그 커밋을 지도에 더한 뒤 검수한다.

## 목적

검수가 끝난 트리만 사용자가 푸시한다. Codex는 이 문서만으로 푸시, 태그, 배포, 버전 bump를 하지 않는다. 실제 Figma 관찰이 없는 인수 조건은 통과로 올리지 않는다.

## 작업서 단위

RD-01부터 RD-09의 `tasks.md`는 번호 단위마다 구현 문장이 있다. 이 패스에서 구현 문장이 없는 번호 단위는 찾지 못했다. 새 구현을 시작하지 않았다.

RD-07 `docs/development-roadmap/RD-07-runtime-boundaries/tasks.md`의 1–5는 모두 문장이 있다. 표의 “이 단위에서는 분리하지 않는다”는 단위 1 당시의 문장이다. 단위 2 이후 문단이 나중 상태다. 기능서 AC는 통과로 기록하지 않았다. 실제 Figma에서 고정 plugin을 다시 열고 runtime identity를 확인한 뒤 read와 승인된 fixture write를 하는 관찰은 없다.

RD-03 작업서 1은 UI 통합이 아직이라고 적는다. 그 문장은 구현된 경계 검사 안의 남은 메모다. 기능서 AC-01의 세 작업·edge 둘과 작업서 3의 edge 하나는 같은 완료로 합치지 않는다.

CHANGELOG `0.26.3`에는 `RD-01 외 제안 기능은 아직 구현되지 않았습니다`가 남아 있다. 이후 커밋과 어긋난다. 이 세션은 CHANGELOG를 고치지 않았다. 인계 문서는 사용자에게 보이는 제품 변경이 아니다.

## 커밋 지도

범위는 `3a3d68e64d178d1ca37c3ff275d97d41bc92274d` 다음부터 개정 직전 HEAD까지다. SHA는 `git rev-parse`와 `git log`로 확인했다. 순서는 부모에서 자식이다.

### RD-01 재사용 컴포넌트

작업서 `docs/development-roadmap/RD-01-components/tasks.md`. AC `RD-01-AC-01`–`RD-01-AC-05`. 기능서는 실제 Figma 관찰이 없어 통과로 기록하지 말라고 적는다.

- 문구 1–3 기준 `7260d2995764d65d736aed031ddc63323ecf4e0c` test: pin shared import labels before text properties
- 구현 `1f80e5d9896e85afb865919aad7dad3572be932e` feat: expose shared import labels as text properties
- 기록 `cb19ac749989bafeda8ca5a75505ebe86abed802` docs: record the shared import label property
- 너비 기준 `15f29963c1f4e7685a7deb6b851a1d360fcbad6b` test: pin width-only component reuse before sharing mains
- 기준 `f838d46167cc8078e755c579bc3340c85968f8aa` test: keep the width-reuse oracle stable after archived keys
- 기준 `76a2d2b73a1d71631abe6f717073d15068c08155` test: give appended layout variants their declared properties
- 구현 `640ff8c1a0ae1f185a60be5284558d6e7c914deb` feat: share a component main when only its width differs
- 기록 `c7327603e61a28342f6ebb1338e6758360f75251` docs: record width-only component main sharing
- 축 기준 `008c01c64e41b255c43b7e81e4029f4368b1f797` test: pin declared variant axes before creating combinations
- 구현 `0ff91654bd6867c816292a9fbac8561d474644d8` feat: keep declared variant axes on existing definitions
- 기록 `d5b26f079e3b2a38ba141877eca8b5782a1bd895` docs: record declared variant axes without new combinations

### RD-02 레이어 계층

작업서 `docs/development-roadmap/RD-02-layer-structure/tasks.md`. 실제 글꼴 측정과 Figma reflow는 작업서가 아직 보지 않았다고 적는다.

- `47bd10f10263a0f7bd2db9bed0511f2532053532` test: pin flat layers apart from declared containers
- `7a1bb8345246b0c0aafd3c30ee9e21557366c4f2` docs: record the pinned flat and declared layer fixtures
- `86e30fb66bb998158034c3c887782f131e269b0f` test: require declared containers to be normalized before authoring
- `108ecded7a1e99ee040a4c4b067a837a85d4d67c` feat: validate declared layer containers before authoring
- `1273bb3365947986b98b66a0b3e012d7a53b6e47` docs: record declared container validation before native authoring
- `b40d9db3300bf8d7de01a0d70fef408d16f43b98` test: require declared parents to reuse authored leaves
- `9a465e535cafbf7e8be7fd4d7a2693b70ada4400` feat: place declared parents after existing leaf authoring
- `942d0cf9a5c194b8decd79918062c84767a0d1ec` docs: record declared parent placement after leaf authoring
- `8421b31163333c0b75e24e096ad6975d07138a33` test: require declared container links to match the native reader
- `946717804fcf45d0d4c85c3e624132ed0c48455f` feat: compare declared container links with the native reader
- `a0f790602dc1a2b6b6efaaf4623b14dc7461faa8` docs: record native readback of declared container links
- `c7a4dfffb39aaa26eca0f6571a3bf0af97762822` test: require hug fill and fixed sizing to follow text and parent resize
- `4ebdb77a73746f95dc985507b2ba0d704975cf9c` feat: refresh declared hug, fill, and fixed sizing after text growth
- `d2122ffbe9ec04470f69dba3010eef0def1fdc6b` docs: record declared hug, fill, and fixed sizing refresh

### RD-08 실행 수명주기

작업서 `docs/development-roadmap/RD-08-operation-lifecycle/tasks.md`. 단위 6은 Figma Desktop을 열지 않은 로컬 HTTP다.

- `dc8c23c4357aba18dc6a074b00107d52c8a1d7a9` test: pin current enqueue poll result timeout and recovery transitions
- `4dc23d6d98a7953572228b6bbf829e54c5417d13` feat: replay current control transitions without inventing native-started
- `a9abc696ca8d6acc7974dc54076dea5e39d8de48` docs: record the pinned control transitions before a lifecycle journal
- `aa0822c58b548c0b61e33874bada12ce4e2403bf` test: require a server operation journal before lifecycle phases are shown
- `4f451eec0b49366519297f878867b05aff0ff197` feat: store a server operation journal on the existing request record
- `16f728ae07a92f515225020fe61779e852eba285` docs: record the server operation journal on existing requests
- `0664a3113792752d37096d12ee02aae08a488b2b` test: require explicit native-started from the claimed runtime
- `24730598c912ef01c3da487193fa44e011981e7d` feat: record native start only from the claimed runtime
- `e8a0ba7e7d6ed97c6f9e594114bfc44430e72f58` docs: record explicit native-started delivery from the claimed runtime
- `c71aabb35f06b4ce860b36837be44d17b8bd2d6c` test: require execution history to read the server journal
- `da3c7c51c4bc20733a5bf27278f9b459de1773ff` feat: let execution history read the server journal
- `d6e35da1559f20ba25c443f8c4bb5e387211652b` docs: record server journal lookup for execution history
- `0b46cdbd575cfe17d901d33925fd03c45c643782` test: require conflict detail to keep the observed value and plan hash
- `b91d26553b3343a61f8094a1ac041e3043506787` feat: keep observed conflict values with the original plan hash
- `f290f48aba0bbabe12a8eda3f315d8cf2205457b` docs: record conflict detail that keeps the observed value
- `5dfc365a6ab9b7e27fed8a8b9d03e2cce9990225` test: require the journal to survive restart when result delivery fails
- `4eab91b666eaeead1fe04395f248f936cdb51b7d` feat: keep the control journal when the result post never arrives
- `66278decfd7f49906bb32d75f71a0be70fafa7ee` docs: record the HTTP restart check for a missed result post

### RD-03 작업 의존성

작업서 `docs/development-roadmap/RD-03-task-dependencies/tasks.md`.

- `d2de8c2b7c390e259c0535a7ca32d6fea7e83661` test: keep task identity apart from a control operation id
- `9c2cec203451ff81f6a0e3f83787d28c2154efca` feat: keep prepared task identity apart from control operation ids
- `0cf1823f9225b694b40961f2b6fb5d6eaa79834c` docs: record that task identity stays apart from operation ids
- `bd53b61a4da349e5857b01f5abfd47ed80e378bd` test: require declared task dependencies to be normalized before publish
- `1f90f63bfeb1fa30a4dacd311daa9720dc25ae8f` feat: normalize declared task dependencies before catalogue publication
- `c5b37301ab91987b07ec317b28ee9ecb27c1fc7a` docs: record declared task dependency checks before catalogue publication
- `7bff2100bccf6db00203cc5351c8773026783d72` test: pin a legacy catalogue apart from one declared dependency edge
- `19b6e1a9d879272179c120cd9c0d303a3e765910` feat: load the legacy catalogue apart from the declared dependency fixture
- `42ac878ba11ff3837fb0b5ed52dd38aa8e94304e` docs: record the legacy catalogue apart from the declared dependency edge
- `ee61c93b47d9938c6379d1ea1b638d449338b48a` test: require one-step predecessor and successor text for the selected task
- `ef624aadc2e99029e227c62d57d7b6b56df21c5e` feat: show one-step predecessors and successors for the selected task
- `d00b3ac9d5ec90137d9a4f5c83c0ee2f2c9f3999` docs: record the one-step predecessor and successor view
- `d93b801dad2cfd6fdb853cb8d8a01f01c26538ba` test: keep stale retired and orphan dependencies read only
- `1c813e3b05c271f043b1360247864ebd216102ae` feat: label stale retired and orphan dependencies without executing them
- `e6b71d55b51c980224e130e399e53502bd79e04d` docs: record stale retired and orphan dependency labels

### RD-04 선택 동기화

작업서 `docs/development-roadmap/RD-04-selective-sync/tasks.md`.

- `3f642cea8eaa461f35508b151b448233a0a4272a` test: pin two independent token changes apart from one alias bundle
- `5fb07911e3a1b1530f34aee2cca47f9df7319910` feat: read the partial token fixture without writing values
- `4ef1c8e5c6b038ea26f097d67a962daf4ae6f477` docs: record the partial token fixture apart from the alias bundle
- `cc53d88e91da49ac33c54c720b1be228b78c93bd` test: require a stable change identity for a serialized selection bundle
- `0ce837ccf732354cf2a0f94cbb42042c9ca6fda2` feat: serialize stable change identities apart from selection order
- `dc1ce4ebd586c452f66c4526acfc4e0b2dbd6e3d` docs: record stable change identities apart from selection order
- `88398e9b2186fb6dac1512eecda2c9e8d8e74af3` test: require the selection count, select-all, and affected targets
- `d85d6388ae1c50a853278af33ca790a411b1e59e` feat: show the selection count, select-all, and affected targets
- `91a6408d4ba0029144bc3f08c90ba7dbe59b85cc` docs: record selection counts and affected targets on change rows
- `5caacfd96b70a03abd80d331a5a8b5317a38e2bf` test: require a partial apply to leave skipped values and the baseline
- `95c8714f29ec1af8094e88896f14b114c4afa63c` feat: apply only the validated selection and limit the baseline
- `964e8f3ae07d4fd1a02a9dde777ca2ae6a82f81b` docs: record the partial apply that limits the baseline
- `80742c55590c46e85ca8289298abc0a58371a9a8` test: require shared component fields to keep the same main component
- `f5e853a2056798c94b5cf5419484255998f6bd85` feat: apply shared component fields without a new main component
- `d161ee42784220bf20a3fb0649fcb7d3c3c3af18` docs: record shared component field selection without a new main

### RD-05 입력 자산

작업서 `docs/development-roadmap/RD-05-asset-inventory/tasks.md`.

- `e4f974ffeed2f9509c948141bce42de13027d157` test: pin the html channel as the only input record route
- `389964b782c69b05fc305c094640132a8aea7a44` feat: confirm the html channel as the input record route
- `34d36385c45b4e36a55aeed42fd561dfbba048a5` docs: record the html channel as the only input record route
- `904175b5b8ed48f6c2a3bd5f8c23ed0066dfb3c2` test: pin one HTML task input record and its safe summary
- `f12b84f03a916c2aed744db43eb7699c95094034` feat: pin an HTML task input record and keep its summary safe
- `f49dba18aa822a9b6463514b66e2079d8e0a7e05` docs: record the pinned HTML input record and its safe summary
- `325e122cb48aebe61663333db337e093bc6a1429` test: require the asset list to filter status and keep the relative source
- `306f26c7454a310f9f9b61f5ddb8b9f557d71318` feat: list input assets by status without loading them
- `b89ee860423de1716456931197d1adffac0dba89` docs: record the asset list that filters status without loading files
- `dbd4c0eb275a75dd5519e924c3c209716aa0578d` test: keep one font when two stylesheets import it and mark byte changes stale
- `29198999ebfe2aa9975576dc5792939315fbc850` feat: keep one font asset when two stylesheets import it
- `9983aab6bfca1bb70ddb9dc1573a6efb054845df` docs: record one font asset for two stylesheets and a stale byte change
- `a069898acd764f726494c713c2b742cb834fcd0b` test: keep the asset list apart from the files a browser actually loads
- `56839c3af04e0be13fa306bc2f743a4d0bbde87d` feat: record the asset list apart from the files Chrome loads
- `ed846239ebafe20621f61d44517ec0eb8b3737eb` docs: record the asset list apart from the files Chrome loads

### RD-06 네이티브 읽기

작업서 `docs/development-roadmap/RD-06-native-read/tasks.md`. 요약 schema는 `figma-flow-native-read-summary-v1`이고 `coverage.complete`는 false다. 세션 캐시는 넣지 않았다.

- `f943bc9f1f316f0f7c6624087e1bba2c1b6f45eb` test: pin the full native read beside the getters it actually uses
- `9c9d5575eea6d883620407e591972c7e92cc244f` feat: record the getters used by one full native read
- `9408fdabedc720a7dd266f7a819953dd1abef969` docs: record the getters used by one full native read
- `e0f34c2d2db5673cc17a63bf8bb99489445c2492` test: pin partial native summary coverage
- `4cf19fe6d9e8f20e9f256c238fca3f5a072ca9c3` feat: show a partial native summary in the import panel
- `b275a28ad9b31347b7663485aabc93b19fb00f7b` docs: record the partial native summary
- `ab8b1fe594b960fb2b22936dff34e3b7e711ff21` test: reject a partial native read as full evidence
- `af2a027d7bebe176de697878f3b36d191ef35fe9` feat: reject a partial native read as full evidence
- `bf65601803dc933fe0001235237c423ac9bf2636` test: require a fresh native read without a stored snapshot
- `c072439ece24499776eb80e9d74f2e600c7461a6` feat: keep each native read fresh without a session snapshot
- `64d89e40f048197c3f09545cbecf4630bf9ea8ab` docs: record the fresh native read without a session cache
- `954a00c7cd0a0d7a61b7cc6cd63bfa66d83e0411` test: measure full and summary native reads on one fixture
- `b3285c42f1189f69ea52d1f7b65ccf71d594a842` feat: measure full and summary native reads on one fixture
- `ffcde43350120941afad855b159ee3785f45619c` docs: record the measured full and summary native reads

`dacfdc577faed0cb155e1b30620cc9265ba4d1bb`는 부분 읽기 거절과 RD-09 진단을 한 기록 커밋에 넣는다.

### RD-09 진단 기록

작업서 `docs/development-roadmap/RD-09-audit-log/tasks.md`. `RD-09-AC-05`는 실제 Figma 패널 전에 통과로 적지 않는다.

- `015f440ee635d817f033dddabb504acaea69895f` test: pin the diagnostic audit export
- `73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2` feat: export a redacted diagnostic record from the graph panel
- `dacfdc577faed0cb155e1b30620cc9265ba4d1bb` docs: record the partial read rejection and diagnostic export

### RD-07 제어 전송

작업서 `docs/development-roadmap/RD-07-runtime-boundaries/tasks.md`. 보고된 SHA는 모두 이 히스토리에 있다.

단위 1

- 기준 `56034e24e922a9ff9b5e4b45e3a5cab00001a248` test: pin the current runtime transport trace
- 구현 `b170f11568364a8c1e4494613f717ad87519ec83` feat: pin the current runtime transport trace
- 기록 `2fb34775511c631fb60f9889fea86c01f676578c` docs: record the pinned runtime transport trace

단위 2. 기록 커밋의 부모는 이전 인계 `4c49dc395ec0f6f8a3bfbc1137da714f1f2b92f8`이다. 구현의 부모는 기준 `2db4fdafa3e8e337c68cdb4d4dd53f9d1f30a797`다.

- 기준 `2db4fdafa3e8e337c68cdb4d4dd53f9d1f30a797` test: require control transport to move without domain checks
- 구현 `199683f8c221fcac718991dd91ad96b6a50ab144` feat: move control transport out of the domain checks
- 기록 `59e4a57ba67a2efa1cace67c54e37b13ce747e1b` docs: record the control transport move

단위 3

- 기준 `5fb446a3ea368317de9b56df62f93597a25a6251` test: require one runtime module list for publish and trust
- 구현 `d26df89c9f8b0ec5ca704c02acc07c23222e6047` feat: share one runtime module list for publish and trust
- 기록 `c7542812a50647435b8236c22e96ced91a422b2c` docs: record the shared runtime module list

단위 4

- 기준 `910e7aa74da7c142d7798dbba12e0920490b38cb` test: run every generated bundle task kind
- 구현 `c4f8338c4803f88807fab96f58607d8e9f2652df` feat: run every generated bundle task kind
- 기록 `517b26733de38a1ea1ae885498b8b5ec41f3b3f4` docs: record the generated bundle task kinds

단위 5

- 기준 `b05f2c444105fa3cf261eabb6f79db5e2ec89675` test: keep only the public runtime boundary symbols
- 구현 `dee7688ffa829298bc794108f057c18dc6e6d766` feat: keep only the public runtime boundary symbols
- 기록 `df65b64205ed85644acf075f0acab8f37f2ac371` docs: record the public runtime boundary symbols

## 로컬 게이트

이 패스는 제품 시험을 다시 실행하지 않았다. 아래 종료 코드는 커밋된 Wiki에 적힌 것만 옮긴다. 그 문장을 이번 실행의 영수증으로 만들지 않는다. RD-01부터 RD-06, RD-08, RD-09의 종료 코드는 이 패스에서 Wiki를 다시 열지 않아 적지 않는다.

RD-07 단위 2. Wiki `docs/llm-wiki/patches/199683f8c221fcac718991dd91ad96b6a50ab144.md`. `node tests/rd07_transport_move.cjs`가 기준 `2db4fdafa3e8e337c68cdb4d4dd53f9d1f30a797`에서 종료 코드 1, 대상에서 종료 코드 0. assertion은 `pure transport must leave domain checks in place`. 조건은 `RD-07-REQ-02`. 같은 구현의 runtime version, workspace control, history oracle, trace, native-started 검사는 종료 코드 0이라고 적혀 있다. 실제 Figma 플러그인 재로드는 하지 않았다고 적혀 있다.

RD-07 단위 3. Wiki `docs/llm-wiki/patches/d26df89c9f8b0ec5ca704c02acc07c23222e6047.md`. `python3 -B -m unittest tests.test_rd07_runtime_assembly`가 기준 `5fb446a3ea368317de9b56df62f93597a25a6251`에서 종료 코드 1, 대상에서 종료 코드 0. assertion은 `publisher assembly and trusted sources must share one module list`. 조건은 `RD-07-REQ-03`. 같은 구현의 trace와 transport move 검사는 종료 코드 0. bundle의 모든 task kind와 실제 Figma 재로드는 하지 않았다고 적혀 있다.

RD-07 단위 4. Wiki `docs/llm-wiki/patches/c4f8338c4803f88807fab96f58607d8e9f2652df.md`. `python3 -B -m unittest tests.test_rd07_bundle_kinds`가 기준 `910e7aa74da7c142d7798dbba12e0920490b38cb`에서 종료 코드 1, 대상에서 종료 코드 0. assertion은 `generated bundle must run every task kind`. 조건은 `RD-07-AC-05`. 그 실행은 mock Plugin API와 mock fetch다. 실제 Figma 재로드와 네이티브 쓰기는 하지 않았다고 적혀 있다.

RD-07 단위 5. Wiki `docs/llm-wiki/patches/dee7688ffa829298bc794108f057c18dc6e6d766.md`. `python3 -B -m unittest tests.test_rd07_public_symbols`가 기준 `b05f2c444105fa3cf261eabb6f79db5e2ec89675`에서 종료 코드 1, 대상에서 종료 코드 0. assertion은 `runtime boundary must keep only its public symbols`. 조건은 `RD-07-REQ-04`. 같은 구현의 assembly, trace, bundle kind 검사는 종료 코드 0. 실제 Figma 재로드는 하지 않았다고 적혀 있다.

기록 커밋 Wiki는 발행 직후 verify를 통과로 적는다. `59e4a57ba67a2efa1cace67c54e37b13ce747e1b`는 커밋 167개와 문서 발행 1개, `c7542812a50647435b8236c22e96ced91a422b2c`는 170개와 1개, `517b26733de38a1ea1ae885498b8b5ec41f3b3f4`는 173개와 1개다. 그 페이지들도 실제 Figma 재로드는 하지 않았다고 적는다.

## 미검증 관찰

아래는 통과가 아니다. 자동 검사와 headless 요청 로그를 사람이 본 창으로 올리지 않는다. 이 패스는 Figma와 브라우저 창을 열지 않았다.

- 실제 Figma 플러그인 재로드, runtime identity, read, 승인된 fixture write. RD-07 작업서와 위 Wiki가 하지 않았다고 남긴다.
- 실제 Figma 속성 패널의 문구 변경. CHANGELOG는 mock Plugin API만 적고 속성 패널은 아직 확인하지 않았다고 적는다.
- 실제 Figma 레이어 트리의 Group, Frame, Auto Layout, prototype, resize. RD-02 작업서는 글꼴 측정과 reflow를 아직 관찰하지 않았다고 적는다.
- 실제 Figma에서 고른 값만 적용되는 선택 동기화. CHANGELOG는 그 적용을 아직 확인하지 않았다고 적는다.
- 사람이 보는 브라우저 창. CHANGELOG는 headless Chrome 요청과 사람이 보는 창을 나누고, 사람이 보는 창은 아직 확인하지 않았다고 적는다.

headless Chrome 요청 로그는 사람이 보는 창이 아니다. `tools/input_effect.py`의 `contrast_css_browser_loading`은 Chrome을 headless로 띄우고 Network 이벤트의 상대 경로를 남긴다. 커밋된 Wiki `56839c3af04e0be13fa306bc2f743a4d0bbde87d`는 그 요청 로그를 적고, 사람이 보는 창과 Figma 렌더는 보지 않았다고 적는다. 이 패스는 그 시험을 다시 실행하지 않았다.

그 밖에 CHANGELOG가 아직 확인하지 않았다고 적은 화면은 진단 내보내기 패널, 부분 읽기 거절 화면, 부분 요약의 실제 문서, 자산 목록을 연 뒤의 사진·서체 로드, 은퇴 의존성 목록, 320px 작업 목록, variant 패널, 너비 공유 렌더다.

## 제품 제약

- 프레임워크, 차트 의존성, LLM 서버, 임의 Figma JavaScript 실행기를 추가하지 않는다.
- input pin, pairing, revision, runtime freshness, uncertain-write blocking을 유지한다.
- 기존 노드 ID, main component, 사용자 override를 유지한다.
- 두 plugin 매니페스트는 `0.26.3`으로 둔다.
- force push하지 않는다.
- 비밀, 토큰, pairing, control 값, 홈 경로를 커밋하지 않는다.
- `.figma-flow/`는 gitignore다. 그 결과를 커밋하지 않는다. `git add -A`를 쓰지 않는다.

## 알려진 한계

세션 캐시. RD-06 작업서 4는 documentchange가 원격 편집, 비동기 페이지 로드, 변수 변경까지 이 런타임에서 보장되는 것을 확인하지 못해 session cache를 넣지 않는다고 적는다. TTL은 coverage가 아니다. 호출마다 다시 읽는다.

요약 읽기. 작업서 2의 `coverage.complete`는 false다. 작업서 3의 `requireFullNativeRead`는 요약을 전체 근거로 받지 않는다. readback, native edit, draft read, graph discovery는 그 검사를 통과한 읽기만 저장한다. 요약 버튼은 부분 결과를 그대로 보여 줄 수 있다.

진단 내보내기. CHANGELOG는 토큰과 홈 경로를 가리고 노드 ID, 리비전, 오류, 작업 식별자는 남긴다고 적는다. 내보내기는 문서를 바꾸지 않는다. 실제 Figma 패널은 아직 확인하지 않았다.

선택 적용. 패널이 selection을 보내기 전에는 전체 plan일 수 있다. JS digest는 Node `crypto`다. 이 한계는 이전 기록과 `figma-bridge/graph_token_sync.js`의 `graphSyncPlanForMessage`, `selectionDigest`에 있다. 이 패스는 그 함수를 다시 실행하지 않았다.

## 검수 명령

실행한 것.

`python3 tools/patch_knowledge.py verify --ref HEAD`

- 실행 때 HEAD는 `df65b64205ed85644acf075f0acab8f37f2ac371`이었다.
- 프로세스 종료 코드 0
- 출력: `verified 176 commits; 1 documentation publication commits; schema=figma-flow-patch-catalog-v1`
- 이어서 `archived pages: 39; structural-only, use legacy verify --source-git for original Git proof`
- 이 통과는 제품 인수나 실제 Figma 관찰의 통과가 아니다.
- 이 인계 파일을 그 뒤에 커밋하면 다음 verify는 그 커밋을 미기록 비문서 커밋으로 볼 수 있다. 제품 결함으로 고치지 말고 Wiki 8개 절을 남긴 뒤 다시 실행한다.

미실행. 이 패스에서 돌리지 않은 명령이다.

```sh
python3 tools/plugin_startup.py check --figma-access forbidden
node --test tests/test_graph_token_sync.cjs tests/test_native_control_icons.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_design_foundations.py'
node --test tests/test_readable_spec_native.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_directions.py'
python3 -B -m unittest discover -s tests -p 'test_design_bundle.py'
python3 -B -m unittest discover -s tests -p 'test_figma_control.py'
python3 -B -m unittest discover -s tests -p 'test_native_edit.py'
node --test tests/test_workspace_control.cjs tests/test_workspace_host.cjs tests/test_native_edit.cjs
python3 -B -m unittest discover -s tests -p 'test_figma_workspace.py'
python3 -B -m unittest discover -s tests -p 'test_workspace_replay.py'
node --test tests/test_workspace_host.cjs tests/test_workspace_activity.cjs
python3 -B -m unittest discover -s tests -p 'test_graph_sync.py'
node --test tests/test_graph_token_sync.cjs tests/test_graph_panel.cjs
python3 -B -m unittest discover -s tests -p 'test_regression_program_inputs.py'
python3 -B -m unittest discover -s tests -p 'test_input_effect_css*.py'
node --test tests/test_native_raster_table.cjs tests/test_graph_token_sync.cjs tests/test_readable_spec_native.cjs
node tests/graph_discovery_raster_oracle.cjs
python3 -B -m unittest discover -s tests -p 'test_native_raster_assets.py'
python3 -B -m unittest discover -s tests -p 'test_workspace_publish_guard.py'
node --test tests/test_workspace_control.cjs tests/test_workspace_host.cjs tests/test_native_runtime_version.cjs
node tests/rd09_audit_log.cjs
python3 -B -m unittest discover -s tests -p 'test_panel_components.py'
node tests/rd06_fresh_read.cjs
node tests/rd06_read_comparison.cjs
node tests/rd07_transport_move.cjs
python3 -B -m unittest tests.test_rd07_runtime_boundary
python3 -B -m unittest tests.test_rd07_runtime_assembly
python3 -B -m unittest tests.test_rd07_bundle_kinds
python3 -B -m unittest tests.test_rd07_public_symbols
```

React 원본을 바꾸면 `npm --prefix panel-ui run build`로 생성 자산을 다시 만들고 원본과 함께 본다. 이 패스는 그 빌드도 미실행이다.

## 푸시 전

사용자가 직접 푸시한다. force push하지 않는다. 버전과 태그를 만들지 않는다. 비밀, 토큰, 홈 경로, `.figma-flow/` 결과를 커밋하지 않는다. `git add`는 경로를 지정한다. 푸시 전에 `python3 tools/patch_knowledge.py verify --ref HEAD`가 미기록 커밋 없이 끝나는지 본다.
