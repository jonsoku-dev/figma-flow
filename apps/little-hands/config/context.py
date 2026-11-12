from django.conf import settings

def service_context(request):
    unread = 0
    if request.user.is_authenticated:
        from booking.models import Notification
        unread = Notification.objects.filter(member=request.user, read_at__isnull=True).count()
    return {'service_name':'작은손 커피공방', 'service_environment':settings.ENVIRONMENT,
            'service_staging':settings.ENVIRONMENT != 'production', 'notifications_unread':unread}
