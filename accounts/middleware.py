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
