from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.session_list, name='session_list'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/review/', views.reserve_preview, name='reserve_preview'),
    path('sessions/<int:pk>/reserve/', views.reserve, name='reserve'),
    path('bookings/', views.my_bookings, name='my_bookings'),
    path('bookings/<uuid:public_id>/', views.booking_detail, name='booking_detail'),
    path('bookings/<uuid:public_id>/cancel/', views.cancel, name='cancel'),
    path('bookings/<uuid:public_id>/reschedule/', views.reschedule, name='reschedule'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/read/', views.notification_read, name='notification_read'),
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/sessions/', views.staff_sessions, name='staff_sessions'),
    path('staff/sessions/new/', views.staff_session_form, name='staff_session_create'),
    path('staff/sessions/<int:pk>/edit/', views.staff_session_form, name='staff_session_edit'),
    path('staff/sessions/<int:pk>/', views.staff_session_detail, name='staff_session_detail'),
    path('staff/sessions/<int:pk>/cancel/', views.staff_session_cancel, name='staff_session_cancel'),
    path('staff/audit/', views.staff_audit, name='staff_audit'),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/signup/', views.signup, name='signup'),
    path('health/', views.health, name='health'),
]
