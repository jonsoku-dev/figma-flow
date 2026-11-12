from datetime import datetime, timezone
from html.parser import HTMLParser
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from booking.forms import ReserveForm, RescheduleForm


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def attrs(self, tag):
        return [attrs for name, attrs in self.elements if name == tag]


class ChoiceWidgetTests(SimpleTestCase):
    def sessions(self):
        return [SimpleNamespace(pk=pk, revision=2, starts_at=datetime(2026, 11, 20, hour, tzinfo=timezone.utc),
                                room=SimpleNamespace(name='공간 <script>'), cancellation_cutoff_minutes=120)
                for pk, hour in [(3, 1), (4, 3)]]

    def test_checkbox_unchecked_and_checked_keep_real_input_and_mark(self):
        for checked in [False, True]:
            form = ReserveForm(initial={'allow_waitlist': checked})
            html = str(form['allow_waitlist'])
            elements = Elements(html)
            control = elements.attrs('input')[0]
            self.assertEqual(control['type'], 'checkbox')
            self.assertEqual(control['name'], 'allow_waitlist')
            self.assertEqual(control['id'], 'id_allow_waitlist')
            self.assertEqual('checked' in control, checked)
            self.assertNotIn('hidden', control)
            self.assertNotIn('tabindex', control)
            self.assertIn('choice-checkbox', control['class'])
            self.assertIn('>×</span>', html)
            mark = elements.attrs('span')[1]
            self.assertEqual(mark['aria-hidden'], 'true')
            self.assertEqual(mark['data-native-type'], 'text')
            self.assertEqual(mark['data-native-key'], 'id_allow_waitlist-mark')

    def test_checkbox_label_binding_submission_and_errors_remain_django_owned(self):
        checked = ReserveForm({'allow_waitlist': 'on', 'quantity': 1})
        unchecked = ReserveForm({'quantity': 1})
        checked.is_valid()
        unchecked.is_valid()
        self.assertTrue(checked.cleaned_data['allow_waitlist'])
        self.assertFalse(unchecked.cleaned_data['allow_waitlist'])
        html = render_to_string('includes/form.html', {'form': checked})
        self.assertIn('for="id_allow_waitlist"', html)
        self.assertIn('바로 확정되지 않으면 대기 신청에 동의합니다', html)
        self.assertIn('name="request_id"', html)
        self.assertIn('name="expected_revision"', html)
        self.assertIn('name="quantity"', checked.as_p())

    def test_radio_options_keep_required_ids_labels_values_and_selected_state(self):
        form = RescheduleForm({'target_session_id': '4:2'}, sessions=self.sessions())
        html = str(form['target_session_id'])
        elements = Elements(html)
        controls = elements.attrs('input')
        self.assertEqual([control['type'] for control in controls], ['radio', 'radio'])
        self.assertEqual([control['name'] for control in controls], ['target_session_id'] * 2)
        self.assertEqual([control['value'] for control in controls], ['3:2', '4:2'])
        self.assertEqual([control['id'] for control in controls], ['id_target_session_id_0', 'id_target_session_id_1'])
        self.assertTrue(all('required' in control for control in controls))
        self.assertEqual(['checked' in control for control in controls], [False, True])
        self.assertEqual([label['for'] for label in elements.attrs('label')], [control['id'] for control in controls])
        marks = [span for span in elements.attrs('span') if span.get('class') == 'choice-radio-mark']
        self.assertEqual(len(marks), 2)
        self.assertTrue(all(mark['aria-hidden'] == 'true' and mark['data-native-type'] == 'surface' for mark in marks))
        self.assertNotIn('<script>', html)
        self.assertIn('공간 &lt;script&gt;', html)
        self.assertIn('취소·변경 시작 120분 전 마감', html)

    def test_unchecked_radio_errors_and_disabled_attributes_are_preserved(self):
        form = RescheduleForm({}, sessions=self.sessions())
        self.assertFalse(form.is_valid())
        html = str(form['target_session_id'])
        controls = Elements(html).attrs('input')
        self.assertTrue(all('checked' not in control for control in controls))
        self.assertTrue(all(control['aria-invalid'] == 'true' for control in controls))
        self.assertTrue(all('id_target_session_id_error' in control['aria-describedby'] for control in controls))
        checkbox = ReserveForm()
        checkbox.fields['allow_waitlist'].disabled = True
        self.assertIn('disabled', Elements(str(checkbox['allow_waitlist'])).attrs('input')[0])

    def test_widget_attribute_values_are_escaped(self):
        form = ReserveForm()
        html = form['allow_waitlist'].as_widget(attrs={'data-note': '"><img src=x onerror=alert(1)>'})
        self.assertNotIn('<img', html)
        self.assertIn('&lt;img', html)
        self.assertEqual(Elements(html).attrs('input')[0]['data-note'], '"><img src=x onerror=alert(1)>')
