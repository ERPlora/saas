"""The one-time code that brings a sign-in from the device's browser into the installed app's window.

The same row as the jump to a hub (``AuthExchangeCode``: only a hash kept, a minute of life, spent once by a
conditional ``UPDATE``), under its own audience and with no hub. The hash covers the code and the challenge of the
app's secret (PKCE ``S256``): only the window that knows both finds the row.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import AuthExchangeCode

#: Never a jump's nor a pass's: ``hub_jump.redeem_code`` finds none of these.
APP_SESSION_AUDIENCE = "app-session"


class InvalidAppCode(Exception):
    """Unknown for that challenge, expired, already spent, or for an account closed meanwhile."""


def _hash(code: str, challenge: str) -> str:
    return AuthExchangeCode.hash_code(f"{challenge}:{code}")


def issue_code(user, challenge: str) -> str:
    """Mint a code that opens ``user``'s session in the window holding ``challenge``; return it."""
    code = secrets.token_urlsafe(32)
    now = timezone.now()
    AuthExchangeCode.objects.create(
        code_hash=_hash(code, challenge),
        user=user,
        audience=APP_SESSION_AUDIENCE,
        hub_slug="",
        created_at=now,
        expires_at=now + timedelta(seconds=settings.EXCHANGE_CODE_TTL_SECONDS),
    )
    return code


def redeem_code(code: str, challenge: str):
    """Spend ``code`` minted for ``challenge``; return the account it opens a session for."""
    if not code:
        raise InvalidAppCode
    now = timezone.now()
    code_hash = _hash(code, challenge)
    with transaction.atomic():
        spent = AuthExchangeCode.objects.filter(
            code_hash=code_hash,
            audience=APP_SESSION_AUDIENCE,
            used_at__isnull=True,
            expires_at__gt=now,
        ).update(used_at=now)
        if spent != 1:
            raise InvalidAppCode
        user = AuthExchangeCode.objects.select_related("user").get(code_hash=code_hash).user
    if not user.is_active:
        raise InvalidAppCode
    return user
