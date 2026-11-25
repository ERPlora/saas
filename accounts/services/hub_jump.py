"""The one-time code of the jump to a hub.

The jump code is stored as its SHA-256, bound to one hub, and spent by a single conditional
``UPDATE … WHERE used_at IS NULL`` instead of ``select_for_update``. Two audiences: ``hub-session``
(a member enters their hub, and the platform's staff enter a business they are no member of as its
support, ``hub_support``) and ``hub-admin`` (the platform's staff open a hub in the Hub's Django
admin at ``hubs.erplora.com``). The business decides whether support comes in: the Hub refuses a
``hub_support`` code while the business has its support access off.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from live.slugs import validate_hub_slug

from accounts.models import AuthExchangeCode
from accounts.queries import account_hubs, two_factor
from accounts.services.platform_staff import SUPPORT_GROUP

logger = logging.getLogger(__name__)


class HubAccessDenied(Exception):
    """The account is no member of the hub it wants to enter, or that is no hub slug."""


class SecondFactorRequired(HubAccessDenied):
    """With ``ACCOUNTS_MFA_ENABLED``, the session has not passed the second factor this code needs.

    A ``HubAccessDenied``: a caller that does not know it still refuses the jump.
    """


class InvalidCode(Exception):
    """The code is unknown, expired, already used, for another hub or for an account that lost access.

    Also when the hub is no hub slug (``live.slugs``): no reserved name ever gets a session.
    """


#: The role a ``hub-admin`` code carries to the Hub's admin: the platform's, never a ``hub_*`` one.
HUB_ADMIN_ROLE_ADMIN = "platform_admin"
HUB_ADMIN_ROLE_SUPPORT = "platform_support"
#: The role of the platform's staff in a business they are no member of: they enter it as ERPlora's support.
HUB_SUPPORT_ROLE = "hub_support"
#: First label of the platform host ``hubs.erplora.com``: never a hub, so no
#: code of either audience names it. ``live.slugs`` reserves it as well; it is refused here too so
#: the SaaS never mints a code for its own host, whatever the shared list says.
PLATFORM_HOST_SLUG = "hubs"


@dataclass(frozen=True)
class HubIdentity:
    """Who the hub opens a session for: the body of ``/internal/auth/redeem``."""

    user_id: str
    email: str
    name: str
    locale: str
    role: str


def is_hub_slug(hub_slug) -> bool:
    """Whether ``hub_slug`` follows the rule shared with the Hub (``live.slugs``) and is no platform host."""
    try:
        validate_hub_slug(hub_slug)
    except ValueError:
        return False
    return hub_slug != PLATFORM_HOST_SLUG


def _platform_role(user) -> str | None:
    """The role ``user`` takes in the Hub's admin, or ``None`` if they may not enter it.

    Only an active staff account with a platform role: ``platform_admin`` for a superuser,
    ``platform_support`` for the ``support`` group. Customers are never staff.
    """
    if not (user.is_active and user.is_staff):
        return None
    if user.is_superuser:
        return HUB_ADMIN_ROLE_ADMIN
    if user.groups.filter(name=SUPPORT_GROUP).exists():
        return HUB_ADMIN_ROLE_SUPPORT
    return None


def _role_in(user, hub_slug: str, audience: str) -> str | None:
    """What ``user`` is on ``hub_slug`` for ``audience``: a member's ``hub_*`` role, ``hub_support`` for the platform's
    staff on a business they are no member of, or a platform role in the Hub admin."""
    if audience == AuthExchangeCode.HUB_ADMIN_AUDIENCE:
        return _platform_role(user)
    role = account_hubs.hub_roles_of(user).get(hub_slug)
    if role is None and _platform_role(user) is not None:
        return HUB_SUPPORT_ROLE
    return role


def _needs_second_factor(user, audience: str, role: str) -> bool:
    """With ``ACCOUNTS_MFA_ENABLED``: ``hub-admin`` and support always, a member if the account has an app."""
    if not settings.ACCOUNTS_MFA_ENABLED:
        return False
    return audience == AuthExchangeCode.HUB_ADMIN_AUDIENCE or role == HUB_SUPPORT_ROLE or two_factor.has_totp(user)


def issue_code(
    user,
    hub_slug: str,
    *,
    audience: str = AuthExchangeCode.HUB_SESSION_AUDIENCE,
    second_factor: bool = False,
) -> str:
    """Mint a one-time code for ``user`` to enter ``hub_slug``; return it (only its hash is kept).

    ``hub-session`` needs a membership of the hub, or else an active staff account with a platform
    role, which enters as support (``hub_support``). ``hub-admin`` needs no membership, only an
    active staff account with a platform role (``_platform_role``). A reserved or malformed slug,
    or the platform host, is refused even if a membership row names it (rows saved without
    validation, or before the shared rule).

    ``second_factor`` is whether the caller's session passed the second factor
    (``mfa.mfa_completed(request)``); it only counts with ``ACCOUNTS_MFA_ENABLED`` on. Then
    ``hub-admin`` and support always need it, and a member needs it from an
    account that turned on an authenticator app; without it, ``SecondFactorRequired``. The access
    is checked first: a stranger is refused as one, whatever their second factor.
    """
    if audience not in (AuthExchangeCode.HUB_SESSION_AUDIENCE, AuthExchangeCode.HUB_ADMIN_AUDIENCE):
        raise ValueError(f"unknown audience {audience!r}")
    role = _role_in(user, hub_slug, audience) if is_hub_slug(hub_slug) else None
    if role is None:
        raise HubAccessDenied(hub_slug)
    if not second_factor and _needs_second_factor(user, audience, role):
        raise SecondFactorRequired(hub_slug)
    if role == HUB_SUPPORT_ROLE:
        logger.info("hub_login.hub_support user=%s hub=%s", user.pk, hub_slug)
    code = secrets.token_urlsafe(32)
    now = timezone.now()
    AuthExchangeCode.objects.create(
        code_hash=AuthExchangeCode.hash_code(code),
        user=user,
        audience=audience,
        hub_slug=hub_slug,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.EXCHANGE_CODE_TTL_SECONDS),
    )
    return code


def redeem_code(code: str, hub_slug: str, *, audience: str = AuthExchangeCode.HUB_SESSION_AUDIENCE) -> HubIdentity:
    """Spend ``code`` for ``hub_slug`` and ``audience``; return who it opens a session for.

    The code is spent by one conditional ``UPDATE``, so two concurrent redemptions cannot both
    win. A code for another hub or another audience is refused without spending it. The access is
    re-checked at redemption (an active account, and the membership or the platform role it was
    minted for): a code does not outlive the access it was minted for. A
    reserved or malformed hub, or the platform host, is refused before the code is looked up, so it
    is not spent.
    """
    if not code or not is_hub_slug(hub_slug):
        raise InvalidCode
    now = timezone.now()
    code_hash = AuthExchangeCode.hash_code(code)
    with transaction.atomic():
        spent = AuthExchangeCode.objects.filter(
            code_hash=code_hash,
            audience=audience,
            hub_slug=hub_slug,
            used_at__isnull=True,
            expires_at__gt=now,
        ).update(used_at=now)
        if spent != 1:
            raise InvalidCode
        user = AuthExchangeCode.objects.select_related("user").get(code_hash=code_hash).user
        role = _role_in(user, hub_slug, audience)
    if not user.is_active or role is None:
        raise InvalidCode
    return HubIdentity(
        user_id=str(user.pk),
        email=user.email,
        name=user.get_full_name() or user.email,
        locale=user.language,
        role=role,
    )
