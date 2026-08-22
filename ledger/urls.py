from django.urls import path
from . import views

app_name = 'ledger'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/add/', views.add_transaction, name='add_transaction'),
    path('transactions/<uuid:pk>/edit/', views.edit_transaction, name='edit_transaction'),
    path('transactions/<uuid:pk>/delete/', views.delete_transaction, name='delete_transaction'),
    path('budgets/', views.budget_list, name='budget_list'),
    path('budgets/add/', views.add_budget, name='add_budget'),
    path('budgets/<uuid:pk>/delete/', views.delete_budget, name='delete_budget'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/<int:year>/<int:month>/<int:day>/', views.day_detail, name='day_detail'),
    path('spreadsheet/', views.spreadsheet_view, name='spreadsheet'),
    path('reports/', views.reports_view, name='reports'),
    path('detail-reports/', views.detail_reports_view, name='detail_reports'),
    path('settings/', views.manage_settings, name='manage_settings'),
    path('settings/category/add/', views.add_category, name='add_category'),
    path('settings/category/<uuid:pk>/toggle/', views.toggle_category, name='toggle_category'),
    path('settings/payment-method/add/', views.add_payment_method, name='add_payment_method'),
    path('settings/payment-method/<uuid:pk>/toggle/', views.toggle_payment_method, name='toggle_payment_method'),
]
