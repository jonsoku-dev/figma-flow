import os
import uuid
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from booking.models import Booking, ClassSession, Course, Room
from booking.services import reserve, save_session


class Command(BaseCommand):
    help = 'Create synthetic staging fixtures. Passwords must be supplied through private environment variables.'

    def add_arguments(self, parser):
        parser.add_argument('--start-date', type=str, help='YYYY-MM-DD; must be in the future')

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ENVIRONMENT not in {'staging', 'development'}:
            raise CommandError('Fixture seeding is prohibited in production.')
        member_password = os.environ.get('LH_FIXTURE_MEMBER_PASSWORD')
        staff_password = os.environ.get('LH_FIXTURE_STAFF_PASSWORD')
        if not member_password or not staff_password or min(len(member_password), len(staff_password)) < 12:
            raise CommandError('Set both LH_FIXTURE_MEMBER_PASSWORD and LH_FIXTURE_STAFF_PASSWORD to private values of at least 12 characters.')
        try:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date() if options['start_date'] else timezone.localdate() + timedelta(days=2)
        except ValueError:
            raise CommandError('Use --start-date YYYY-MM-DD.')
        if start_date <= timezone.localdate():
            raise CommandError('The fixture start date must be in the future.')
        User = get_user_model()
        members = []
        for username in ['member-a', 'member-b', 'member-c']:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(member_password)
                user.save(update_fields=['password'])
            elif user.is_staff or user.is_superuser:
                raise CommandError('Fixture member username belongs to a privileged user.')
            members.append(user)
        operator, created = User.objects.get_or_create(username='operator', defaults={'is_staff': True})
        if operator.is_superuser:
            raise CommandError('Fixture operator must not be a superuser.')
        if created:
            operator.set_password(staff_password)
            operator.save(update_fields=['password'])
        group, _ = Group.objects.get_or_create(name='공방 운영자')
        group.permissions.add(Permission.objects.get(codename='manage_operations', content_type__app_label='booking'))
        operator.groups.add(group)
        courses = []
        for slug, title, summary, description, price in [
            ('hand-drip', '나의 첫 핸드드립', '물줄기와 향을 느끼는 90분', '원두를 고르고 분쇄와 추출을 익힙니다. 각자의 속도로 두 잔을 내리고 맛을 나눕니다.', 45000),
            ('latte-art', '우유 위 작은 그림', '에스프레소와 우유가 만나는 시간', '우유의 온도와 질감을 배우고 하트 라테 아트를 연습합니다. 처음 오시는 분도 참여할 수 있습니다.', 55000),
        ]:
            course, _ = Course.objects.get_or_create(slug=slug, defaults={'title': title, 'summary': summary, 'description': description, 'duration_minutes': 90, 'price_krw': price})
            courses.append(course)
        rooms = [Room.objects.get_or_create(name=name, defaults={'capacity': 8})[0] for name in ['드립 테이블', '에스프레소 바']]
        sessions = []
        for offset in range(3):
            for index, course in enumerate(courses):
                starts_at = timezone.make_aware(datetime.combine(start_date + timedelta(days=offset), time(11 + index * 3)))
                session = ClassSession.objects.filter(course=course, room=rooms[index], starts_at=starts_at).first()
                if not session:
                    result = save_session(actor=operator, request_id=uuid.uuid4(), values={'course': course, 'room': rooms[index], 'starts_at': starts_at,
                        'ends_at': starts_at + timedelta(minutes=90), 'capacity': 4 if offset == 0 else 8, 'price_krw': course.price_krw})
                    session = ClassSession.objects.get(pk=result['session_id'])
                sessions.append(session)
        for member, quantity in [(members[0], 2), (members[1], 2), (members[2], 1)]:
            if not Booking.objects.filter(member=member, session=sessions[0]).exists():
                reserve(actor=member, session_id=sessions[0].pk, quantity=quantity, allow_waitlist=True,
                    expected_revision=sessions[0].revision, request_id=uuid.uuid4())
        self.stdout.write(self.style.SUCCESS('Synthetic staging fixtures are ready. Existing fixture passwords were preserved.'))
