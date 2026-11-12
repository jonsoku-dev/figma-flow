import uuid
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import services
from .forms import ActionForm, RequestForm, ReserveForm, RescheduleForm, SessionCancelForm, SessionForm, SignupForm
from .models import AuditEvent, Booking, ClassSession, Course, Notification


def operator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        services.require_operator(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def _sessions():
    return ClassSession.objects.select_related('course', 'room').annotate(
        confirmed_count=Coalesce(Sum('bookings__quantity', filter=Q(bookings__status='confirmed')), Value(0), output_field=IntegerField()),
        waitlisted_count=Coalesce(Sum('bookings__quantity', filter=Q(bookings__status='waitlisted')), Value(0), output_field=IntegerField()),
    ).annotate(remaining=F('capacity') - F('confirmed_count')).order_by('starts_at', 'pk')


def _page(request, queryset, size=20):
    return Paginator(queryset, size).get_page(request.GET.get('page'))


def _error(request, error, recovery_url):
    return render(request, 'booking/conflict.html', {'message': error.message, 'recovery_url': recovery_url}, status=error.status)


@require_GET
def session_list(request):
    sessions = _sessions().filter(status='scheduled', course__active=True, starts_at__gt=timezone.now())
    course = request.GET.get('course', '')
    if course:
        sessions = sessions.filter(course__slug=course)
    page = _page(request, sessions)
    return render(request, 'booking/session_list.html', {'sessions': page, 'page_obj': page, 'courses': Course.objects.filter(active=True), 'selected_course': course})


@require_GET
def session_detail(request, pk):
    session = get_object_or_404(_sessions(), pk=pk)
    return render(request, 'booking/session_detail.html', {'session': session, 'reserve_form': ReserveForm(initial={'expected_revision': session.revision}),
        'remaining': session.remaining, 'waitlist_count': session.waitlisted_count,
        'can_reserve': session.status == 'scheduled' and session.course.active and session.starts_at > timezone.now()})


@login_required
@require_POST
def reserve_preview(request, pk):
    session = get_object_or_404(_sessions(), pk=pk)
    form = ReserveForm(request.POST)
    if form.is_valid():
        try:
            services._available(session)
            services._revision(session.revision, form.cleaned_data['expected_revision'])
            if form.cleaned_data['quantity'] > session.capacity:
                raise services.BookingError('인원이 회차 정원을 초과합니다.', 400)
        except services.BookingError as error:
            return _error(request, error, reverse('session_detail', args=[pk]))
        quantity = form.cleaned_data['quantity']
        return render(request, 'booking/reserve_review.html', {'session': session, 'reserve_form': form, 'quantity': quantity, 'total_price': quantity * session.price_krw})
    return render(request, 'booking/session_detail.html', {'session': session, 'reserve_form': form, 'remaining': session.remaining, 'waitlist_count': session.waitlisted_count}, status=400)


@login_required
@require_POST
def reserve(request, pk):
    get_object_or_404(ClassSession, pk=pk)
    form = ReserveForm(request.POST)
    if not form.is_valid():
        return render(request, 'booking/conflict.html', {'message': '신청 내용을 확인해 주세요.', 'form': form, 'recovery_url': reverse('session_detail', args=[pk])}, status=400)
    try:
        result = services.reserve(actor=request.user, session_id=pk, **form.cleaned_data)
    except services.BookingError as error:
        return _error(request, error, reverse('session_detail', args=[pk]))
    messages.success(request, '신청이 접수되었습니다. 확정·대기 상태를 확인해 주세요.')
    return redirect('booking_detail', public_id=result['booking_id'])


@login_required
@require_GET
def my_bookings(request):
    page = _page(request, Booking.objects.filter(member=request.user).select_related('session__course', 'session__room'))
    return render(request, 'booking/my_bookings.html', {'bookings': page, 'page_obj': page})


def _own_booking(request, public_id):
    return get_object_or_404(Booking.objects.select_related('session__course', 'session__room'), public_id=public_id, member=request.user)


def _can_change(booking):
    return booking.status != 'cancelled' and booking.session.starts_at - timezone.now() > timedelta(minutes=booking.session.cancellation_cutoff_minutes)


@login_required
@require_GET
def booking_detail(request, public_id):
    booking = _own_booking(request, public_id)
    can_change = _can_change(booking)
    return render(request, 'booking/booking_detail.html', {'booking': booking, 'can_cancel': can_change, 'can_reschedule': can_change})


@login_required
@require_http_methods(['GET', 'POST'])
def cancel(request, public_id):
    booking = _own_booking(request, public_id)
    if request.method == 'GET' and not _can_change(booking):
        return redirect('booking_detail', public_id=public_id)
    form = ActionForm(request.POST if request.method == 'POST' else None, initial={'expected_revision': booking.revision})
    if request.method == 'POST' and form.is_valid():
        try:
            result = services.cancel(actor=request.user, public_id=public_id, **form.cleaned_data)
        except services.BookingError as error:
            return _error(request, error, reverse('booking_detail', args=[public_id]))
        messages.success(request, '예약을 취소했습니다.')
        return redirect('booking_detail', public_id=result['booking_id'])
    return render(request, 'booking/cancel.html', {'booking': booking, 'action_form': form}, status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def reschedule(request, public_id):
    booking = _own_booking(request, public_id)
    if request.method == 'GET' and not _can_change(booking):
        return redirect('booking_detail', public_id=public_id)
    sessions = list(_sessions().filter(course=booking.session.course, status='scheduled', starts_at__gt=timezone.now()).exclude(pk=booking.session_id)[:100])
    form = RescheduleForm(request.POST if request.method == 'POST' else None, sessions=sessions, initial={'expected_revision': booking.revision})
    if request.method == 'POST' and form.is_valid():
        try:
            result = services.reschedule(actor=request.user, public_id=public_id, **form.cleaned_data)
        except services.BookingError as error:
            return _error(request, error, reverse('booking_detail', args=[public_id]))
        messages.success(request, '회차를 변경했습니다.')
        return redirect('booking_detail', public_id=result['booking_id'])
    return render(request, 'booking/reschedule.html', {'booking': booking, 'form': form, 'sessions': sessions}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def notifications(request):
    page = _page(request, Notification.objects.filter(member=request.user).select_related('booking'))
    for notification in page:
        notification.request_id = uuid.uuid4()
    return render(request, 'booking/notifications.html', {'notifications': page, 'page_obj': page})


@login_required
@require_POST
def notification_read(request, pk):
    get_object_or_404(Notification, member=request.user, pk=pk)
    form = RequestForm(request.POST)
    if not form.is_valid():
        return _error(request, services.BookingError('요청 번호를 확인해 주세요.', 400), reverse('notifications'))
    try:
        services.read_notification(actor=request.user, notification_id=pk, **form.cleaned_data)
    except services.BookingError as error:
        return _error(request, error, reverse('notifications'))
    return redirect('notifications')


@operator_required
@require_GET
def staff_dashboard(request):
    now = timezone.now()
    sessions = _sessions().filter(status='scheduled', starts_at__gte=now)
    stats = {'session_count': sessions.count(), 'capacity': sessions.aggregate(total=Sum('capacity'))['total'] or 0}
    active_bookings = Booking.objects.filter(session__status='scheduled', session__starts_at__gte=now)
    for status, key in [('confirmed', 'confirmed_count'), ('waitlisted', 'waitlisted_count')]:
        stats[key] = active_bookings.filter(status=status).aggregate(total=Sum('quantity'))['total'] or 0
    today = timezone.localdate()
    counts = {row['date']: row['count'] for row in Booking.objects.filter(created_at__date__gte=today - timedelta(days=6), created_at__date__lte=today).annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('pk'))}
    highest = max(counts.values(), default=1) or 1
    daily_counts = [{'date': today - timedelta(days=offset), 'count': counts.get(today - timedelta(days=offset), 0),
        'bar_width': round(counts.get(today - timedelta(days=offset), 0) * 100 / highest)} for offset in reversed(range(7))]
    return render(request, 'staff/dashboard.html', {'sessions': sessions[:8], 'stats': stats, 'daily_counts': daily_counts})


@operator_required
@require_GET
def staff_sessions(request):
    page = _page(request, _sessions().order_by('-starts_at'))
    return render(request, 'staff/session_list.html', {'sessions': page, 'page_obj': page})


@operator_required
@require_http_methods(['GET', 'POST'])
def staff_session_form(request, pk=None):
    session = get_object_or_404(ClassSession, pk=pk) if pk else None
    form = SessionForm(request.POST if request.method == 'POST' else None, instance=session)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data.copy()
        request_id, expected_revision = data.pop('request_id'), data.pop('expected_revision')
        try:
            result = services.save_session(actor=request.user, values=data, request_id=request_id, session_id=pk, expected_revision=expected_revision)
        except services.BookingError as error:
            if pk is None:
                form.add_error(None, error.message)
                form.data = form.data.copy()
                form.data['request_id'] = str(uuid.uuid4())
                return render(request, 'staff/session_form.html', {'form': form, 'session': None}, status=error.status)
            return _error(request, error, reverse('staff_session_edit', args=[pk]) if pk else reverse('staff_session_create'))
        messages.success(request, '회차 정보를 저장했습니다.')
        return redirect('staff_session_detail', pk=result['session_id'])
    return render(request, 'staff/session_form.html', {'form': form, 'session': session}, status=400 if request.method == 'POST' else 200)


@operator_required
@require_GET
def staff_session_detail(request, pk):
    session = get_object_or_404(_sessions(), pk=pk)
    bookings = Booking.objects.filter(session=session).select_related('member').order_by('queued_at', 'pk')
    confirmed = _page(request, bookings.filter(status='confirmed'), 50)
    waitlisted = Paginator(bookings.filter(status='waitlisted'), 50).get_page(request.GET.get('wait_page'))
    return render(request, 'staff/session_detail.html', {'session': session, 'confirmed': confirmed, 'waitlisted': waitlisted,
        'cancel_form': SessionCancelForm(initial={'expected_revision': session.revision})})


@operator_required
@require_POST
def staff_session_cancel(request, pk):
    get_object_or_404(ClassSession, pk=pk)
    form = SessionCancelForm(request.POST)
    if not form.is_valid():
        return render(request, 'booking/conflict.html', {'message': '취소 사유와 요청을 확인해 주세요.', 'form': form, 'recovery_url': reverse('staff_session_detail', args=[pk])}, status=400)
    try:
        services.cancel_session(actor=request.user, session_id=pk, **form.cleaned_data)
    except services.BookingError as error:
        return _error(request, error, reverse('staff_session_detail', args=[pk]))
    messages.success(request, '회차를 취소하고 신청자에게 알림을 남겼습니다.')
    return redirect('staff_session_detail', pk=pk)


@operator_required
@require_GET
def staff_audit(request):
    page = _page(request, AuditEvent.objects.select_related('actor', 'booking', 'session__course'), 30)
    return render(request, 'staff/audit.html', {'events': page, 'page_obj': page})


@require_http_methods(['GET', 'POST'])
def signup(request):
    form = SignupForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        member = form.save()
        login(request, member, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('session_list')
    return render(request, 'registration/signup.html', {'form': form}, status=400 if request.method == 'POST' else 200)


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    return JsonResponse({'status': 'ok'})
