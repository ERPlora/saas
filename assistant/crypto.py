"""The providers' keys, encrypted at rest (ASSISTANT-G26; saas#528 of the old product).

Fernet (AES-128-CBC + HMAC-SHA256) with ``settings.FERNET_KEY``, the scheme of WhatsApp's Meta credentials
(``whatsapp.crypto``): during a rotation ``FERNET_KEY_PREVIOUS`` still opens what it closed, and everything is
written with the current key (``MultiFernet``). The database and its backups only ever hold the token. Without a
key nothing is stored (``NotConfigured``), which the admin says out loud. ``rotate`` writes a token again with the
current key without the value ever leaving this module (``rotate_encryption_keys``, ASSISTANT-G03).
"""

import binascii

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class NotConfigured(Exception):
    """``FERNET_KEY`` is empty or is no Fernet key: no provider key can be kept."""


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


def _keys() -> list[Fernet]:
    if not configured():
        raise NotConfigured("FERNET_KEY is not set: no provider key can be kept.")
    keys = [settings.FERNET_KEY, getattr(settings, "FERNET_KEY_PREVIOUS", "")]
    return [Fernet(key.encode()) for key in keys if key and key_problem(key) is None]


def encrypt(value: str) -> str:
    """The token that stores ``value``."""
    return MultiFernet(_keys()).encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """The value ``token`` stores; ``Undecryptable`` if no live key opens it."""
    try:
        return MultiFernet(_keys()).decrypt(token.encode()).decode()
    except InvalidToken:
        raise Undecryptable("The token is no token of FERNET_KEY nor of FERNET_KEY_PREVIOUS.") from None


def is_current(token: str) -> bool:
    """Whether ``token`` is already written with ``FERNET_KEY``."""
    try:
        _keys()[0].decrypt(token.encode())
    except InvalidToken:
        return False
    return True


def rotate(token: str) -> str:
    """``token`` written again with ``FERNET_KEY``; ``Undecryptable`` if no live key opens it."""
    try:
        return MultiFernet(_keys()).rotate(token.encode()).decode()
    except InvalidToken:
        raise Undecryptable("The token is no token of FERNET_KEY nor of FERNET_KEY_PREVIOUS.") from None
