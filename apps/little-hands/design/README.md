# 실제 Django 화면의 정상 Figma Flow 경로

`graph.json`이 관계 정본이다. `source.py`는 실제 staging 브라우저 측정만 읽어 gallery, 화면 명세, 실제 DOM 대응표와 편집 가능한 native layout을 만든다. 브라우저나 Figma를 실행하거나 승인·성공 영수증을 생성하지 않는다. `tokens.json`과 `UI_CONTRACT.md`는 현재 프론트엔드 정본을 읽기만 한다.

## 실제 캡처

부모의 허용된 브라우저 평가 문맥에서 `measure.js`의 함수 본문을 읽고 `littleHandsMeasure('state-memberhome')`을 실행한다. 이 함수는 렌더 DOM과 스타일을 읽고 문자열을 직렬화한다. DOM을 변경하지 않는다. 실제 body의 `data-environment` 또는 보이는 footer 환경 표시에 staging이 있어야 한다. hidden input·CSRF·password value·개인 JS 상태를 읽거나 내보내지 않는다. 일반 visible input/select 값은 시각 원본에 포함한다. Figma에 전달 가능한 격리 staging 계정으로만 캡처한다.

반환 JSON 전체를 `captures/memberhome-desktop.json`과 `captures/memberhome-mobile.json`처럼 저장한다. `.html`에는 같은 시점의 실제 보이는 DOM이 들어 있다. 폼은 실제 form 태그·메서드를 보존하고 inert·data-export-only를 붙이며 action을 제거하고 버튼을 button 타입으로 제한하여 정적 소스에서 업무 처리를 막는다. form에 의존하는 실제 CSS를 유지한다. 실제 폼 메서드·경로는 control metadata에 유지한다. 페이지 아래의 콘텐츠도 측정하고 실제 문서 높이를 보존한다. CSS 숨김·보조 클리핑·음수 좌표의 기본 skip link만 제외하며 aria-hidden 시각 요소는 보존한다.

기본 뷰포트는 desktop1200×900, mobile390×960이다. 실제 JPEG를 `previews/littlehands-desktop.jpg`와 `previews/littlehands-mobile.jpg`에 저장한다. 사진·레이아웃을 합성해 미리보기로 쓰지 않는다. 전체 페이지 캡처를 후보 미리보기로 넣는 경우 candidate-spec.json의 width/height도 실제 파일 크기와 일치해야 한다. 후보 비교용 두 파일은 정확한 위 viewport 캡처로 준비하는 편이 간단하다.

22개 상태 ID는 `source.py`의 STATES 목록에 있다. 신청 검토·409·취소·대기 같은 조건부 화면은 실제 HTTP/DB 상태에서 캡처한다. 아직 없는 조건부 화면을 모델 객체나 fakecontext로 렌더하지 않는다.

## 소스 빌드

저장소 루트에서 실행한다.

```sh
python3 apps/little-hands/design/source.py --static-root "$LH_STATIC_ROOT"
python3 skills/figma-flow/scripts/graph.py validate apps/little-hands/design/graph.json
python3 apps/little-hands/design/prepare_fonts.py
python3 tools/design_quality.py --layout apps/little-hands/design/native-layout.json --out apps/little-hands/design/quality.json
```

기존 graph가 있는 첫 실행은 같은 ID의 기존 값과 사람이 추가한 노드·관계를 보존한다. 생성 원본과 다른 값은 출력의 `retained_legacy_edits`에서 확인한다. 다음 실행부터는 로컬 `.figma-flow/last-source-proposal.json`과 비교해 원본만 바뀐 필드를 반영한다. 양쪽에서 같은 필드를 다르게 바꾸면 경로를 출력하고 저장을 중단한다. 원본에서 사라진 노드·관계는 `graph.json`에 보존하고 출력과 `source-status.json`의 `orphan_candidates`에 이전 근거·연결 관계와 함께 보고한다(`retained_without_source`는 원본 없는 항목 전체를 유지한다).

다른 클론으로 생성 기준을 넘길 때는 `--proposal-out <새 파일>`로 디자인 디렉터리 밖에 이전 생성 후보를 보관하고, 다음 빌드에 `--base-graph <이전 후보>`를 전달한다. 검토한 정확한 그래프 바이트에만 적용하려면 `--expected-sha256 <SHA256>`을 지정한다. 생성기는 토큰 수정기와 같은 잠금을 잡고 임시 출력에서 명세·레이아웃을 완성한 뒤 파일별로 교체한다. 게시 도중 프로세스가 종료됐으면 같은 입력으로 다시 실행하고 명세·레이아웃의 SHA를 확인한다.

`source-status.json`은 누락된 실제 측정/미리보기, 현재 CSS epoch와 실제 블록 콘텐츠 상자 메타데이터, 측정할 수 없는 UA 입력 내부 표현을 표시한다. 전체44개가 모이면 현재 staging static manifest의 CSS와 새 메타데이터가 일치해야 최종 소스를 작성한다. 실제 collected static의 해시 파일·폰트는 source_assets에 바이트 그대로 복사한다. [Circular] 전송 별칭은 같은 실제 DOM selector의 앞선 실제 스타일만 재사용하며 dom-map에 원본 레코드를 남긴다. missing이 있으면 정상 native draft가 닫힌 상태다. graph는 소스에서 읽은 구현을 observed로 기록하지만 acceptance/test는 실제 근거 연결 전 unverified다. strict-local은 이 상태에서 통과하지 않는 것이 맞다.

`prototype-targets.json`을 선택적으로 두어 특정 실제 조작의 시각 목적지를 명시할 수 있다. 키는 `<state-id>/<state-prefixed-control-id>`, 값은 `confirmed` 같은 STATES의 짧은 이름 또는 null이다. 기존 href와 실제 서버 행동을 확인해 연결하며, 같은 상태 링크는 항상 정적으로 둔다. 각 상태의 실제 원본 selector와 native key는 `dom-map.json`에 보존된다.

## 정상 단일안 검토

44개 실제 측정과 두 실제 미리보기, 원본·gallery를 준비한 뒤 정상 CLI를 실행한다. 새 출력 디렉터리를 사용한다.

```sh
python3 tools/design_actions.py draft --project apps/little-hands --brief design/brief.md --research design/research.md --from-existing design/candidate-spec.json --mode direct --out apps/little-hands/design/reviews/r1
```

현재 실제 원본·미리보기를 본 부모가 구체적인 비평을 기록하고 `design_actions.py review`를 실행한다. 그 뒤 정상 `prepare-native-review`/등록 작업공간 경로로 전달한다. 준비된 번들은 실제 실행이나 네이티브 검증이 아니다. 실제 Figma getter·시각 관측·직접 프로토타입 실행과 admit-direct 관리 사용자 이벤트는 부모가 제공한다. 이 폴더는 승인·사용자 이벤트·네이티브 ID를 꾸미지 않는다.

## 읽기 전용 SSR 보조 내보내기

현재 런타임의 비공개 staging 환경을 적용한 Python으로 실행할 수 있다.

```sh
python3 apps/little-hands/design/export.py --out apps/little-hands/design/exports/ssr-001
```

실제 기존 member-a/operator 계정에 Client.force_login을 사용해 GET 화면만 내보낸다. 세션 준비는 시각 소스 용도이며 인증·업무 동작·인수 테스트의 증거가 아니다. production/development는 거절한다. POST 상태는 이 경로에서 만들지 않는다. 기존 확정/대기/취소 데이터가 없으면 pending으로 남긴다. 이 SSR HTML에는 실제 브라우저 geometry가 없으므로 native layout 입력을 대신할 수 없다.

## 실제 검증

부모가 실제 PostgreSQL 테스트·브라우저 행동·화면 비평·Figma 직접 조작/읽기를 각각 수행하고 범위에 맞는 실제 근거를 graph와 bindings에 연결한다. 기술 검사가 시각 품질이나 실서비스 운영 인수를 대신하지 않는다.

## 실제 앱의 Group 회귀 재현

[grouping-qa.json](grouping-qa.json)은 같은44개 화면 자료에서 desktop/mobile 공개 첫 화면의 footer 텍스트 네 개만 Group으로 묶는 선언이다. 원본 [native-layout.json](native-layout.json)의 SHA256을 먼저 확인하고, 각 group의 children을 기존 parent.children에서 제거한 뒤 group.key로 대체하고 containers에 group을 추가한다. 기본 소스와 캡처를 덮어쓰지 않고 `reviews/` 아래 새 입력 디렉터리에 쓴다.

새 layout 디렉터리에서는 assets의 상대 경로가 같은 원본 파일을 가리키도록 다시 계산하고, 로컬 metric 검사용 `fonts/sources.json`과 두 실제 Hahmlet TTF를 함께 준비한다. 위 `prepare_fonts.py`는 동봉 OFL WOFF2에서 이를 만든다. 원본 후보 spec의 native_layout 경로만 새 파일로 바꾼 뒤 정상 `design_actions.py draft → quality → review → prepare-native-review` 경로를 사용한다. 현재 artifact에 연결한 agent critique와 경고 판정이 필요하며 사람의 선택이나 production 승인을 새로 만들면 안 된다.

정상 현재 제작기에서 실제 Group 두 개를 포함한4,820개 노드를 읽어 검증했다. 이전 제작본과 비교한3,171개 leaf의 절대 bbox 차이는0이고 기존550개 Frame의 clip과314개 nonempty reaction 노드(제품312개와 palette2개)의 의미 연결이 같다. 같은 패킷 재실행은 같은 페이지·전체 node ID를 유지했다. 이는 정적 Design·prototype의 범위이며 Django 인증·POST·DB 동작과 공개 운영 배포는 별도다. 상세 범위는 [검증 기록](VERIFICATION.md)에서 구분한다.

## 대표 폼·표 안정 semantic ID 선언 (`--family-targets`)

[family-targets.json](family-targets.json)은 체크인된 원본 [graph.json](graph.json)이나 기존 재사용 ID(`Solid-*`, `Outline-*`, `Text-*`)를 덮어쓰지 않고, 대표 폼(`state-sessionavailable`, `state-reschedule`, `state-staffedit`)과 표(`state-staffsessions`)의 실제 DOM selector만 안정 semantic ID로 opt-in 매핑하기 위한 선언 파일이다.

- 대상 계열: `Field`, `Input`, `Checkbox`, `Radio`, `TableRow`, `TableCell`
- 보존 계약: 미선언 컨트롤·`a`/`button` 액션·`control_styles` 재사용 변형과 원본 `original_key`를 그대로 보존하며, 비밀번호·숨김 입력·버튼 덮어쓰기는 거부한다.
- 실행 예시(임시 작업본 또는 별도 출력 경로에서 사용):

```sh
python3 apps/little-hands/design/source.py --family-targets apps/little-hands/design/family-targets.json --static-root apps/little-hands/design/source_assets
```

이 단계의 매핑 규격은 정적 레이아웃·DOM 추적용이며, 컴포넌트 계열 compiler(`design_system` / `native` schema) 정본 연결은 핵심 계열 작업자의 계약 확정 후 후속 단계에서 맞춘다.
