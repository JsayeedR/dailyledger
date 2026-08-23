import json
import urllib.request
import urllib.error
from django.core.mail import EmailMessage, get_connection
from . import audit


def notify_super_admins(subject, email_body, telegram_text=None, actor=None):
    """Alerts every active Super Admin by email and Telegram about something
    that needs their attention (a new pending signup, a pending preference
    change request, etc). Called once per event by the caller — this function
    itself doesn't dedupe, so callers should only invoke it right when the
    item first becomes pending, not on every page view."""
    from .models import CustomUser, Role, ApprovalStatus, NotificationSettings

    settings_obj = NotificationSettings.get_solo()
    admins = CustomUser.objects.filter(role=Role.SUPER_ADMIN, approval_status=ApprovalStatus.APPROVED, is_active=True)

    for admin in admins:
        if admin.email:
            send_email(settings_obj, admin.email, subject, email_body, actor=actor)
        if admin.telegram_id:
            send_telegram(settings_obj, admin.telegram_id, telegram_text or email_body, actor=actor)


def send_email(settings_obj, to_email, subject, body, actor=None):
    if not settings_obj.is_email_configured():
        audit.log(
            actor=actor,
            action='EMAIL_FAILED',
            target_type='Email',
            target_id=to_email,
            detail='Email is not configured.',
        )
        return False, 'Email is not configured yet.'
    try:
        connection = get_connection(
            host=settings_obj.smtp_host,
            port=settings_obj.smtp_port,
            username=settings_obj.smtp_username,
            password=settings_obj.smtp_password,
            use_tls=settings_obj.smtp_use_tls,
            timeout=15,
        )
        display_name = settings_obj.from_display_name or 'DailyLedger'
        from_header = f'"{display_name}" <{settings_obj.smtp_username}>'
        reply_to = settings_obj.reply_to_email or settings_obj.smtp_username

        msg = EmailMessage(
            subject, body, from_header, [to_email],
            connection=connection,
            reply_to=[reply_to],
        )
        msg.send()

        audit.log(
            actor=actor,
            action='EMAIL_SENT',
            target_type='Email',
            target_id=to_email,
            detail=f'Email sent: {subject}'[:255],
        )

        return True, 'Sent successfully.'
    except Exception as e:
        audit.log(
            actor=actor,
            action='EMAIL_FAILED',
            target_type='Email',
            target_id=to_email,
            detail=f'Email failed: {str(e)}'[:255],
        )
        return False, str(e)


def send_telegram(settings_obj, chat_id, text, actor=None):
    if not settings_obj.is_telegram_configured():
        audit.log(
            actor=actor,
            action='TELEGRAM_FAILED',
            target_type='Telegram',
            target_id=chat_id,
            detail='Telegram bot is not configured.',
        )
        return False, 'Telegram bot is not configured yet.'
    if not chat_id:
        audit.log(
            actor=actor,
            action='TELEGRAM_FAILED',
            target_type='Telegram',
            target_id='',
            detail='No Telegram Chat ID provided.',
        )
        return False, 'No Telegram Chat ID provided for this user.'

    token = settings_obj.telegram_bot_token
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())

            if result.get('ok'):
                audit.log(
                    actor=actor,
                    action='TELEGRAM_SENT',
                    target_type='Telegram',
                    target_id=chat_id,
                    detail='Telegram message sent successfully.',
                )
                return True, 'Sent successfully.'

            detail = result.get('description', 'Unknown Telegram API error.')
            audit.log(
                actor=actor,
                action='TELEGRAM_FAILED',
                target_type='Telegram',
                target_id=chat_id,
                detail=f'Telegram failed: {detail}'[:255],
            )
            return False, detail

    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            detail = body.get('description', f'HTTP {e.code} error.')
        except Exception:
            detail = f'HTTP {e.code} error from Telegram (could not read details).'

        audit.log(
            actor=actor,
            action='TELEGRAM_FAILED',
            target_type='Telegram',
            target_id=chat_id,
            detail=f'Telegram failed: {detail}'[:255],
        )
        return False, detail

    except urllib.error.URLError as e:
        detail = str(e)
        audit.log(
            actor=actor,
            action='TELEGRAM_FAILED',
            target_type='Telegram',
            target_id=chat_id,
            detail=f'Telegram failed: {detail}'[:255],
        )
        return False, detail

    except Exception as e:
        detail = str(e)
        audit.log(
            actor=actor,
            action='TELEGRAM_FAILED',
            target_type='Telegram',
            target_id=chat_id,
            detail=f'Telegram failed: {detail}'[:255],
        )
        return False, detail
