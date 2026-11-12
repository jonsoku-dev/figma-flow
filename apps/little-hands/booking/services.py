"""Transactional writes. Lock session IDs in ascending order before booking rows."""
import hashlib
import json
import uuid
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from .models import AuditEvent, Booking, ClassSession, Course, Notification, Operation, Room


class BookingError(Exception):
    def __init__(self, message, status=409):
        self.message = message
        self.status = status
        super().__init__(message)


def require_operator(actor):
    if not actor.is_active or not actor.has_perm('booking.manage_operations'):
        raise PermissionDenied('운영 권한이 필요합니다.')


def _operate(actor, request_id, action, payload, perform):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    request_id = uuid.UUID(str(request_id))
    fingerprint = hashlib.sha256(json.dumps({'action': action, **payload}, sort_keys=True, default=str).encode()).hexdigest()
    lock_key = int.from_bytes(hashlib.sha256(f'{actor.pk}:{request_id}'.encode()).digest()[:8], 'big', signed=True)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_key])
        previous = Operation.objects.filter(actor=actor, request_id=request_id).first()
        if previous:
            if previous.fingerprint != fingerprint:
                raise BookingError('이미 사용한 요청 번호입니다. 화면을 새로 열어 주세요.')
            return previous.result
        result = perform()
        Operation.objects.create(actor=actor, request_id=request_id, action=action, fingerprint=fingerprint, result=result)
        return result


def _sessions(ids):
    sessions = {s.pk: s for s in ClassSession.objects.select_for_update(of=('self',)).select_related('course', 'room').filter(pk__in=ids).order_by('pk')}
    if len(sessions) != len(set(ids)):
        raise BookingError('회차를 찾을 수 없습니다.', 404)
    return sessions


def _remaining(session):
    used = Booking.objects.filter(session=session, status=Booking.Status.CONFIRMED).aggregate(total=Sum('quantity'))['total'] or 0
    return session.capacity - used


def _revision(actual, expected):
    if actual != expected:
        raise BookingError('다른 변경이 반영되었습니다. 최신 내용을 확인한 뒤 다시 시도해 주세요.')


def _available(session):
    if session.status != ClassSession.Status.SCHEDULED or not session.course.active or session.starts_at <= timezone.now():
        raise BookingError('이 회차는 신청할 수 없습니다.')


def _policy(booking, session):
    if booking.status == Booking.Status.CANCELLED:
        raise BookingError('이미 취소된 예약입니다.')
    if session.starts_at - timezone.now() <= timedelta(minutes=session.cancellation_cutoff_minutes):
        raise BookingError('취소·변경 마감 시간이 지났습니다.')


def _facts(booking):
    return {'status': booking.status, 'quantity': booking.quantity, 'session_id': booking.session_id,
            'revision': booking.revision, 'unit_price_krw': booking.unit_price_krw}


def _session_label(session):
    return f'{timezone.localtime(session.starts_at):%Y.%m.%d %H:%M}~{timezone.localtime(session.ends_at):%H:%M} · {session.room.name}'


def _record(actor, action, booking, before=None, message=None, source_session=None):
    AuditEvent.objects.create(actor=actor, action=action, booking=booking, session_id=booking.session_id, before=before or {}, after=_facts(booking))
    confirmed = booking.status == Booking.Status.CONFIRMED
    titles = {
        'reserve': '예약 확정' if confirmed else '대기 신청 접수',
        'promote': '대기 예약 확정',
        'cancel': '예약 취소',
        'reschedule': '일정 변경 완료',
        'session_cancel_booking': '수업 운영 취소',
    }
    details = f'{booking.session.course.title} · {booking.quantity}명'
    when = _session_label(booking.session)
    if action == 'reschedule':
        body = f'{details} · {_session_label(source_session)} → {when}. 일정을 변경했습니다.'
    else:
        explanations = {
            'reserve': '예약이 확정되었습니다.' if confirmed else '대기 신청이 접수되었습니다. 아직 예약 확정 상태가 아닙니다.',
            'promote': '대기 순서에 따라 예약이 확정되었습니다.',
            'cancel': '예약을 취소했습니다.',
            'session_cancel_booking': '운영 사유로 수업이 취소되었습니다.',
        }
        body = f'{details} · {when}. {message or explanations[action]}'
    Notification.objects.get_or_create(member=booking.member, event_key=f'booking:{booking.pk}:{booking.revision}:{action}', defaults={
        'booking': booking, 'title': titles[action], 'message': body,
    })


def _promote(actor, session):
    if session.status != ClassSession.Status.SCHEDULED or session.starts_at <= timezone.now():
        return
    remaining = _remaining(session)
    for booking in Booking.objects.select_for_update().filter(session=session, status=Booking.Status.WAITLISTED).order_by('queued_at', 'pk'):
        if booking.quantity > remaining:
            break
        before = _facts(booking)
        booking.status = Booking.Status.CONFIRMED
        booking.revision += 1
        booking.save(update_fields=['status', 'revision', 'updated_at'])
        remaining -= booking.quantity
        _record(actor, 'promote', booking, before)


def reserve(*, actor, session_id, quantity, allow_waitlist, expected_revision, request_id):
    def perform():
        session = _sessions([session_id])[session_id]
        _available(session)
        _revision(session.revision, expected_revision)
        if not 1 <= quantity <= min(8, session.capacity):
            raise BookingError('신청 인원은 회차 정원 이내의 1~8명이어야 합니다.', 400)
        if Booking.objects.filter(member=actor, session=session, status__in=['confirmed', 'waitlisted']).exists():
            raise BookingError('이미 이 회차에 신청한 예약이 있습니다.')
        _promote(actor, session)
        queued = Booking.objects.filter(session=session, status='waitlisted').exists()
        status = Booking.Status.CONFIRMED if not queued and _remaining(session) >= quantity else Booking.Status.WAITLISTED
        if status == Booking.Status.WAITLISTED and not allow_waitlist:
            raise BookingError('바로 확정할 수 없습니다. 대기 신청에 동의하거나 다른 회차를 선택해 주세요.')
        booking = Booking.objects.create(member=actor, session=session, quantity=quantity, status=status,
            unit_price_krw=session.price_krw, consented_session_revision=session.revision)
        _record(actor, 'reserve', booking)
        return {'booking_id': str(booking.public_id), 'status': status}
    return _operate(actor, request_id, 'reserve', {'session_id': session_id, 'quantity': quantity,
        'allow_waitlist': allow_waitlist, 'expected_revision': expected_revision}, perform)


def _snapshot(actor, public_id):
    try:
        return Booking.objects.only('pk', 'session_id', 'revision').get(public_id=public_id, member=actor)
    except Booking.DoesNotExist:
        raise BookingError('예약을 찾을 수 없습니다.', 404)


def cancel(*, actor, public_id, expected_revision, request_id):
    def perform():
        snapshot = _snapshot(actor, public_id)
        session = _sessions([snapshot.session_id])[snapshot.session_id]
        booking = Booking.objects.select_for_update().get(pk=snapshot.pk)
        if booking.session_id != snapshot.session_id or booking.revision != snapshot.revision:
            raise BookingError('예약이 변경되었습니다. 다시 확인해 주세요.')
        _revision(booking.revision, expected_revision)
        _policy(booking, session)
        before = _facts(booking)
        booking.status = Booking.Status.CANCELLED
        booking.revision += 1
        booking.save(update_fields=['status', 'revision', 'updated_at'])
        _record(actor, 'cancel', booking, before)
        _promote(actor, session)
        return {'booking_id': str(booking.public_id), 'status': booking.status}
    return _operate(actor, request_id, 'cancel', {'public_id': str(public_id), 'expected_revision': expected_revision}, perform)


def reschedule(*, actor, public_id, target_session_id, target_revision, expected_revision, request_id):
    def perform():
        snapshot = _snapshot(actor, public_id)
        sessions = _sessions([snapshot.session_id, target_session_id])
        source, target = sessions[snapshot.session_id], sessions[target_session_id]
        booking = Booking.objects.select_for_update().get(pk=snapshot.pk)
        if booking.session_id != snapshot.session_id or booking.revision != snapshot.revision:
            raise BookingError('예약이 변경되었습니다. 다시 확인해 주세요.')
        _revision(booking.revision, expected_revision)
        _policy(booking, source)
        _available(target)
        _revision(target.revision, target_revision)
        if source.pk == target.pk or source.course_id != target.course_id:
            raise BookingError('같은 강좌의 다른 회차를 선택해 주세요.', 400)
        if Booking.objects.filter(member=actor, session=target, status__in=['confirmed', 'waitlisted']).exists():
            raise BookingError('목적 회차에 이미 신청한 예약이 있습니다.')
        _promote(actor, target)
        if Booking.objects.filter(session=target, status='waitlisted').exists() or _remaining(target) < booking.quantity:
            raise BookingError('목적 회차에 확정 가능한 좌석이 부족합니다. 기존 예약은 유지됩니다.')
        before = _facts(booking)
        booking.session = target
        booking.status = Booking.Status.CONFIRMED
        booking.consented_session_revision = target.revision
        booking.revision += 1
        booking.save(update_fields=['session', 'status', 'consented_session_revision', 'revision', 'updated_at'])
        _record(actor, 'reschedule', booking, before, source_session=source)
        _promote(actor, source)
        return {'booking_id': str(booking.public_id), 'status': booking.status}
    return _operate(actor, request_id, 'reschedule', {'public_id': str(public_id), 'target_session_id': target_session_id, 'target_revision': target_revision,
        'expected_revision': expected_revision}, perform)


def save_session(*, actor, values, request_id, session_id=None, expected_revision=None):
    require_operator(actor)
    def perform():
        if set(values) != {'course', 'room', 'starts_at', 'ends_at', 'capacity', 'price_krw'}:
            raise BookingError('수정 가능한 회차 항목을 확인해 주세요.', 400)
        session = _sessions([session_id])[session_id] if session_id else ClassSession()
        if session_id:
            _revision(session.revision, expected_revision)
            if session.status != 'scheduled' or session.starts_at <= timezone.now():
                raise BookingError('취소되었거나 시작한 회차는 수정할 수 없습니다.')
        if values['starts_at'] <= timezone.now() or values['ends_at'] <= values['starts_at']:
            raise BookingError('앞으로 시작하는 올바른 시간을 입력해 주세요.', 400)
        room = Room.objects.get(pk=values['room'].pk)
        if not 1 <= values['capacity'] <= room.capacity:
            raise BookingError('회차 정원은 공간 정원 이내여야 합니다.', 400)
        if session_id and _remaining(session) + values['capacity'] - session.capacity < 0:
            raise BookingError('확정 인원보다 정원을 줄일 수 없습니다.')
        if session_id:
            largest_waiting_group = Booking.objects.filter(session=session, status='waitlisted').aggregate(largest=Max('quantity'))['largest'] or 0
            if values['capacity'] < largest_waiting_group:
                raise BookingError('대기 중인 그룹 인원보다 정원을 줄일 수 없습니다.')
        if session_id and values['course'].pk != session.course_id:
            raise BookingError('생성된 회차의 강좌는 바꿀 수 없습니다.')
        if session_id and session.has_booking_history:
            for key in ['course', 'room', 'starts_at', 'ends_at']:
                if getattr(session, key) != values[key]:
                    raise BookingError('예약 이력이 있는 회차의 시간·공간·강좌는 변경할 수 없습니다. 회차를 취소한 뒤 새로 만들어 주세요.')
        if session_id and all(getattr(session, key) == value for key, value in values.items()):
            return {'session_id': session.pk}
        before = {key: str(getattr(session, key, '')) for key in values}
        for key, value in values.items():
            setattr(session, key, value)
        if not session_id:
            session.cancellation_cutoff_minutes = Course.objects.get(pk=session.course_id).cancellation_cutoff_minutes
        if session_id:
            session.revision += 1
        try:
            with transaction.atomic():
                session.full_clean(validate_constraints=False)
                session.save()
        except IntegrityError:
            raise BookingError('해당 공간의 다른 회차와 시간이 겹칩니다.')
        except ValidationError:
            raise BookingError('회차 입력값을 확인해 주세요.', 400)
        AuditEvent.objects.create(actor=actor, action='session_edit' if session_id else 'session_create', session=session,
            before=before, after={key: str(getattr(session, key)) for key in values} | {'revision': session.revision,
                'cancellation_cutoff_minutes': session.cancellation_cutoff_minutes})
        if session_id:
            for booking in Booking.objects.select_for_update().filter(session=session, status__in=['confirmed', 'waitlisted']).order_by('pk'):
                Notification.objects.get_or_create(member=booking.member, event_key=f'session:{session.pk}:{session.revision}:booking:{booking.pk}', defaults={
                    'booking': booking, 'title': '신청 회차 정보 변경',
                    'message': '신청한 회차의 정원 또는 신규 참가비가 변경되었습니다. 기존 예약의 참가비는 신청 당시 금액으로 유지됩니다.',
                })
            _promote(actor, session)
        return {'session_id': session.pk}
    return _operate(actor, request_id, 'save_session', {'session_id': session_id, 'expected_revision': expected_revision,
        'values': {key: getattr(value, 'pk', value) for key, value in values.items()}}, perform)


def cancel_session(*, actor, session_id, expected_revision, request_id, reason):
    require_operator(actor)
    def perform():
        session = _sessions([session_id])[session_id]
        _revision(session.revision, expected_revision)
        if session.status == 'cancelled' or not reason.strip():
            raise BookingError('취소 사유를 입력하고 회차 상태를 확인해 주세요.', 400)
        session.status = 'cancelled'
        session.revision += 1
        session.save(update_fields=['status', 'revision'])
        for booking in Booking.objects.select_for_update().filter(session=session, status__in=['confirmed', 'waitlisted']).order_by('pk'):
            before = _facts(booking)
            booking.status = 'cancelled'
            booking.revision += 1
            booking.save(update_fields=['status', 'revision', 'updated_at'])
            _record(actor, 'session_cancel_booking', booking, before, f'운영 사유로 수업이 취소되었습니다. {reason}')
        AuditEvent.objects.create(actor=actor, action='session_cancel', session=session,
            before={'status': 'scheduled'}, after={'status': 'cancelled', 'reason': reason})
        return {'session_id': session.pk}
    return _operate(actor, request_id, 'cancel_session', {'session_id': session_id, 'expected_revision': expected_revision, 'reason': reason}, perform)


def read_notification(*, actor, notification_id, request_id):
    def perform():
        notification = Notification.objects.select_for_update().filter(pk=notification_id, member=actor).first()
        if not notification:
            raise BookingError('알림을 찾을 수 없습니다.', 404)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
        return {'notification_id': notification.pk}
    return _operate(actor, request_id, 'notification_read', {'notification_id': notification_id}, perform)
