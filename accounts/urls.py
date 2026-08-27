from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('setup/', views.setup_wizard, name='setup_wizard'),
    path('password/', views.change_password, name='change_password'),
    path('profile/', views.profile_view, name='profile'),
    path('notification-settings/', views.notification_settings_view, name='notification_settings'),
    path('notification-preference/', views.notification_preference_view, name='notification_preference'),
    path('preference-approvals/', views.preference_approvals, name='preference_approvals'),
    path('preference-approvals/<uuid:pref_id>/approve/', views.approve_preference, name='approve_preference'),
    path('preference-approvals/<uuid:pref_id>/reject/', views.reject_preference, name='reject_preference'),
    path('approvals/', views.user_approvals, name='user_approvals'),
    path('approvals/<uuid:user_id>/approve/', views.approve_user, name='approve_user'),
    path('approvals/<uuid:user_id>/reject/', views.reject_user, name='reject_user'),
    path('audit-log/', views.audit_log_view, name='audit_log'),
    path('activity/', views.user_activity_view, name='user_activity'),
    path('users/', views.user_list, name='user_list'),
    path('users/<uuid:user_id>/profile/', views.user_profile_view, name='user_profile'),
    path('users/<uuid:user_id>/set-notification-preference/', views.set_notification_preference_admin, name='set_notification_preference_admin'),
    path('users/<uuid:user_id>/toggle-active/', views.toggle_user_active, name='toggle_user_active'),
]
