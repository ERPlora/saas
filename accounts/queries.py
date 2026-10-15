"""Reads of accounts: the hubs an account can enter (``accounts.hub.list``, the launcher's), the
re-read of an account before a live re-run, the hubs the admin's «Open in the Hub admin» lists, the
authenticators of the second factor (``mfa.py``), whether an email has an account (the unified login),
whether an account proved its email or has any way in (the invitation of ``hubs``, saas#2541), and the
Account page (plan 2026-10-13, L3-A): the profile, the
preferences, the live sessions and the API keys, and the key a request carries (``api_auth``)."""

import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode, urlsplit

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone, translation
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Unauthorized
from live.operations import operation

from accounts.models import (
    API_KEY_PREFIX_LENGTH,
    API_KEY_SCOPES,
    ApiKey,
    EmailChangeRequest,
    HubMembership,
    ProfilePhoto,
    UserPreferences,
)
from accounts.schemas import (
    ApiKeyListIn,
    ApiKeyListOut,
    HubListIn,
    HubListOut,
    PreferencesGetIn,
    PreferencesOut,
    ProfileGetIn,
    ProfileOut,
    SessionListIn,
    SessionListOut,
)


def hub_slugs_of(user) -> list[str]:
    """The slugs of the hubs ``user`` is a member of, alphabetically."""
    return list(HubMembership.objects.filter(user=user).order_by("hub_slug").values_list("hub_slug", flat=True))


def hubs_with_members() -> list[tuple[str, int]]:
    """Every hub with members, alphabetically, as ``(slug, member count)``.

    The SaaS has no ``Hub`` model yet (``HubMembership`` stands in), so a hub is a slug with members.
    """
    rows = HubMembership.objects.values("hub_slug").annotate(members=Count("id")).order_by("hub_slug")
    return [(row["hub_slug"], row["members"]) for row in rows]


def hub_admin_path(slug: str) -> str:
    """The deep link of the hub ``slug`` in the Hub's admin at ``hubs.erplora.com`` (PLAN §18.1.5)."""
    return f"/admin/hub/{slug}/"


def active_user(pk):
    """The account ``pk`` read again from the database, or ``None`` if it was deleted or deactivated."""
    return get_user_model().objects.filter(pk=pk, is_active=True).first()


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


def hub_origin(slug: str) -> str:
    """``scheme://host`` of the hub ``slug``, from the callback the jump posts to (``HUB_CALLBACK_TEMPLATE``)."""
    callback = urlsplit(settings.HUB_CALLBACK_TEMPLATE.format(slug=slug))
    return f"{callback.scheme}://{callback.netloc}"


#: Where a hub starts every jump into it: it binds the jump to the browser (the ``state`` cookie)
#: and only then sends it to the SaaS's ``/hub-login/`` (login CSRF; ``accounts.handoff``).
HUB_START_PATH = "/auth/login"


def local_path(value: str) -> str:
    """``value`` if it is a path on the hub (``/…``, not ``//host`` nor ``/\\host``), else ``/``."""
    parts = urlsplit(value)
    if not value.startswith("/") or value.startswith(("//", "/\\")) or parts.scheme or parts.netloc:
        return "/"
    return value


def hub_start_url(slug: str, next_path: str = "/") -> str:
    """The jump to the hub ``slug``, landing on ``next_path`` there (a non-local path lands on ``/``).

    It starts at the hub: ``http://a.localhost:8000/auth/login?next=/`` locally,
    ``https://a.erplora.com/auth/login?next=/`` in production (``hub_origin``). A link straight to
    ``/hub-login/`` would carry no ``state``, and the Hub refuses it. Also for ``hubs`` (one place).
    """
    return f"{hub_origin(slug)}{HUB_START_PATH}?{urlencode({'next': local_path(next_path)}, safe='/')}"


@operation("accounts.hub.list", kind="query", permission=None, input=HubListIn, output=HubListOut)
def hub_list(ctx: OperationContext, data: HubListIn) -> dict[str, Any]:
    """The hubs of the signed-in account, alphabetically, each with its host and the jump to it.

    No permission: every account may read its own hubs. But only an account: a caller without one
    (anonymous) is refused, whatever route or stream asks.
    """
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to see your businesses."))
    return {
        "hubs": [
            {"slug": slug, "host": urlsplit(hub_origin(slug)).netloc, "url": hub_start_url(slug)}
            for slug in hub_slugs_of(ctx.actor)
        ]
    }


def email_has_account(email: str) -> bool:
    """Whether an account holds ``email``, as its own or as an address on record, whatever the case.

    The unified login (``accounts.unified_login``) signs in such an email and signs up any other one, as
    ERPlora/saas ``SubdomainLoginView._email_exists`` (ADR-0154).
    """
    return (
        get_user_model().objects.filter(email__iexact=email).exists()
        or EmailAddress.objects.filter(email__iexact=email).exists()
    )


def email_is_proven(user, email: str) -> bool:
    """Whether ``user`` holds ``email`` by proof rather than by having typed it first (saas#2541).

    Proven means a **verified** ``EmailAddress`` for that address (another verified address proves
    nothing). Two kinds of account have nothing to prove and count as proven: staff, and an account with
    **no** address on record (made by an invitation, which leaves no password until the mailbox's owner
    claims it, by the console or by staff). Ported from ERPlora/saas ``apps/auth/users/services.py``.
    """
    if user.is_staff or user.is_superuser:
        return True
    addresses = EmailAddress.objects.filter(user=user)
    if not addresses.exists():
        return True
    return addresses.filter(email__iexact=email, verified=True).exists()


def linked_providers(user) -> list[str]:
    """The providers the account signs in with (``google``), alphabetically."""
    return sorted(set(SocialAccount.objects.filter(user=user).values_list("provider", flat=True)))


def has_no_way_in(user) -> bool:
    """Whether ``user`` has no way to sign in yet: no usable password and no linked Google. Whoever opens
    its mailbox claims it with «Forgot your password?» or with Google (the invitation's mail says so)."""
    return not user.has_usable_password() and not SocialAccount.objects.filter(user=user).exists()


# --- The Account page (plan 2026-10-13, L3-A) ---------------------------------------------------------------


def account_of(ctx: OperationContext):
    """The account behind ``ctx``; without one, 401 (a live stream or a route always has one)."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to manage your account."))
    return ctx.actor


def preferences_of(user) -> dict[str, Any]:
    """What the account chose, or the defaults when it never changed anything (no row is written)."""
    preferences = UserPreferences.objects.filter(user=user).first() or UserPreferences(user=user)
    return {
        "theme_mode": preferences.theme_mode,
        "language": user.language,
        "hub_alerts": preferences.hub_alerts,
        "marketing_emails": preferences.marketing_emails,
    }


@operation(
    "accounts.preferences.get", kind="query", permission="accounts.view", input=PreferencesGetIn, output=PreferencesOut
)
def preferences_get(ctx: OperationContext, data: PreferencesGetIn) -> dict[str, Any]:
    """Account → Preferences of the signed-in account."""
    return preferences_of(account_of(ctx))


#: Seconds a code works (the mail says so: ``emails.CODE_MINUTES``).
EMAIL_CODE_LIFETIME = 15 * 60


def email_change_of(user, request):
    """The change of address ``user`` asked for in ``request``'s session and can still finish, if any."""
    change = EmailChangeRequest.objects.filter(user=user).first()
    if (
        change is None
        or change.session_key != current_session_key(request)
        or time.time() - change.created_at.timestamp() > EMAIL_CODE_LIFETIME
    ):
        return None
    return change


def pending_email_of(user, request=None) -> str | None:
    """The address waiting for its code in this session (``accounts.email.change``), if any."""
    change = email_change_of(user, request)
    return change.email if change is not None else None


def profile_of(user, request=None) -> dict[str, Any]:
    photo = ProfilePhoto.objects.filter(user=user).first()
    return {
        "id": user.pk,
        "email": user.email,
        "email_verified": email_is_proven(user, user.email),
        "pending_email": pending_email_of(user, request),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.get_full_name(),
        "photo": photo.data_url() if photo is not None else None,
        "has_password": user.has_usable_password(),
        "date_joined": user.date_joined,
    }


@operation("accounts.profile.get", kind="query", permission="accounts.view", input=ProfileGetIn, output=ProfileOut)
def profile_get(ctx: OperationContext, data: ProfileGetIn) -> dict[str, Any]:
    """Account → Profile of the signed-in account."""
    return profile_of(account_of(ctx), ctx.request)


# --- Sessions -------------------------------------------------------------------------------------


def current_session_key(request) -> str | None:
    return getattr(getattr(request, "session", None), "session_key", None)


def session_is_alive(user_session, user) -> bool:
    """Whether ``user_session`` still signs ``user`` in: its session exists, has not expired and was opened
    with the account's current password (Django ends the others when it changes). Read only: unlike
    ``django.contrib.auth.get_user``, a dead session is not flushed here."""
    from importlib import import_module

    from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
    from django.utils.crypto import constant_time_compare

    data = import_module(settings.SESSION_ENGINE).SessionStore(user_session.session_key).load()
    if data.get(SESSION_KEY) != str(user.pk):
        return False
    stored = data.get(HASH_SESSION_KEY) or ""
    hashes = [user.get_session_auth_hash(), *getattr(user, "get_session_auth_fallback_hash", lambda: ())()]
    return any(constant_time_compare(stored, candidate) for candidate in hashes)


def live_sessions(user) -> list:
    """The account's sessions that still sign it in, the last used first."""
    from allauth.usersessions.models import UserSession

    sessions = UserSession.objects.filter(user=user).order_by("-last_seen_at", "-pk")
    return [session for session in sessions if session_is_alive(session, user)]


def session_row(session, current: str | None) -> dict[str, Any]:
    from accounts.devices import describe

    device = describe(session.user_agent)
    return {
        "id": session.pk,
        "device": device.platform,
        "browser": device.browser,
        "browser_version": device.browser_version,
        "app_version": device.app_version,
        "ip": session.ip,
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
        "is_current": session.session_key == current,
    }


@operation("accounts.session.list", kind="query", permission="accounts.view", input=SessionListIn, output=SessionListOut)
def session_list(ctx: OperationContext, data: SessionListIn) -> dict[str, Any]:
    """Account → Security → Active sessions: this session first, then the rest by last use."""
    user = account_of(ctx)
    current = current_session_key(ctx.request)
    sessions = sorted(live_sessions(user), key=lambda session: session.session_key != current)
    return {"rows": [session_row(session, current) for session in sessions], "total": len(sessions)}


# --- API keys -------------------------------------------------------------------------------------

#: The most keys ``accounts.apikey.list`` returns (the newest), within the live results' size.
API_KEY_LIST_LIMIT = 100


def api_key_row(key: ApiKey, now) -> dict[str, Any]:
    return {
        "id": key.pk,
        "name": key.name,
        "prefix": key.display_prefix,
        "scopes": list(key.scopes or []),
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "expires_at": key.expires_at,
        "expired": key.expires_at is not None and key.expires_at <= now,
    }


def api_key_scopes(language: str) -> list[dict[str, str]]:
    with translation.override(language):
        return [{"id": scope, "label": str(label)} for scope, label in API_KEY_SCOPES.items()]


@operation("accounts.apikey.list", kind="query", permission="accounts.view", input=ApiKeyListIn, output=ApiKeyListOut)
def apikey_list(ctx: OperationContext, data: ApiKeyListIn) -> dict[str, Any]:
    """Account → API keys: the account's keys that are not revoked, the newest first, and the scopes on offer."""
    user = account_of(ctx)
    now = timezone.now()
    keys = ApiKey.objects.filter(user=user, revoked_at__isnull=True).order_by("-created_at", "-pk")
    return {
        "rows": [api_key_row(key, now) for key in keys[:API_KEY_LIST_LIMIT]],
        "total": keys.count(),
        "scopes": api_key_scopes(ctx.language),
    }


def api_key_for(raw: str, now) -> ApiKey | None:
    """The usable key ``raw`` opens (not revoked nor expired, of an active account), or ``None``. Anything that
    is not shaped like a key costs no query; the hash is compared in constant time."""
    body = ApiKey.parse(raw)
    if body is None:
        return None
    digest = ApiKey.hash_key(raw.strip())
    candidates = ApiKey.objects.select_related("user").filter(prefix=body[:API_KEY_PREFIX_LENGTH], revoked_at__isnull=True)
    for candidate in candidates:
        if constant_time_compare(candidate.key_hash, digest) and candidate.is_usable(now) and candidate.user.is_active:
            return candidate
    return None
