# 작은손 커피공방 운영 앱

이 앱은 회원과 운영자가 같은 예약 데이터를 사용하는 독립 Django 서비스다. Figma Flow 자체의 의존성과 분리한다. 현장 결제 수업을 다루며 온라인 결제나 외부 메시지 발송을 실행하지 않는다. 운영 DB와 동일한 PostgreSQL 엔진에 격리된 검증 데이터를 넣어 인수한다.

## 정본과 역할

- `booking/models.py`, migrations는 데이터와 DB 제약을 소유한다.
- `booking/services.py`는 예약·취소·변경·대기 승급·정원 변경의 유일한 쓰기 경로다.
- Django 세션·CSRF·암호 해시·그룹 권한을 사용한다. 회원은 자기 예약만 조회·변경한다. 운영자는 전용 운영 화면을 쓴다.
- Django admin에서 예약·회차·대기열·감사 기록을 직접 변경하는 경로는 허용하지 않는다.
- `templates/`와 `static/`은 실제 서버 응답을 표시한다. 가짜 성공 상태나 브라우저 저장소를 예약 정본으로 사용하지 않는다.
- `design/graph.json`은 요구사항·화면·행동·코드·증거 관계를 소유한다. Figma는 편집 가능한 디자인·프로토타입이며 서버 트랜잭션을 실행하는 것으로 표시하지 않는다.

## 데이터 계약

| 모델 | 주요 필드 |
| --- | --- |
| Course | title, slug, summary, description, duration_minutes, price_krw, active, cancellation_cutoff_minutes |
| Room | name, capacity |
| ClassSession | course, room, starts_at, ends_at, capacity, price_krw, cancellation_cutoff_minutes, revision, status scheduled/cancelled |
| Booking | public_id UUID, member, session, quantity, status confirmed/waitlisted/cancelled, revision, queued_at, unit_price_krw |
| Operation | actor, request_id UUID, action, fingerprint, result. actor+request_id unique |
| AuditEvent | actor, action, booking/session identity, safe before/after facts, created_at. 불변 |
| Notification | member, event_key, title, message, booking identity, read_at. member+event_key unique |

회차 revision은 시간·장소·정원 등 운영 조건이 바뀔 때 증가한다. 좌석 수 변동만으로 단순한 대기 동의를 무효화하지 않는다. 예약 revision은 상태·수량·회차 변경마다 증가한다. 가격은 예약 시 저장하고 이후 강좌 가격 변경으로 과거 금액을 바꾸지 않는다.

`ClassSession.cancellation_cutoff_minutes`는 회차 생성 시 강좌의 취소 마감을 복사한 값이다. `booking/migrations/0003_session_cancellation_policy.py`는 기존 회차에 당시 강좌 값을 채운다. 이후 강좌 정책 변경은 기존 회차에 소급되지 않으며, 화면과 서비스는 회차 값을 사용한다.

`Notification.request_id`는 DB 필드가 아니다. `notifications` 뷰가 표시할 각 객체에 UUID를 붙이고 템플릿의 hidden input으로 전달한다. `notification_read`는 `RequestForm` 검증 후 `services.read_notification`에 이 값을 넘기며, `Operation`이 읽음 처리의 멱등 결과를 보존한다.

## 쓰기 규칙

1. 회원·권한·폼을 검증한다. 수량은1~8명이며 회차 정원을 넘을 수 없다.
2. `request_id`와 정규화한 행동·값의 fingerprint를 검증한다. 같은 키·같은 요청은 같은 결과를 돌려주고 다른 내용은409다.
3. 필요한 회차를 ID 오름차순으로 잠근 뒤 관련 예약을 잠근다. 잠금 전 조회한 예약의 회차·revision이 바뀌었으면 충돌로 중단한다.
4. 정원과 취소·변경 정책을 검증한다. 어떤 검증 실패도 기존 예약·좌석·대기열·감사 상태를 부분 변경하지 않는다.
5. 예약·감사·알림·멱등 결과를 같은 트랜잭션으로 기록한다.

잔여석이 없으면 명시적으로 대기 등록에 동의한 회원만 대기열에 들어간다. 대기자가 있으면 신규 신청이 먼저 자리를 차지하지 않는다. 취소 시 FIFO의 첫 그룹이 들어갈 수 있을 때만 승급하고, 큰 그룹을 건너뛰어 뒤 그룹을 승급하지 않는다. 일정 변경은 같은 강좌의 다른 회차를 대상으로 하며 목적지 확보 실패 시 원래 예약을 보존한다. 계정 하나가 여러 참석자를 위해 예약할 수 있으므로 다른 회차의 시간 중복만으로 계정을 차단하지 않는다.

같은 Room의 활성 회차가 겹치지 않도록 PostgreSQL 범위 exclusion constraint를 사용한다. 예약·대기 중복과 수량·시간·정원의 기본 불변식도 DB 제약으로 보강한다.

## 뷰·템플릿 계약

모든 POST는 CSRF 검사를 받는다. 예약·운영 회차·알림 상태 변경 POST는 `request_id`로 멱등 처리한다. 예약 변경·취소는 예약의 `expected_revision`, 수업 예약은 회차 운영 조건의 `expected_revision`을 받는다. `RescheduleForm.target_session_id`는 `PaintedRadioSelect`로 렌더하며 option 값은 `<회차 ID>:<회차 revision>`이다. 폼은 이를 정수 `target_session_id`와 `target_revision`으로 분리하고 서비스가 실제 대상·revision·권한·정원을 검사한다. 이미 바뀐 대상도 같은 POST의 멱등 재생을 처리할 수 있도록 선택값의 형식과 범위를 검증하며 현재 표시 목록만으로 거절하지 않는다. 정상 변경은302로 상세 화면에 이동한다. 충돌은409, 다른 회원의 예약은404, 운영자 권한 없음은403이다.

취소·변경 불가 예약의 cancel/reschedule GET은 상세로 돌려보낸다. POST에는 이 GET 전용 제한을 적용하지 않아 이미 성공한 요청의 멱등 재생을 서비스가 처리할 수 있다. 새 요청의 정책·revision 검사는 서비스에 남는다.

| URL 이름 | 메서드·경로 | 템플릿·context |
| --- | --- | --- |
| session_list | GET `/` | `booking/session_list.html`: sessions, courses |
| session_detail | GET `/sessions/<int:pk>/` | `booking/session_detail.html`: session, reserve_form, remaining, waitlist_count |
| reserve_preview | POST `/sessions/<int:pk>/review/` | `booking/reserve_review.html`: session, reserve_form, quantity, total_price |
| reserve | POST `/sessions/<int:pk>/reserve/` | 검증 후 booking_detail로 이동 |
| my_bookings | GET `/bookings/` | `booking/my_bookings.html`: bookings |
| booking_detail | GET `/bookings/<uuid:public_id>/` | `booking/booking_detail.html`: booking, can_cancel, can_reschedule |
| cancel | GET/POST `/bookings/<uuid:public_id>/cancel/` | `booking/cancel.html`: booking, action_form |
| reschedule | GET/POST `/bookings/<uuid:public_id>/reschedule/` | `booking/reschedule.html`: booking, form, sessions |
| notifications | GET `/notifications/` | `booking/notifications.html`: notifications, page_obj, 각 객체의 임시 request_id |
| notification_read | POST `/notifications/<int:pk>/read/` | 자신의 알림만 읽음 처리 |
| staff_dashboard | GET `/staff/` | `staff/dashboard.html`: sessions, stats, daily_counts |
| staff_sessions | GET `/staff/sessions/` | `staff/session_list.html`: sessions |
| staff_session_create | GET/POST `/staff/sessions/new/` | `staff/session_form.html`: form |
| staff_session_edit | GET/POST `/staff/sessions/<int:pk>/edit/` | `staff/session_form.html`: form, session |
| staff_session_detail | GET `/staff/sessions/<int:pk>/` | `staff/session_detail.html`: session, confirmed, waitlisted |
| staff_session_cancel | POST `/staff/sessions/<int:pk>/cancel/` | cancel form, expected_revision, reason |
| staff_audit | GET `/staff/audit/` | `staff/audit.html`: events, page_obj |
| login/logout/signup | `/accounts/login/`, `/accounts/logout/`, `/accounts/signup/` | `registration/login.html`, `registration/signup.html` |
| health | GET `/health/` | 실행·DB 연결 상태만 반환. 비밀·구성값을 반환하지 않음 |

폼은 Django 필드의 렌더링·검증을 사용하고 입력값·오류는 템플릿에서 escape한다. `form.quantity`, `form.allow_waitlist`와 숨김 request_id/expected_revision을 재구현하지 않는다. 백엔드와 UI의 context 변경은 이 표를 갱신해 공유한다.

## 운영과 인프라

운영은 HTTPS 종단 안에서 Gunicorn과 PostgreSQL을 사용한다. Django debug, wildcard hosts, 고정 secret, 기본 관리자 암호는 사용하지 않는다. 실행 DB role은 테이블 CRUD만 허용하고 migration role을 분리한다. Argon2·로그인 시도 제한·엄격한 CSP·cookie·CSRF·권한 검사를 적용한다.

초기 DB는 고객·관리자·가상의 예약을 만들지 않는다. 운영자가 자신의 비밀값과 초기 관리자를 준비한다. 검증용 seed는 staging/development에 한정하며 production에서는 거절한다. 실제 배포 대상이 지정되지 않았으므로 실도메인 공개·과금·외부 메일 발송은 이 작업에서 실행하지 않는다.

PostgreSQL dump를 별도 DB에 실제로 복원하고 예약·감사의 불변식을 다시 확인한다. 운영자는 배포 대상의 TLS·관측·백업 보존 기간과 복구 절차를 구성한다.
