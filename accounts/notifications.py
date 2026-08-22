import json
import urllib.request
import urllib.error
from django.core.mail import EmailMessage, get_connection


def send_email(settings_obj, to_email, subject, body):
    if not settings_obj.is_email_configured():
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
        return True, 'Sent successfully.'
    except Exception as e:
        return False, str(e)


def send_telegram(settings_obj, chat_id, text):
    if not settings_obj.is_telegram_configured():
        return False, 'Telegram bot is not configured yet.'
    if not chat_id:
        return False, 'No Telegram Chat ID provided for this user.'
    token = settings_obj.telegram_bot_token
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get('ok'):
                return True, 'Sent successfully.'
            return False, result.get('description', 'Unknown Telegram API error.')
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            return False, body.get('description', f'HTTP {e.code} error.')
        except Exception:
            return False, f'HTTP {e.code} error from Telegram (could not read details).'
    except urllib.error.URLError as e:
        return False, str(e)
