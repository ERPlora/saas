"""The Meta credentials of a WhatsApp number (its business token and its PIN), encrypted at rest (WHATSAPP-G04).

Fernet (AES-128-CBC + HMAC-SHA256) with ``settings.FERNET_KEY``, as the old product did (``fernet_fields``);
during a rotation ``FERNET_KEY_PREVIOUS`` still opens what it closed, and everything is written with the
current key (``MultiFernet``). The database and its backups only ever hold the token (saas#1906). Without a
key nothing is stored: a number cannot be connected (``NotConfigured``), which the doors say out loud.
"""

import binascii

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class NotConfigured(Exception):
    """``FERNET_KEY`` is empty: no credential of Meta can be kept."""


class Undecryptable(Exception):
    """The stored token is no token of the current key nor of the previous one."""


def key_problem(key: str) -> str | None:
    """Why ``key`` cannot encrypt, or ``None`` when it is a Fernet key."""
    try:
        Fernet(key.encode())
    except (ValueError, binascii.Error) as problem:
        return str(problem) or "not a Fernet key"
    return None


def configured() -> bool:
    key = str(getattr(settings, "FERNET_KEY", "") or "")
    return bool(key) and key_problem(key) is None


def _fernet() -> MultiFernet:
    if not configured():
        raise NotConfigured("FERNET_KEY is not set: no credential of Meta can be kept.")
    keys = [settings.FERNET_KEY, getattr(settings, "FERNET_KEY_PREVIOUS", "")]
    return MultiFernet([Fernet(key.encode()) for key in keys if key and key_problem(key) is None])


def encrypt(value: str) -> str:
    """The token that stores ``value``."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """The value ``token`` stores; ``Undecryptable`` if no live key opens it."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise Undecryptable("The credential is no token of FERNET_KEY nor of FERNET_KEY_PREVIOUS.") from None
