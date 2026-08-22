from .models import PageViewCounter


def page_views(request):
    try:
        return {'page_views': PageViewCounter.current()}
    except Exception:
        return {'page_views': 0}
