"""Two-factor authentication: whether an account has an authenticator app, and whether this browser is trusted
to skip its code."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.internal.flows.trust import create_config_fingerprint, decode_trust_cookie
from allauth.mfa.models import Authenticator
from django.conf import settings
from live.context import OperationContext
from live.operations import AI, operation

from accounts.queries.account_lookup import account_of
from accounts.schemas import BrowserTrustGetIn, BrowserTrustOut


def has_totp(user) -> bool:
    """Whether ``user`` has turned on an authenticator app. Recovery codes alone are no second factor:
    they are the way back in when the phone is lost."""
    if not user.is_authenticated:
        return False
    return Authenticator.objects.filter(user_id=user.pk, type=Authenticator.Type.TOTP).exists()


def owns_authenticator(user, ids: Iterable) -> bool:
    """Whether one of ``ids`` (pks of ``Authenticator``) is an authenticator of ``user``."""
    pks = {pk for pk in ids if pk is not None}
    if not pks:
        return False
    return Authenticator.objects.filter(user_id=user.pk, pk__in=pks).exists()


def browser_trusted_until(user, request) -> datetime | None:
    """Until when ``request``'s browser skips ``user``'s app code at sign-in, or ``None``.

    The trust is allauth's ``mfa_trusted`` cookie (``MFA_TRUST_ENABLED``): signed entries of a fingerprint of the
    account's password and authenticators and the moment it was given. One of them for the account as it is now, and
    younger than ``MFA_TRUST_COOKIE_AGE``, trusts this browser; the newest says until when. Nothing is kept on the
    server, so no other browser can be told. Only an account with the app, and only with ``ACCOUNTS_MFA_ENABLED``:
    off, no sign-in asks for the app.
    """
    if request is None or not settings.ACCOUNTS_MFA_ENABLED or not has_totp(user):
        return None
    fingerprint = create_config_fingerprint(user)
    given = [trust.at for trust in decode_trust_cookie(request) if trust.fingerprint == fingerprint]
    if not given:
        return None
    return datetime.fromtimestamp(max(given), tz=UTC) + mfa_settings.TRUST_COOKIE_AGE


@operation(
    "accounts.browser_trust.get",
    kind="query",
    permission="accounts.view",
    input=BrowserTrustGetIn,
    output=BrowserTrustOut,
    ai=AI(
        description="Whether this browser is trusted for two-factor authentication, and until when.",
        asks={
            "en": (
                "is this browser trusted for 2FA?",
                "will it ask me for the code again on this computer?",
                "until when does this browser skip the two-step code?",
            ),
            "es": (
                "¿este navegador es de confianza?",
                "¿me volverá a pedir el código en este ordenador?",
                "¿hasta cuándo no me pide aquí el segundo factor?",
            ),
        },
    ),
)
def browser_trust_get(ctx: OperationContext, data: BrowserTrustGetIn) -> dict[str, Any]:
    """Security → Two-factor authentication: whether this browser is trusted, and until when."""
    return {"trusted_until": browser_trusted_until(account_of(ctx), ctx.request)}
