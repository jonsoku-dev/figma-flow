# UI 제작과 실제 디자인 검토

일반 사용자는 Figma **Design 모드**의 로컬 플러그인만 사용한다. Figma Dev Mode·Computer Use·후크·원격 MCP는 필수가 아니다. Figma가 요청된 탐색 단계는 실제 네이티브 화면/주석과 Design 캔버스의 읽을 수 있는 대상 링크 주석 보드·팔레트·토큰·프로토타입 왕복 연결을 검증해야 사용자 선택 대기로 진행한다. 로컬 HTML만 읽고 네이티브 검증 완료라고 하지 않는다. 승인 전 본제작과 승인 전 명시적 탐색용 Figma 리뷰를 구분한다. 개발 검수의 CU는 별도 사용자 허용 시에만 가능하며 일반 실행 경로에는 의존하지 않는다.

0.15의 [방향 선택·실행 계약](direction-selection.md)이 먼저 적용된다. 실제 시안 비교와 사용자 선택이 없는 제작은 차단한다. 이 문서의 폰트·비평·자산 검사는 선택을 대체하지 않는다. 본제작 디자인 검토 영수증의 캡처는 검사기가 허용하는 출처를 따른다. 사용자가 허용한 Computer Use로 Figma 등록·실행·저장을 조작할 수 있지만, 그 조작 기록만으로 네이티브 읽기·디자인 검토를 통과할 수는 없다. 실제 정적 렌더링 파일, 승인 후 공식 네이티브 API 내보내기, 사용자가 직접 제공한 실제 관측 자료를 구분해 검토하고 라이브 브라우저 실행을 가장하지 않는다.

웹·프론트엔드 UI를 새로 만들거나 리디자인할 때 이 절차를 기본으로 실행한다. Figma를 사용하는지와 무관하다. 단순 열람·기술 검사·백엔드 작업은 해당 범위만 수행하고 디자인 완료를 주장하지 않는다. 폰트 표본·생성 원본·검토 증거가 없으면 제작 완료를 `pending`/`blocked`로 남긴다.

## 1. 실제 스킬을 먼저 읽고 폰트부터 정하기

내장 [Unslop 절차](unslop.md)에서 제품·성격·세계관·강조할 장면·고유 디테일을 후보별로 정한다. 기존 디자인 시스템과 선택한 방향을 유지하며, 별도 전역 Unslop 설치는 요구하지 않는다. 실제 브라우저 관찰이 필요하면 [접근 등록](browser-access.md)을 먼저 수행한다.

[동봉 의존성 계약](skill-dependencies.md)에 따라 `tools/skill_dependencies.py --check`를 실행하고, 그 플러그인의 `vendor/skills/impeccable/SKILL.md`와 `vendor/skills/design-taste-frontend/SKILL.md`를 읽는다. 전역 스킬을 탐색하거나 설치하지 않는다. 검증된 원문을 읽지 못하면 필요한 창작 단계를 차단하고 정상 패키지를 복구한다. 해시를 기록한 것만으로 원문을 읽거나 따랐다고 주장하지 않는다.

- Impeccable의 원문을 실제로 읽되, 후크나 GUI를 실행하는 상위 스킬 단계/기본 선택 폴백을 사용하지 않는다. 해당 제작/리디자인 playbook과 편집 직전 craft-floor, 제작 후 critique 지침을 읽는다. 허가된 범위에서 실제 디자인 평가와 기계/브라우저 검사를 수행하고 독립성·제약을 그대로 보고한다.
- `design-taste-frontend`는 웹 랜딩·포트폴리오·해당 리디자인의 기본 창작 지침이다. 제품·정보·대상·기존 시각 원본에서 Design Read를 정한다. 대시보드/고밀도 제품 UI 등 원문 제외 범위에는 그 사실을 기록하고 Impeccable의 Operate 지침과 기존 제품 규칙을 따른다. 랜딩 취향을 앱 전체에 억지로 적용하지 않는다.
- **현재 사용자의 이미지 생성 의무가 스킬의 라이브러리 아이콘/SVG 권장보다 우선한다.** 로고·아이콘은 진짜 이미지 생성 원본이어야 한다. 직접 SVG 경로를 쓰거나 따라 그리기, 폰트로 만든 마크, 이모지, 기존 아이콘 라이브러리는 대체물이 아니다.

레이아웃 제작 전에 실제 대상 언어로 적어도 두 폰트 후보를 렌더링하고 제목·본문·조작 역할을 선택한다. 한국어 대상은 한국어 표본, 일본어 대상은 해당 실제 문자 표본을 사용한다. 데스크톱과 모바일에서 실제 폰트 로딩·줄바꿈·획 밀도·역할 대비를 관찰하고 결정 파일을 남긴다. 기존 폰트를 유지하는 요청이면 실제 사용 폰트를 기준으로 적합성·폴백을 검사한다. 숫자/라틴만 그럴듯한 표본으로 한국어 검토를 대체하지 않는다.

## 2. 게임 콘셉트와 전체 자산을 생성 전에 고정하기

게임별 콘셉트 ID/버전, 정확한 컨텍스트 파일, 잠근 참조 시트와 필요한 역할 목록을 먼저 정한다. 캐릭터·키아트·로고·아이콘·섹션 제목 장식·버튼 프레임과 필요한 상태 인장/장식을 처음부터 포함한다. `primary-confirm`, `destination-choice`, `rhythm-pad`, `navigation`처럼 실제 행동/섹션 목적을 구분한다. 같은 의미의 행동을 데스크톱/모바일에서 재사용하는 것은 정상이며 화면 폭마다 새 자산을 만들 필요는 없다. 다른 목적의 조작을 한 가지 범용 버튼 그림으로 일괄 덮지 않는다.

```sh
python3 tools/asset_batch.py --concept /프로젝트/concept-v2.json --reference /프로젝트/reference.png --selection /프로젝트/proposals/review-001/selection.json --batch-id game-v2-b01 --game-id game --concept-id game/concept --version 2 --role hero:key_art --role lead:character --role brand:logo --role navigate:icon --role chapter-title:section_title --role primary-confirm:button_frame --out /프로젝트/production/v2
```

출력은 원본 바이트를 보존한 `concept.*`·참조 이미지, `batch.json`, 실제 전체 문맥이 담긴 `shared-prompt.txt`, 실행 가능한 역할별 `generation-requests.json`이다. **호스트 에이전트는 각 요청의 `args`로 실제 `image_gen.imagegen` 도구를 호출한다.** 패킷 파일을 만들었다고 이미지를 생성했다고 보고하지 않는다. 모든 계획 역할을 같은 배치/컨텍스트/참조로 생성하고 원래 도구 결과와 `~/.codex/generated_images/.../exec-....png` 원본을 보존한 뒤 시각 UI를 제작한다. 역할 호출은 독립적으로 겹쳐 실행하거나 하나의 한정된 제작 배치로 진행할 수 있다. 동시각 실행을 가장하지 않는다. 같은 배치의 실패 역할만 같은 컨텍스트로 재시도한다. 콘셉트·참조·역할 범위가 늘면 새 버전의 전체 배치를 고정하고 이전 시안은 참조로만 남긴다.

일반 웹의 로고/아이콘 제작은 `--profile website`로 필요한 역할만 정할 수 있다. 게임용 모든 장식을 일반 웹에 요구하지 않는다. 참조가 없는 일반 웹은 해당 옵션을 생략한다. 실제 로고/아이콘이 요청과 최종 화면 모두에 없을 때만 그 역할을 생략한다.

생성 결과는 실제 도구 실행 ID, 원본 파일·해시, 원래 입력 프롬프트/컨텍스트/참조와 연결한다. 원본과 같거나 실제 자르기·크기 변경·색 모드/파일 형식 변환만 한 래스터를 사용한다. 로고/아이콘을 벡터 경로로 재제작하지 않는다. `crop`은 `[left,top,right,bottom]`, `resize`는 `LANCZOS`이며 선택적 Pillow가 원본에서 연산을 재현해 정확한 RGBA 픽셀과 크기를 대조한다. 진짜 생성 원본과 도구 반환 기록이 없는 그림/스크린샷/직접 쓴 매니페스트는 통과하지 않는다.

## 3. 생성된 장식은 실제 텍스트를 감싸기

섹션 제목/버튼 그림에 표시 문구를 구워 넣지 않는다. 장식 비트맵과 실제 HTML TEXT/Figma TEXT를 분리한다. `titleFor`로 제목과 내용 영역의 관계를 명시하고, 제목 문구가 여러 줄로 바뀌면 내용 래퍼와 아래 섹션이 흐름에 맞게 내려가게 한다.

- HTML은 실제 텍스트를 감싸는 `inline-flex`/grid 컨테이너와 내용에 맞는 폭·높이를 사용한다. 생성 프레임은 `border-image` 9조각 또는 모서리를 유지하는 반복 중앙/가장자리로 적용한다. 고정 크기 `<img>` 위에 문구만 겹치지 않는다. 최대 가용 폭에서 문구가 줄바꿈되고 버튼의 실제 터치 영역은 최소 44px을 유지한다.
- Figma는 동일한 생성 비트맵에서만 모서리/가장자리/중앙 조각을 추출하고, 실제 TEXT를 가진 오토레이아웃 프레임을 양축 HUG로 만든다. 내용 래퍼·제목·후속 흐름 관계를 유지하고 중요한 조작은 실제 컴포넌트/상태·변수 연결을 보존한다. 하나의 잘 늘어나는 그림을 모든 의미의 조작에 무차별 적용하지 않는다.
- 실제 대상에서 짧은 문구를 긴 한국어/여러 줄 문구로 바꾸는 모바일 스트레스 검사를 수행한다. 같은 뷰포트에서 프레임 폭 또는 높이가 실제로 커지고, 라벨/패딩이 들어맞고, 모서리 두 축의 물리 크기가 유지되며, 아래 내용이 겹치지 않는지 측정한다. 도구의 실제 결과와 PNG를 보존하고 변경 문구를 복원한다. 테스트용 캡처는 `state: responsive-probe`로 분리하며 실제 완성 화면이라고 납품하지 않는다.

재사용 가능한 웹 작성 도구는 `tools/content-skin.css`와 `tools/content_skin.js`다. 프로젝트에 복사해 실제 생성 PNG와 **측정한** 원본 slice/물리 cap 값을 연결한다. 예를 들어 실제 조작에만 다음처럼 적용한다.

```js
const confirm = createContentSkin({roleId: 'primary-confirm', label: '편지 열기', imageUrl: 'assets/confirm-frame.png', slice: 48, cap: 16, padding: 6});
const content = document.createElement('div');
content.append(actualSectionContent);
const section = createTitledSection({id: 'program-content', roleId: 'program-heading', title: '오늘의 프로그램', content, imageUrl: 'assets/program-heading.png', slice: 48, cap: 16, padding: 6});
```

숫자/경로는 예시이며 원본 이미지에 맞게 측정한다. 제목과 `titleFor` 내용은 같은 흐름의 래퍼 안에 있어 긴 문구에서 내용·후속 섹션이 같이 내려간다. 0.14의 `browser_probes.js`는 0.15에서 비활성화했다. 새 관측은 GUI 자동화가 아닌 실제 정적/네이티브 API 결과나 사용자 제공 관측으로 구분하고, 확인하지 않은 라이브 동작은 미검증으로 보고한다. 이 helper의 수치/fixture 테스트가 제품의 실제 생성 자산·시각 비평을 대체하지 않는다. 셸에서 브라우저 드라이버를 새로 띄우지 않는다.

`responsive_skins`는 실제 선언한 `section_title`/`button_frame` 역할과 실제 웹/Figma 납품 표면에만 요구한다. 장식 없는 실제 텍스트 조작은 그 의미에 맞게 유지할 수 있다.

## 4. 구체적인 비평·수정과 최종 관측 남기기

내장 [Unslop의 아홉 항목 비평](unslop.md#3-아홉-항목-순서로-비평수정하기)을 기존 자기 비평과 아래 완성 UI 검토에 적용한다. 수정 범위는 실제 결함에 맞추고, 관찰과 변경은 기존 후보 검토 메모·`critique.findings`/`critique.checks`에 남긴다.

선택 전 탐색 시안에는 [시안 시각 품질 요구사항](visual-quality.md)의 자기 비평 루프가 먼저 적용된다. 미리보기 렌더 → `python3 tools/design_quality.py --layout ...`와 체크리스트 → 수정 → 경고 0개 또는 경고마다 사유 기록을 마친 뒤에 검토 패키지를 준비한다. 오류는 막고 경고는 막지 않지만, 경고를 사유 없이 남기지 않는다. 아래 비평은 선택 후 완성 UI에 대한 것이며 이 루프를 대신하지 않는다.

완성 UI를 실제 데스크톱·모바일에서 보고 타이포그래피·구성·초점 크롭·섹션/조작 처리·클릭 영역을 비평한다. 발견한 결함은 실제로 수정하고 바뀐 값/노드·전후 캡처를 남긴다. 이미 좋은 대상을 통과시키기 위해 가짜 결함이나 불필요한 수정은 만들지 않는다. 깨끗한 검토도 각 기준의 실제 locator·관찰 값·최종 캡처가 필요하며 단순 `pass`/`문제 없음`으로 대체하지 않는다.

현재 구현·네이티브 재읽기·에셋 사용 매니페스트를 `artifacts`에 등록한다. 최종 캡처는 그 현재 해시 목록에 연결한다. 각 생성 역할은 실제 최종 상태에서 보이는 대상/locator/경계/이미지 해시와 연결한다. 숨김·프리로드·미사용 선언은 최종 사용 증거가 아니다. 상태별 자산은 그 자산이 실제 보이는 상태를 캡처한다. 제목/버튼 장식의 `label_text`는 실제 텍스트여야 한다. 서로 다른 조작 목적에 프레임을 재사용하면 그 목적들과 실제 최종 검토의 이유를 명시한다.

## 5. 관측 결과를 영수증으로 고정하고 정상 진입에서 검사하기

해시를 손으로 재작성하지 않도록 준비 도구를 사용한다. 폰트/비평/스킨 JSON에는 실제 관찰·스크린샷 경로를 넣는다. 준비 도구는 실제 스킬 위치·파일 해시·이미지 크기·현재 산출물 연결을 계산하며 관찰하지 않은 필드는 `PENDING`으로 남긴다.

```sh
python3 tools/prepare_design_review.py --project /프로젝트 --out /프로젝트/evidence/review-001 --target-kind game-campaign --game-id game --artifact app/index.html --artifact app/site.css --artifact evidence/native-readback.json --applications /프로젝트/evidence/skill-applications.json --font /프로젝트/evidence/font-observations.json --critique /프로젝트/evidence/creative-critique.json --assets /프로젝트/production/v2/asset-receipts.json --skin /프로젝트/evidence/skin-observations.json
```

출력 `bindings-design-review.json`을 프로젝트 bindings에 합친다. 관측 원문·원래 배치·도구 증거의 해시를 새 값으로 덮어쓰지 않는다. 하위 handoff 폴더의 bindings에서 원래 프로젝트를 가리킬 때는 `design_review.project_root`를 명시한다. receipt 경로만 bindings 기준이고 그 안의 산출물은 명시한 프로젝트 루트 기준이다. 동결 배치의 원래 cwd가 다른 경우 `asset_batch.path_base`, 도구 반환의 상대 경로 기준이 다른 경우 `generation.path_base`로 원래 기준만 설명한다. 원래 파일 바이트나 배치 해시는 보존한다.

```json
{"design_review":{"operation":"create","target_kind":"game-campaign","game_id":"game","receipt":"evidence/review-001/design-review.json"}}
```

```sh
python3 tools/design_review.py --project /프로젝트 --bindings /프로젝트/bindings.json --out /작업/creative-check-001
python3 tools/check_project.py --init --intent create --brief /프로젝트/brief.md --graph /프로젝트/graph.json --bindings /프로젝트/bindings.json --out /작업/check-001
```

`bindings.design_directions.selection`에 실제 선택 영수증을 연결한다. 사용자 선택 검사는 기본 `--init`의 출력 생성 전에도 실행된다. `check_project.py`의 `auto`도 프론트엔드/네이티브 제작에서 **전체 review 선언 누락**을 차단한다. 앱 생성기 `promote_idea.py`는 제작 의도를 생성 전에 고정하고 기본 `create`로 같은 게이트를 실행한다. 생성기가 bindings에 `technical`이라고 써서 이를 무시할 수 없다. 실제 기술 부분 작업은 호출자가 명시적으로 `--intent technical`, 과거 결과의 순수 열람/검사는 `--intent inspect`로 수행하며 `design_completion: not-claimed`가 된다. 창작/리디자인 완료에 이 옵션을 사용하지 않는다.

프로젝트 출력은 `design-review.json`과 `summary.json`의 `design_review_status`, `design_completion`, `design_review_receipt`다. 성공은 **제공한 증거의 구조·현재 바이트·생성 원본/변환 연결을 검사했다**는 뜻이다. 스킬을 실제로 따랐다는 사실, 도구 실행의 서버 인증, 미적 완성도나 스크린샷의 진위를 해시가 암호학적으로 입증하지 않는다. 실제 생성 세션·브라우저·Figma 관측의 범위와 제약을 별도로 보고한다. 기존 필수 Figma 네이티브 전달 게이트는 함께 통과해야 한다.

정확한 필드/거부 사유는 `tools/design_review.py`가 검증한다. 실제 관측이 없는 fixture나 준비 템플릿을 제품 증거로 전달하지 않는다.
