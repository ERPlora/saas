"""Reads of accounts: the hubs an account can enter (``accounts.hub.list``, the launcher's), the
re-read of an account before a live re-run, the hubs the admin's «Open in the Hub admin» lists, the
authenticators of the second factor (``mfa.py``), whether an email has an account (the unified login),
whether an account proved its email or has any way in (the invitation of ``hubs``, saas#2541), and the
Account page (plan 2026-10-13, L3-A): the profile, the
preferences, the live sessions, whether this browser is trusted (ACCOUNTS-F17) and the API keys, and the key a
request carries (``api_auth``)."""

import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

from allauth.account.models import EmailAddress
from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.internal.flows.trust import create_config_fingerprint, decode_trust_cookie
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
from live.operations import AI, INTERNAL, operation

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
    BrowserTrustGetIn,
    BrowserTrustOut,
    DataExportIn,
    DataExportOut,
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


def stored_staff_flags(pk) -> tuple[bool, bool] | None:
    """``(is_staff, is_superuser)`` of account ``pk`` as saved, or ``None`` if it is not saved yet (``User.clean``
    tells raising a flag from keeping it)."""
    return get_user_model().objects.filter(pk=pk).values_list("is_staff", "is_superuser").first()


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


@operation(
    "accounts.hub.list",
    kind="query",
    permission=None,
    input=HubListIn,
    output=HubListOut,
    ai=INTERNAL,  # screen
)
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


def active_account(account_id: str):
    """The active account whose id is ``account_id`` (the Hub's session names it), or ``None`` (none, off, no id)."""
    try:
        account = uuid.UUID(account_id)
    except (TypeError, ValueError, AttributeError):
        return None
    return active_user(account)


def preferences_of(user) -> dict[str, Any]:
    """What the account chose, or the defaults when it never changed anything (no row is written)."""
    preferences = UserPreferences.objects.filter(user=user).first() or UserPreferences(user=user)
    return {
        "theme_mode": preferences.theme_mode,
        "language": user.language,
        "hub_alerts": preferences.hub_alerts,
    }


def receives_business_notices(user) -> bool:
    """Whether ``user`` gets the business notices (Account → Preferences, ``hub_alerts``; on until turned off): the
    mail that a business is ready (``hubs.emails.send_ready``). The mails that keep the account safe or its businesses
    running ask nobody (ACCOUNTS-F23)."""
    preferences = UserPreferences.objects.filter(user=user).values_list("hub_alerts", flat=True).first()
    return True if preferences is None else preferences


@operation(
    "accounts.preferences.get",
    kind="query",
    permission="accounts.view",
    input=PreferencesGetIn,
    output=PreferencesOut,
    ai=AI(
        description="The account's preferences: theme, language and alerts of its businesses.",
        asks={
            "en": ("what language is my account in?", "do I get alerts from my businesses?", "show my preferences"),
            "es": ("¿en qué idioma tengo la cuenta?", "¿qué preferencias tengo?", "¿qué tema tengo puesto?"),
        },
    ),
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


@operation(
    "accounts.profile.get",
    kind="query",
    permission="accounts.view",
    input=ProfileGetIn,
    output=ProfileOut,
    ai=INTERNAL,  # photo
)
def profile_get(ctx: OperationContext, data: ProfileGetIn) -> dict[str, Any]:
    """Account → Profile of the signed-in account."""
    return profile_of(account_of(ctx), ctx.request)


# --- Sessions -------------------------------------------------------------------------------------


def current_session_key(request) -> str | None:
    return getattr(getattr(request, "session", None), "session_key", None)


def live_sessions(user) -> list[tuple[int, str]]:
    """``(id, session key)`` of the account's sessions that still sign it in, the last used first: their session
    exists, has not expired and was opened with the account's current password (Django ends the others when it
    changes). One query brings the unexpired ones with their data, checked here: no session load per row (a
    thousand sessions were a thousand queries on every run of the list). Read only: unlike
    ``django.contrib.auth.get_user``, a dead session is not flushed here."""
    from importlib import import_module

    from allauth.usersessions.models import UserSession
    from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
    from django.db.models import OuterRef, Subquery

    store = import_module(settings.SESSION_ENGINE).SessionStore
    stored = store.get_model_class().objects.filter(session_key=OuterRef("session_key"), expire_date__gt=timezone.now())
    sessions = (
        UserSession.objects.filter(user=user)
        .annotate(session_data=Subquery(stored.values("session_data")[:1]))
        .filter(session_data__isnull=False)
        .order_by("-last_seen_at", "-pk")
        .values_list("pk", "session_key", "session_data")
    )
    hashes = [user.get_session_auth_hash(), *getattr(user, "get_session_auth_fallback_hash", lambda: ())()]
    decode = store().decode

    def signs_in(data: dict) -> bool:
        stored_hash = data.get(HASH_SESSION_KEY) or ""
        return data.get(SESSION_KEY) == str(user.pk) and any(constant_time_compare(stored_hash, h) for h in hashes)

    return [(pk, key) for pk, key, data in sessions if signs_in(decode(data))]


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


@operation(
    "accounts.session.list",
    kind="query",
    permission="accounts.view",
    input=SessionListIn,
    output=SessionListOut,
    ai=AI(
        description="The account's active sessions (browsers and apps), this one first.",
        asks={
            "en": ("where am I logged in?", "which devices have my account open?", "show my active sessions"),
            "es": (
                "¿dónde tengo la sesión abierta?",
                "¿qué dispositivos están conectados a mi cuenta?",
                "¿qué sesiones tengo abiertas?",
            ),
        },
    ),
)
def session_list(ctx: OperationContext, data: SessionListIn) -> dict[str, Any]:
    """Account → Security → Active sessions, a page at a time: this session first, then the rest by last use."""
    from allauth.usersessions.models import UserSession

    user = account_of(ctx)
    current = current_session_key(ctx.request)
    sessions = sorted(live_sessions(user), key=lambda session: session[1] != current)
    page = [pk for pk, _ in sessions[data.offset : data.offset + data.limit]]
    found = UserSession.objects.in_bulk(page)
    return {
        "rows": [session_row(found[pk], current) for pk in page if pk in found],
        "total": len(sessions),
        "limit": data.limit,
        "offset": data.offset,
        "others": sum(1 for _, key in sessions if key != current),
    }


# --- Two-factor authentication: the trusted browsers (ACCOUNTS-F05, ACCOUNTS-F17) -------------------------------


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


@operation(
    "accounts.apikey.list",
    kind="query",
    permission="accounts.view",
    input=ApiKeyListIn,
    output=ApiKeyListOut,
    ai=AI(
        description="The account's API keys that are not revoked, with their scopes (never their secret).",
        asks={
            "en": ("what API keys do I have?", "show me my integration keys", "which keys can get into my account?"),
            "es": (
                "¿qué claves de API tengo?",
                "enséñame las claves de la API",
                "¿tengo alguna clave para integraciones?",
            ),
        },
    ),
)
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


# --- Account → Profile → «Download my data» (GDPR art. 20, ACCOUNTS-F26) ------------------------------------------

#: The other apps' reads the file carries, called by their name: accounts never imports hubs nor billing.
BUSINESS_LIST = "hubs.business.list"
INVOICE_LIST = "billing.invoice.list"
INVOICE_GET = "billing.invoice.get"
#: The largest page each of those reads gives.
EXPORT_PAGE = 100


def _every_row(ctx: OperationContext, name: str, **params) -> list:
    """Every row of the paged read ``name`` (``rows``, ``total``, ``limit``), page after page."""
    from live import operations

    read = operations.get(name)
    rows: list = []
    while True:
        page = read(ctx, read.input(limit=EXPORT_PAGE, offset=len(rows), **params))
        rows.extend(page.rows)
        if not page.rows or len(rows) >= page.total:
            return rows


def _export_account(user) -> dict[str, Any]:
    return {
        "id": user.pk,
        "email": user.email,
        "email_verified": email_is_proven(user, user.email),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language": user.language,
        "has_password": user.has_usable_password(),
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        "terms": {
            "accepted_at": user.terms_accepted_at,
            "terms_version": user.terms_version,
            "privacy_version": user.privacy_version,
        },
    }


def _export_sessions(user) -> list[dict[str, Any]]:
    from allauth.usersessions.models import UserSession

    order = [pk for pk, _ in live_sessions(user)]
    found = UserSession.objects.in_bulk(order)
    return [session_row(found[pk], None) for pk in order if pk in found]


@operation(
    "accounts.data.export",
    kind="query",
    permission="accounts.view",
    input=DataExportIn,
    output=DataExportOut,
    ai=INTERNAL,  # file
)
def data_export(ctx: OperationContext, data: DataExportIn) -> dict[str, Any]:
    """Account → Profile → «Download my data»: everything the account is and did here, in one JSON document (GDPR
    art. 20). Only the caller's: each part is read for its account, and the businesses and invoices through the
    operations that already keep them to it (``hubs.business.list``, ``billing.invoice.list``/``.get``)."""
    from live import operations

    user = account_of(ctx)
    preferences = preferences_of(user)
    photo = ProfilePhoto.objects.filter(user=user).first()
    invoice_get = operations.get(INVOICE_GET)
    invoices = [
        invoice_get(ctx, invoice_get.input(id=row.id)).model_dump(mode="json")
        for row in _every_row(ctx, INVOICE_LIST)
    ]
    return {
        "format": "erplora.account-export",
        "version": 1,
        "exported_at": timezone.now(),
        "account": _export_account(user),
        "preferences": {key: preferences[key] for key in ("theme_mode", "language", "hub_alerts")},
        "photo": photo.data_url() if photo is not None else None,
        "email_addresses": list(
            EmailAddress.objects.filter(user=user).order_by("-primary", "email").values("email", "verified", "primary")
        ),
        "connected_accounts": list(
            SocialAccount.objects.filter(user=user)
            .order_by("provider", "uid")
            .values("provider", "uid", "date_joined", "last_login")
        ),
        "sessions": _export_sessions(user),
        "api_keys": [
            {
                "name": key.name,
                "prefix": key.display_prefix,
                "scopes": list(key.scopes or []),
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "last_used_at": key.last_used_at,
                "revoked_at": key.revoked_at,
            }
            for key in ApiKey.objects.filter(user=user).order_by("-created_at", "-pk")
        ],
        "businesses": [row.model_dump(mode="json") for row in _every_row(ctx, BUSINESS_LIST)],
        "invoices": invoices,
    }
