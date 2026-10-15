"""The documents of an authorisation, encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) and
``settings.FISCAL_DOCUMENTS_KEY``, as the old product did with ``FISCAL_ENCRYPTION_KEY``.

They carry personal data (a copy of an identity card, a signature): the database and its backups only ever
hold the token, and only the admin's review page decrypts them, for the staff who decide (``fiscal.admin``).
Nothing here reaches the database. The key is checked at start-up (``fiscal.checks``, ``fiscal.E001``).
"""

import binascii

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class Undecryptable(Exception):
    """The stored bytes are no token of the current key (another key, or damaged)."""


def _fernet() -> Fernet:
    return Fernet(settings.FISCAL_DOCUMENTS_KEY.encode())


def encrypt(data: bytes) -> bytes:
    """The token that stores ``data``."""
    return _fernet().encrypt(bytes(data))


def decrypt(token: bytes | memoryview) -> bytes:
    """The bytes ``token`` stores; ``Undecryptable`` if it is no token of the current key."""
    try:
        return _fernet().decrypt(bytes(token))
    except InvalidToken:
        raise Undecryptable(
            "The document is no token of FISCAL_DOCUMENTS_KEY."
        ) from None


def key_problem(key: str) -> str | None:
    """Why ``key`` cannot encrypt the documents, or ``None`` when it is a Fernet key."""
    try:
        Fernet(key.encode())
    except (ValueError, binascii.Error) as problem:
        return str(problem) or "not a Fernet key"
    return None
