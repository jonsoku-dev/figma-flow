# 작은손 커피공방 UI 계약

## 제품과 시각 방향

회원은 DB의 수업을 고르고 Django 서버 폼으로 신청·대기·취소·변경한다. 운영자는 같은 DB의 실제 정원·예약 명단·변경 기록을 관리한다. 모드는 Operate다. 종이색 바탕, 따뜻한 크림 면, 녹슨 적갈색 행동, 짙은 녹색 확정 상태를 사용한다. 차분한 공방의 인상을 주되 작업을 방해하는 장식은 두지 않는다. 회원 진입 화면의 큰 한국어 제목과 붉은 바탕 위 흰 커피잔 사진이 시각 중심이며, 운영 화면은 표와 수량이 중심이다. 가짜 주소·운영 시간·평판·통계는 만들지 않는다.

색·간격·서체는 `tokens.json`과 `static/littlehands/app.css`가 일치한다. Hahmlet의 본문 Regular 400, 제목 Bold 700을 로컬 WOFF2로 제공한다. 사진·글꼴 출처는 `static/littlehands/sources.json`, 글꼴 라이선스는 `static/littlehands/fonts/OFL.txt`다. 사진은 붉은 바탕 위 흰 잔과 긴 그림자이며 나무·원두·실제 공방 내부로 묘사하지 않는다. 사진 모서리는 0이다.

## 서버와 화면

명명된 URL과 모델·폼 계약은 `../ARCHITECTURE.md`를 따른다. 모든 예약 쓰기는 서버 CSRF 폼이다. JS는 제출 중 상태 문구만 노출하며 예약 결과·좌석·인증·영속 데이터를 만들지 않는다. JS를 끄더라도 모든 핵심 흐름이 일반 GET/POST로 작동한다. 암호는 Django PasswordInput으로 렌더링하며 값을 재주입하지 않는다. CSP 때문에 인라인 스크립트·스타일·이벤트 핸들러가 없다.

- `base.html`: 회원 메뉴, 권한 기반 운영 메뉴, `notifications_unread` 건수, POST 로그아웃. `service_staging`일 때만 footer 환경 표시.
- `booking/session_list.html`: `sessions` Page와 `page_obj`, 실제 가격/정원/잔여석. 빈 일정과 페이지 이동.
- `booking/session_detail.html`: `session`, `reserve_form`, `remaining`, `waitlist_count`. 대기 동의는 실제 Django checkbox, 매진은 설명과 대기 선택을 제공한다.
- `booking/reserve_review.html`: 검증된 `reserve_form` 각 필드의 `as_hidden`, 인원·총액, 최종 신청과 다시 선택. 서버가 신청 상태를 결정한다.
- `booking/booking_detail.html`: `booking`, `can_cancel`, `can_reschedule`; confirmed/waitlisted/cancelled를 문구로 구분한다. `booking.total_price`는 예약 당시 단가를 사용한다.
- `booking/cancel.html`: `action_form` hidden revision/request ID, 취소 확정과 유지.
- `booking/reschedule.html`: `form`의 서버 생성 회차 선택, `sessions`가 없을 때 유지 안내. 새 자리를 얻지 못하면 기존 예약 유지라는 서비스 계약을 설명한다.
- `booking/conflict.html`: 실제 409/400 메시지와 폼 오류, 서버가 reverse로 만든 `recovery_url`. POST 재전송 버튼은 없다.
- `booking/notifications.html`: `notifications` Page, 각 알림의 `request_id` UUID. 서로 다른 알림에 동일 멱등 키를 재사용하지 않는다. 외부 메일 발송을 암시하지 않는다.
- `staff/dashboard.html`: stats의 `session_count`, `capacity`, `confirmed_count`, `waitlisted_count`는 앞으로 예정된 수업/인원이다. daily_counts의 `date`, `count`, `bar_width`는 최근 7일 생성된 예약 건수이며 취소 이후에도 생성 건수에 포함된다. SVG 막대는 0..100의 서버 집계 숫자이고 날짜·건수 텍스트가 같이 있다.
- `staff/session_form.html`: 실제 SessionForm. 예약 이력이 있는 회차의 시간·공간·강좌 불변 및 새 가격 적용 범위를 설명한다.
- `staff/session_detail.html`: confirmed/waitlisted의 별도 Page 명단, `cancel_form`, 취소 사유 필수. 명단에는 소유자 회원명·인원·예약 당시 단가·예약 번호만 노출한다.
- `staff/audit.html`: `events` Page의 실제 actor/action/before/after. 수정 컨트롤이 없는 읽기 화면.
- `403.html`, `404.html`, `500.html`: 복구 링크가 있는 실제 오류 화면.

## 컴포넌트·접근성·측정

재사용 컴포넌트는 서버 include다: form, busy, status, booking_facts, staff_nav, pagination, roster_table, session_table. form은 label-for, Django 오류 목록·aria-invalid/aria-describedby, 상단 오류 요약의 필드 이동 링크를 사용한다. 도움말의 서버 HTML은 Django/자체 폼 선언만 허용하며 사용자 입력은 escape한다. `safe`는 Django 폼 help_text에만 쓴다.

모든 주요 텍스트/표면에는 `data-native-key`와 `data-native-type=text|surface|image|control`이 있고 실행 가능한 링크/버튼에는 `data-action`이 있다. 반복 모델 행의 키에는 DB PK 또는 공개 예약 UUID가 들어간다. 부모가 실제 서버 DOM을 측정해 네이티브를 만들며 hidden form fields는 디자인 레이어로 취급하지 않는다. 이 속성은 레이아웃 실측이나 Figma 검증 결과를 보장하지 않는다. 실제 GET/POST 상태를 각각 캡처해야 한다.

44px 이상의 링크·행동 타깃, 48px 기본 폼/버튼, 본문 건너뛰기, 보이는 3px focus, 문구를 동반한 상태, 표 caption/th scope, 실제 날짜와 건수 텍스트를 제공한다. 760px에서 hero/split을 한 열로 바꾸며 표는 가로 스크롤로 보존한다. 359px 이하에서는 16px 여백과 단일 열 일정 행을 사용한다. 시스템 reduced-motion에서 smooth scroll을 끈다. 오류·빈 목록·매진·대기·취소·변경 불가·다른 revision의 복구를 화면으로 제공한다.

실제 320/390/1200px 브라우저, 키보드 동작, 색 대비와 네이티브 Figma 검수는 부모 통합 세션에서 수행한다. 이 문서는 그 실행을 대신하지 않는다.
