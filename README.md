# Figma Flow 0.20.1

그래프의 컴포넌트 디자인 토큰을 정본으로 삼아 Figma와 웹으로 내보내고, 디자이너의 직접 편집을 그래프로 역수입합니다. [Graph SSOT 절차](examples/graph-ssot/README.md)에서 최초 이관·실측 검증·충돌 복구를 확인하세요. 기존 Unslop 비평과 프로젝트별 브라우저 접근 등록도 유지합니다.

Figma Flow는 기획과 디자인 시스템을 데스크톱·모바일 시안으로 만들고, 사람이 선택한 방향의 Figma 화면·컴포넌트·변수·주석을 다시 읽어 대조하는 Codex 플러그인입니다. 전문 분석 보고서, GitHub의 컴포넌트 코드, 디자인 시스템 사이트도 기획과 함께 사용할 수 있습니다.

**처음 시작할 때** 빈 작업 폴더에서 [클론 전부터 맡기는 설치 프롬프트](docs/installation-and-updates.md#1-클론-전부터-codex에-맡기기)를 Codex에 보내세요. Codex 플러그인을 먼저 설치하고 Figma 개발 플러그인 연결과 실제 읽기 검증까지 이어갑니다. Computer Use가 없으면 같은 패키지·검증을 사용하고 Figma 버튼만 사람이 조작합니다. 직접 클론하려면 아래 명령과 [클론 후 프롬프트](docs/codex-setup-prompts.md)를 사용하세요.

```sh
git clone --branch v0.18.2 https://github.com/jonsoku-dev/figma-flow.git
cd figma-flow
```

| 하려는 일 | 문서 |
|---|---|
| Figma에 처음 등록하고 첫 시안 비교하기 | [실제 스크린샷으로 따라 하는 사용 가이드](docs/figma-guide.md) |
| Codex에서 설치와 예제 실행 맡기기 | [Computer Use 사용·미사용 프롬프트](docs/codex-setup-prompts.md) |
| 클론 전 설치·Figma 연결·업데이트·롤백 | [단계별 가이드와 프롬프트](docs/installation-and-updates.md) · [연동 스킬](skills/figma-plugin-setup/SKILL.md) |
| 회사 private 저장소로 복제·배포 | [Private 저장소 가이드](docs/private-repository.md) |
| Node LTS·회사 npm 설정·lockfile 제외 | [환경 설정 가이드](docs/npm-environment.md) |
| 지정한 디자인 시스템으로 화면 만들기 | [shadcn/ui와 MUI 비교 결과](docs/design-system-trials.md) |
| 제품에 맞게 화면을 비평·수정하기 | [내장 Unslop 절차](skills/figma-flow/references/unslop.md) |
| 브라우저 작업 사이트를 허용 목록에 추가하기 | [로컬 URL·새 사이트의 등록과 적용 확인](skills/figma-flow/references/browser-access.md) |
| 릴리스 내려받기·버전 확인 | [GitHub Releases](https://github.com/jonsoku-dev/figma-flow/releases) · [변경 기록](CHANGELOG.md) · [개발·릴리스 절차](CONTRIBUTING.md) |

### 이전 버전의 주요 변경

0.18.0의 `--require-match`는 선택한 그래프의 주석과 실제 Figma 읽기 결과를 대조합니다. 팔레트 인스턴스에 복사된 라벨을 구분하고, 화면에 배치된 버튼의 문구와 변수 바인딩을 계속 검사합니다. 구현 검사 요약의 `freshness_unverified`에는 확인할 노드와 사유, 누락 경로가 나옵니다. 시안 패키지와 본제작 번들은 내장한 이미지의 base64가 총 4 MB(4,000,000바이트)를 넘으면 결과 JSON에 경고를 남깁니다.

전문 분석 플러그인의 보고서·캡처·실행 기록을 브리프와 함께 첨부할 수 있습니다. 시안에 반영할 관찰과 원본 위치는 기존 `--research` 입력에 담습니다. “이 디자인 시스템대로”라는 요청과 함께 shadcn/ui·MUI 같은 시스템의 저장소나 문서를 주면, 기획의 화면·행동을 해당 버전의 컴포넌트·변형·토큰과 연결합니다. [자료를 시안에 연결하는 방법](skills/figma-flow/SKILL.md#첨부한-분석-자료-사용)

0.17.6은 앱 구현 검사를 실제로 돌리다 드러난 두 가지를 고칩니다. 구현 검사가 `checks/001/../../review/selection.json`처럼 상대 경로로 같은 선택 기록에 닿으면 "복사된 기록"으로 오판하던 경로 비교를 정규화했습니다(복사본은 계속 거부). Figma 가져오기가 만든 컴포넌트 변형 세트에 Figma 기본값 5px 모서리가 남아 "변수에 연결되지 않은 렌더링 값"으로 차단되던 문제를 모서리 0으로 고쳤습니다.


0.17.5는 고른 시안으로 앱을 구현할 수 있게 합니다. 지금까지 구현 검사는 구현 그래프가 선택 당시 그래프와 바이트까지 같기를 요구했는데, 구현 검사 자체는 요구사항·코드·테스트 연결과 화면의 `observed` 상태를 요구해 두 조건을 동시에 만족할 수 없었습니다. 이제 구현 그래프는 선택 그래프에 요구사항·인수 기준·코드·테스트 노드와 그 연결만 **더할** 수 있고, 선택한 노드의 `status`·`source` 외 모든 필드, 선택한 연결, 디자인 기반값, 프로토타입은 그대로여야 합니다(하나라도 바뀌면 거부).


0.17.4는 고른 시안을 본제작으로 넘기다 드러난 두 문제를 고칩니다. 검토 단계가 본제작 도구가 거부할 제품 그래프(노드 `status` 누락 등)를 통과시켰으므로, 이제 사람이 고르기 전에 같은 그래프 검사를 적용합니다. 또 본제작 키 아트 요청문에 "참조 시안의 글자·버튼을 그리지 말 것"을 명시합니다(참조로 자동 추가되는 검토 시안에 실제 UI 글자가 있기 때문입니다). 동봉 예제 그래프도 본제작 검사를 통과하도록 고쳤습니다.

0.17.3: 검토 플러그인 ID는 캠페인마다 달라야 하며, 이미지 `fit`은 FILL·FIT·CROP·TILE만 허용합니다. 0.17.2: [MIT 라이선스](LICENSE).

0.17.1은 품질 관문이 **버튼의 색**을 보도록 고칩니다. 지금까지 관문은 버튼의 위치·크기와 글자 크기만 확인했기 때문에, 배경과 같은 색으로 칠해져 보이지 않는 버튼이나 읽을 수 없는 버튼 글자가 그대로 통과했습니다(이전 캠페인 네 건 모두에서 돌아가기 버튼이 이 상태였습니다).

- **`control-invisible`(오류):** 버튼 fill과 그 아래 배경의 명도 대비가 1.25:1 미만이면 차단합니다. 배경이 이미지·그라디언트면 판정하지 않습니다.
- **`control-label-contrast`(오류):** 버튼 글자와 버튼 fill의 대비가 4.5:1(24px 이상은 3:1) 미만이면 차단합니다.
- 버튼이 쓰는 변형(Primary/Return)은 시안의 `annotations.json`에서 읽습니다. 변형을 알 수 없으면 모든 변형이 실패할 때만 오류로 봅니다. 자세한 내용은 [시안 시각 품질 요구사항](skills/figma-flow/references/visual-quality.md)을 보세요.
- 워크플로 정본 해시, 레이어 어휘, Figma 가져오기 코드는 0.17.0과 같습니다. 0.17.0에서 통과하던 레이아웃이 이 두 오류로 막히면 버튼 색을 고친 뒤 검토 패키지를 다시 준비하세요.

0.17.0은 **검토 시안의 품질**을 플러그인 차원에서 다룹니다. 플러그인은 시안을 직접 그리지 않고, 에이전트가 작성한 레이아웃을 검증·작성·읽기 검증합니다. 그래서 품질을 끌어올릴 수단인 표현 어휘·품질 관문·작성 지침을 함께 바꿨습니다.

- **레이어 어휘 확장:** `rect`에 `radius`·`stroke`·`stroke_width`·`opacity`, 새 `ellipse`, 모든 도형의 `role`. 각 속성은 Figma에 쓰기 전에 검증되고, 테두리와 원의 색도 실제 색상 사용처로 집계되며, 원본 읽기에서 다시 대조됩니다. 0.16.x 형식의 기존 레이아웃은 그대로 통과합니다.
- **쓰기 전 일괄 점검:** 글꼴·이미지·글꼴 역할·버튼 위치 문제와 레이아웃의 모든 문제를 페이지를 만들기 전에 한 메시지로 보여 줍니다(`검토 초안을 만들기 전에 확인이 필요합니다 (파일은 변경되지 않았습니다)`).
- **품질 관문:** `python3 tools/design_quality.py --layout native-layout.json` 또는 `python3 tools/design_actions.py quality --manifest …`. 대비·화면 밖·텍스트 겹침/넘침·작은 글자·버튼 크기는 **오류**로 `prepare-native-review`를 막고, 의미 없는 장식 막대·역할 누락·시각적 중심 없음·단조로운 가운데 정렬·타입 스케일·밀도는 **경고**로 보고합니다. 우회 옵션은 없습니다.
- **시각 품질 지침:** [시안 시각 품질 요구사항](skills/figma-flow/references/visual-quality.md)과 미리보기 → 관문 → 수정의 자기 비평 루프를 검토 패키지 준비 전 필수 단계로 둡니다. 예제(`examples/native-direction-review`)를 이 기준으로 다시 작성했습니다(경고 23건 → 0건).
- **상태 조회:** `python3 tools/design_actions.py status --manifest …`는 워크플로 상태, 입력 파일별 current/stale/missing, 다음 이벤트를 읽기 전용으로 보여 줍니다. 차단 출력에는 `cause` 분류가 붙습니다.
- **결함 수정:** "Figma 필요 없어요/使わないで" 같은 명시적 제외의 경로 판정, 선택 후 일반 대화가 선택을 철회하던 문제, 브리프 부정문 오인, macOS 테스트 정리 오류, 그라디언트·팔레트·표시값의 쓰기 전 검증, 본제작 import의 같은 크기 글자 역할, 문서의 실행 불가 명령 등.

기존 캠페인 레이아웃은 품질 관문에서 오류가 날 수 있습니다(예: 12px 미만 글자, WCAG 대비 미달). 이 경우 해당 캠페인의 검토 패키지를 0.17.0으로 다시 준비하기 전에 레이아웃을 고쳐야 합니다. 이미 진행 중인 리뷰의 워크플로 정본 해시는 바뀌지 않았습니다.

0.16.1은 색상 역할마다 작성할 화면·텍스트·컴포넌트의 실제 배경·도형 fill·텍스트 ink·사용 중인 컨트롤 fill/ink 소비 대상을 제작 전에 대조합니다. 변수나 팔레트 범례만 존재하고 실제 화면에서 쓰이지 않는 색상은 Figma 쓰기 전에 차단하며, 가져온 결과에서도 실제 paint 바인딩을 다시 검사합니다. 이 검사는 새 캠페인의 검토 시안에도 적용되며 사용자 선택 이전의 본제작을 허용하지 않습니다.

0.16.0은 토큰 계획의 명시적인 `native.type`·`native.value`·`native.bindings`를 작성·네이티브 생성·읽기 검증이 함께 사용하도록 연결합니다. 글꼴 크기 `FLOAT`와 글꼴 이름 `STRING`, 간격·반경의 실제 소비 속성을 구분하고, 선언 값과 작성된 값·실제 바인딩을 대조합니다. 같은 이름에 다른 값이 모이거나 서로 다른 역할이 숫자만 같다는 이유로 결합되는 경우를 검사합니다. 해석할 수 없는 제안은 제작 전 단계에서 보완하며, 사용자 선택·공유 배치·Design 모드 주석/팔레트 검증은 계속 필요합니다. 실제 네이티브 문서의 변경·실행 증거는 패키지 검사와 별도로 보고합니다.

0.15.0은 브리프·조사 → 실제 비교 시안 2–3개와 계획 주석/팔레트 → 에이전트의 실제 결과 검토 → 새 UI의 기본 경로인 실제 네이티브 탐색 시안·주석/연결/팔레트·토큰 검증(명시적 로컬 전용 요청만 제외) → **사용자의 명시적인 한 시안 선택** → 선택한 콘셉트의 자산·Figma·웹 본제작 순서를 코드로 검사합니다. 세 캠페인 형태를 모두 고르는 것은 스타일 선택이 아닙니다. 기본 쓰기 함수는 선택 없으면 출력 디렉터리 생성 전 차단하며, 탐색 시안만 별도 범위로 성공할 수 있습니다. [정상 선택·실행 명령](skills/figma-flow/references/direction-selection.md)을 사용하세요. 모든 제작 상태·전이는 [유일한 워크플로 그래프](library/workflow.json)에서 가져오며, [도식](skills/figma-flow/references/workflow.generated.md)은 자동 생성됩니다. 일반 사용자에게 후크·Computer Use·Stagehand·브라우저 드라이버·GUI 자동화나 Figma Dev Mode를 요구하지 않습니다. 로컬 개발 플러그인은 Figma의 일반 Design 모드에서 사용하며 실제 API 주석과 함께 읽을 수 있는 연결된 주석 보드·가이드를 캔버스에 제공합니다. 개발 검수의 Computer Use는 사용자가 별도로 허용한 경우에만 사용하며 플러그인 의존성이 아닙니다. 로컬 도구는 사용자 기록과 해시를 검증할 수 있지만 사람의 신원을 암호학적으로 인증하지 않으며, 호스트는 실제 시안을 제시하고 실제 사용자 응답을 기다려야 합니다.

0.14.0에서 도입한 UI 제작·리디자인에서 Impeccable/웹 tasteskill 원문, 대상 언어의 폰트 우선 표본, 실제 비평·수정과 현재 산출물의 캡처를 기본으로 요구합니다. 로고·아이콘은 실제 이미지 생성 원본에서만 오며, 게임 자산은 생성 전에 고정한 한 콘셉트·참조·전체 역할 배치를 사용합니다. 생성된 제목/버튼 장식은 실제 문구에 맞춰 늘어나는 nine-slice/HUG 구조와 실제 긴 문구 검사를 거칩니다. [정상 제작·검사 명령](skills/figma-flow/references/design-review.md)을 따르세요. 기술/열람 범위는 명시적으로 유지하고 디자인 완료를 주장하지 않습니다.

모든 Figma 포함 경로에서 네이티브 의미 전달을 필수로 검사합니다. 실제 화면·조작 주석, 화면에서 사용하는 컴포넌트 인스턴스, 변수 바인딩과 모드·별칭을 재읽어 기대 계약과 대조해야 완료할 수 있습니다. `SSOT` 문구나 로컬/MCP 전송 방식과 무관하며, 준비 번들은 `pending_native_handoff`로 남습니다. 순수 로컬·SVG 수동 내보내기는 계속 사용할 수 있지만 네이티브 전달 완료 증거가 아닙니다.


기획서에서 요구사항·화면·수용 기준·구현·검증을 하나의 그래프로 연결하는 Codex 플러그인입니다. **로컬 전용 흐름은 Figma 없이 실행**할 수 있습니다. Figma가 요청되어도 기본은 로컬 디자인 번들과 개발 플러그인을 통한 가져오기·재읽기입니다. 원격 Figma MCP는 사용자가 명시적으로 선택했을 때만 사용합니다.

## 프롬프트에서 디자인 경로 선택하기

`$figma-flow`에 원하는 결과를 말하면 키아트, 전용 로고, 조작 아이콘, 수집 인장, 글꼴과 모션을 **필요한 대상별로** 배정합니다. 이미지 생성 없이 기존 원화를 쓰거나 특정 폰트를 유지하라는 조건도 계획에 반영합니다. 브라우저에서 예시를 비교하려면 플러그인 루트에서 `python3 tools/serve_design_routes.py`를 실행하세요. [사용 방법과 예시](skills/figma-flow/references/design-routing.md) · [로고·아이콘·활자 제작 절차](skills/campaign-identity/SKILL.md)

## Figma를 디자인 원본으로 지정하기

지정한 Figma 파일의 편집 가능한 최종 프레임에서 레이아웃, 서체, 상태와 에셋을 읽은 다음 웹으로 옮깁니다. 시각 디자인을 수정하면 Figma에서 다시 읽어 구현을 갱신합니다. 그래프에는 원문 출처 노드와 요구사항을 `informs`로 연결하고, 화면·Figma 노드·코드·실제 테스트 경로를 남깁니다. [그래프 계약](skills/figma-flow/references/graph-contract.md)

## 모바일게임 캠페인 레퍼런스

한국 18건과 일본 15건을 [레퍼런스 데이터](library/campaigns.json)에 보존했습니다. 캠페인 한 건에 여러 카테고리를 붙일 수 있습니다. 18개 반복 패턴에는 관찰 근거, 출처 ID, 적용 아이디어, 확인 항목과 적용 한계가 있습니다.

| 카테고리 | 조회 ID |
| --- | --- |
| 사전등록·출시 준비 | `prelaunch` |
| 주년·기념 | `anniversary` |
| 업데이트·신규 콘텐츠 | `update` |
| 참여·미션·보상 | `participation` |
| 현장 행사·협업 | `event` |
| 브랜드·캐릭터·세계관 | `brand-world` |

새 캠페인은 먼저 해당하는 카테고리의 계획을 생성합니다. 프로젝트에 맞는 항목을 수용 기준에 연결하고 브라우저에서 확인한 결과를 별도 기록하면, 같은 테스트를 다른 캠페인에서 다시 사용할 수 있습니다. 다음 명령은 참여형 캠페인의 한국 사례, 일본 사례에서 도출한 검사 계획, 전체 오프라인 카탈로그를 각각 만듭니다.

```sh
python3 tools/campaign_library.py list --category participation --market KR
python3 tools/campaign_library.py plan --category participation --market JP
python3 tools/campaign_library.py report --out ./campaign-library.html
```

[조회·검사 계획·데이터 갱신 방법](skills/figma-flow/references/campaign-library.md)

## 0.5에서 추가된 로컬 디자인과 감사

기존 기획 → 그래프 → 앱 → 변경 테스트 흐름에 디자인 토큰·컴포넌트·화면 선언과 소스/기획 감사가 연결됩니다. 로컬 디자인 번들은 Figma MCP나 Figma AI를 호출하지 않습니다. 여기서 디자인 토큰은 색·간격·글꼴 값입니다. Codex가 기획을 해석하거나 앱을 생성하는 모델 토큰 사용과 Figma MCP 사용량은 별개입니다. Figma 계정의 좌석·편집 권한·크레딧이 제공되거나 무료라고 보장하지 않습니다.

```sh
python3 tools/design_bundle.py --design /프로젝트/design.json --graph /프로젝트/graph.json --out /작업/새-디자인-번들
```

`index.html`에서 와이어프레임·스타일 시안·화면별 SVG·가져오기 키트와 투영 그래프를 확인합니다. 원본 디자인과 제품 그래프는 보존되며 새 폴더에 `preview/`, `figma-plugin/`, `design-graph.json`, `bundle.json`이 생성됩니다. 디자인 값과 사용처 의존성은 변경 영향의 입력이며, 미리보기 자체는 실제 앱 동작이나 Figma 가져오기 성공 증거가 아닙니다.

[로컬 디자인·감사 절차](skills/figma-flow/references/local-design-audit.md)는 디자인 원본의 형식, Figma 개발 플러그인 등록·가져오기·재읽기, 소스 의존성 누락과 기획 모순의 분리, 감사 결과에 따른 테스트 범위와 완료 주장의 한계를 설명합니다.

## 0.9.0: 치수도 실제 앱의 전후 값으로 비교하기

복습 카드 비교 화면에서 네이티브 **패딩 네 방향·모서리 반경 네 곳·변수에 연결된 버튼 라벨 글자 크기**를 CSS px로 비교합니다. 라이브 버튼 클릭에 연결된 이전 상태가 있으면 실제 앱의 적용 전·후 값을 각각 읽어 네이티브 측정값과 대조합니다. 값이 없거나 혼합 상태이거나 과거 실측이 없으면 해당 값은 `unknown`이며 이전 값을 추정하지 않습니다. [치수 비교 범위와 증거](skills/figma-flow/references/token-sync.md#치수와-실제-앱의-전후-비교-090)

## 버튼 한 번으로 앱에 반영하기: 0.8.0 설정 유지

처음 한 번 로컬 도우미를 시작하고, 출력된 `PRIVATE_DIR/plugin/manifest.json`을 Figma Desktop의 개발 플러그인으로 등록합니다. `2:77`은 실제 가져오기 페이지 ID로, 나머지 값도 자신의 프로젝트·파일·Figma 발급 플러그인 ID로 바꾸세요.

```sh
python3 tools/serve_figma_sync.py --project PROJECT --resolved ORIGINAL_RESOLVED --page-id 2:77 --file-key FILE_KEY --plugin-id FIGMA_ID --state-dir PRIVATE_DIR [--prior-sync PRIOR_0_7_APPLIED]
```

대괄호 항목은 선택 사항입니다. 기존 적용 이력이 없으면 **편집하지 않은 원본 디자인에서 먼저 ‘앱에 반영’을 눌러 기준선을 저장**합니다. 이후 같은 페이지의 토큰을 바꾸고 다시 누르면 현재 페이지를 읽어 앱에 적용합니다. 0.7.0에서 이어 오는 경우 첫 설정에 정확한 직전 성공 적용 폴더를 `--prior-sync`로 지정합니다. 도우미는 켜 둔 채 사용하며 재시작할 때 같은 비공개 상태 폴더를 사용합니다. 같은 파일 키·페이지·최초 원본과 보호된 적용 체인을 유지합니다. 토큰 연결 구조나 변수 바인딩을 바꾸려면 새 번들을 가져와 새 페이지에서 시작합니다.

생성 플러그인과 상태는 앱 밖에 보관하고 페어링 키가 든 파일은 공유하지 마세요. 이 동기화 플러그인만 로컬 쓰기 API에 연결합니다. 별도 읽기 전용 비교 화면은 실제 앱과 Figma 네이티브 색·지원 치수를 비교하며 현재 선택자 매핑은 복습 카드 예제입니다. 그래프 선언·정적 사용처·실제 비교·미검증 범위를 나누어 읽으세요. 원격 Figma MCP는 필요 없으며 기존 비페어링 플러그인은 네트워크 비활성 상태를 유지합니다. [버튼 방식 설정과 제한](skills/figma-flow/references/token-sync.md#버튼-한-번으로-반영하기-080)

## JSON으로 직접 계획하고 적용하기: 0.7.0 방식

Figma Desktop에서 **선택한 실제 가져오기 페이지**의 변경 전·후 재읽기 JSON을 내보내고, 로컬 앱에 반영할 스칼라 토큰 변경을 먼저 검토합니다. Figma MCP 연결 없이 실행하며 Figma의 가져오기·편집·내보내기는 사용자가 선택한 파일에서 진행합니다.

```sh
python3 tools/apply_figma_change.py --project PROJECT --resolved ORIGIN_RESOLVED --before BEFORE_JSON --after AFTER_JSON --page-id PAGE_ID --out NEW_DIR [--prior-sync PREVIOUS_RUN] [--apply]
```

대괄호 항목은 선택 사항입니다. `--apply`가 없으면 계획만 만들고 프로젝트를 바꾸지 않습니다. `--apply`는 검증된 `design.json`과 영향받는 기존 생성 자산만 갱신합니다. `--resolved`는 해당 페이지를 처음 가져올 때 사용한 원본 `resolved.json`입니다. 후속 편집도 같은 원본을 유지하고 `--prior-sync`에는 직전 성공한 적용의 **바깥 실행 폴더**를 전달합니다.

[재읽기 → 앱 빠른 시작](skills/figma-flow/references/token-sync.md#빠른-시작)에서 입력 준비, 계획·적용·연속 변경과 검증 절차를 따르세요. 선언 그래프의 화면과 실제 앱 클래스 사용처를 따로 보고하며 정적 분석의 누락 가능성도 남깁니다. 생성 CSS가 수동 변경되어 기대한 내용과 다르면 덮어쓰지 않고 실패합니다. 제공된 JSON의 구조 검증은 실제 Figma 출처 인증이나 브라우저의 시각·포인터 동작 검증이 아닙니다.

## 로컬로 먼저 실행하기

번들 실행에는 Python 3과 TAP 테스트를 지원하는 Node.js가 필요합니다. 기존 번들 실행 검증에는 Python 3.13.3과 Node.js 26.7.0을 사용했습니다. 새 설치는 `.nvmrc`의 LTS를 사용합니다. 이 폴더에서 아직 존재하지 않는 출력 경로를 지정합니다.

```sh
python3 tools/run_local.py --out /tmp/figma-flow-study-001
```

번들 [모음 기획서](examples/idea-notes/brief.md)와 앱으로 로컬 산출물·엄격한 추적 범위 검사·해시 스냅샷을 재현합니다. 이 명령은 임의 기획서를 제품으로 자동 구현하는 생성기가 아닙니다. 출력과 성공 조건, 변경 후 stale 확인과 검토 후 재개는 [한국어 자습 실습](skills/figma-flow/references/live-example.md)을 따르세요. 브라우저 동작, Figma 작성·재읽기와 원격 일치 여부는 각각 별도 증거가 필요합니다.

새 기획서에는 다음처럼 요청합니다.

```text
$figma-flow 이 기획서로 로컬 전용 흐름을 끝까지 진행해 줘.
기획서: [파일 경로 또는 아이디어 본문]
프로젝트: [기존 프로젝트 경로 또는 새 초안 출력 경로]
범위: 요구사항 분석, canonical graph, 연결된 화면 명세, 프론트엔드와 관련 검증,
strict-local coverage, local-only SSOT snapshot/check, 변경 시 검토 후 재개.
```

에이전트가 원문에서 필요한 의미 ID와 수용 기준을 정하고 기존 프로젝트를 살펴 구현합니다. 작은 아이디어도 입력으로 쓸 수 있으며 결정되지 않은 정책은 추론 또는 미정으로 기록합니다. 중요한 미정 사항은 해당 동작만 막습니다. 스크립트는 그래프 의미나 앱 동작의 정답을 자동 판단하지 않습니다.

## 내 프로젝트 등록과 변경 확인

기획서·그래프·바인딩과 실제 산출물을 준비한 프로젝트는 첫 기준선을 만들 수 있습니다. 플러그인 루트에서 실행하며 출력은 새 폴더로 지정합니다.

```sh
python3 tools/check_project.py --init --brief /프로젝트/brief.md --graph /프로젝트/graph.json --bindings /프로젝트/bindings.json --out /작업/첫-기준선
```

이 명령은 strict-local 관계 검사 후 local-only 기준선 `manifest-001.json`과 검사 보고서를 저장합니다. 그래프 원본의 정확한 바이트도 `baseline-graph.json`으로 보존합니다. 첫 등록은 기존 검토 체인을 갱신하는 용도가 아닙니다. **정리되지 않은 새 아이디어는 먼저 위의 `$figma-flow` 요청으로 graph·화면 명세·구현·증거를 준비**하세요. `--init`은 이 산출물을 자동으로 만드는 명령이 아닙니다.

기존 매니페스트를 선택해 검사합니다. 읽기만 하는 검사는 `--intent inspect`로 실행합니다. 기본값 `auto`는 frontend·디자인 검토 프로젝트를 새 UI 생성으로 보고 현재 시안 선택이 없으면 `WAIT_SELECTION`(종료 코드 1)으로 멈춥니다. 이전 그래프를 함께 지정하면 저장된 기준선 해시와 일치하는지 확인한 뒤 노드 필드·추가/삭제·연결의 전후 차이를 설명합니다.

```sh
python3 tools/check_project.py /작업/첫-기준선/manifest-001.json --previous-graph /작업/첫-기준선/baseline-graph.json --intent inspect --out /작업/검사-001
```

`summary.json`은 관계 검사와 내용 최신성을 별도로 보여 주고, `check.json`과 오프라인 `trace.html`에는 변경 출발점과 명시된 의존 경로가 남습니다. 검증된 이전 그래프를 지정한 경우 `graph-diff.json`과 `graph-diff.html`에 정확한 그래프 전후 비교가 추가됩니다. 이전 그래프가 없으면 해시·증거 변경과 의존 경로는 확인할 수 있지만 정확한 그래프 필드의 전후 값은 확인 불가로 남깁니다. 기존에 stale이던 노드는 원인을 추측하지 않고 미해결 이력으로 표시합니다.

종료 코드 `0`은 선언된 관계와 등록된 내용이 현재임을, `2`는 stale 또는 확인할 수 없는 증거가 있음을, `1`은 입력·관계·검사 오류를 뜻합니다. 검사는 프로젝트 테스트나 브라우저를 실행하지 않으며 새 기준선을 승인하지 않습니다. 실제 검토와 재검증 후에는 [검토 후 재개 절차](skills/figma-flow/references/live-example.md#4-실제-검토-후-재개하기)로 기존 체인을 이어 갑니다.

## 여러 프로젝트의 아이디어 모아 보기

매니페스트가 있는 프로젝트 두 개 이상을 한 화면에서 찾아볼 수 있습니다. 프로젝트별 요구사항을 기능 목록으로, 화면을 화면 목록으로 보여 주며 검색과 프로젝트/유형 필터를 제공합니다.

```sh
python3 tools/idea_catalog.py --project 모음 /작업/첫-기준선/manifest-001.json --project 업무 /다른프로젝트/run/manifest-001.json --out /작업/아이디어-모음
```

아직 구현하지 않은 텍스트 아이디어 여러 개도 먼저 모아 볼 수 있습니다.

```text
$figma-flow 아래 두 아이디어를 각각 기획 초안 그래프로 정리하고 하나의 아이디어 모음으로 보여 줘.
A: [첫 아이디어 본문 또는 기획서 경로]
B: [둘째 아이디어 본문 또는 기획서 경로]
각 아이디어의 요구사항과 제안 화면을 연결하고, 추론한 내용은 제안으로 표시해 줘.
구현·테스트를 수행한 것처럼 기록하지 말고 --idea로 모음을 만들어 줘.
```

정리된 그래프가 있으면 `python3 tools/idea_catalog.py --idea A /초안A/graph.json --idea B /초안B/graph.json --out /작업/초안-모음`으로 바로 볼 수 있습니다. `--project`와 `--idea`도 함께 쓸 수 있습니다. 초안의 화면 연결은 제안이며 구현·검증 완료를 뜻하지 않습니다.

`index.html`에서 구현 프로젝트의 기능 또는 화면을 선택하면 해당 프로젝트의 추적 뷰로 연결됩니다. 초안은 추적 검사 없이 제안 목록을 보여 줍니다. `REQ-001` 같은 ID가 서로 같아도 프로젝트 라벨로 구분합니다. `catalog.json`과 프로젝트별 검사 결과도 저장합니다. 그래프의 선언 상태와 내용 최신성은 따로 읽으세요. 오래되거나 잘못된 프로젝트를 다른 프로젝트의 성공으로 덮지 않습니다. 전체 종료 코드는 오류나 stale이 없으면 `0`이며 유효 초안도 여기에 포함됩니다. 오류 없이 stale이 있으면 `2`, 잘못된 프로젝트가 있으면 `1`입니다. [두 프로젝트 실습](skills/figma-flow/references/live-example.md#5-두-프로젝트의-기능과-화면-모아-보기)을 따라 시작할 수 있습니다.

## 초안을 선택해 앱 만들기와 변경 테스트

정적 `idea_catalog.py` 결과는 아이디어 탐색용입니다. **앱 생성은 명시적으로 선택한 초안 하나와 원문, 새 출력 폴더를 받는 로컬 작업대**에서 시작합니다. 플러그인 루트에서 실행합니다.

```sh
python3 tools/serve_ideas.py --catalog /작업/아이디어-모음/catalog.json --idea '복습 카드' --graph /초안/cards-graph.json --brief /초안/cards.md --selection /작업/reviews/r1/selection.json --out /작업/새-복습카드-앱
```

`--selection`은 실제 사용자가 고른 시안의 선택 기록이며 `design_actions.py select`로 남기고 `validate-selection`으로 확인합니다([시안 검토 및 사용자 선택](skills/figma-flow/references/direction-selection.md)). 선택 기록이 없거나 그 기록의 브리프·그래프가 `--brief`·`--graph`와 다르면 **앱 만들기**는 `409 WAIT_SELECTION`을 돌려줍니다. 선택 기록을 대신 만들지 마세요. 출력된 `127.0.0.1` 주소에서 선택한 초안의 **앱 만들기**를 누르면 로컬 Codex 생성과 실제 Node 테스트, strict-local·SSOT 검사가 실행됩니다. 작업대는 로컬 실행 권한을 가진 프로그램입니다. 열람만 할 때는 정적 `index.html`을 사용하세요. Python·Node·인증된 Codex CLI와 지원되는 실행 격리가 필요하며 Figma는 호출하지 않습니다. 시작 후 입력이 달라지면 고정한 해시와의 불일치를 실패로 남깁니다. 기존 프로젝트를 덮어쓰지 않고, 실패한 부분 산출물과 로그도 보존합니다.

직접 CLI로 실행하거나 준비한 산출물을 검토한 뒤 마무리하려면 [초안 → 앱 실습](skills/figma-flow/references/draft-build.md)을 따르세요. 이 문서는 실제 `복습 카드` 초안 경로, `promote_idea.py`의 SHA-256 고정·`--prepare-only`·`--finish`, 규칙별 명세와 테스트 파일별 증거, `affected_tests.py`의 계획/실행, 기존 기준선 선택과 검토 후 재개를 설명합니다. `prepared`는 준비만, `accepted`는 기록된 로컬 검사 범위의 통과만 뜻합니다. 생성 실패·검사 실패·격리 미지원은 완료로 표시하지 않습니다.

변경 테스트는 기존 매니페스트와 명시적 테스트 파일 매핑에서 선언된 의존 경로를 따라 선택합니다. 공통 기준 원본·brief·bindings 변경 또는 불완전한 경로는 보수적으로 전체 매핑 테스트를 선택합니다. 계획만 만든 결과는 실행 증거가 아니며, 실제 실행의 `receipt.json`과 파일별 TAP·표준 오류를 읽어야 합니다. 성공 영수증도 검토나 새 기준선을 자동 승인하지 않습니다.

성공한 작업대에서 **완성된 앱 열기**를 누르면 생성 제어와 분리된 로컬 주소에 앱이 열립니다. 나중에 같은 선택과 출력 폴더를 다시 열려면 작업대 명령에 `--open-reviewed /프로젝트/admission/manifest-003.json`처럼 실제 검토가 끝난 매니페스트를 지정하세요. 이 모드는 입력과 승인 이력·현재 파일을 검사하고 기존 앱을 엽니다. [선택한 초안의 생성 및 영향 검사 절차](skills/figma-flow/references/draft-build.md)

## 실행 환경 확인

방향 비교 이미지·휴대 가능한 검토 화면·전체 검사는 **명령을 실행하는 같은 Python 환경의 Pillow**가 필요합니다. 기본 `python3`와 다른 환경에 설치된 Pillow는 사용할 수 없습니다. 먼저 확인하세요.

```sh
python3 -c "from PIL import Image; import sys; print(sys.executable)"
```

없으면 사용자 전역이나 플러그인 캐시를 바꾸지 않고 작업용 가상환경을 만듭니다. 플러그인 루트에서 다음과 같이 실행할 수 있습니다.

```sh
python3 -m venv ../figma-flow-env
../figma-flow-env/bin/python -m pip install -r requirements-optional.txt
../figma-flow-env/bin/python -m unittest discover -s tests -v
```

시각 작업과 검사는 위 가상환경의 Python을 계속 사용합니다. 순수 그래프/읽기 도구의 표준 라이브러리 범위와 달리 새 UI 시각 작업에는 이 의존성이 필수이며, 설치되지 않으면 실제 시안 검토를 완료했다고 보고하지 않습니다.

## 설치와 Figma 사용

```sh
codex plugin marketplace add /절대경로/figma-flow-plugin
codex plugin add figma-flow@figma-flow-local
codex plugin list
```

설치는 로컬 Codex 설정과 플러그인 캐시를 변경합니다. 앱 목록이 갱신되지 않으면 새로 열어 확인하세요. Figma 연결이나 로그인은 이 패키지가 수행하지 않습니다.

Figma 작업이 필요하면 [로컬 디자인·감사 절차](skills/figma-flow/references/local-design-audit.md)를 따라 번들을 검토하고 Figma Desktop에서 개발 플러그인을 등록하세요. Figma가 개발 플러그인 ID를 요구하면 해당 앱에서 새 개발 플러그인을 만들어 받은 숫자 ID를 `design_bundle.py --plugin-id ID`에 전달해 새 폴더로 다시 생성합니다. SVG는 시각적 가져오기 대안이며 변수·컴포넌트·프로토타입 관계의 보존 증거는 아닙니다.

사용자가 **원격 Figma MCP 사용을 명시**한 경우에는 기존 [Figma 워크플로](skills/figma-flow/references/figma-workflow.md)를 사용합니다. MCP 없는 요청에서 연결 검사나 원격 도구 호출을 하지 않습니다. 로컬 키트 생성, 실제 Figma 가져오기, 현재 파일의 재읽기, 앱과의 시각·동작 일치는 각각 별도 증거로 보고합니다. 이번 로컬 구현의 시뮬레이션 검사는 실제 Figma 가져오기·재읽기 성공을 입증하지 않습니다.

## 도구와 계약

- [Figma 재읽기 → 앱](skills/figma-flow/references/token-sync.md): 선택 페이지의 스칼라 토큰 계획·적용·연속 변경과 실제 검증.
- [로컬 디자인·감사](skills/figma-flow/references/local-design-audit.md): 기본 no-MCP 디자인 번들, Figma 개발 플러그인, 로컬 의존성·기획 감사와 변경 테스트.
- [스킬](skills/figma-flow/SKILL.md): 임의 기획서에서 로컬 또는 Figma 포함 흐름을 수행하는 에이전트 절차.
- [그래프 계약](skills/figma-flow/references/graph-contract.md): `graph.py validate --strict-local`, 렌더링과 선택적 영향 분석. 그래프 JSON이 관계의 기준이며 화면 명세와 Markdown/Mermaid는 같은 ID를 참조합니다.
- [SSOT 계약](skills/figma-flow/references/graph-contract.md#local-freshness-manifests): `ssot.py`의 local-only 범위, 변경 감지와 증거를 고정한 검토 후 재개.
- [실행 기록](skills/figma-flow/references/run-record.md): 사실별 기준 원본, 검증 증거, 차단과 다음 행동.
- [초안 → 앱과 변경 테스트](skills/figma-flow/references/draft-build.md): 작업대·고정 입력 생성·규칙별 명세·선택 테스트·검토 재개.

`python3 -m unittest discover -s tests -v`로 로컬 도구를 검사합니다. 기본 검사·렌더링·SSOT에는 표준 라이브러리만 사용합니다. 선택적 `graph.py impact GRAPH --from ID`는 NetworkX가 필요하며 [선택 의존성](requirements-optional.txt)을 작업용 가상환경에 설치할 수 있습니다. 영향 분석은 관계를 따라 도달한 재검토 후보입니다.

strict-local 성공은 **선언된 추적 범위**가 채워졌다는 뜻이고 local-only check 성공은 **등록된 로컬 내용**이 현재라는 뜻입니다. 누락된 요구사항의 의미, 테스트 결과의 진위, 실제 브라우저 동작과 원격 Figma 상태를 증명하지 않습니다. 범위별 검증 결과를 따로 보고합니다.

번들 실행기는 갱신한 Node TAP 결과의 테스트 ID를 그래프의 테스트 노드와 대조합니다. 브라우저 기록에서는 그래프의 `check_ids`와 실제 검사 ID, 기록 당시 앱 파일의 SHA-256을 확인합니다. 실행 시 생성되는 `run.json`에 새로 실행한 검사와 재사용한 브라우저 기록 건수가 남습니다.

0.6.1에서는 CSS의 정적 `@import`도 소스 의존성 검사 대상입니다. Figma Desktop에서 내보낸 JSON과 원본을 자동 판정할 때는 `figma_bridge.py --inspect-readback EXPORT.json --input preview/resolved.json --expected figma-plugin/expected-native-handoff.json --require-match`를 사용하세요.

## 라이선스

[MIT](LICENSE)

## Graph SSOT 동기화

컴포넌트 토큰을 그래프에 한 번 정의하고 Figma·웹 사이에서 편집을 왕복할 때는 [graph-ssot](skills/graph-ssot/SKILL.md)를 사용합니다. 최초 소비자 이관, 디자이너 직접 편집, 충돌·복구 절차와 [지원 속성](examples/graph-ssot/README.md)을 확인하세요.
