from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet():
    key = settings.ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_value(raw: str) -> str:
    """Encrypts a secret (SMTP password, bot token) before storing it in the DB."""
    if not raw:
        return ''
    return _get_fernet().encrypt(raw.encode()).decode()


def decrypt_value(token: str) -> str:
    """Decrypts a stored secret. Returns '' on any failure rather than raising,
    so a corrupted/old value never crashes a page — it just shows as unset."""
    if not token:
        return ''
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except Exception:
        return ''
