import re
import uuid

from django import forms
from django.conf import settings
from django.forms.renderers import DjangoTemplates
from django.utils.functional import cached_property
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Course, Room


class RequestForm(forms.Form):
    request_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)


class ActionForm(RequestForm):
    expected_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class ChoiceWidgetRenderer(DjangoTemplates):
    @cached_property
    def engine(self):
        engine = super().engine
        engine.engine.dirs.insert(0, settings.BASE_DIR / 'templates')
        return engine


class PaintedCheckboxInput(forms.CheckboxInput):
    template_name = 'widgets/checkbox.html'


class PaintedRadioSelect(forms.RadioSelect):
    option_template_name = 'widgets/radio_option.html'
    # The shared form include renders fields directly, without Django's fieldset.
    use_fieldset = False


class ReserveForm(ActionForm):
    default_renderer = ChoiceWidgetRenderer
    quantity = forms.IntegerField(label='참가 인원', min_value=1, max_value=8, initial=1)
    allow_waitlist = forms.BooleanField(label='바로 확정되지 않으면 대기 신청에 동의합니다', required=False,
        widget=PaintedCheckboxInput(attrs={'class': 'choice-input choice-checkbox'}))


class SessionChoiceField(forms.ChoiceField):
    def valid_value(self, value):
        if not re.fullmatch(r'[1-9][0-9]{0,18}:[1-9][0-9]{0,9}', str(value)):
            return False
        session_id, revision = map(int, str(value).split(':'))
        return session_id <= 9223372036854775807 and revision <= 2147483647


class RescheduleForm(ActionForm):
    default_renderer = ChoiceWidgetRenderer
    target_session_id = SessionChoiceField(label='변경할 회차',
        widget=PaintedRadioSelect(attrs={'class': 'choice-input choice-radio'}))

    def __init__(self, *args, sessions, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_session_id'].choices = [
            (f'{session.pk}:{session.revision}', f'{timezone.localtime(session.starts_at):%m월 %d일 %H:%M} · {session.room.name} · 취소·변경 시작 {session.cancellation_cutoff_minutes}분 전 마감')
            for session in sessions
        ]

    def clean(self):
        cleaned = super().clean()
        if 'target_session_id' in cleaned:
            session_id, revision = cleaned['target_session_id'].split(':')
            cleaned['target_session_id'] = int(session_id)
            cleaned['target_revision'] = int(revision)
        return cleaned


class SessionCancelForm(ActionForm):
    reason = forms.CharField(label='취소 사유', max_length=500, widget=forms.Textarea(attrs={'rows': 3}))


class SessionForm(forms.Form):
    course = forms.ModelChoiceField(label='강좌', queryset=Course.objects.all())
    room = forms.ModelChoiceField(label='공간', queryset=Room.objects.all())
    starts_at = forms.DateTimeField(label='시작 일시', input_formats=['%Y-%m-%dT%H:%M'], widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    ends_at = forms.DateTimeField(label='종료 일시', input_formats=['%Y-%m-%dT%H:%M'], widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    capacity = forms.IntegerField(label='회차 정원', min_value=1, max_value=32767)
    price_krw = forms.IntegerField(label='참가비(원)', min_value=0, max_value=2147483647)
    request_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    expected_revision = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        if instance:
            for name in ['course', 'room', 'starts_at', 'ends_at', 'capacity', 'price_krw']:
                self.fields[name].initial = getattr(instance, name)
            self.fields['expected_revision'].initial = instance.revision
            self.fields['expected_revision'].required = True
            if instance.has_booking_history:
                for name in ['course', 'room', 'starts_at', 'ends_at']:
                    self.fields[name].disabled = True
                self.fields['price_krw'].help_text = '새 신청에만 적용됩니다. 기존 예약·대기 금액은 유지됩니다.'

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('starts_at') and cleaned.get('ends_at') and cleaned['ends_at'] <= cleaned['starts_at']:
            self.add_error('ends_at', '종료는 시작 이후여야 합니다.')
        if cleaned.get('room') and cleaned.get('capacity') and cleaned['capacity'] > cleaned['room'].capacity:
            self.add_error('capacity', '공간 정원을 초과할 수 없습니다.')
        return cleaned


class SignupForm(UserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ['username']
