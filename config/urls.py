from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views
from ledger import views as ledger_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', account_views.login_view, name='login'),
    path('logout/', account_views.logout_view, name='logout'),
    path('register/', account_views.register, name='register'),
    path('about/', ledger_views.about, name='about'),
    path('accounts/', include('accounts.urls')),
    path('', include('ledger.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
