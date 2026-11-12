import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, connections, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from booking import services
from booking.forms import RescheduleForm, SessionForm
from booking.models import AuditEvent, Booking, ClassSession, Course, Notification, Operation, Room


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BookingTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'These proofs require PostgreSQL, never SQLite.')
        User = get_user_model()
        self.users = [User.objects.create_user(username=f'member-{i}') for i in range(6)]
        self.operator = User.objects.create_user(username='operator', is_staff=True)
        self.operator.user_permissions.add(Permission.objects.get(codename='manage_operations', content_type__app_label='booking'))
        self.course = Course.objects.create(title='드립', slug='drip', summary='커피 수업', description='합성 검증 수업', price_krw=45000)
        self.room = Room.objects.create(name='공간 A', capacity=8)
        self.start = timezone.now() + timedelta(days=3)
        self.session = self.make_session(capacity=2)
        self.target = self.make_session(starts_at=self.start + timedelta(days=1), capacity=2)

    def make_session(self, **values):
        defaults = {'course': self.course, 'room': self.room, 'starts_at': self.start,
            'ends_at': self.start + timedelta(minutes=90), 'capacity': 2, 'price_krw': 45000,
            'cancellation_cutoff_minutes': values.get('course', self.course).cancellation_cutoff_minutes}
        if 'starts_at' in values:
            defaults['ends_at'] = values['starts_at'] + timedelta(minutes=90)
        return ClassSession.objects.create(**(defaults | values))

    def reserve(self, member=0, session=None, quantity=1, allow_waitlist=True, **kwargs):
        session = session or self.session
        result = services.reserve(actor=self.users[member], session_id=session.pk, quantity=quantity,
            allow_waitlist=allow_waitlist, expected_revision=kwargs.pop('expected_revision', session.revision),
            request_id=kwargs.pop('request_id', uuid.uuid4()), **kwargs)
        return Booking.objects.get(public_id=result['booking_id'])

    def cancel(self, booking, **kwargs):
        return services.cancel(actor=booking.member, public_id=booking.public_id,
            expected_revision=kwargs.pop('expected_revision', booking.revision), request_id=kwargs.pop('request_id', uuid.uuid4()))

    def change(self, booking, target=None, **kwargs):
        target = target or self.target
        return services.reschedule(actor=booking.member, public_id=booking.public_id, target_session_id=target.pk,
            target_revision=kwargs.pop('target_revision', target.revision), expected_revision=kwargs.pop('expected_revision', booking.revision), request_id=uuid.uuid4())

    def edit_values(self, session=None, **values):
        session = session or self.session
        return {key: values.get(key, getattr(session, key)) for key in ['course', 'room', 'starts_at', 'ends_at', 'capacity', 'price_krw']}

    def edit(self, session=None, **values):
        session = session or self.session
        return services.save_session(actor=self.operator, values=self.edit_values(session, **values), session_id=session.pk,
            expected_revision=session.revision, request_id=uuid.uuid4())

    def race(self, *jobs):
        barrier = Barrier(len(jobs))
        def run(job):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return job()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            futures = [executor.submit(run, job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    def test_final_seat_concurrent_confirmed_and_waitlisted(self):
        self.reserve(member=0)
        self.race(lambda: self.reserve(member=1), lambda: self.reserve(member=2))
        self.assertEqual(Booking.objects.filter(status='confirmed').count(), 2)
        self.assertEqual(Booking.objects.filter(status='waitlisted').count(), 1)
        self.assertEqual(services._remaining(self.session), 0)

    def test_concurrent_cancel_new_reserve_preserves_queue_priority(self):
        confirmed = self.reserve(member=0, quantity=2)
        head = self.reserve(member=1, quantity=2)
        self.race(lambda: self.cancel(confirmed), lambda: self.reserve(member=2))
        head.refresh_from_db()
        self.assertEqual(head.status, 'confirmed')
        self.assertEqual(Booking.objects.get(member=self.users[2]).status, 'waitlisted')

    def test_fifo_does_not_skip_larger_group_with_free_seat(self):
        self.reserve(member=0)
        head = self.reserve(member=1, quantity=2)
        tail = self.reserve(member=2)
        self.assertEqual((head.status, tail.status), ('waitlisted', 'waitlisted'))
        self.assertEqual(services._remaining(self.session), 1)

    def test_full_reservation_requires_explicit_waitlist_consent(self):
        self.reserve(quantity=2)
        counts = (Booking.objects.count(), AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count())
        with self.assertRaises(services.BookingError):
            self.reserve(member=1, allow_waitlist=False)
        self.assertEqual(counts, (Booking.objects.count(), AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count()))

    def test_idempotent_cancel_promotes_and_notifies_once(self):
        original = self.reserve(quantity=2)
        head = self.reserve(member=1, quantity=2)
        request_id = uuid.uuid4()
        first = self.cancel(original, request_id=request_id)
        counts = (AuditEvent.objects.count(), Notification.objects.count())
        second = self.cancel(original, request_id=request_id)
        self.assertEqual(first, second)
        self.assertEqual(counts, (AuditEvent.objects.count(), Notification.objects.count()))
        head.refresh_from_db()
        self.assertEqual((head.status, head.revision), ('confirmed', 2))
        self.session.refresh_from_db()
        self.assertEqual(self.session.revision, 1)

    def test_same_request_different_payload_conflicts(self):
        request_id = uuid.uuid4()
        self.reserve(request_id=request_id)
        with self.assertRaises(services.BookingError) as caught:
            self.reserve(quantity=2, request_id=request_id)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_concurrent_duplicate_request_creates_one_booking(self):
        request_id = uuid.uuid4()
        results = self.race(lambda: self.reserve(request_id=request_id), lambda: self.reserve(request_id=request_id))
        self.assertEqual(results[0].pk, results[1].pk)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Operation.objects.count(), 1)

    def test_reschedule_releases_original_and_promotes_waitlist(self):
        original = self.reserve(quantity=2)
        head = self.reserve(member=1, quantity=2)
        self.change(original)
        original.refresh_from_db()
        head.refresh_from_db()
        self.assertEqual(original.session_id, self.target.pk)
        self.assertEqual(original.revision, 2)
        self.assertEqual(head.status, 'confirmed')

    def test_failed_reschedule_preserves_original_queue_audit_notifications(self):
        original = self.reserve(quantity=2)
        head = self.reserve(member=1, quantity=2)
        self.reserve(member=2, session=self.target, quantity=2)
        counts = (AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count())
        with self.assertRaises(services.BookingError):
            self.change(original)
        original.refresh_from_db()
        head.refresh_from_db()
        self.assertEqual((original.session_id, original.status, original.revision), (self.session.pk, 'confirmed', 1))
        self.assertEqual(head.status, 'waitlisted')
        self.assertEqual(counts, (AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count()))

    def test_stale_booking_and_target_revision_conflict(self):
        original = self.reserve()
        with self.assertRaises(services.BookingError):
            self.cancel(original, expected_revision=99)
        self.edit(session=self.target, price_krw=49000)
        with self.assertRaises(services.BookingError):
            self.change(original, target_revision=1)
        original.refresh_from_db()
        self.assertEqual(original.session_id, self.session.pk)

    def test_stale_session_revision_rejects_new_registration(self):
        self.edit(price_krw=49000)
        with self.assertRaises(services.BookingError):
            self.reserve(expected_revision=1)
        self.assertEqual(Booking.objects.count(), 0)

    def test_capacity_price_edits_preserve_waitlist_terms_and_promote(self):
        first = self.reserve(quantity=2)
        waiting = self.reserve(member=1, quantity=1)
        self.edit(capacity=3, price_krw=60000)
        waiting.refresh_from_db()
        self.assertEqual((waiting.status, waiting.unit_price_krw), ('confirmed', 45000))
        first.refresh_from_db()
        self.assertEqual(first.unit_price_krw, 45000)
        self.session.refresh_from_db()
        self.assertEqual(self.session.revision, 2)
        new = self.reserve(member=2, quantity=1)
        self.assertEqual(new.unit_price_krw, 60000)

    def test_cannot_reduce_capacity_below_confirmed_or_edit_booked_time(self):
        self.reserve(quantity=2)
        for change in [{'capacity': 1}, {'starts_at': self.start + timedelta(minutes=10)}]:
            with self.assertRaises(services.BookingError):
                self.edit(**change)
        self.session.refresh_from_db()
        self.assertEqual(self.session.capacity, 2)
        self.assertEqual(self.session.starts_at, self.start)

    def test_same_room_overlap_excluded_but_adjacent_allowed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_session(starts_at=self.start + timedelta(minutes=30))
        adjacent = self.make_session(starts_at=self.session.ends_at)
        self.assertIsNotNone(adjacent.pk)
        other_room = Room.objects.create(name='공간 B', capacity=8)
        self.assertIsNotNone(self.make_session(room=other_room).pk)

    def test_database_quantity_times_status_and_duplicates_constraints(self):
        booking = self.reserve()
        for values in [{'quantity': 0}, {'quantity': 9}, {'status': 'invented'}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Booking.objects.filter(pk=booking.pk).update(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(member=booking.member, session=booking.session, quantity=1, status='waitlisted', unit_price_krw=45000)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassSession.objects.filter(pk=self.session.pk).update(ends_at=self.session.starts_at)

    def test_audit_and_operation_immutable_in_database(self):
        self.reserve()
        for model in [AuditEvent, Operation]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                model.objects.all().update(created_at=timezone.now())
            with self.assertRaises(DatabaseError), transaction.atomic():
                model.objects.all().delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Room.objects.filter(pk=self.room.pk).update(capacity=9)

    def test_cutoff_member_blocked_staff_can_cancel_with_reason(self):
        original = self.reserve()
        ClassSession.objects.filter(pk=self.session.pk).update(starts_at=timezone.now() + timedelta(minutes=30), ends_at=timezone.now() + timedelta(minutes=120))
        with self.assertRaises(services.BookingError):
            self.cancel(original)
        services.cancel_session(actor=self.operator, session_id=self.session.pk, expected_revision=1,
            request_id=uuid.uuid4(), reason='시설 점검')
        original.refresh_from_db()
        self.assertEqual(original.status, 'cancelled')
        self.assertEqual(AuditEvent.objects.filter(action='session_cancel', after__reason='시설 점검').count(), 1)

    def test_same_course_only_reschedule_and_other_session_parallel_allowed(self):
        booking = self.reserve()
        self.reserve(member=0, session=self.target)
        another_course = Course.objects.create(title='라테', slug='latte', summary='우유', description='검증', price_krw=55000)
        other_room = Room.objects.create(name='공간 C', capacity=8)
        different = self.make_session(course=another_course, room=other_room)
        self.reserve(member=0, session=different)
        with self.assertRaises(services.BookingError):
            self.change(booking, target=different)
        self.assertEqual(Booking.objects.filter(member=self.users[0], status='confirmed').count(), 3)

    def test_owner_and_staff_authorization_and_method_guards(self):
        booking = self.reserve()
        self.client.force_login(self.users[1])
        for route in ['booking_detail', 'cancel', 'reschedule']:
            self.assertEqual(self.client.get(reverse(route, args=[booking.public_id])).status_code, 404)
        for route in ['staff_dashboard', 'staff_sessions', 'staff_audit', 'staff_session_create']:
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        self.assertEqual(self.client.post(reverse('staff_session_cancel', args=[self.session.pk]), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('reserve', args=[self.session.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('staff_session_cancel', args=[self.session.pk])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            services.cancel_session(actor=self.users[1], session_id=self.session.pk, expected_revision=1, request_id=uuid.uuid4(), reason='권한 없음')

    def test_get_confirmation_pages_never_mutate(self):
        booking = self.reserve()
        self.client.force_login(booking.member)
        counts = (Booking.objects.count(), AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count())
        for route in ['booking_detail', 'cancel', 'reschedule']:
            self.assertEqual(self.client.get(reverse(route, args=[booking.public_id])).status_code, 200)
        self.assertEqual(counts, (Booking.objects.count(), AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count()))

    def test_csrf_required_for_write_and_post_redirect_get(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.users[0])
        url = reverse('reserve', args=[self.session.pk])
        data = {'quantity': 1, 'expected_revision': 1, 'request_id': uuid.uuid4()}
        self.assertEqual(client.post(url, data).status_code, 403)
        client.get(reverse('session_detail', args=[self.session.pk]))
        csrf_name = __import__('django.conf', fromlist=['settings']).settings.CSRF_COOKIE_NAME
        token = client.cookies[csrf_name].value
        response = client.post(url, data | {'csrfmiddlewaretoken': token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get(response.url).status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)

    def test_view_idempotency_reuse_and_stale_target_are_409(self):
        self.client.force_login(self.users[0])
        request_id = uuid.uuid4()
        url = reverse('reserve', args=[self.session.pk])
        data = {'quantity': 1, 'expected_revision': 1, 'request_id': request_id}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data | {'quantity': 2}).status_code, 409)
        booking = Booking.objects.get(member=self.users[0])
        self.edit(session=self.target, price_krw=49000)
        self.assertEqual(self.client.post(reverse('reschedule', args=[booking.public_id]), {
            'request_id': uuid.uuid4(), 'expected_revision': 1, 'target_session_id': f'{self.target.pk}:1'}).status_code, 409)

    def test_notifications_scoped_and_distinct_request_ids(self):
        booking = self.reserve()
        self.edit(price_krw=50000)
        self.client.force_login(self.users[0])
        response = self.client.get(reverse('notifications'))
        rows = list(response.context['notifications'])
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(len({row.request_id for row in rows}), len(rows))
        own = rows[0]
        self.assertEqual(self.client.post(reverse('notification_read', args=[own.pk]), {'request_id': uuid.uuid4()}).status_code, 302)
        own.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.client.force_login(self.users[1])
        self.assertEqual(self.client.post(reverse('notification_read', args=[own.pk]), {'request_id': uuid.uuid4()}).status_code, 404)

    def test_dashboard_uses_database_totals_and_admin_cannot_mutate(self):
        self.reserve(quantity=2)
        self.reserve(member=1)
        self.client.force_login(self.operator)
        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['confirmed_count'], 2)
        self.assertEqual(response.context['stats']['waitlisted_count'], 1)
        self.assertEqual(sum(row['count'] for row in response.context['daily_counts']), 2)
        for model in [Booking, ClassSession, AuditEvent, Operation]:
            registered = admin.site._registry[model]
            self.assertFalse(registered.has_add_permission(None))
            self.assertFalse(registered.has_change_permission(None))
            self.assertFalse(registered.has_delete_permission(None))

    def test_signup_cannot_assign_privilege_and_password_policy(self):
        url = reverse('signup')
        self.assertEqual(self.client.post(url, {'username': 'bad', 'password1': 'short', 'password2': 'short'}).status_code, 400)
        password = 'Synthetic-Access-9381!'
        response = self.client.post(url, {'username': 'new-member', 'password1': password, 'password2': password, 'is_staff': 'true', 'is_superuser': 'true'})
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='new-member')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.password.startswith('argon2$'))

    @override_settings(ENVIRONMENT='production')
    def test_seed_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command('seed_staging')

    def test_health_minimal_database_response(self):
        response = self.client.get(reverse('health'))
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_http_reschedule_replay_returns_same_result(self):
        booking = self.reserve()
        self.client.force_login(booking.member)
        data = {'request_id': uuid.uuid4(), 'expected_revision': 1, 'target_session_id': f'{self.target.pk}:1'}
        url = reverse('reschedule', args=[booking.public_id])
        first = self.client.post(url, data)
        self.assertEqual(first.status_code, 302)
        counts = (AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count())
        second = self.client.post(url, data)
        self.assertEqual((second.status_code, second.url), (302, first.url))
        self.assertEqual(counts, (AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count()))

    def test_http_staff_create_replay_and_overlap_conflict(self):
        self.client.force_login(self.operator)
        starts_at = timezone.localtime(self.start + timedelta(days=2))
        data = {'request_id': uuid.uuid4(), 'course': self.course.pk, 'room': self.room.pk,
            'starts_at': starts_at.strftime('%Y-%m-%dT%H:%M'), 'ends_at': (starts_at + timedelta(minutes=90)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 4, 'price_krw': 49000}
        url = reverse('staff_session_create')
        first = self.client.post(url, data)
        self.assertEqual(first.status_code, 302)
        second = self.client.post(url, data)
        self.assertEqual((second.status_code, second.url), (302, first.url))
        failed_request = data | {'request_id': uuid.uuid4()}
        conflict = self.client.post(url, failed_request)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.context['form']['starts_at'].value(), data['starts_at'])
        self.assertEqual(conflict.context['form']['capacity'].value(), str(data['capacity']))
        self.assertNotEqual(str(conflict.context['form']['request_id'].value()), str(failed_request['request_id']))
        self.assertContains(conflict, '해당 공간의 다른 회차와 시간이 겹칩니다.', status_code=409)
        self.assertEqual(ClassSession.objects.count(), 3)

    def test_unavailable_action_gets_return_to_detail_without_mutation(self):
        cancelled = self.reserve()
        self.cancel(cancelled)
        late = self.reserve(session=self.make_session(starts_at=timezone.now() + timedelta(minutes=60)))
        self.client.force_login(self.users[0])
        before = (Booking.objects.count(), AuditEvent.objects.count(), Operation.objects.count(), Notification.objects.count())
        for booking in (cancelled, late):
            for action in ('cancel', 'reschedule'):
                response = self.client.get(reverse(action, args=[booking.public_id]))
                self.assertEqual((response.status_code, response.url), (302, reverse('booking_detail', args=[booking.public_id])))
        self.assertEqual(before, (Booking.objects.count(), AuditEvent.objects.count(), Operation.objects.count(), Notification.objects.count()))

    def test_concurrent_cancel_reschedule_one_stale_request_no_double_release(self):
        booking = self.reserve(quantity=2)
        waiter = self.reserve(member=1, quantity=2)
        def attempt(action):
            try:
                return action()
            except services.BookingError as error:
                return {'error': error.status}
        results = self.race(lambda: attempt(lambda: self.cancel(booking)), lambda: attempt(lambda: self.change(booking)))
        self.assertEqual(sum(result.get('error') == 409 for result in results), 1)
        booking.refresh_from_db()
        waiter.refresh_from_db()
        self.assertEqual(booking.revision, 2)
        self.assertEqual(waiter.status, 'confirmed')
        self.assertEqual(AuditEvent.objects.filter(action='promote', booking=waiter).count(), 1)

    def test_booked_metadata_immutable_even_after_member_cancellation(self):
        booking = self.reserve()
        self.cancel(booking)
        for values in [{'room': Room.objects.create(name='공간 D', capacity=8)},
                       {'starts_at': self.start + timedelta(minutes=10)},
                       {'ends_at': self.session.ends_at + timedelta(minutes=10)}]:
            with self.assertRaises(services.BookingError):
                self.edit(**values)
        form = SessionForm(instance=self.session)
        self.assertTrue(all(form.fields[name].disabled for name in ['course', 'room', 'starts_at', 'ends_at']))

    def test_missing_fixture_passwords_refused(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'LH_FIXTURE_MEMBER_PASSWORD': '', 'LH_FIXTURE_STAFF_PASSWORD': ''}):
            with self.assertRaises(CommandError):
                call_command('seed_staging')

    def test_capacity_cannot_make_waiting_group_impossible(self):
        self.reserve(quantity=1)
        self.reserve(member=1, quantity=2)
        with self.assertRaises(services.BookingError):
            self.edit(capacity=1)
        self.session.refresh_from_db()
        self.assertEqual(self.session.capacity, 2)

    def test_noop_session_save_keeps_revision_and_notifications(self):
        self.reserve()
        counts = (AuditEvent.objects.count(), Notification.objects.count())
        self.edit()
        self.session.refresh_from_db()
        self.assertEqual(self.session.revision, 1)
        self.assertEqual(counts, (AuditEvent.objects.count(), Notification.objects.count()))

    def test_expired_session_detail_disables_reservation(self):
        ClassSession.objects.filter(pk=self.session.pk).update(starts_at=timezone.now() - timedelta(hours=2), ends_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(reverse('session_detail', args=[self.session.pk]))
        self.assertFalse(response.context['can_reserve'])

    def test_course_admin_policy_change_preserves_published_session_policy(self):
        soon = self.make_session(starts_at=timezone.now() + timedelta(hours=3))
        booking = self.reserve(session=soon)
        self.course.cancellation_cutoff_minutes = 240
        admin.site._registry[Course].save_model(None, self.course, None, change=True)
        soon.refresh_from_db()
        self.assertEqual(soon.cancellation_cutoff_minutes, 120)
        self.client.force_login(booking.member)
        response = self.client.get(reverse('booking_detail', args=[booking.public_id]))
        self.assertTrue(response.context['can_cancel'])
        self.cancel(booking)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        values = self.edit_values(starts_at=self.start + timedelta(days=3), ends_at=self.start + timedelta(days=3, minutes=90))
        result = services.save_session(actor=self.operator, values=values, request_id=uuid.uuid4())
        self.assertEqual(ClassSession.objects.get(pk=result['session_id']).cancellation_cutoff_minutes, 240)
        self.assertEqual(AuditEvent.objects.get(session_id=result['session_id'], action='session_create').after['cancellation_cutoff_minutes'], 240)
        self.edit(price_krw=49000)
        self.session.refresh_from_db()
        self.assertEqual(self.session.cancellation_cutoff_minutes, 120)

    def test_session_policy_cannot_be_changed_through_staff_service(self):
        self.reserve()
        with self.assertRaises(services.BookingError):
            services.save_session(actor=self.operator, values=self.edit_values() | {'cancellation_cutoff_minutes': 240},
                session_id=self.session.pk, expected_revision=1, request_id=uuid.uuid4())
        self.session.refresh_from_db()
        self.assertEqual(self.session.cancellation_cutoff_minutes, 120)

    def test_original_reschedule_replay_after_two_moves_and_target_cancelled(self):
        booking = self.reserve()
        third = self.make_session(starts_at=self.start + timedelta(days=2))
        self.client.force_login(booking.member)
        original_data = {'request_id': uuid.uuid4(), 'expected_revision': 1, 'target_session_id': f'{self.target.pk}:1'}
        url = reverse('reschedule', args=[booking.public_id])
        first = self.client.post(url, original_data)
        self.assertEqual(first.status_code, 302)
        second = self.client.post(url, {'request_id': uuid.uuid4(), 'expected_revision': 2, 'target_session_id': f'{third.pk}:1'})
        self.assertEqual(second.status_code, 302)
        services.cancel_session(actor=self.operator, session_id=self.target.pk, expected_revision=1,
            request_id=uuid.uuid4(), reason='이전 회차 운영 종료')
        before = (Booking.objects.count(), AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count())
        replay = self.client.post(url, original_data)
        self.assertEqual((replay.status_code, replay.url), (first.status_code, first.url))
        self.assertEqual(before, (Booking.objects.count(), AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count()))
        booking.refresh_from_db()
        self.assertEqual((booking.session_id, booking.revision), (third.pk, 3))
        fresh = self.client.post(url, original_data | {'request_id': uuid.uuid4(), 'expected_revision': 3})
        self.assertEqual(fresh.status_code, 409)
        booking.refresh_from_db()
        self.assertEqual((booking.session_id, booking.revision), (third.pk, 3))

    def test_reschedule_target_structure_validated_independently_of_choices(self):
        valid = RescheduleForm({'request_id': uuid.uuid4(), 'expected_revision': 1, 'target_session_id': '123:4'}, sessions=[])
        self.assertTrue(valid.is_valid())
        self.assertEqual((valid.cleaned_data['target_session_id'], valid.cleaned_data['target_revision']), (123, 4))
        for value in ['0:1', '-1:1', '1:0', '1:-1', '1:2:3', '1:1\n', '9223372036854775808:1', '1:2147483648', '1:' + '9' * 100]:
            form = RescheduleForm({'request_id': uuid.uuid4(), 'expected_revision': 1, 'target_session_id': value}, sessions=[])
            self.assertFalse(form.is_valid(), value)

    def test_moved_away_booking_history_keeps_source_terms_immutable(self):
        booking = self.reserve()
        self.change(booking)
        self.assertFalse(Booking.objects.filter(session=self.session).exists())
        self.assertTrue(self.session.has_booking_history)
        original_values = self.edit_values()
        before = (AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count())
        room = Room.objects.create(name='이력 검증 공간', capacity=8)
        course = Course.objects.create(title='이력 검증 강좌', slug='history-course', summary='검증', description='검증', price_krw=45000)
        for values in [{'starts_at': self.start + timedelta(minutes=10)}, {'room': room}, {'course': course}]:
            with self.assertRaises(services.BookingError) as caught:
                self.edit(**values)
            self.assertEqual(caught.exception.status, 409)
        self.session.refresh_from_db()
        self.assertEqual(self.edit_values(), original_values)
        self.assertEqual(before, (AuditEvent.objects.count(), Notification.objects.count(), Operation.objects.count()))
        form = SessionForm(instance=self.session)
        self.assertTrue(all(form.fields[name].disabled for name in ['course', 'room', 'starts_at', 'ends_at']))

    def test_reschedule_preserves_original_quote_and_discloses_target_policy(self):
        booking = self.reserve(quantity=2)
        self.edit(session=self.target, price_krw=65000)
        self.target.refresh_from_db()
        ClassSession.objects.filter(pk=self.target.pk).update(cancellation_cutoff_minutes=240)
        self.target.refresh_from_db()
        form = RescheduleForm(sessions=[self.target])
        label = str(form.fields['target_session_id'].choices[0][1])
        self.assertIn('240분 전 마감', label)
        self.assertNotIn('65,000', label)
        self.change(booking)
        booking.refresh_from_db()
        self.assertEqual((booking.unit_price_krw, booking.total_price), (45000, 90000))
        self.assertEqual(booking.session.cancellation_cutoff_minutes, 240)
        event = AuditEvent.objects.get(booking=booking, action='reschedule')
        self.assertEqual(event.after['unit_price_krw'], event.before['unit_price_krw'])

    def test_reschedule_notification_identifies_previous_and_new_session(self):
        booking = self.reserve(quantity=2)
        other_room = Room.objects.create(name='변경 대상 공간', capacity=8)
        self.target.room = other_room
        self.target.save(update_fields=['room'])
        self.change(booking)
        notification = Notification.objects.get(booking=booking, event_key=f'booking:{booking.pk}:2:reschedule')
        self.assertEqual(notification.title, '일정 변경 완료')
        previous_time = timezone.localtime(self.session.starts_at).strftime('%Y.%m.%d %H:%M')
        new_time = timezone.localtime(self.target.starts_at).strftime('%Y.%m.%d %H:%M')
        self.assertIn(self.course.title, notification.message)
        self.assertIn('2명', notification.message)
        self.assertIn(previous_time, notification.message)
        self.assertIn(new_time, notification.message)
        self.assertIn(self.room.name, notification.message)
        self.assertIn(other_room.name, notification.message)
        self.assertLess(notification.message.index(previous_time), notification.message.index('→'))
        self.assertLess(notification.message.index('→'), notification.message.index(new_time))

    def test_waitlist_promotion_notification_distinguishes_new_confirmation(self):
        original = self.reserve(quantity=2)
        waiting = self.reserve(member=1)
        wait_notice = Notification.objects.get(booking=waiting, event_key=f'booking:{waiting.pk}:1:reserve')
        self.assertEqual(wait_notice.title, '대기 신청 접수')
        self.assertIn('아직 예약 확정 상태가 아닙니다.', wait_notice.message)
        self.cancel(original)
        promotion = Notification.objects.get(booking=waiting, event_key=f'booking:{waiting.pk}:2:promote')
        self.assertEqual(promotion.title, '대기 예약 확정')
        self.assertIn('대기 순서에 따라 예약이 확정되었습니다.', promotion.message)
        self.assertIn(timezone.localtime(self.session.starts_at).strftime('%Y.%m.%d %H:%M'), promotion.message)
        self.assertIn(self.room.name, promotion.message)
        cancellation = Notification.objects.get(booking=original, event_key=f'booking:{original.pk}:2:cancel')
        self.assertEqual(cancellation.title, '예약 취소')
        self.assertIn('예약을 취소했습니다.', cancellation.message)
