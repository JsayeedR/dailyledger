from django.shortcuts import redirect
from .models import PageViewCounter

EXEMPT_PATH_PREFIXES = ('/admin', '/static', '/media', '/login', '/logout', '/register', '/about', '/accounts/setup')


class PageViewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # path_info excludes the /dailyledger script-name prefix — path does not.
        path = request.path_info
        if request.method == 'GET' and not path.startswith('/admin') and not path.startswith('/static') and not path.startswith('/media'):
            try:
                PageViewCounter.increment()
            except Exception:
                pass
        return response


class SetupWizardMiddleware:
    """Forces every authenticated user with an incomplete workspace setup
    to the setup wizard before they can use the rest of the app."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and hasattr(user, 'tenant'):
            if not user.tenant.setup_completed and not request.path_info.startswith(EXEMPT_PATH_PREFIXES):
                return redirect('accounts:setup_wizard')
        return self.get_response(request)


from django.conf import settings
from django.utils import timezone as _tz
from datetime import timedelta as _timedelta

IDLE_TIMEOUT = _timedelta(minutes=getattr(settings, 'ACTIVITY_IDLE_TIMEOUT_MINUTES', 20))


class ActivityTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            now = _tz.now()
            if user.last_seen is None or (now - user.last_seen) > IDLE_TIMEOUT:
                user.session_count += 1
            else:
                gap = (now - user.last_seen).total_seconds()
                user.total_active_seconds += int(gap)
            user.last_seen = now
            user.save(update_fields=['last_seen', 'total_active_seconds', 'session_count'])
        return response
