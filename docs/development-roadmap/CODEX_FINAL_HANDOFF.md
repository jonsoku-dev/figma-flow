# Codex 최종 검수 인계

이 문서는 저장소 루트에서 2026-11-12에 읽은 Git 객체와 작업서 기준이다. 사용자는 Codex에서 직접 검수하고 고친 뒤, 최종 버전만 직접 푸시한다. 이 세션은 푸시, 태그, 배포, 버전 bump를 하지 않았다.

초안은 gitignore된 `.figma-flow/codex-final-handoff.md`에 먼저 저장했다. `2fb34775511c631fb60f9889fea86c01f676578c`에서 복사하려 할 때 HEAD가 이미 바뀌어 추적 복사본을 만들지 않았다. 이 문서를 다시 맞춘 복사 조건의 HEAD는 `199683f8c221fcac718991dd91ad96b6a50ab144`다. 그 SHA에서 porcelain에 제품·시험·Wiki 변경이 없을 때만 `docs/development-roadmap/CODEX_FINAL_HANDOFF.md`를 만들고 그 파일만 커밋한다.

이 핸드오프 커밋은 `CHANGELOG.md`도 `docs/llm-wiki/`도 아니다. 커밋되면 `python3 tools/patch_knowledge.py verify --ref HEAD`는 먼저 `2db4fdafa3e8e337c68cdb4d4dd53f9d1f30a797`을 미기록 비문서 커밋으로 보고, 그 다음 이 핸드오프 커밋도 같은 종류로 남는다. 둘 다 제품 assertion 실패가 아니다. 푸시 전에 RD-07 단위 2의 기록과 이 핸드오프 커밋의 Wiki 8개 절을 남긴다. 커밋 SHA는 `git log -1 --format='%H %P %s'`로 확인하고, 부모가 `199683f8c221fcac718991dd91ad96b6a50ab144`인지 본다.

읽기 전에 `git status --porcelain`과 `git rev-parse HEAD`를 다시 실행한다. 이 문서의 HEAD보다 새 제품 커밋이 있으면 그 커밋을 지도에 더한 뒤 검수한다.

## 작성 시점의 저장소

- 브랜치: `main`
- 업스트림: `origin/main` = `3a3d68e64d178d1ca37c3ff275d97d41bc92274d`
- 그 커밋 제목: `docs: publish 0.26.3 design roadmap and patch evidence`
- ahead 110, behind 0
- HEAD: `199683f8c221fcac718991dd91ad96b6a50ab144`
- HEAD 제목: `feat: move control transport out of the domain checks`
- `plugin.json` version: `0.26.3`
- `.codex-plugin/plugin.json` version: `0.26.3`
- `origin/main..HEAD`에서 두 매니페스트를 바꾼 커밋은 없다. 버전은 0.26.3에 둔다.

로드맵 문서가 부르는 이전 기준은 따로 있다. `docs/development-roadmap/README.md`와 `docs/development-roadmap/CURRENT_STATE.md`의 기준 Git은 `9a6f8ba694666ef5040a296c14b1af49bddcd722`이고, 그 문장은 0.26.2 기준이다. 그 문단은 계획 발행 시점의 설명이다. 이후 구현 여부는 아래 커밋과 각 `tasks.md`로 판단한다.

초안을 처음 쓰는 동안 `docs/llm-wiki/patches/ffcde43350120941afad855b159ee3785f45619c.md`, `docs/llm-wiki/patches/56034e24e922a9ff9b5e4b45e3a5cab00001a248.md`, `docs/llm-wiki/patches/b170f11568364a8c1e4494613f717ad87519ec83.md`가 미추적이었다. 상태 재확인 때는 그 페이지가 `2fb34775511c631fb60f9889fea86c01f676578c`에 커밋되어 있었고 porcelain은 비어 있었다. 커밋된 Wiki만 기록으로 본다.

## 목적

사용자는 Codex에서 남은 단위와 이미 올라간 커밋을 직접 검수하고 고친다. 검수가 끝난 트리만 사용자가 푸시한다. Codex도 이 인계만으로 푸시, 태그, 배포, 버전 bump를 하지 않는다. 푸시 권한은 사용자의 다음 지시에서 온다.

## 커밋 지도

범위는 `3a3d68e64d178d1ca37c3ff275d97d41bc92274d` 다음 커밋부터 HEAD까지다. 순서는 부모에서 자식이다. 한 줄이 기준(test), 구현(feat), 기록(docs)이다. SHA는 `git rev-parse`로 확인한 전체 값이다.

이전에 전달된 SHA는 모두 이 히스토리에 있다.

- `015f440ee635d817f033dddabb504acaea69895f` — `test: pin the diagnostic audit export`
- `73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2` — `feat: export a redacted diagnostic record from the graph panel`
- `dacfdc577faed0cb155e1b30620cc9265ba4d1bb` — `docs: record the partial read rejection and diagnostic export`
- `bf65601803dc933fe0001235237c423ac9bf2636` — `test: require a fresh native read without a stored snapshot`

`bf65601803dc933fe0001235237c423ac9bf2636`의 Wiki 페이지는 그 커밋 안에 없고, 이후 기록 커밋 `64d89e40f048197c3f09545cbecf4630bf9ea8ab`에 들어 있다. 그 페이지가 없던 때의 verify 실패는 미기록 커밋이었다. `2fb34775511c631fb60f9889fea86c01f676578c`에서 다시 실행한 verify는 통과했다. 그 뒤 RD-07 단위 2 커밋에는 이 세션의 verify를 다시 실행하지 않았다.

### RD-01 재사용 컴포넌트와 편집 속성

작업서: `docs/development-roadmap/RD-01-components/tasks.md`. 기능서 AC는 `RD-01-AC-01`부터 `RD-01-AC-05`. 기능서는 mock·oracle에서 재현했다고 적고, 실제 Figma 관찰이 없어 통과로 기록하지 말라고 적는다.

문구 속성, 단위 1–3:

- 기준 `7260d2995764d65d736aed031ddc63323ecf4e0c` test: pin shared import labels before text properties
- 구현 `1f80e5d9896e85afb865919aad7dad3572be932e` feat: expose shared import labels as text properties
- 기록 `cb19ac749989bafeda8ca5a75505ebe86abed802` docs: record the shared import label property

너비 재사용, 단위 4. 기준 커밋이 셋이다:

- 기준 `15f29963c1f4e7685a7deb6b851a1d360fcbad6b` test: pin width-only component reuse before sharing mains
- 기준 `f838d46167cc8078e755c579bc3340c85968f8aa` test: keep the width-reuse oracle stable after archived keys
- 기준 `76a2d2b73a1d71631abe6f717073d15068c08155` test: give appended layout variants their declared properties
- 구현 `640ff8c1a0ae1f185a60be5284558d6e7c914deb` feat: share a component main when only its width differs
- 기록 `c7327603e61a28342f6ebb1338e6758360f75251` docs: record width-only component main sharing

선언된 variant 축, 단위 5:

- 기준 `008c01c64e41b255c43b7e81e4029f4368b1f797` test: pin declared variant axes before creating combinations
- 구현 `0ff91654bd6867c816292a9fbac8561d474644d8` feat: keep declared variant axes on existing definitions
- 기록 `d5b26f079e3b2a38ba141877eca8b5782a1bd895` docs: record declared variant axes without new combinations

### RD-02 레이어 계층과 컨테이너

작업서: `docs/development-roadmap/RD-02-layer-structure/tasks.md`. AC는 `RD-02-AC-01`부터 `RD-02-AC-05`. 기능서는 통과로 기록하지 않았다. 작업서 5는 실제 글꼴 측정과 Figma reflow를 아직 보지 않았다고 적는다.

- 단위 1 기준 `47bd10f10263a0f7bd2db9bed0511f2532053532` test: pin flat layers apart from declared containers
- 단위 1 기록 `7a1bb8345246b0c0aafd3c30ee9e21557366c4f2` docs: record the pinned flat and declared layer fixtures
- 단위 2 기준 `86e30fb66bb998158034c3c887782f131e269b0f` test: require declared containers to be normalized before authoring
- 단위 2 구현 `108ecded7a1e99ee040a4c4b067a837a85d4d67c` feat: validate declared layer containers before authoring
- 단위 2 기록 `1273bb3365947986b98b66a0b3e012d7a53b6e47` docs: record declared container validation before native authoring
- 단위 3 기준 `b40d9db3300bf8d7de01a0d70fef408d16f43b98` test: require declared parents to reuse authored leaves
- 단위 3 구현 `9a465e535cafbf7e8be7fd4d7a2693b70ada4400` feat: place declared parents after existing leaf authoring
- 단위 3 기록 `942d0cf9a5c194b8decd79918062c84767a0d1ec` docs: record declared parent placement after leaf authoring
- 단위 4 기준 `8421b31163333c0b75e24e096ad6975d07138a33` test: require declared container links to match the native reader
- 단위 4 구현 `946717804fcf45d0d4c85c3e624132ed0c48455f` feat: compare declared container links with the native reader
- 단위 4 기록 `a0f790602dc1a2b6b6efaaf4623b14dc7461faa8` docs: record native readback of declared container links
- 단위 5 기준 `c7a4dfffb39aaa26eca0f6571a3bf0af97762822` test: require hug fill and fixed sizing to follow text and parent resize
- 단위 5 구현 `4ebdb77a73746f95dc985507b2ba0d704975cf9c` feat: refresh declared hug, fill, and fixed sizing after text growth
- 단위 5 기록 `d2122ffbe9ec04470f69dba3010eef0def1fdc6b` docs: record declared hug, fill, and fixed sizing refresh

### RD-08 실행 수명주기

작업서: `docs/development-roadmap/RD-08-operation-lifecycle/tasks.md`. AC는 `RD-08-AC-01`부터 `RD-08-AC-05`. 기능서는 통과로 기록하지 않았다. 작업서 6은 로컬 HTTP로 결과 POST 누락을 보고, Figma Desktop은 열지 않는다고 적는다.

- 단위 1 기준 `dc8c23c4357aba18dc6a074b00107d52c8a1d7a9` test: pin current enqueue poll result timeout and recovery transitions
- 단위 1 구현 `4dc23d6d98a7953572228b6bbf829e54c5417d13` feat: replay current control transitions without inventing native-started
- 단위 1 기록 `a9abc696ca8d6acc7974dc54076dea5e39d8de48` docs: record the pinned control transitions before a lifecycle journal
- 단위 2 기준 `aa0822c58b548c0b61e33874bada12ce4e2403bf` test: require a server operation journal before lifecycle phases are shown
- 단위 2 구현 `4f451eec0b49366519297f878867b05aff0ff197` feat: store a server operation journal on the existing request record
- 단위 2 기록 `16f728ae07a92f515225020fe61779e852eba285` docs: record the server operation journal on existing requests
- 단위 3 기준 `0664a3113792752d37096d12ee02aae08a488b2b` test: require explicit native-started from the claimed runtime
- 단위 3 구현 `24730598c912ef01c3da487193fa44e011981e7d` feat: record native start only from the claimed runtime
- 단위 3 기록 `e8a0ba7e7d6ed97c6f9e594114bfc44430e72f58` docs: record explicit native-started delivery from the claimed runtime
- 단위 4 기준 `c71aabb35f06b4ce860b36837be44d17b8bd2d6c` test: require execution history to read the server journal
- 단위 4 구현 `da3c7c51c4bc20733a5bf27278f9b459de1773ff` feat: let execution history read the server journal
- 단위 4 기록 `d6e35da1559f20ba25c443f8c4bb5e387211652b` docs: record server journal lookup for execution history
- 단위 5 기준 `0b46cdbd575cfe17d901d33925fd03c45c643782` test: require conflict detail to keep the observed value and plan hash
- 단위 5 구현 `b91d26553b3343a61f8094a1ac041e3043506787` feat: keep observed conflict values with the original plan hash
- 단위 5 기록 `f290f48aba0bbabe12a8eda3f315d8cf2205457b` docs: record conflict detail that keeps the observed value
- 단위 6 기준 `5dfc365a6ab9b7e27fed8a8b9d03e2cce9990225` test: require the journal to survive restart when result delivery fails
- 단위 6 구현 `4eab91b666eaeead1fe04395f248f936cdb51b7d` feat: keep the control journal when the result post never arrives
- 단위 6 기록 `66278decfd7f49906bb32d75f71a0be70fafa7ee` docs: record the HTTP restart check for a missed result post

### RD-03 작업 의존성

작업서: `docs/development-roadmap/RD-03-task-dependencies/tasks.md`. AC는 `RD-03-AC-01`부터 `RD-03-AC-05`. 기능서는 통과로 기록하지 않았다. 작업서 1은 UI 통합이 아직이라고 적는다. 기능서 AC-01은 세 작업의 edge 둘을 말하고, 작업서 3의 고정 fixture는 import-task에서 review의 `code.js`로 가는 edge 하나다. 검수할 때 두 문장을 같은 완료로 합치지 않는다. AC-05의 320px·키보드 이동은 CHANGELOG에서 아직 보지 않은 관찰로 남아 있다.

- 단위 1 기준 `d2de8c2b7c390e259c0535a7ca32d6fea7e83661` test: keep task identity apart from a control operation id
- 단위 1 구현 `9c2cec203451ff81f6a0e3f83787d28c2154efca` feat: keep prepared task identity apart from control operation ids
- 단위 1 기록 `0cf1823f9225b694b40961f2b6fb5d6eaa79834c` docs: record that task identity stays apart from operation ids
- 단위 2 기준 `bd53b61a4da349e5857b01f5abfd47ed80e378bd` test: require declared task dependencies to be normalized before publish
- 단위 2 구현 `1f90f63bfeb1fa30a4dacd311daa9720dc25ae8f` feat: normalize declared task dependencies before catalogue publication
- 단위 2 기록 `c5b37301ab91987b07ec317b28ee9ecb27c1fc7a` docs: record declared task dependency checks before catalogue publication
- 단위 3 기준 `7bff2100bccf6db00203cc5351c8773026783d72` test: pin a legacy catalogue apart from one declared dependency edge
- 단위 3 구현 `19b6e1a9d879272179c120cd9c0d303a3e765910` feat: load the legacy catalogue apart from the declared dependency fixture
- 단위 3 기록 `42ac878ba11ff3837fb0b5ed52dd38aa8e94304e` docs: record the legacy catalogue apart from the declared dependency edge
- 단위 4 기준 `ee61c93b47d9938c6379d1ea1b638d449338b48a` test: require one-step predecessor and successor text for the selected task
- 단위 4 구현 `ef624aadc2e99029e227c62d57d7b6b56df21c5e` feat: show one-step predecessors and successors for the selected task
- 단위 4 기록 `d00b3ac9d5ec90137d9a4f5c83c0ee2f2c9f3999` docs: record the one-step predecessor and successor view
- 단위 5 기준 `d93b801dad2cfd6fdb853cb8d8a01f01c26538ba` test: keep stale retired and orphan dependencies read only
- 단위 5 구현 `1c813e3b05c271f043b1360247864ebd216102ae` feat: label stale retired and orphan dependencies without executing them
- 단위 5 기록 `e6b71d55b51c980224e130e399e53502bd79e04d` docs: record stale retired and orphan dependency labels

### RD-04 선택 동기화

작업서: `docs/development-roadmap/RD-04-selective-sync/tasks.md`. AC는 `RD-04-AC-01`부터 `RD-04-AC-05`. 기능서는 통과로 기록하지 않았다.

- 단위 1 기준 `3f642cea8eaa461f35508b151b448233a0a4272a` test: pin two independent token changes apart from one alias bundle
- 단위 1 구현 `5fb07911e3a1b1530f34aee2cca47f9df7319910` feat: read the partial token fixture without writing values
- 단위 1 기록 `4ef1c8e5c6b038ea26f097d67a962daf4ae6f477` docs: record the partial token fixture apart from the alias bundle
- 단위 2 기준 `cc53d88e91da49ac33c54c720b1be228b78c93bd` test: require a stable change identity for a serialized selection bundle
- 단위 2 구현 `0ce837ccf732354cf2a0f94cbb42042c9ca6fda2` feat: serialize stable change identities apart from selection order
- 단위 2 기록 `dc1ce4ebd586c452f66c4526acfc4e0b2dbd6e3d` docs: record stable change identities apart from selection order
- 단위 3 기준 `88398e9b2186fb6dac1512eecda2c9e8d8e74af3` test: require the selection count, select-all, and affected targets
- 단위 3 구현 `d85d6388ae1c50a853278af33ca790a411b1e59e` feat: show the selection count, select-all, and affected targets
- 단위 3 기록 `91a6408d4ba0029144bc3f08c90ba7dbe59b85cc` docs: record selection counts and affected targets on change rows
- 단위 4 기준 `5caacfd96b70a03abd80d331a5a8b5317a38e2bf` test: require a partial apply to leave skipped values and the baseline
- 단위 4 구현 `95c8714f29ec1af8094e88896f14b114c4afa63c` feat: apply only the validated selection and limit the baseline
- 단위 4 기록 `964e8f3ae07d4fd1a02a9dde777ca2ae6a82f81b` docs: record the partial apply that limits the baseline
- 단위 5 기준 `80742c55590c46e85ca8289298abc0a58371a9a8` test: require shared component fields to keep the same main component
- 단위 5 구현 `f5e853a2056798c94b5cf5419484255998f6bd85` feat: apply shared component fields without a new main component
- 단위 5 기록 `d161ee42784220bf20a3fb0649fcb7d3c3c3af18` docs: record shared component field selection without a new main

### RD-05 입력 자산 목록

작업서: `docs/development-roadmap/RD-05-asset-inventory/tasks.md`. AC는 `RD-05-AC-01`부터 `RD-05-AC-05`. 기능서는 통과로 기록하지 않았다.

- 단위 1 기준 `e4f974ffeed2f9509c948141bce42de13027d157` test: pin the html channel as the only input record route
- 단위 1 구현 `389964b782c69b05fc305c094640132a8aea7a44` feat: confirm the html channel as the input record route
- 단위 1 기록 `34d36385c45b4e36a55aeed42fd561dfbba048a5` docs: record the html channel as the only input record route
- 단위 2 기준 `904175b5b8ed48f6c2a3bd5f8c23ed0066dfb3c2` test: pin one HTML task input record and its safe summary
- 단위 2 구현 `f12b84f03a916c2aed744db43eb7699c95094034` feat: pin an HTML task input record and keep its summary safe
- 단위 2 기록 `f49dba18aa822a9b6463514b66e2079d8e0a7e05` docs: record the pinned HTML input record and its safe summary
- 단위 3 기준 `325e122cb48aebe61663333db337e093bc6a1429` test: require the asset list to filter status and keep the relative source
- 단위 3 구현 `306f26c7454a310f9f9b61f5ddb8b9f557d71318` feat: list input assets by status without loading them
- 단위 3 기록 `b89ee860423de1716456931197d1adffac0dba89` docs: record the asset list that filters status without loading files
- 단위 4 기준 `dbd4c0eb275a75dd5519e924c3c209716aa0578d` test: keep one font when two stylesheets import it and mark byte changes stale
- 단위 4 구현 `29198999ebfe2aa9975576dc5792939315fbc850` feat: keep one font asset when two stylesheets import it
- 단위 4 기록 `9983aab6bfca1bb70ddb9dc1573a6efb054845df` docs: record one font asset for two stylesheets and a stale byte change
- 단위 5 기준 `a069898acd764f726494c713c2b742cb834fcd0b` test: keep the asset list apart from the files a browser actually loads
- 단위 5 구현 `56839c3af04e0be13fa306bc2f743a4d0bbde87d` feat: record the asset list apart from the files Chrome loads
- 단위 5 기록 `ed846239ebafe20621f61d44517ec0eb8b3737eb` docs: record the asset list apart from the files Chrome loads

### RD-06 목적별 네이티브 읽기

작업서: `docs/development-roadmap/RD-06-native-read/tasks.md`. AC는 `RD-06-AC-01`부터 `RD-06-AC-05`. 기능서는 통과로 기록하지 않았다. 작업서 1–5의 구현 문장은 커밋 `954a00c7`에 단위 5 문장까지 들어 있다. 실제 Figma 비교와 무효화는 작업서의 관찰 항목으로 남아 있다.

- 단위 1 기준 `f943bc9f1f316f0f7c6624087e1bba2c1b6f45eb` test: pin the full native read beside the getters it actually uses
- 단위 1 구현 `9c9d5575eea6d883620407e591972c7e92cc244f` feat: record the getters used by one full native read
- 단위 1 기록 `9408fdabedc720a7dd266f7a819953dd1abef969` docs: record the getters used by one full native read
- 단위 2 기준 `e0f34c2d2db5673cc17a63bf8bb99489445c2492` test: pin partial native summary coverage
- 단위 2 구현 `4cf19fe6d9e8f20e9f256c238fca3f5a072ca9c3` feat: show a partial native summary in the import panel
- 단위 2 기록 `b275a28ad9b31347b7663485aabc93b19fb00f7b` docs: record the partial native summary
- 단위 3 기준 `ab8b1fe594b960fb2b22936dff34e3b7e711ff21` test: reject a partial native read as full evidence
- 단위 3 구현 `af2a027d7bebe176de697878f3b36d191ef35fe9` feat: reject a partial native read as full evidence
- 단위 4 기준 `bf65601803dc933fe0001235237c423ac9bf2636` test: require a fresh native read without a stored snapshot
- 단위 4 구현 `c072439ece24499776eb80e9d74f2e600c7461a6` feat: keep each native read fresh without a session snapshot
- 단위 4 기록 `64d89e40f048197c3f09545cbecf4630bf9ea8ab` docs: record the fresh native read without a session cache
- 단위 5 기준 `954a00c7cd0a0d7a61b7cc6cd63bfa66d83e0411` test: measure full and summary native reads on one fixture
- 단위 5 구현 `b3285c42f1189f69ea52d1f7b65ccf71d594a842` feat: measure full and summary native reads on one fixture
- 단위 5 기록 `ffcde43350120941afad855b159ee3785f45619c` docs: record the measured full and summary native reads

`dacfdc577faed0cb155e1b30620cc9265ba4d1bb`는 단위 3 거절과 RD-09 진단을 한 기록 커밋에 넣는다. 제목이 그 둘을 함께 말한다.

### RD-09 진단 기록

작업서: `docs/development-roadmap/RD-09-audit-log/tasks.md`. AC는 `RD-09-AC-01`부터 `RD-09-AC-05`. `RD-09-AC-05`는 실제 Figma 패널 관찰 전에 통과로 적지 않는다. 작업서 4도 라이브 Figma를 열지 않은 관찰을 성공으로 적지 말라고 한다.

- 기준 `015f440ee635d817f033dddabb504acaea69895f` test: pin the diagnostic audit export
- 구현 `73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2` feat: export a redacted diagnostic record from the graph panel
- 기록 `dacfdc577faed0cb155e1b30620cc9265ba4d1bb` docs: record the partial read rejection and diagnostic export

### RD-07 제어 전송과 실행 정책

디렉터리 이름은 `docs/development-roadmap/RD-07-runtime-boundaries/`다. AC는 `RD-07-AC-01`부터 `RD-07-AC-05`. 기능서의 현재 구현은 `figma_workspace.publish`, `workspace_control`, `trusted_sources`가 한곳에 있는 상태다. 기능서는 인수 조건을 통과로 기록하지 않았다.

단위 1은 기준, 구현, 기록 커밋이 있다. 커밋된 Wiki는 `python3 -B -m unittest tests.test_rd07_runtime_boundary`를 기준에서 종료 코드 1, 대상 `b170f11568364a8c1e4494613f717ad87519ec83`에서 종료 코드 0으로 적고, 생성된 bundle 실행과 실제 Figma 재로드는 하지 않았다고 적는다. 이 세션은 그 시험을 다시 실행하지 않았다. 조건 표기는 그 Wiki의 `RD-07-REQ-01`이다. 기능서 AC는 통과로 남아 있지 않다.

- 기준 `56034e24e922a9ff9b5e4b45e3a5cab00001a248` test: pin the current runtime transport trace
- 구현 `b170f11568364a8c1e4494613f717ad87519ec83` feat: pin the current runtime transport trace
- 기록 `2fb34775511c631fb60f9889fea86c01f676578c` docs: record the pinned runtime transport trace

단위 1이 고정한 내용:

- `tests/test_rd07_runtime_boundary.py`
- `tests/fixtures/rd07/protocol-trace.json` schema `figma-flow-runtime-boundary-v1`
- `tools/figma_workspace.py`의 `load_runtime_boundary_trace`
- 전송 경로는 `poll`, `native-started`, `result`. 메서드는 POST. authorization은 Bearer 자리만 고정한다.
- 허용 operation은 review `create`, import `read`/`import`/`sync`, discover `read`, sync `read`/`apply`, native-edit `read`/`apply`
- source pin 폴더는 `figma-bridge`, `library`, `tools`. 접미사는 `.css`, `.html`, `.js`, `.json`, `.py`
- 작업서 표는 `workspace_transport`를 제안 이름으로 남기고, 이 단위에서는 분리하지 않는다고 적는다. publisher와 `trusted_sources`도 이 단위에서 옮기지 않는다고 적는다.

단위 2는 기준과 구현이 있고 기록 커밋은 없다.

- 기준 `2db4fdafa3e8e337c68cdb4d4dd53f9d1f30a797` test: require control transport to move without domain checks
- 구현 `199683f8c221fcac718991dd91ad96b6a50ab144` feat: move control transport out of the domain checks
- 기록: HEAD에 없음

단위 2가 옮긴 것: `controlRequest`만 `figma-bridge/workspace_transport.js`로 간다. kind, operation, scope, revision 검사는 `figma-bridge/workspace_control.js`에 남는다. `tools/figma_workspace.py`의 `publish`는 기존 이어 붙이기에 `workspace_transport.js`를 `workspace_control.js`보다 앞에 넣는다. `trusted_sources` 함수 자체는 옮기지 않는다. 로컬 게이트 파일은 `tests/rd07_transport_move.cjs`다. 이 세션은 그 파일을 실행하지 않았다.

단위 3, 4, 5는 작업서에 구현 문장이 없다.

- 단위 3: publisher 조립과 `trusted_sources`를 같은 변경에서 이관
- 단위 4: 생성된 bundle의 모든 task kind를 실행하고 오류·uncertainty를 비교
- 단위 5: 구 경로를 지우고 필요한 공개 심볼만 남김

설계서의 새 파일 이름 `workspace_transport.js`는 제안이다. 그 파일이 이 트리에 있는지는 구현 전에 다시 확인한다. 설계서는 동적 import와 외부 eval로 연결하지 말라고 적는다.

## 단위별 상태

로컬 게이트가 있는 단위. 게이트는 `origin/main` 이후에 추가된 검사이고, 이 세션은 다시 실행하지 않았다.

- RD-01: `tests/semantic_component_reuse_oracle.cjs`, `tests/test_semantic_component_reuse.cjs`, `tests/test_variant_axes.py`, `tests/variant_axes_oracle.cjs`. 작업서가 이어서 부르는 기존 검사는 `tests/test_figma_bridge.py`의 mock Plugin API다.
- RD-02: `tests/test_rd02_layer_fixtures.py`, `tests/test_rd02_layer_normalize.py`, `tests/rd02_container_placement_oracle.cjs`, `tests/rd02_container_readback_oracle.cjs`, `tests/rd02_container_sizing_oracle.cjs`, `tests/fixtures/rd02/`
- RD-03: `tests/test_rd03_identity_boundary.py`, `tests/test_rd03_task_dependencies.py`, `tests/test_rd03_task_fixtures.py`, `tests/test_rd03_dependency_view.py`, `tests/test_rd03_dependency_freshness.py`, `tests/fixtures/rd03/`
- RD-04: `tests/test_rd04_selective_fixture.py`, `tests/test_rd04_selection_identity.py`, `tests/test_rd04_selection_rows.py`, `tests/test_rd04_selective_apply.py`, `tests/test_rd04_component_fields.py`, `tests/fixtures/rd04/`
- RD-05: `tests/test_rd05_input_route.py`, `tests/test_rd05_html_input_record.py`, `tests/test_rd05_asset_inventory.py`, `tests/test_rd05_asset_freshness.py`, `tests/test_rd05_browser_contrast.py`
- RD-06: `tests/rd06_full_getter_ledger.cjs`, `tests/rd06_summary_coverage.cjs`, `tests/rd06_reject_partial.cjs`, `tests/rd06_fresh_read.cjs`, `tests/rd06_read_comparison.cjs`
- RD-08: `tests/test_rd08_operation_transitions.py`, `tests/test_rd08_operation_journal.py`, `tests/test_rd08_native_started.py`, `tests/test_rd08_journal_history.py`, `tests/test_rd08_conflict_detail.py`, `tests/test_rd08_restart_delivery.py`
- RD-09: `tests/rd09_audit_log.cjs`
- RD-07 단위 1: `tests/test_rd07_runtime_boundary.py`, `tests/fixtures/rd07/protocol-trace.json`
- RD-07 단위 2: `tests/rd07_transport_move.cjs`. 이 세션은 미실행이다.

로컬 게이트가 아직 없는 범위는 RD-07 단위 3–5다. 작업서의 기존 검사 명령은 분할 전의 회귀이고, 모듈 분리의 완료 증거가 아니다.

문서만 있는 범위도 RD-07 단위 3–5다. `feature.md`, `design.md`, `tasks.md`의 그 세 문단이 현재 계약이다. RD-01부터 RD-06, RD-08, RD-09와 RD-07 단위 1–2는 작업서에 구현 문장과 커밋이 있다. 그 기능서들은 그래도 AC를 통과로 올리지 않았다.

CHANGELOG `0.26.3`은 진단 내보내기, 부분 읽기 거절, 부분 요약, headless Chrome 대조, 자산 목록, 선택 행, 의존성 상태, 선행·후속, variant 축, 너비 공유, 문구 속성을 사용자 문장으로 적는다. 같은 절에는 RD-02 컨테이너, RD-06의 세션 캐시 거절과 mock 바이트 대조, RD-08 수명주기 문장이 없다. `RD-01 외 제안 기능은 아직 구현되지 않았습니다`라는 문장이 이후 커밋과 어긋난다. CHANGELOG를 다음에 고칠 때 그 문장을 현재 커밋에 맞춘다. 이 세션은 CHANGELOG를 수정하지 않았다.

## 아직 사람이 보지 않은 관찰

아래는 통과가 아니다. 자동 검사나 headless 요청 로그를 사람이 본 창으로 올리지 않는다. 이 세션은 Figma도 브라우저 창도 열지 않았다.

headless Chrome 요청 로그와 사람이 본 창:

- `tools/input_effect.py`의 `contrast_css_browser_loading`과 `_chrome_requested_paths`는 Chrome을 `--headless=new`로 띄우고 원격 디버깅 Network 이벤트의 상대 경로를 남긴다. 커밋된 Wiki `docs/llm-wiki/patches/56839c3af04e0be13fa306bc2f743a4d0bbde87d.md`는 그 실행에서 `photos/mark.png`와 `fonts/body.woff2`가 요청되고 `fonts/spare.woff2`는 요청되지 않았다고 적는다. 그것은 요청 로그다.
- CHANGELOG와 그 Wiki는 사람이 보는 브라우저 창과 Figma 렌더는 보지 않았다고 적는다. 이 세션은 `tests/test_rd05_browser_contrast.py`를 다시 실행하지 않았다. 과거 로그를 이번 검수의 브라우저 통과로 쓰지 않는다.

CHANGELOG가 아직 확인하지 않았다고 적은 화면:

- 그래프 패널에서 진단 기록을 복사·저장하는 실제 Figma 패널. 문서는 바꾸지 않는 동작이다.
- 부분 네이티브 읽기를 전체 근거로 거절하는 실제 Figma 문서 화면.
- 가져오기 패널의 너비·높이 부분 요약. 실제 문서의 속도와 화면.
- 자산 목록을 연 뒤 브라우저에서 사진과 서체가 로드되는지.
- 그래프에서 고른 값만 Figma에 적용되는지.
- Figma 패널의 은퇴 의존성 목록.
- 작업 의존성의 320px 화면과 Figma 패널.
- 실제 Figma variant 패널.
- 너비 공유의 실제 Figma 렌더. 자동 검사는 mock Plugin API다.
- 문구 속성의 실제 Figma 속성 패널. 자동 검사는 mock Plugin API다.

작업서가 관찰로 남겨 둔 것:

- RD-01: property 패널의 문구 변경, main 수정의 여러 instance 반영, resize, 재실행. 소유 fixture 밖 main·instance는 바꾸지 않는다.
- RD-02: 레이어 트리의 Group/Frame/Auto Layout, prototype 전진·복귀, resize. geometry 일치만으로 편집 사용성을 승인하지 않는다. 실제 글꼴 측정과 reflow는 미관찰이다.
- RD-03: 같은 catalogue가 브라우저와 Figma 패널에서 같은 관계로 보이는지, edge 조회가 native mutation을 보내지 않는지.
- RD-04: 실제 Figma에서 선택한 두 값과 미선택 한 값, 웹 projection, pairing. UI 체크만 바뀌고 실행 범위가 그대로이면 완료가 아니다.
- RD-05: 실제 브라우저 패널의 missing, rejected, external, stale, empty. present만으로 사진·글꼴 렌더를 통과시키지 않는다.
- RD-06: 실제 Figma에서 요약과 전체 읽기, 편집·페이지 전환 뒤 무효화. fixture의 getter 감소와 실사용 지연은 따로 보고한다. 커밋된 Wiki `b3285c42f1189f69ea52d1f7b65ccf71d594a842.md`는 실제 문서의 지연과 전송 크기를 측정하지 않았다고 적는다.
- RD-07: 기존 고정 plugin을 다시 열고 runtime identity를 확인한 뒤 read와 승인된 fixture write. source unit test만으로 생성된 runtime을 인증하지 않는다.
- RD-08: 하나의 읽기와 충돌 복구에서 journal, 패널, 실제 값이 맞는지. timeout 재현 중 원래 페이지를 지우거나 미확정 요청을 성공으로 고치지 않는다. 재시작 검사는 Figma Desktop을 열지 않은 로컬 HTTP다.
- RD-09: 진단 버튼을 눌러 복사한 기록과 문서가 그대로인지. 그 관찰이 없으면 `RD-09-AC-05`를 통과로 적지 않는다.

## 제품 제약

구현과 검수는 지금 있는 플러그인, 패널, Python 도구 안에서 한다.

- 프레임워크, 차트 의존성, LLM 서버, 임의 Figma JavaScript 실행기를 추가하지 않는다.
- input pin, pairing, revision, runtime freshness, uncertain-write blocking을 유지한다.
- 기존 노드 ID, main component, 사용자가 고친 override를 유지한다.
- `plugin.json`과 `.codex-plugin/plugin.json`은 `0.26.3`으로 둔다.
- RD-07을 이으면 한 단위만 고친다. 전송을 옮기는 단위에서도 domain validator의 호출 위치, wire schema, task closure의 격리를 유지한다. 설계서가 금지한 동적 import와 외부 eval을 넣지 않는다.
- 한 파일에는 한 작성자만 둔다. RD-07은 `tools/figma_workspace.py`, `figma-bridge/workspace_control.js`, `figma-bridge/workspace_host.js`를 건드리므로 RD-08과 동시에 그 파일을 편집하지 않는다.

## 알려진 한계

선택 적용. `figma-bridge/graph_token_sync.js`의 `graphSyncPlanForMessage`는 `message.selection`과 `message.component_fields`가 둘 다 null이면 받은 plan을 그대로 반환한다. 패널이 selection을 보내기 전에는 적용이 전체 plan일 수 있다. `selectionDigest`는 `require('crypto').createHash('sha256')`이다. `require`가 없으면 `selective apply digest is unavailable`로 던진다. 플러그인 런타임에서 그 Node crypto 경로가 없으면, 화면이 selection을 보내기 전에 선택 적용 분기가 실행되지 않는다. 빈 selection은 `empty selection`으로 거절된다. alias 묶음의 반쪽 선택은 `partial alias bundle`로 거절된다.

요약 읽기. RD-06 작업서 2의 summary schema는 `figma-flow-native-read-summary-v1`이고 `coverage.complete`는 false다. 작업서 3의 `requireFullNativeRead`는 그 요약을 전체 근거로 받지 않는다. readback, native edit, draft read, graph discovery는 그 검사를 통과한 읽기만 저장한다. 요약 버튼은 부분 결과를 그대로 보여 줄 수 있다. 부분 결과를 full 소비자에 저장하지 않는다.

세션 캐시. 작업서 4는 이 런타임에서 documentchange가 원격 편집, 비동기 페이지 로드, 변수 변경까지 보장되는 것을 확인하지 못해 session cache를 넣지 않는다고 적는다. TTL은 coverage가 아니다. `nativeReadSessionSnapshot`은 null만 반환하고, null이 아니면 `native read must not serve a stored snapshot`으로 거절한다. 실제 문서 변경 이벤트를 확인하기 전에는 세션 캐시를 넣지 않는다.

진단 로그. `figma-bridge/audit_log.js`의 `redactText`는 쿼리의 access_token, refresh_token, id_token, sync_token, local_sync_token, chat_token, token, api_key, apikey, key, secret, password, capability, bearer, auth 값을 `[redacted]`로 가린다. 홈 디렉터리 접두와 Bearer 토큰도 가린다. 노드 ID, 리비전, 오류, 작업 식별자는 남긴다. 내보내기는 적용 메시지를 보내지 않는다.

측정값. `compareNativeReadProfiles`의 커밋된 Wiki는 이 mock에서 summary getter 8개, full getter 19개, UTF-8 JSON full 13362바이트, summary 297바이트라고 적는다. `invalidation`은 unmeasured이고 `wallClockMs`는 없다. 이 숫자는 노드 하나의 mock이다. 0.26.2의 사진 JSON 9.16MB에서 0.68MB 결과는 이 비교에 재사용하지 않는다. wall-clock 개선율은 통과로 적지 않는다.

## 검수 명령

실행한 명령만 종료를 적는다. 나머지는 미실행이다.

실행함. `python3 tools/patch_knowledge.py verify --ref HEAD`

- 실행 때 HEAD는 `b170f11568364a8c1e4494613f717ad87519ec83`였고, 그 시점 porcelain은 비어 있었다.
- 프로세스 종료 코드 2
- 출력: `patch_knowledge: unrecorded non-document commit after catalog source: 56034e24e922a9ff9b5e4b45e3a5cab00001a248`
- 커밋된 `docs/llm-wiki/catalog.json`의 `source_commit`은 `b3285c42f1189f69ea52d1f7b65ccf71d594a842`다. 그 뒤 `ffcde43350120941afad855b159ee3785f45619c`는 Wiki만 고친 기록 커밋이다. 그 다음 `56034e24e922a9ff9b5e4b45e3a5cab00001a248`가 `tasks.md`와 `tests/test_rd07_runtime_boundary.py`를 바꿔 검사기가 먼저 멈춘다. `b170f11568364a8c1e4494613f717ad87519ec83`도 Wiki 없이 `tools/figma_workspace.py`와 fixture를 바꾼다.
- 이 실패는 미기록 커밋이다. 제품 assertion 실패가 이 출력에 없다.

같은 명령을 기록 커밋 뒤에 다시 실행했다.

- 실행 때 HEAD는 `2fb34775511c631fb60f9889fea86c01f676578c`였고, 끝난 뒤에도 그 SHA였다. porcelain은 비어 있었다.
- 프로세스 종료 코드 0
- 출력: `verified 163 commits; 1 documentation publication commits; schema=figma-flow-patch-catalog-v1` 그리고 `archived pages: 39; structural-only, use legacy verify --source-git for original Git proof`
- 커밋된 catalog의 `source_commit`은 `b170f11568364a8c1e4494613f717ad87519ec83`다. `2fb34775511c631fb60f9889fea86c01f676578c`는 그 뒤의 Wiki 기록 커밋 1개로 센다. 이 통과는 제품 인수나 Figma 관찰의 통과가 아니다.
- `199683f8c221fcac718991dd91ad96b6a50ab144`에서는 이 명령을 다시 실행하지 않았다. 미실행이다. 커밋된 catalog의 `source_commit`은 `b170f11568364a8c1e4494613f717ad87519ec83`이고, `2db4fdafa3e8e337c68cdb4d4dd53f9d1f30a797`과 `199683f8c221fcac718991dd91ad96b6a50ab144`는 Wiki 밖 파일을 바꾼다. 검사기는 그 형태를 미기록 비문서 커밋으로 멈춘다. 제품 assertion으로 단정하지 말고, 기록 커밋 뒤에 명령을 다시 실행한다.

실행함. `python3 tools/plugin_startup.py check --figma-access forbidden`

- 프로세스 종료 코드 0
- 출력 JSON: `{"schema": "figma-flow-startup-v1", "mode": "check", "codex": {"status": "exception", "reason": "development-checkout"}, "native": {"status": "exception", "reason": "figma-access-forbidden"}}`
- `development-checkout`은 설치된 패키지 루트에 `.git`이 있어 그 설치본을 현재 패키지로 인증하지 않은 결과다. 설치 경로는 여기에 적지 않는다.
- `figma-access-forbidden`은 이 명령에 넘긴 접근 정책이다. Figma를 열지 않았고, native 런타임을 확인하지 않았다. 종료 코드 0을 패키지 최신이나 Figma 통과로 읽지 않는다.

미실행. 작업서의 기존 검사와 이번 로드맵 게이트:

```sh
node --test tests/test_graph_token_sync.cjs tests/test_native_control_icons.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_design_foundations.py'
node --test tests/test_readable_spec_native.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_directions.py'
python3 -B -m unittest discover -s tests -p 'test_design_bundle.py'
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
python3 -B -m unittest discover -s tests -p 'test_figma_control.py'
python3 -B -m unittest discover -s tests -p 'test_native_edit.py'
node --test tests/test_workspace_control.cjs tests/test_workspace_host.cjs tests/test_native_edit.cjs
node tests/rd09_audit_log.cjs
python3 -B -m unittest discover -s tests -p 'test_panel_components.py'
python3 -B -m unittest tests.test_rd07_runtime_boundary
node tests/rd06_full_getter_ledger.cjs
node tests/rd06_summary_coverage.cjs
node tests/rd06_reject_partial.cjs
node tests/rd06_fresh_read.cjs
node tests/rd06_read_comparison.cjs
```

React 원본을 바꾸면 `npm --prefix panel-ui run build`로 생성 자산을 다시 만들고 원본과 함께 본다. 이 세션은 그 빌드도 미실행이다. `python3 tools/patch_knowledge_check.py gate`도 실행하지 않았다.

## 푸시 전 체크

사용자가 직접 푸시한다.

- 비밀, 토큰, pairing, control 값, 개인 홈 경로를 커밋하지 않는다. 진단 기록이 가리는 것과 같은 범위다.
- gitignore된 `.figma-flow/` 결과, 원시 Figma readback, 개선 게이트 JSON을 커밋하지 않는다.
- `git add -A`로 다른 작성자의 미추적 Wiki나 시험을 함께 담지 않는다. 경로를 지정해 담는다.
- force push하지 않는다.
- 버전 bump와 태그를 만들지 않는다. 두 plugin 매니페스트는 0.26.3이다.
- 푸시 전에 `git status --porcelain`이 의도한 커밋만 남았는지 보고, `python3 tools/patch_knowledge.py verify --ref HEAD`가 미기록 커밋 없이 끝나는지 본다. `2fb34775511c631fb60f9889fea86c01f676578c`에서는 종료 코드 0이었다. 이 핸드오프 커밋이 그 뒤에 있으면, 그 커밋의 Wiki를 남긴 뒤에 다시 통과해야 한다.

## 손대면 안 되는 진행 중 파일

다른 작성자가 이어서 RD-07 기록과 남은 단위를 올리고 있다. porcelain에 그 경로가 남아 있는 동안에는 수정, 스테이지, revert, 재포맷을 하지 않는다. `git add -A`를 쓰지 않는다. 작업 트리가 깨끗해지고 사용자가 그 단위를 이어서 하라고 한 뒤에만, 해당 `tasks.md`의 한 단위 안에서 편집한다.

작성 시점에 더럽거나 방금 커밋된 진행 경로:

- `figma-bridge/native_semantic_read.js`
- `tests/rd06_*.cjs`
- `docs/development-roadmap/RD-06-native-read/`
- `docs/development-roadmap/RD-07-runtime-boundaries/`
- `tests/test_rd07_runtime_boundary.py`
- `tests/fixtures/rd07/`
- `tools/figma_workspace.py`
- `CHANGELOG.md`
- `docs/llm-wiki/`

복사 결정 때 porcelain은 비어 있었다. 그 다음에 다시 더러워지면 그 경로를 수정, 스테이지, revert, 재포맷하지 않는다. `docs/` 아래에 새 미추적 파일을 두면 진행 중인 게이트가 실패한다.

## Codex가 이어서 할 일

완료 기준: RD-07 단위 3–5 가운데 사용자가 맡긴 한 단위의 인수 조건이 구현·자동 검사·미검증 이유로 연결되고, 단위 2의 빠진 기록과 CHANGELOG·Wiki 8개 절이 그 커밋의 diff와 맞고, `verify --ref HEAD`가 미기록 커밋 없이 끝난다. 실제 Figma 관찰이 없으면 해당 AC는 미검증으로 남긴다.

1. `git status --porcelain`과 `git log -1 --format='%H %s'`를 본다. porcelain이 더럽으면 그 작성자의 파일이 정리된 뒤에 편집한다. 이 문서의 부모로 기대한 커밋은 `199683f8c221fcac718991dd91ad96b6a50ab144`다.
2. 남은 구현 단위는 `docs/development-roadmap/RD-07-runtime-boundaries/tasks.md`의 3, 4, 5다. 먼저 `feature.md`의 `RD-07-AC-01`부터 `RD-07-AC-05`, `design.md`, `tasks.md`를 읽는다. 단위 1은 기록 `2fb34775511c631fb60f9889fea86c01f676578c`까지 있다. 단위 2는 구현 `199683f8c221fcac718991dd91ad96b6a50ab144`까지 있고 기록 커밋이 없다. 그 기록을 새 구현과 섞지 않는다.
3. 한 단위만 구현한다. 실패하는 검사를 먼저 그 단위의 기준 커밋으로 고정하고, 구현 커밋을 분리한다. 검사 파일의 blob을 구현 커밋에서 느슨하게 바꾸지 않는다.
4. 제품 동작이 사용자에게 보이면 CHANGELOG `0.26.3`에 짧은 문장을 추가한다. 같은 편집에서 `RD-01 외 제안 기능은 아직 구현되지 않았습니다`를 현재 커밋에 맞게 고친다. 버전 번호는 올리지 않는다.
5. Wiki 8개 절을 `docs/llm-wiki/patches/<전체 SHA>.md`에 채운다. 절 이름은 `문제와 계기`, `결과 동작`, `변경 파일과 인터페이스`, `설계 이유와 출처`, `호환성·이관·복구`, `검증과 미검증`, `한계와 후속 개선`, `관련 기록`이다. `python3 tools/patch_knowledge.py sync --ref HEAD`로 생성 메타데이터만 맞추고, 사람이 쓴 본문은 유지한다.
6. `python3 tools/patch_knowledge.py verify --ref HEAD`를 실행한다. 미기록 커밋이 남아 있으면 완료로 보고하지 않는다. 제품 결함과 미기록 커밋을 같은 실패로 적지 않는다.
7. 실패를 재현하는 개선이면 `skills/patch-knowledge/SKILL.md`의 게이트를 사용자가 검토한 제안 파일로 실행한다. 이 인계 세션은 그 게이트를 실행하지 않았다. 게이트 출력을 공유 Wiki에 복사하지 않는다.
8. 검수가 끝나면 사용자가 푸시한다. Codex는 푸시하지 않는다.

RD-01부터 RD-06, RD-08, RD-09의 기능서 AC는 여전히 통과 기록이 아니다. 코드를 더 바꾸기 전에 해당 커밋의 diff와 작업서 문장이 같은지 읽고, 실제 Figma·브라우저 관찰은 위의 미관찰 목록에 남겨 둔다.
