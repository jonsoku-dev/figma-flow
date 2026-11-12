import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Course(models.Model):
    title = models.CharField('강좌명', max_length=120)
    slug = models.SlugField(unique=True)
    summary = models.CharField('한 줄 소개', max_length=240)
    description = models.TextField('상세 소개')
    duration_minutes = models.PositiveIntegerField('수업 시간(분)', default=90, validators=[MinValueValidator(1)])
    price_krw = models.PositiveIntegerField('현장 결제 금액', validators=[MinValueValidator(0)])
    active = models.BooleanField('운영 중', default=True)
    cancellation_cutoff_minutes = models.PositiveIntegerField('취소 마감(분 전)', default=120)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(duration_minutes__gte=1), name='course_duration_positive')]

    def __str__(self):
        return self.title


class Room(models.Model):
    name = models.CharField('공간명', max_length=80, unique=True)
    capacity = models.PositiveSmallIntegerField('공간 정원', validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(capacity__gte=1), name='room_capacity_positive')]

    def __str__(self):
        return self.name


class ClassSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', '예약 가능'
        CANCELLED = 'cancelled', '운영 취소'

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='sessions', verbose_name='강좌')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='sessions', verbose_name='공간')
    starts_at = models.DateTimeField('시작 일시')
    ends_at = models.DateTimeField('종료 일시')
    capacity = models.PositiveSmallIntegerField('회차 정원', validators=[MinValueValidator(1)])
    price_krw = models.PositiveIntegerField('회차 참가비')
    cancellation_cutoff_minutes = models.PositiveIntegerField('취소 마감(분 전)')
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ['starts_at', 'pk']
        permissions = [('manage_operations', '공방 회차와 예약 운영')]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=models.F('starts_at')), name='session_end_after_start'),
            models.CheckConstraint(condition=Q(capacity__gte=1), name='session_capacity_positive'),
            models.CheckConstraint(condition=Q(revision__gte=1), name='session_revision_positive'),
            models.CheckConstraint(condition=Q(status__in=['scheduled', 'cancelled']), name='session_valid_status'),
            ExclusionConstraint(name='scheduled_room_no_overlap', expressions=[
                ('room', RangeOperators.EQUAL),
                (models.Func('starts_at', 'ends_at', models.Value('[)'), function='TSTZRANGE', output_field=DateTimeRangeField()), RangeOperators.OVERLAPS),
            ], condition=Q(status='scheduled')),
        ]
        indexes = [models.Index(fields=['status', 'starts_at'])]

    @property
    def has_booking_history(self):
        return self.bookings.exists() or self.auditevent_set.filter(booking__isnull=False).exists()

    def __str__(self):
        return f'{self.course} · {timezone.localtime(self.starts_at):%m/%d %H:%M}'


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', '예약 확정'
        WAITLISTED = 'waitlisted', '대기 중'
        CANCELLED = 'cancelled', '취소됨'

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='bookings')
    session = models.ForeignKey(ClassSession, on_delete=models.PROTECT, related_name='bookings')
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(8)])
    unit_price_krw = models.PositiveIntegerField()
    consented_session_revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices)
    revision = models.PositiveIntegerField(default=1)
    queued_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1, quantity__lte=8), name='booking_quantity_1_to_8'),
            models.CheckConstraint(condition=Q(revision__gte=1), name='booking_revision_positive'),
            models.CheckConstraint(condition=Q(status__in=['confirmed', 'waitlisted', 'cancelled']), name='booking_valid_status'),
            models.UniqueConstraint(fields=['member', 'session'], condition=Q(status__in=['confirmed', 'waitlisted']), name='one_active_booking_per_member_session'),
        ]
        indexes = [models.Index(fields=['session', 'status', 'queued_at', 'id'])]

    @property
    def total_price(self):
        return self.quantity * self.unit_price_krw


class Operation(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    action = models.CharField(max_length=40)
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'request_id'], name='operation_actor_request_unique')]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.PROTECT)
    session = models.ForeignKey(ClassSession, null=True, blank=True, on_delete=models.PROTECT)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class Notification(models.Model):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='notifications')
    event_key = models.CharField(max_length=160)
    title = models.CharField(max_length=120)
    message = models.TextField()
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.PROTECT)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['member', 'event_key'], name='notification_member_event_unique')]
