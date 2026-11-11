# 요청에 맞는 방향으로 제작하기

새 UI·리디자인은 실제 브리프·기존 제품·디자인 시스템부터 확인한다. 구체적인 방향·참조·단일안 요청은 `direct` 한 안으로 진행하고, 비교 요청이나 방향 선택이 필요한 작업은 `compare` 2~3개 안을 만든다. 조사·참고만 요청한 URL, 일반 정책 문장, 이전 선택은 현재 제작 권한이 아니다. 중단·보류 요청은 기존 승인을 무효화한다. Figma 금지·텍스트 전용 요청은 해당 작업에 Figma 접근을 허용하지 않는다.

매번 시작할 때 [최신 실행본 확인](../../../docs/guide.md#automatic-startup)을 따른다. 사용 안내의 정본은 통합 가이드이며 이 문서는 입력·검토·승인 계약을 설명한다.

## 한 번의 비교에서 고정할 것

제안한 제품과 콘텐츠, 대상 언어, 방문 목적과 주 행동을 고정한다. `compare`의 2~3개 시안은 구성·서체 역할·첫 행동 또는 다음 장면이 분명하게 달라야 한다. `direct`는 요청에 맞는 한 안에 같은 품질 검토를 적용한다. 기존 허가된 원화나 임시 이미지를 비교에 사용할 수 있다. 실제 원화 제작과 시안용 참조 이미지의 비용과 증거를 구분한다. 미리보기에는 실서비스 예약·공유 같은 부작용을 연결하지 않는다.

`candidate-spec.json`은 공통 콘텐츠 파일과 후보별 `id, title, source, review, graph, composition, typography, interaction, previews`를 담는다. source는 시안 HTML, review는 설명·팔레트를 보여주는 HTML이다. previews의 두 행은 `path, viewport, width, height`로 모바일과 데스크톱의 실제 비교 이미지를 지정한다. 공통 콘텐츠의 `required_text`에는 비교할 고정 문구를 둔다. 각 후보의 그래프에 화면·행동·기능 상태와 사람이 읽을 주석, 토큰·샘플 계획을 선언한다. 주석 링크는 시안의 실제 요소를 가리켜야 하고 토큰과 컴포넌트는 검토 문서에서 볼 수 있어야 한다. 팔레트 샘플(`design_foundations.palette.samples`)은 주·보조 사용 예로 후보마다 2개 이상 둔다. 0.17.0부터 1개뿐이면 Figma에 쓰기 전에 거부된다(이전에는 원본 읽기 단계에서야 실패했다).

## 실행과 판단

프로젝트 디렉터리에서 실행하는 예시는 다음과 같다. `TOOLS`는 설치된 플러그인의 tools 디렉터리다.

```sh
python3 "$TOOLS/design_actions.py" graph --format mermaid
python3 "$TOOLS/design_actions.py" draft --project . --brief brief.md --research research.md --from-existing candidate-spec.json --mode compare --out reviews/r1
python3 "$TOOLS/design_actions.py" review --manifest reviews/r1/directions.json --judgement agent-review.json
```

첫 명령으로 정본의 상태 전이를 읽는다. `--mode`는 해결된 실제 요청을 따른다. 생략은 기존 문서 호환용이며 새 작업은 명시한다. `direct` 입력에는 실제 사용자 요청 전체인 `direct_instruction.request_text`와 그 요청을 보존한 brief의 literal excerpt를 포함한 `anchors`가 필요하다. 참조 파일을 사용할 때는 실제 경로와 해시도 고정한다. 첨부 자체나 URL만으로 제작 승인을 만들지 않는다.

새 경로의 `agent-review.json`은 `figma-flow-artifact-critique-v2`를 사용한다. 현재 brief/native_layout, 후보 원본·검토·graph·미리보기의 핀과 후보 해시를 연결한다. 목적, 정보 위계, 타이포그래피, 레이아웃, 에셋, 반응형, 상호작용의 관찰마다 실제 artifact·locator·literal excerpt 또는 캡처 영역, 관찰·이유·해결 상태를 남긴다. 현재 경고는 각각 처리 이유를 적는다. 문자열 존재·해시·검토 점수는 시각 품질을 증명하지 않으며 `visual_quality: unverified`는 실제 관찰 전까지 유지한다. 금지된 이미지·브라우저·Figma 접근을 검토를 이유로 실행하지 않는다.

새 비교 경로는 현재 검토 ID·해시, 모든 후보 ID·해시와 고정된 검토·미리보기 링크를 실제 최종 메시지 또는 질문에 제시한다. Figma 목적지는 검증된 각 후보의 네이티브 링크도 제시한다. 질문 응답은 실제 이전 질문 호출과 연결되어야 한다. 코드 서식과 자연스러운 질문 언어는 승인 의미를 바꾸지 않는다. 비교 경로는 검토 HTML과 실제 미리보기를 제시하고 `selection-prompt.txt`의 리뷰 ID·해시에 대한 이후 실제 사용자 선택을 기다린다. 단일안 경로는 같은 자료를 검토하지만 후보 선택 프롬프트를 만들지 않는다. 로컬 단일안은 `SELECTION_READY`, Figma 목적지는 실제 네이티브 검토 전까지 `NATIVE_REVIEW_PENDING`이다. Figma가 허용되지 않으면 해당 검토는 blocked로 남기고 허용된 로컬 작업만 계속한다.

## Figma에서 선택 전 검토하기

새 디자인의 기본 목적지는 일반 Figma 디자인 모드다. 목적지 옵션을 생략하면 이 경로를 사용한다. 명시적인 로컬 HTML 전용 브리프만 로컬 검토를 사용할 수 있다. Dev Mode 또는 Figma MCP를 쓰지 않는 조건은 HTML 전용 요청이 아니다. Figma 목적지의 에이전트 검토 후 상태는 `State.NATIVE_REVIEW_PENDING`이다. 사용자에게 Figma 금지 지시가 있으면 이 경로를 실행하지 않는다. 정본 후보의 화면, 행동, 상태, 양방향 연결 및 실제 사용할 편집 가능한 배치를 입력으로 사용한다. 대상 파일을 고정하고 `figma_workspace.py prepare --kind review`로 기존 Figma Flow 작업공간에 검토 작업을 준비한다. 대상 Figma 파일에서 같은 고정 플러그인을 실행하면 기존 제작 페이지와 구분되는 초안 페이지에 시안·컴포넌트·변수·주석·프로토타입을 만든다. 참고 원화나 웹 캡처가 래스터라면 편집 가능한 요소와 구분해 표시한다.

시작할 때 에이전트가 검토 자료와 같은 프로젝트에 편집 가능한 배치 파일을 만들고 후보 명세에 `"native_layout": {"path":"native-layout.json"}`을 선언한다. Figma Desktop이 발급한 ID로 고정 작업공간을 한 번 등록하고 모든 프로젝트의 검토·본제작에서 재사용한다. 개별 작업의 manifest는 새로 등록하지 않는다. 다른 ID의 기존 private data는 원래 패키지를 보존하고 작업공간 이관 범위를 확인한다. 처음 한 번 등록하는 메뉴는 Figma의 **플러그인 → 개발**이며, 화면을 보는 Dev Mode나 유료 기능이 아니다. 플러그인이 반환한 원본 읽기 결과를 저장한 뒤 검증 명령을 실행한다. 검토 전용 페이지와 현재 후보가 일치하고, 실제 주석·팔레트·변수·클릭 출발지와 도착지·복귀 연결이 확인되어야 `State.WAIT_SELECTION`에 진입한다. 각 안에는 화면 밖의 읽기 쉬운 설명 보드를 둔다. 실제 화면·버튼에는 짧은 사람용 어노테이션과 해당 보드 항목의 전체 스펙 링크를 붙이고 보드에는 정확한 대상으로 돌아가는 링크를 둔다. 설명과 private 스펙 메타데이터는 같은 graph의 화면·동작 의미를 따른다. 기술 정보·과거 소유 주석은 별도로 보존하며 [설명 계약](../../../docs/guide.md#readable-specifications)에 따라 갱신·검증한다. Figma 페이지, 주석 보드, 프레젠테이션 시작 링크를 사용자에게 제시한다. HTML 링크만 보여주거나, 준비된 플러그인 패키지 자체를 실행 결과로 취급하지 않는다.

```sh
python3 "$TOOLS/figma_workspace.py" prepare --workspace "$WORKSPACE" \
  --key direction-review --title "디자인 방향 검토" --project "내 프로젝트" --kind review -- \
  --manifest reviews/r1/directions.json --file-key "$FILE_KEY"
# 고정 WORKSPACE/manifest.json의 Figma Flow를 한 번 실행한 상태에서 로컬 명령을 수행한다.
python3 "$TOOLS/figma_control.py" run --workspace "$WORKSPACE" --key direction-review \
  --operation create --file-key "$FILE_KEY" --page-id "$PAGE_ID" --expected-revision "$REVISION"
python3 "$TOOLS/design_actions.py" verify-native-review --manifest reviews/r1/directions.json --readback ACTUAL_FIGMA_READBACK.json
```

Computer Use와 공식 Figma MCP는 소비자 실행에 필요하지 않다. 로컬 명령을 쓸 수 없으면 같은 작업 패널의 생성·JSON 저장을 사용한다. [최초 등록·재시작·실제 검증](../../../docs/guide.md)을 따르며, 패키지 생성 자체를 실행 결과로 기록하지 않는다.

### 0.15.0 의미 역할과 실제 값

역할 이름은 사용 목적이고 실제 네이티브 타입·값·사용처는 별도 계약이다. `design_foundations.roles[].native`에 `type: "FLOAT" | "STRING"`, `value`, `bindings: [{key, field}]`를 선언한다. `key`는 후보·뷰포트·상태·레이어 또는 실제 컴포넌트/인스턴스의 의미 키다. 선언한 대상과 속성이 실제 배치에 없거나 값·타입이 다르면 가져오기 전에 차단한다. 글꼴 크기를 가족 이름 문자열로 대체하거나 모든 본문에 임의의 대표 크기를 바인딩하지 않는다. 서로 다른 크기·가족은 별도 역할로 나눈다.

동봉된 `examples/native-direction-review`의 의미 역할은 다음과 같다. 후보 접두사는 실제 변수 이름에 한 번만 붙는다.

| 역할 | 정본 토큰 → 별칭 | 네이티브 값 | 실제 사용처 |
| --- | --- | --- | --- |
| Reading size | `type/body` → `size/body` | `FLOAT: 16` | 양쪽 뷰포트의 16px 본문과 메인 컴포넌트·화면 인스턴스의 레이블 `fontSize` |
| Reading family | `type/family/body` → `font/family/body` | `STRING: "Inter"` | 같은 텍스트의 `fontFamily`; 크기·배치를 바꾸지 않음 |
| Content gap | `space/content` → `space/base` | `FLOAT: 24` | 양쪽 뷰포트 메인 컴포넌트·화면 인스턴스의 `paddingLeft`, `paddingRight` |
| Control radius | `radius/control` → `radius/base` | `FLOAT: 6` | 같은 컨트롤의 `cornerRadius` |

예를 들어 Reading size의 바인딩은 `{"key":"bulletin.desktop.component.Primary.label","field":"fontSize"}`다. 샘플 생성기는 선언한 사용처를 실제 레이아웃·컨트롤 값과 먼저 비교하고 그래프·배치 핀을 함께 갱신한다. `python3 -B -m unittest discover -s examples/native-direction-review -p test_demo.py`는 생성 소스의 바이트 동일성과 누락 대상·잘못된 값 거부만 검사한다. 실제 Figma 결과는 별도 읽기 검증이 필요하다.

위 표는 정본 역할의 사용 범위다. 제목, 주석 보드와 설명용 팔레트의 보조 글자·간격이 이 본문 역할을 사용하는 것처럼 보고하지 않는다. 그 보조 값이 실제 토큰에 연결되어 있어도 해당 사용처가 정본 역할 계약에 명시되어 검증된 것과 구분한다. 샘플의 버튼 세로 패딩 14px도 Content gap 24px의 근거가 아니다.

이 경로에는 Dev Mode, 유료 업그레이드, 훅과 Computer Use가 필요 없다. 이용자는 Figma의 일반 플러그인 실행·결과 저장 기능을 사용한다. 개발 중 승인받아 Figma 프레젠테이션을 조작했다면 직접 걸어 본 경로와 프로그램이 확인한 연결 수를 구분해 기록한다.

## 선택과 후속 작업

`compare`는 실제 사용자 답변에 특정 후보가 있어야 한다. 답변이 새 시안을 요구하거나 보이지 않는다고 하면 선택되지 않은 상태로 둔다. 도우미가 테스트 승인 파일을 작성하거나 이전 유형 선택·위임·시간 경과를 승인으로 대체해서는 안 된다. 현재 리뷰 제시 이후의 실제 관리된 사용자 턴을 확인할 수 있는 호스트에서만 다음 명령을 실행한다. 로컬 기록 검사는 암호화된 신원 인증과 다르다.

```sh
python3 "$TOOLS/design_actions.py" select --manifest reviews/r1/directions.json --user-event ACTUAL_MANAGED_USER_EVENT --out reviews/r1/selection.json
python3 "$TOOLS/design_actions.py" validate-selection --selection reviews/r1/selection.json
```

`direct`는 비교 선택을 꾸미지 않고 실제 요청의 범위·현재 핀을 확인한다. 실제 관리된 사용자 기록은 제작 전 요청도 사용할 수 있지만 조건부 정책·조사·보류·철회는 권한이 아니다.

```sh
python3 "$TOOLS/design_actions.py" admit-direct --manifest reviews/r1/directions.json --user-event ACTUAL_MANAGED_USER_EVENT --out reviews/r1/selection.json
python3 "$TOOLS/design_actions.py" validate-selection --selection reviews/r1/selection.json
```

이후 `asset_batch.py --selection …`로 선택한 구도·콘셉트·참조 이미지·전체 역할 목록을 고정한다. 호스트 호출 직전 `design_actions.py generate-requests --selection … --batch … --requests …`로 현재 요청을 다시 검증한다. 호스트에서 실제 이미지 생성 결과를 얻어야 다음 단계로 넘어갈 수 있다. 필요한 에셋이 있는 Figma 번들은 `design_bundle.py --selection … --batch … --asset-receipts … --design … --graph … --out …`로 만든다. 승인 전 시험은 명시적 `--draft-only`로 실행하며 설치 가능 플러그인을 만들지 않는다.

선택 후 Figma 원본의 실제 주석 본문, 팔레트 샘플의 ID·배치·메인 컴포넌트 연결, 문구에 따라 늘어나는 프레임, 실제로 사용하는 색상·타입·여백·간격·모서리 토큰을 확인한다. 계획 HTML이나 단순 색상 목록으로 네이티브 사용을 인정하지 않는다. 선택한 파일이나 정본 그래프가 바뀌면 재검토가 필요하며, 기존 기록은 이력으로 보관한다.

설계 검토의 방법론은 동봉된 [Impeccable의 시안 비교](../../../vendor/skills/impeccable/reference/visualize.md), [design-taste-frontend](../../../vendor/skills/design-taste-frontend/SKILL.md), [Google Design Sprint의 결정 단계](https://designsprintkit.withgoogle.com/methodology/phase4-decide)를 참고한다. 동봉 원문은 [의존성 검사](skill-dependencies.md)로 확인하며, 허용된 도구와 최종 결정 권한은 현재 사용자의 지시를 따른다.

### 색상 사용 계획

색상 역할은 작성할 실제 화면·텍스트·컴포넌트의 배경·도형 fill·텍스트 ink·사용 중인 컨트롤 fill/ink 소비 대상과 연결한다. 그라디언트의 단순 색상 stop은 의미 토큰 사용으로 세지 않는다. stroke는 해당 작성 경로가 실제 속성 바인딩을 지원할 때만 사용 증거로 인정한다. 토큰 목록·범례·팔레트 샘플만으로 화면 사용을 대신하지 않는다. 미사용 색상은 정상 사전 검사에서 Figma 쓰기 전에 차단하므로, 의도한 실제 소비 대상을 보완하거나 필요 없는 역할을 계획에서 제거하고 시안 계약을 다시 검증한다. 가져온 뒤에도 실제 paint와 변수 바인딩을 재읽는다. 탐색 시안의 검증 성공은 사람의 선택이나 본제작 승인이 아니다.
