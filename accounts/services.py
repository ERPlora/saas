"""Writes of accounts: the one-time code of the jump to a hub (PLAN-SAAS §2.1, §3.1 steps 5-6).

Ported from ERPlora/saas ``AuthExchangeCode.issue``/``redeem`` (``apps/auth/users/models.py``),
with the code stored as its SHA-256, bound to one hub, and spent by a single conditional
``UPDATE … WHERE used_at IS NULL`` instead of ``select_for_update``. Two audiences: ``hub-session``
(a member enters their hub) and ``hub-admin`` (the platform's staff open a hub in the Hub's Django
admin at ``hubs.erplora.com``, ronda 13, PLAN §18).
"""

import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from live.slugs import validate_hub_slug

from accounts import queries
from accounts.models import AuthExchangeCode, HubMembership


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


class PlatformRoleRefused(Exception):
    """The account cannot take a platform role: it is a customer of a hub, or the role is unknown."""


class SupportGroupMissing(Exception):
    """The ``support`` group (data migration ``0003_support_group``) is not in the database."""


#: Platform roles, only for the SaaS admin: never stored in ``HubMembership`` nor sent to a hub.
PLATFORM_ADMIN = "admin"
PLATFORM_SUPPORT = "support"
PLATFORM_ROLES = (PLATFORM_ADMIN, PLATFORM_SUPPORT)
#: The group of ``support`` (view only on accounts), created by a data migration.
SUPPORT_GROUP = "support"
#: The role a ``hub-admin`` code carries to the Hub's admin: the platform's, never a ``hub_*`` one.
HUB_ADMIN_ROLE_ADMIN = "platform_admin"
HUB_ADMIN_ROLE_SUPPORT = "platform_support"
#: First label of the platform host ``hubs.erplora.com`` (ronda 13, PLAN §18): never a hub, so no
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
    """Whether ``hub_slug`` follows the rule shared with hub-next (``live.slugs``) and is no platform host."""
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
    """What ``user`` is on ``hub_slug`` for ``audience``: a member's ``hub_*`` role or a platform role."""
    if audience == AuthExchangeCode.HUB_ADMIN_AUDIENCE:
        return _platform_role(user)
    membership = HubMembership.objects.filter(user=user, hub_slug=hub_slug).first()
    return membership.role if membership is not None else None


def _needs_second_factor(user, audience: str) -> bool:
    """With ``ACCOUNTS_MFA_ENABLED``: ``hub-admin`` always, ``hub-session`` if the account has an app."""
    if not settings.ACCOUNTS_MFA_ENABLED:
        return False
    return audience == AuthExchangeCode.HUB_ADMIN_AUDIENCE or queries.has_totp(user)


def issue_code(
    user,
    hub_slug: str,
    *,
    audience: str = AuthExchangeCode.HUB_SESSION_AUDIENCE,
    second_factor: bool = False,
) -> str:
    """Mint a one-time code for ``user`` to enter ``hub_slug``; return it (only its hash is kept).

    ``hub-session`` needs a membership of the hub. ``hub-admin`` needs no membership, only an
    active staff account with a platform role (``_platform_role``). A reserved or malformed slug,
    or the platform host, is refused even if a membership row names it (rows saved without
    validation, or before the shared rule).

    ``second_factor`` is whether the caller's session passed the second factor
    (``mfa.mfa_completed(request)``); it only counts with ``ACCOUNTS_MFA_ENABLED`` on. Then
    ``hub-admin`` always needs it (PLAN-SAAS §2.1, PLAN §17-§18), and ``hub-session`` needs it from an
    account that turned on an authenticator app; without it, ``SecondFactorRequired``. The access
    is checked first: a stranger is refused as one, whatever their second factor.
    """
    if audience not in (AuthExchangeCode.HUB_SESSION_AUDIENCE, AuthExchangeCode.HUB_ADMIN_AUDIENCE):
        raise ValueError(f"unknown audience {audience!r}")
    if not is_hub_slug(hub_slug) or _role_in(user, hub_slug, audience) is None:
        raise HubAccessDenied(hub_slug)
    if not second_factor and _needs_second_factor(user, audience):
        raise SecondFactorRequired(hub_slug)
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
    re-checked at redemption (an active account, and its membership for ``hub-session`` or its
    platform role for ``hub-admin``): a code does not outlive the access it was minted for. A
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


def seed_demo_owner(email: str, password: str, hub_slugs: list[str]):
    """Create (or leave as it is) a customer account that owns every hub in ``hub_slugs``.

    A customer is never staff: owning a hub gives no access to the platform's admin.
    """
    return seed_demo_member(email, password, hub_slugs, HubMembership.Role.OWNER)


def seed_demo_member(email: str, password: str, hub_slugs: list[str], role: str):
    """Create (or leave as it is) a customer account with ``role`` in every hub in ``hub_slugs``.

    ``role`` is a customer role (``hub_*``); a platform role is refused, since it never belongs to a
    hub's member. A customer is never staff, whatever their role in a hub.
    """
    if role not in HubMembership.Role.values:
        raise ValueError(f"{role!r} is not a customer role")
    with transaction.atomic():
        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            user = get_user_model().objects.create_user(email=email, password=password)
        for slug in hub_slugs:
            HubMembership.objects.get_or_create(
                user=user, hub_slug=slug, defaults={"role": role}
            )
    return user


def create_platform_user(email: str, role: str, password: str | None = None):
    """Create or update a member of the platform's staff; return ``(user, created)``.

    ``admin`` is a superuser; ``support`` is staff in the ``support`` group (view only). An
    existing account takes the role and keeps its password unless ``password`` is given; a new
    one without ``password`` has no usable password. A customer of a hub is refused: platform and
    customer roles never share an account.
    """
    if role not in PLATFORM_ROLES:
        raise PlatformRoleRefused(f"unknown platform role {role!r}")
    user_model = get_user_model()
    email = user_model.objects.normalize_email(email).lower()
    with transaction.atomic():
        support = Group.objects.filter(name=SUPPORT_GROUP).first()
        if support is None:
            raise SupportGroupMissing(SUPPORT_GROUP)
        user = user_model.objects.select_for_update().filter(email=email).first()
        created = user is None
        if created:
            user = user_model(email=email)
        elif HubMembership.objects.filter(user=user).exists():
            raise PlatformRoleRefused(f"{email} is a customer of a hub")
        if password is not None:
            user.set_password(password)
        elif created:
            user.set_unusable_password()
        user.is_staff = True
        user.is_superuser = role == PLATFORM_ADMIN
        user.save()
        if role == PLATFORM_SUPPORT:
            user.groups.add(support)
        else:
            user.groups.remove(support)
    return user, created


def seed_demo_platform_admin(email: str, password: str):
    """Create (or leave as it is) a platform administrator: superuser of the admin, member of no hub."""
    user = get_user_model().objects.filter(email=email).first()
    if user is None:
        user, _ = create_platform_user(email, PLATFORM_ADMIN, password)
    return user
