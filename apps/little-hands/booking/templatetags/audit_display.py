"""Present stored audit facts without consulting mutable related objects."""
import json
import re
from datetime import date, datetime

from django import template

register = template.Library()

ACTIONS = {
    'reserve': '예약 신청',
    'promote': '대기 예약 확정',
    'cancel': '예약 취소',
    'reschedule': '예약 일정 변경',
    'session_cancel_booking': '수업 취소에 따른 예약 취소',
    'session_create': '수업 일정 등록',
    'session_edit': '수업 일정 수정',
    'session_cancel': '수업 취소',
}
FIELDS = {
    'status': '상태', 'quantity': '참석 인원', 'session_id': '회차',
    'revision': '정보 버전', 'unit_price_krw': '예약 당시 1인 수업료',
    'course': '강좌', 'course_id': '강좌 ID', 'room': '공간', 'room_id': '공간 ID',
    'starts_at': '시작 일시', 'ends_at': '종료 일시', 'capacity': '정원',
    'price_krw': '1인 수업료', 'cancellation_cutoff_minutes': '취소·변경 마감',
    'reason': '취소 사유', 'booking_id': '예약 ID', 'public_id': '공개 예약 번호',
    'consented_session_revision': '동의한 회차 버전',
}
STATUSES = {'confirmed': '예약 확정', 'waitlisted': '대기 중', 'cancelled': '취소됨', 'scheduled': '진행 예정'}
MISSING = object()


@register.filter
def audit_action(action):
    return ACTIONS.get(action, f'알 수 없는 행동 ({action})')


def _value(key, value):
    if value is MISSING:
        return '기록 없음'
    if value is None:
        return '값 없음 (null)'
    if value == '':
        return '빈 문자열'
    if isinstance(value, bool):
        return '예 (true)' if value else '아니요 (false)'
    if key == 'status':
        return STATUSES.get(str(value), f'알 수 없는 상태 ({value})')
    integer = re.fullmatch(r'-?[0-9]+', str(value))
    if integer and key in {'quantity', 'capacity', 'unit_price_krw', 'price_krw', 'cancellation_cutoff_minutes'}:
        number = f'{int(value):,}'
        if key in {'unit_price_krw', 'price_krw'}:
            return f'{number}원'
        if key == 'cancellation_cutoff_minutes':
            return f'시작 {number}분 전'
        return f'{number}명'
    if key in {'session_id', 'booking_id', 'course_id', 'room_id'}:
        return f'{FIELDS[key].removesuffix(" ID")} #{value}'
    if key in {'starts_at', 'ends_at'} and isinstance(value, str):
        try:
            if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
                day = date.fromisoformat(value)
                return f'{day.year}년 {day.month}월 {day.day}일'
            moment = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            clock = moment.strftime('%H:%M:%S')
            if moment.microsecond:
                clock += f'.{moment.microsecond:06d}'
            zone = moment.strftime('%z')
            if zone:
                zone = f' (UTC{zone[:3]}:{zone[3:5]}' + (f':{zone[5:]}' if len(zone) > 5 else '') + ')'
            return f'{moment.year}년 {moment.month}월 {moment.day}일 {clock}{zone}'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@register.filter
def audit_changes(event):
    before, after = event.before, event.after
    if not isinstance(before, dict) or not isinstance(after, dict):
        return [{'label': '기록 전체', 'before': _value('', before), 'after': _value('', after)}]
    return [
        {'label': FIELDS.get(key, f'알 수 없는 항목 ({key})'),
         'before': _value(key, before.get(key, MISSING)), 'after': _value(key, after.get(key, MISSING))}
        for key in dict.fromkeys([*before, *after])
    ]
