from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import AuditEvent, Booking, ClassSession, Course, Notification, Operation, Room


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'price_krw', 'active']
    prepopulated_fields = {'slug': ['title']}


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'capacity']

    def get_readonly_fields(self, request, obj=None):
        return ['capacity'] if obj else []

    def save_model(self, request, obj, form, change):
        if change and Room.objects.get(pk=obj.pk).capacity != obj.capacity:
            raise ValidationError('공간 정원은 생성 후 변경할 수 없습니다.')
        super().save_model(request, obj, form, change)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in [Booking, ClassSession, AuditEvent, Operation, Notification]:
    admin.site.register(model, ReadOnlyAdmin)
