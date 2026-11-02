"""Encrypts third-party credentials stored in the database."""
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from .config import settings


def _cipher():
    if len(settings.secret_key) < 16:
        raise ValueError('Set SECRET_KEY on the server before saving credentials.')
    material = hashlib.sha256(b'tura-settings-v1:' + settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Returns an empty value when SECRET_KEY has changed since it was saved."""
    if not value:
        return ''
    try:
        return _cipher().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ''
