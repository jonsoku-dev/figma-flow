from types import SimpleNamespace

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.utils.safestring import SafeData

from booking.templatetags.audit_display import audit_action, audit_changes


class AuditDisplayTests(SimpleTestCase):
    def rows(self, before, after):
        return audit_changes(SimpleNamespace(before=before, after=after))

    def test_actions_and_actual_stored_values(self):
        self.assertEqual(audit_action('session_cancel_booking'), '수업 취소에 따른 예약 취소')
        rows = self.rows({'status': 'waitlisted', 'quantity': 2, 'session_id': 3, 'revision': 1},
                         {'status': 'confirmed', 'quantity': 2, 'session_id': 4, 'revision': 2, 'unit_price_krw': 45000})
        self.assertEqual(rows, [
            {'label': '상태', 'before': '대기 중', 'after': '예약 확정'},
            {'label': '참석 인원', 'before': '2명', 'after': '2명'},
            {'label': '회차', 'before': '회차 #3', 'after': '회차 #4'},
            {'label': '정보 버전', 'before': '1', 'after': '2'},
            {'label': '예약 당시 1인 수업료', 'before': '기록 없음', 'after': '45,000원'},
        ])

    def test_session_strings_dates_cutoff_and_reason(self):
        rows = self.rows({}, {'price_krw': '120000', 'capacity': '8', 'starts_at': '2026-11-13 09:30:00+09:00',
                              'ends_at': '2026-11-13T11:00:00.123456Z', 'cancellation_cutoff_minutes': 120,
                              'reason': '공간 정비', 'room': '기록 당시 공간'})
        self.assertEqual([row['after'] for row in rows], [
            '120,000원', '8명', '2026년 11월 13일 09:30:00 (UTC+09:00)',
            '2026년 11월 13일 11:00:00.123456 (UTC+00:00)', '시작 120분 전', '공간 정비', '기록 당시 공간',
        ])

    def test_missing_null_empty_zero_and_unknown_are_distinct(self):
        rows = self.rows({'reason': None, 'quantity': 0, 'old_key': {'html': '<script>'}},
                         {'reason': '', 'quantity': 0, 'new_key': False, 'status': 'future_status'})
        self.assertEqual(rows[0], {'label': '취소 사유', 'before': '값 없음 (null)', 'after': '빈 문자열'})
        self.assertEqual(rows[1]['after'], '0명')
        self.assertEqual(rows[2], {'label': '알 수 없는 항목 (old_key)', 'before': '{"html": "<script>"}', 'after': '기록 없음'})
        self.assertEqual(rows[3]['after'], '아니요 (false)')
        self.assertEqual(rows[4]['after'], '알 수 없는 상태 (future_status)')
        self.assertEqual(audit_action('future_action'), '알 수 없는 행동 (future_action)')
        self.assertEqual(self.rows({}, {'starts_at': 'not-a-date'})[0]['after'], 'not-a-date')
        self.assertEqual(self.rows({}, {'starts_at': '2026-11-13'})[0]['after'], '2026년 11월 13일')

    def test_unknown_html_is_escaped_by_django(self):
        event = SimpleNamespace(action='<script>alert(1)</script>', before={'<img>': '<b>old</b>'}, after={'<img>': ['<i>new</i>']})
        output = Template('{% load audit_display %}{{ event.action|audit_action }}{% for row in event|audit_changes %}{{ row.label }}:{{ row.before }}:{{ row.after }}{% endfor %}').render(Context({'event': event}))
        for tag in ['<script>', '<img>', '<b>', '<i>']:
            self.assertNotIn(tag, output)
        self.assertIn('&lt;script&gt;', output)
        self.assertIn('&lt;img&gt;', output)
        self.assertIn('&lt;b&gt;old&lt;/b&gt;', output)
        self.assertNotIsInstance(audit_action(event.action), SafeData)

    @override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_real_template_uses_stored_ids_and_scroll_region_without_related_objects(self):
        event = SimpleNamespace(pk=7, created_at=None, actor_id=2, booking_id=5, session_id=3,
                                action='cancel', before={'status': 'confirmed'}, after={'status': 'cancelled'})
        from django.template.loader import render_to_string
        output = render_to_string('staff/audit.html', {'events': [event]})
        self.assertIn('aria-label="변경 기록 표 가로 스크롤"', output)
        self.assertIn('tabindex="0"', output)
        self.assertIn('계정 #2', output)
        self.assertIn('예약 #5', output)
        self.assertIn('회차 #3', output)
        self.assertIn('이전: 예약 확정', output)
        self.assertIn('이후: 취소됨', output)
        self.assertEqual(self.rows({}, {}), [])

    def test_non_mapping_legacy_facts_are_kept_visible(self):
        self.assertEqual(self.rows(['legacy'], None), [
            {'label': '기록 전체', 'before': '["legacy"]', 'after': '값 없음 (null)'},
        ])
