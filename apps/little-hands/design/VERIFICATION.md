# 작은손 실제 검증 근거와 남은 인수

이 문서는0.27.0의 범위별 검증 기록이다. 코드 커밋·최종 릴리스·설치 상태는 [패치 Wiki](../../../docs/llm-wiki/releases.md)에서 확인한다. 문서의 버전이나 과거 base commit은 배포 영수증이 아니다. 전체 조건은 [최종 인수 행렬](../../../docs/development-roadmap/FINAL_ACCEPTANCE.md)을 따르고, 작은 집계와 원시 SHA256은 [native QA 요약](native-qa-summary.json)에 있다. native 식별자·파일 키·개인 경로·원시 readback·비밀은 공개하지 않는다.

## R8 정상 제작과 보존 검증

최종 기록 대상 R8은 정상 producer와 native verifier를 통과했다. 실제 full readback은4,820개 노드·30,278,208바이트이며 SHA256은 요약 JSON의 `native_r8.raw_sha256`이다. 화면44개, Group2개, main24개, set2개, instance494개, variable69개·collection1개다. product prototype getter312개, 복귀 getter110개, 연결 설명 target536개를 확인했다. 생성 영수증 경과 시간485.154초와 같은 패킷 재실행15.502초는 서로 같은 작업의 짝지은 성능 benchmark가 아니다. 재실행은 같은 페이지와4,820개 전체 노드 identity를 유지했다.

[Group QA 선언](grouping-qa.json)의 두 footer Group overlay는 실제 R8과 일치한다. base native layout은 그대로 두고 보호된 캡처 입력90개를 보존했다. R7 대비 product leaf3,171개의 absolute bounding box는 모든 필드가 정확히 같고 최대 차이는0이다. 기존 Frame550개의 clip과 nonempty reaction node314개의 의미 연결도 같다. reaction node는 product312개와 palette2개다.

두 실제 set은 각각 선언한 Visual12개와 정확히 같고 속성은 TEXT와 Visual뿐이다. 구성 설명과 documentation link는 desktop/mobile 실제 UI에서 모두 비어 있었다. 이 기록의 양의 구현 범위는 TEXT·선언 축·사용처다. 선언하지 않은 BOOLEAN·INSTANCE_SWAP이 없다는 음의 검사로 해당 속성의 양의 작성 기능까지 구현됐다고 주장하지 않는다. 그 기능은 NF-01 후속 제안이다.

R8의 실제 정적 prototype은14단계를 관측했다. desktop은 publichome → login → memberhome → session → review → confirmed → reschedule → confirmed-return → cancelconfirm → cancelled 경로다. mobile은 운영 화면의 세로 스크롤과 표의 가로 오른쪽 드래그·원위치 복귀를 확인했다. Figma가 인증·업무 POST를 실행한 것이 아니며 실제 Django 업무 검증은 별도다.312개 링크의 전체 GUI 실행도 아니다.

공식 Figma 앱의 version history에서 이름을 붙인0.27 기록과 저장한 R8 페이지 제목을 관찰했다. 로컬 `.fig` 백업은2,767,296바이트이며 SHA256은 요약에 있다. 독립 remote API 다운로드·암호학적 클라우드 지속성 검증은 수행하지 않았다. 전달 대상 fresh R8의 opacity override는0건이다.

## 과거 R7 전체 getter 읽기와 정상 검증

보호된 `r7-native-create.json` 영수증이 가리키는 실제 full readback은4,818개 노드,30,103,016바이트다. 원시 SHA256은 요약 JSON의 `native_r7.raw_sha256`이다. 실제 읽기에는 main24개, component set2개, instance494개, variable69개와 collection1개가 있다. instance는 화면 컨트롤492개와 palette2개로 구분한다.

정상 R7 검토의 `directions.json.native_review.report.passed`는 true다. 화면44개, prototype getter 검사312개, 복귀 getter 검사110개, 설명 보드가 연결한 target536개를 확인한다. 이 검사는 실제 native getter와 선언을 대조한 결과다. 프로토타입 UI를 재생해 전진·복귀했다는 증거, 시각·창작 품질 승인, 사람의 production admission을 뜻하지 않는다. 현재 범위는 exploratory다.

R7의494개 instance override를 집계하면 `fills`, `fontName`, `fontSize`, `letterSpacing` 각각0건이다. 이 네 필드에 대한 관측만 기록한다. 다른 override가 없거나 모든 스타일이 완전히 계승된다고 확대하지 않는다.

## 실제 프로토타입 UI와 full 진단의 관측 범위

주 세션은 CUA로 R7의 실제 정적 프로토타입을 열어 desktop의 publichome → login → publichome과 mobile의 같은 왕복을 native 링크로 수행했다. mobile 운영 dashboard에서는 표까지 세로 스크롤하고 가로 드래그해 정원·확정·대기·상태·관리 열을 확인했다. 반대 드래그로 강좌·날짜 열이 다시 보이는 것도 확인했다. 보호된 desktop/mobile home 이미지·return 기록과 mobile table left/right/restored 이미지의 SHA256을 요약 JSON에 남겼다. 이 관측은 주 세션의 실제 조작이며 문서 작성자의 새 재생이 아니다.

이는 정적 Figma 화면의 탐색·스크롤이다. 인증이나 업무 POST는 별도의 실제 Django 검증 대상이다. getter로 대조한312개 prototype 링크를 전부 GUI에서 실행한 것은 아니며 다른 링크·상태의 실제 재생은 여전히 대기다.

정상 R7 discovery의 실제 GraphPanel full 읽기 `actual-r7-panel-full-read.json`은4,818개 노드와 variable69개다. 실제 export한 `diagnostic-actual-r7-full.json`은 profile full, complete true, fields76개이며 node identity 집합이 해당 원시 읽기와 정확히 같다. 원시 식별자는 공개 요약에 넣지 않았다. 이 full 결과는 summary UI가 full과 같거나 summary 인수가 완료되었다는 증거가 아니다. 새로 완료한 표준 summary UI와 full 전환 검증은 아래 범위에 한정한다.

## 표준 summary와 full 전환·진단 다운로드

수정 후 실제 R7의 표준 discovery UI에서 width·height만 요청한 summary는4,818개 노드를 반환했다. full과 크기를 대조해 차이는0건이고 complete false이며 heavy field는 없다. `summary-native-evidence.json`은 진단의 node identity·field·omission도 해당 summary와 정확히 일치함을 기록한다. 정상 import `--apply`와 pair 경로는 이 summary를 거절했고 출력 파일이 생기지 않았으며 graph bytes는 바뀌지 않았다.

같은 패널에서 summary 뒤에 full을 읽으면 진단도 full·complete true·4,818개 노드·76개 field로 교체되었다. 전후 node·variable·collection이 정확히 같다. 이 검증은 실제 primary 페이지의 width·height summary 범위이며 다른 profile이나 전체 내용을 summary가 증명한다는 뜻이 아니다.

실제 저장한 `diagnostic-native-version-027.json`은 plugin version0.27.0을 표시한다. 읽기를 하지 않은 경우 native read는 null이고 unobserved로 남는다. 실제 브라우저에서 compiled legacy 패널도0.27.0을 표시했으며 Markdown 파일 내용과 보이는 textarea, fenced JSON과 다운로드 JSON이 각각 같았다. 과거 키보드 경로에서는 CUA clipboard API가 빈 값을 반환해 전달을 관측하지 못했다. 이후 `diagnostic-copy-retest.json`의 marker 준비 뒤 trusted click 재검사에서는 실제 클립보드2,464자가 Markdown 다운로드·보이는 내용과 같고, fenced JSON도 JSON 다운로드와 같았다. 이 최신 전달 관측은 version0.27.0에서 확인했으며 앞의 빈 관측은 과거 기록으로 남긴다.

## 원본 TEXT 속성·상호작용 후 보존·의존성 화면

`r7-actual-text-property-evidence.json`은 복사본이 아닌 원본의 같은 main을 참조하는3개 instance를 확인한다. `수업 둘러보기`, `로그인`, `나의 예약`의 TEXT property 값과 실제 characters가 서로 구분되고, 실제 main TEXT 정의·label reference가 일치한다. 원본에 새 property GUI 편집을 했다는 주장이 아니며 직접 편집 실험은 앞의 복사본 범위다.

프로토타입 상호작용 후 정상 `readDraft`를 다시 검증한 `r7-post-interaction-native-check.json`은 통과했고 같은 페이지를 유지했다. 로컬 `.fig` 백업은2,100,822바이트이며 SHA256은 요약 JSON에 있다. 이는 독립적인 클라우드 저장 확인이 아니다.

실제 native task dependency 화면에서는 현재·오래된 revision pin을 관찰했다. 실제 catalogue를 투영한 브라우저 화면은320px에서 Enter로 펼친 뒤 H3에 focus를 옮기고 같은6개 텍스트 관계를 제공했다. content/scroll width가305/305로 가로 넘침이 없고 이 폭에서는 SVG를 숨긴다.560px에서는 SVG497px가 표시되며 가로 넘침이 없다. 가짜 API 상태를 실제 native 실행 근거로 사용하지 않았다.

## 전체 검사 기록의 기준

앞선 안정 후보 로그는 Python1,107개 검사 OK·skip2, Node289개 중288개 통과·skip1·실패0이다. 이 기록을 이후 Group 통합·깨끗한 패키지 기준의 최종 전체 검사나 CI 결과로 표시하지 않는다. 최종 실행 판정과 새 검사 결과는 주 세션이 별도로 기록한다.

## 같은 패킷의 재실행

보호된 `r7-idempotent-current-review.json`의 요청부터 완료까지는14.99초이며 기존 페이지를 재사용했다. 최초 읽기와 페이지 identity 및 전체 노드 identity 집합이 같다. 새 페이지를 만들지 않았고 `r7-idempotent-native-check.json`의 순수 검사는 통과했다. 이 시간은 재실행 영수증의 경과 시간이다. 최초 생성과 동일한 작업의 성능 개선 배수로 계산하지 않는다.

## 실제 앱 컴포넌트 복사본의 편집 실험

실제 앱의 component set 하나를 CUA로 복사한 별도 실험에서 instance5개를 직접 만들었다. `component-lab-initial-read.json`과 `component-reuse-native-evidence.json`이 이 범위의 실제 근거다. 그중3개는 같은 Solid main을 참조하고 서로 다른 TEXT property·보이는 문구를 유지하며 너비는180·240·300이다.

`copied-main-color-applied.json`의 실제 적용 후 읽기에서는 복사한 main의 color 변경이 대응하는3개 instance의 글자색에 전파되었다. 레이블·TEXT property와 각 너비는 보존되었다. `copied-main-color-restored.json`에서는 시각적 원래 색을 복원했다. color는 이 편집 계약에서 글자색이며 배경색 변경으로 표시하지 않는다.

복사본의 변수 binding을 의도적으로 분리한 실험이다. 이 초기 복사본 실험 동안에는 원본 앱의 main·instance를 수정하지 않았다. 이후 archived R7의 사용자 override 검사는 아래와 같이 별도다. 색 복원은 복사본의 원래 binding 구조 전체를 복원했다는 뜻이 아니다. 이 작은 실험은 원본44개 화면의 모든 편집·override·상태를 검증한 결과가 아니다.

## 복사본 sizing과 archived R7 사용자 override

복사본에서는 한글 문구를 늘리고 FIXED 너비·HUG 높이 부모를360에서420으로 바꿨다. FILL 너비·HUG 높이 instance는340에서400으로 늘고 높이는48이며 label은 HUG/HUG를 유지했다. 같은 main·instance identity가 보존되었다. 실험 뒤5개 label·너비·높이·main·부모를 모두 복원하고 소유 wrapper를 제거했다.

이후 archived R7에서 사용자가 실제 GUI로 instance opacity를0.9로 바꾼 뒤 같은 패킷을 재실행했다. main24·set2·instance494와 전체 identity, 같은 main 및 실제 opacity override metadata를 보존했다. numeric opacity를1로 복원한 뒤 정상 verifier는 통과했지만 explicit opacity override flag는 archived R7에 남는다. fresh 전달 대상 R8의 opacity override0건과 혼동하지 않는다.

## 실제 앱·브라우저·패키지 근거

보호된 `littlehands-final-58-tests.txt`는 실제 PostgreSQL에서58개 백엔드 테스트 통과를 기록한다. `live-signup-http-evidence.json`은 격리 staging의 실제 HTTP 가입을 기록하며 역할 주입 뒤 staff·superuser가 false이고 group은0이다. 회원 예약 페이지200, 운영 접근403, 로그아웃302와 이후 보호 페이지302를 확인한다. HTTP 관측은 브라우저에서 암호를 입력했다는 주장이 아니다.

현재 [원본 캡처](captures/)는22개 상태의 desktop/mobile44개다. 주 세션은 실제 브라우저 흐름과47개 이미지의 주 검토를 보고했다. 이 문서 작성자는 그47개 이미지를 새로 전부 검토하지 않았다. 화면별 의미와 원본 측정 계약은 [화면 명세](screen-spec.md)와 [정상 디자인 경로](README.md)를 따른다. 캡처 수는 접근성 전체 인증·native 재생 성공률이 아니다.

기존 `littlehands-deployment-tests.txt`는 패키지 검사4개 통과 범위다. `backup-restore-final.json`은 별도 PostgreSQL DB로 복원한21개 테이블의 모든 행 일치를 기록한다. Docker·권한·정적 자산·복구 절차는 [앱 운영 안내](../README.md)와 [아키텍처](../ARCHITECTURE.md)의 범위를 유지한다. 이 근거는 물리 기기, 실제 공개 DNS/TLS 구성, 공개 상용 운영이나 고가용성 검증을 포함하지 않는다.

## 복사본과 임시 Django 소비자의 제한된 Graph SSOT 왕복

새 실험은 실제 앱에서 복사한 라이브러리와 같은 origin의 실제 Django 응답에 임시로 연결한 외부 CSS 소비자를 대상으로 했다. 대상은 brand·navigation·primary의 color3필드다. 원본 R7 앱의 native 페이지는 변경하지 않았다. 앱 전체44개 화면이나 영속 Graph SSOT 채택의 인수로 확대하지 않는다.

`initial-pair.json` 뒤 선택 적용에서는 primitive root3개 중2개를 적용했다. alias를 포함한 선택 manifest 행은4개이며 두 값 변경·세 번째 값 보존과 이전 graph marker 보존이 실제 범위 근거에 남아 있다. partial 결과로 pair를 시도하면 거절되었고 금지된 pair 출력도 남지 않았다. 나머지 root는 partial 후의 최신 full getter를 바탕으로 계획을 새로 만들고 CAS 적용했다. `remaining-applied.json`과 `changed-pair.json`은 그 뒤의 전체 pairing 범위다. 부분 결과나 예전 plan을 전체 완료로 취급하지 않았다.

복사본 페이지에서 실제 finite variable을 편집한 뒤 `native-import-report.json/import-report.json`의 `--apply` 결과는 applied true이며 `navigation/ink` 한 값만 가져왔다. `primaryAxisSizingMode` 등으로 추정해 임의의 width를 만들지 않았다. 실제 보고의 unsupported sizing5건은 그대로 남겼다. `reverse-native-applied.json`, `reverse-pair.json`, `reverse-web-proof.json`은 그 값이 Figma에서 graph를 거쳐 실제 웹 소비자까지 돌아온 제한된 왕복과 전체 pairing을 증명한다. 웹 proof는 해당3개 소비자 검사이며44개 화면 인수가 아니다.

`restore-native-applied.json`, `restored-pair.json`, `restored-web-proof.json`으로 원래 값과 전체 pairing을 확인했다. 최종 실험 graph bytes는 초기 graph와 정확히 같다. `overlay-restoration-evidence.json`은 임시 template source hash 복원과 외부 CSS/MJS 제거를 확인한다. `clean-live-app-proof.json`의 실제 응답은 graph attribute0개, overlay link0개이며 사진이 로드된다. 임시 소비자는 제거되었고 이 문서는 이를 출시 기능으로 표시하지 않는다. 보호된 근거의 SHA256만 요약 JSON에 기록했다.

## 아직 통과로 표시하지 않는 범위

현재 앱 `graph.json`에는 `design_system`이 없다.12개 계열과 candidate foundations는 관측 profile이며 수락된 Graph SSOT binding이 아니다. template graph SHA와 외부 CSS의 영속 SSOT 연결도 아직 없다. 위의 임시 Django 외부 CSS 실험은 제한된 범위에서 완료 후 제거되었으며 출시할 영속 기능으로 표시하지 않는다.

위에서 관측한 왕복·표 스크롤 이외의 prototype UI 재생, 창작 품질·사람의 production admission, 앱 전체의 영속 Graph SSOT 연결은 대기다. 정상 R7 full·width/height summary·진단 일치는 위의 제한된 범위에서 확인했다. Group 통합 후 전체 clean-package 검사·CI, 최종 코드 커밋·설치·릴리스와 독립 remote API 기반 클라우드 저장 확인은 별도 최종 기록이 필요하다. 물리 기기는 검증하지 않았고 공개 DNS/TLS 배포도 실행하지 않았다. 기존61개 회귀 사례의 전체 인수와 채팅 첨부 UI도 검증하지 않았다. 주 세션이 같은 소스·범위의 새 실제 근거로 인수 행렬을 갱신하기 전에는 이 목록을 통과로 바꾸지 않는다. 기존 캡처·snapshot·review·pin은 이 요약 작성으로 변경하지 않았다.

## 예약 CTA의 영속 웹 소비와 실제 Figma 왕복

2026-11-13에 기존 작은손 파일의 컴포넌트 페이지에서 등록된 개발 플러그인을 열고, Django/Gunicorn과 PostgreSQL에서 제공한 수업 상세 화면을 실제 브라우저로 읽었다. 로그인 전 예약 링크, 같은 main을 쓰는 네이티브 인스턴스 두 개, 예약 전용 색상 변수만 이번 왕복의 범위다.

| 단계 | 그래프 SHA-256 | 브라우저 계산값 | Figma에서 확인한 값 |
| --- | --- | --- | --- |
| 최초 채택 | `fcd5a360440de3e0f5c734241f94da8a292ebcd86ec967f38edaaedee45d714c` | `rgb(142, 62, 40)` | 독립 collection의 원색과 semantic alias, main 하나와 instance 두 개의 배경 연결 |
| 그래프에서 색 변경 | `979a22705467198e36df8dc8f9fbcfee4f9dabfd34ee2b3cc9a36cc707594aae` | `rgb(119, 57, 37)` | 같은 원색 ID와 alias가 새 색을 반환하고 같은 세 소비자가 이를 사용 |
| Figma에서 원색을 편집하고 역수입 | `0ad13ff5eb6b6363712694f37f8d61fd0ec42d564f334aafc6fc75f56b059830` | `rgb(142, 62, 40)` | 전체 변경 범위를 다시 읽어 dry-run 후 이전 graph SHA로 적용. CSS 재발행·collectstatic·서버 재시작 후 새 pairing 통과 |

마지막 그래프는 Figma getter가 반환한 부동소수점 원색을 보존한다. 각 관측에서 DOM의 `data-graph-sha`와 같은 그래프의 브라우저 색상, 네이티브 연결, 생성한 웹 모듈을 `graph_sync.py pair`로 대조했다. 원래 96개 노드의 ID·부모·이름·위치·치수·채움·반응은 끝까지 일치했다. 새 노드 7개에는 작업 프레임, main, 두 instance와 각 텍스트가 포함된다. 재적용 두 번 모두 같은 ID와 변경 수 0을 반환했다. 원본 캡처 44개를 사용해 재생성한 명세가 마지막 graph SHA를 가리켰다.

첫 실험에서 TEXT의 의미 키를 잘못 찾는 오류와 dynamic-page에서 동기 main getter를 호출하는 오류를 발견했다. 실제 페이지를 다시 읽고 소유 프레임과 변수만 식별한 뒤 같은 노드에서 작업을 복구했다. 변수 채택 단계에서는 점이 들어간 정본 이름을 Figma의 슬래시 그룹으로 변환하지 않아 첫 요청이 거절됐다. 이름 충돌 검사와 매핑을 고친 뒤 실제 적용을 완료했다. 세션별 원시 Figma·브라우저 기록은 비공개 작업 폴더에 보존한다.

실제 Figma 환경은 무료 표시가 있는 초안 파일의 기존 페이지였다. 정확히 3페이지인 Starter 팀 파일과 다른 계정의 보기 권한 시험은 별도 환경이 필요하다. 실물 iOS·Android 기기 검사는 수행하지 않았다.

최종 인계 팩을 대조하면서 예약 버튼의 두 인스턴스에 같은 임시 문구가 남은 것을 발견했다. 실제 Django 템플릿의 두 분기를 읽어 기존 노드에서 회원 버튼은 **예약 내용 확인**, 비회원 링크는 **로그인하고 예약하기**로 교정했다. 사용자 문구는 충돌로 보존한다. 실제 Figma에서 두 건을 수정하고 같은 요청을 다시 적용해 변경 수 0을 확인했다. 최신 전체 읽기·정본·브라우저 증명·정책 영향 보고서로 컴포넌트 범위 인계 팩을 생성했다. 비회원 문구는 실제 브라우저에서도 확인했고 회원 문구는 템플릿과 native getter를 비교했다.
