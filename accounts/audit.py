from .models import AuditLog


def log(actor=None, action='', target_type='', target_id='', detail='', request=None):
    """Best-effort audit write. Never blocks or breaks the calling action."""
    ip_address = None
    user_agent = ''
    if request is not None:
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
    try:
        AuditLog.objects.create(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else '',
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception:
        pass
