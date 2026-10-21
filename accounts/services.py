"""Writes of accounts: the one-time code of the jump to a hub (PLAN-SAAS §2.1, §3.1 steps 5-6) and the
commands of the Account page (plan 2026-10-13, L3-A: preferences, profile, photo, email, sessions and API keys).

Ported from ERPlora/saas ``AuthExchangeCode.issue``/``redeem`` (``apps/auth/users/models.py``),
with the code stored as its SHA-256, bound to one hub, and spent by a single conditional
``UPDATE … WHERE used_at IS NULL`` instead of ``select_for_update``. Two audiences: ``hub-session``
(a member enters their hub) and ``hub-admin`` (the platform's staff open a hub in the Hub's Django
admin at ``hubs.erplora.com``, ronda 13, PLAN §18).
"""

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial

from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from live import operations
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, LiveMisuse, NotFound, OperationError
from live.operations import operation
from live.outbox import record_event
from live.slugs import validate_hub_slug

from accounts import emails, events, photos, queries, signals
from accounts.models import (
    PRIVACY_VERSION,
    TERMS_VERSION,
    ApiKey,
    AuthExchangeCode,
    EmailChangeRequest,
    HubMembership,
    ProfilePhoto,
    UserPreferences,
)
from accounts.schemas import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyRevokeIn,
    ApiKeyRowOut,
    EmailChangeIn,
    EmailVerifyIn,
    EmailVerifyOut,
    PhotoRemoveIn,
    PhotoUploadIn,
    PreferencesOut,
    PreferencesUpdateIn,
    SessionCloseIn,
    SessionCloseOthersIn,
    SessionsClosedOut,
    ProfileDeletedOut,
    ProfileDeleteIn,
    ProfileOut,
    ProfileUpdateIn,
)

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


def release_unproven_account(user, *, reason: str) -> None:
    """Strip every credential of an account whose holder never proved its email (saas#2541).

    The address is then reserved by nobody: only whoever opens that mailbox gets in, through «Forgot your
    password?» (or Google, which proves the address), like any invited person. allauth's own defence when
    Google proves an address the account never verified (``socialaccount/internal/flows/
    email_authentication.py``), taken further: that one only wipes the password, and a second factor or a
    linked Google of the squatter's would still let them in, or lock the real owner out at the second step.

    Removes the password (which also ends every browser session of the SaaS: Django checks the session
    against the password hash), every second factor and every linked social account. The account, its
    addresses and what hangs from it stay. Its sessions in the hubs are the caller's to end (``hubs``
    queues a ``SessionRevocation`` of every business). Ported from ERPlora/saas
    ``apps/auth/users/services.py``; without its refresh tokens, which the SaaS no longer has.
    """
    from allauth.mfa.models import Authenticator
    from allauth.socialaccount.models import SocialAccount

    with transaction.atomic():
        user.set_unusable_password()
        user.save(update_fields=["password"])
        Authenticator.objects.filter(user=user).delete()
        SocialAccount.objects.filter(user=user).delete()
    logger.warning("accounts.released_unproven_account user=%s reason=%s", user.pk, reason)


def accept_legal_texts(sender, request=None, user=None, **kwargs) -> None:
    """allauth's ``user_signed_up`` and Django's ``user_logged_in``: the account accepts today's terms and privacy
    policy (ACCOUNTS-G119). Creating the account and signing in happen under «By continuing you agree to our Terms &
    Privacy Policy» (the launcher, Google's button too), so each records when and which versions
    (``models.TERMS_VERSION``, ``PRIVACY_VERSION``) unless the account already accepted those: the first date stays."""
    if user is None or (user.terms_version, user.privacy_version) == (TERMS_VERSION, PRIVACY_VERSION):
        return
    accepted = {"terms_accepted_at": timezone.now(), "terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION}
    get_user_model().objects.filter(pk=user.pk).update(**accepted)
    for field, value in accepted.items():
        setattr(user, field, value)
    logger.info("accounts.legal_texts_accepted user=%s terms=%s privacy=%s", user.pk, TERMS_VERSION, PRIVACY_VERSION)


def prove_mailbox_by_reset(sender, request=None, user=None, **kwargs) -> None:
    """allauth's ``password_reset`` signal: a password set from the key mailed by «Forgot your password?»
    proves the mailbox, so the account's address becomes verified and primary (L1-A2).

    How an account made by an invitation is claimed (its mail links to the reset): allauth's reset leaves
    its address on record unverified, and accepting needs it proved (``queries.email_is_proven``). Only
    when the login address is the only one on record: the key goes to the address typed, which may be any
    address of the account, so with another one (a squatter's own, verified) nothing is proven here.
    """
    if user is None:
        return
    from allauth.account.models import EmailAddress

    with transaction.atomic():
        addresses = EmailAddress.objects.select_for_update().filter(user=user)
        if addresses.exclude(email__iexact=user.email).exists():
            return
        address = addresses.first()
        if address is None:
            EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        elif not (address.verified and address.primary):
            address.verified = True
            address.primary = True
            address.save(update_fields=["verified", "primary"])
    logger.info("accounts.reset_proved_the_mailbox user=%s", user.pk)


def _prove_demo_address(user) -> None:
    """A local account of ``demo_seed`` never owes the code that proves its address, only the sign-in code
    every password sign-in mails (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``): its address is on record, proven, also
    on an account seeded before every account had to prove it (``ACCOUNT_EMAIL_VERIFICATION``)."""
    from allauth.account.models import EmailAddress

    EmailAddress.objects.update_or_create(
        user=user, email=user.email.lower(), defaults={"verified": True, "primary": True}
    )


def seed_demo_customer(email: str, password: str):
    """Create (or leave as it is) a customer account of ``demo_seed``: never staff, in no hub yet, its
    address proven.

    Its businesses and roles are ``hubs.services.seed_demo_business``'s: the access the jump reads
    (``HubMembership``) is the mirror of a business's members, written only by ``hubs.services.sync_access``.
    """
    user = get_user_model().objects.filter(email=email).first()
    if user is None:
        user = get_user_model().objects.create_user(email=email, password=password)
    _prove_demo_address(user)
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
    """Create (or leave as it is) a platform administrator: superuser of the admin, member of no hub, its
    address proven."""
    user = get_user_model().objects.filter(email=email).first()
    if user is None:
        user, _ = create_platform_user(email, PLATFORM_ADMIN, password)
    _prove_demo_address(user)
    return user


# --- Account → Preferences ------------------------------------------------------------------------


@operation(
    "accounts.preferences.update",
    kind="command",
    permission="accounts.manage",
    input=PreferencesUpdateIn,
    output=PreferencesOut,
)
def preferences_update(ctx: OperationContext, data: PreferencesUpdateIn) -> dict:
    """Change what was sent and nothing else. The language is the account's own (``User.language``); the
    rest lives in ``UserPreferences``, whose row is born with the first change."""
    user = queries.account_of(ctx)
    changes = data.model_dump(exclude_none=True)
    language = changes.pop("language", None)
    if language is not None and language != user.language:
        user.language = language
        user.save(update_fields=["language"])
    if changes:
        preferences, _ = UserPreferences.objects.select_for_update().get_or_create(user=user)
        for field, value in changes.items():
            setattr(preferences, field, value)
        preferences.save()
    record_event(ctx, events.PREFERENCES_UPDATED)
    return queries.preferences_of(user)


# --- Account → Profile ------------------------------------------------------------------------------


@operation("accounts.profile.update", kind="command", permission="accounts.manage", input=ProfileUpdateIn, output=ProfileOut)
def profile_update(ctx: OperationContext, data: ProfileUpdateIn) -> dict:
    """The names, trimmed: the first one is required (audit 2 S-10), an empty last one clears it. The sign-in email
    has its own door, ``accounts.email.change``."""
    user = queries.account_of(ctx)
    user.first_name = data.first_name.strip()
    user.last_name = data.last_name.strip()
    user.save(update_fields=["first_name", "last_name"])
    record_event(ctx, events.PROFILE_UPDATED)
    return queries.profile_of(user, ctx.request)


# --- A recent sign-in (allauth's reauthentication) ------------------------------------------------


class ReauthenticationRequired(OperationError):
    """401 ``reauthentication_required``: the command needs a recent sign-in (``ACCOUNT_REAUTHENTICATION_TIMEOUT``).

    Its envelope lists the ``flows`` that confirm it, in allauth.headless's words: ``reauthenticate`` (the password,
    ``POST /_allauth/browser/v1/auth/reauthenticate``), ``mfa_reauthenticate`` (a code of the second factor) and
    ``provider_redirect`` (signing in again with a linked provider through allauth.headless's provider redirect,
    whose ``providers`` it names). The panel confirms and sends the command again."""

    status = 401
    code = "reauthentication_required"

    def __init__(self, flows: list[str], providers: list[str]) -> None:
        super().__init__(gettext("Confirm it's you: enter your password again."))
        self.flows = flows
        self.providers = providers

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"].update(flows=list(self.flows), providers=list(self.providers))
        return envelope


def require_recent_authentication(ctx: OperationContext) -> None:
    """Refuse unless the caller's session signed in, or confirmed it, within allauth's window.

    Stricter than allauth's ``did_recently_authenticate``, which lets an account with neither a password nor a
    second factor through with nothing to confirm: here any account needs a recent sign-in of its own, and one that
    signs in only with Google confirms by signing in with Google again (allauth records it). A request carrying an
    API key never counts (403 ``api_key_not_allowed``), nor does a context without a request (a system call).
    """
    from allauth.account import app_settings as account_settings
    from allauth.account.authentication import get_authentication_records
    from allauth.account.internal.flows.reauthentication import get_reauthentication_flows

    user = queries.account_of(ctx)
    request = ctx.request
    if isinstance(getattr(request, "auth", None), ApiKey):
        raise OperationError(
            gettext("API keys cannot be used here: this operation is only for signed-in people."),
            code="api_key_not_allowed",
            status=403,
        )
    if request is not None and getattr(request, "user", None) == user:
        records = get_authentication_records(request)
        if records and time.time() - records[-1]["at"] < account_settings.REAUTHENTICATION_TIMEOUT:
            return
    flows = [flow["id"] for flow in get_reauthentication_flows(user)]
    providers = queries.linked_providers(user)
    if providers:
        flows.append("provider_redirect")
    raise ReauthenticationRequired(flows, providers)


# --- Account → Profile → «Delete account» ----------------------------------------------------------


class HoldsBusinesses(Conflict):
    """409 that names the businesses holding the account (``businesses: [{id, name}]``), so the panel links each
    one: ``accounts.owns_businesses`` (it owns them, saas#2567) or ``accounts.pays_businesses`` (it pays for them
    after a hand-over: deleting it would leave Stripe charging a card nobody can stop)."""

    def __init__(self, message: str, *, code: str, businesses: list[dict]) -> None:
        super().__init__(message, code=code)
        self.businesses = businesses

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["businesses"] = self.businesses
        return envelope


#: The businesses of an account, read through their operation (accounts never imports hubs).
BUSINESS_LIST = "hubs.business.list"


def businesses_holding(ctx: OperationContext) -> tuple[list[dict], list[dict]]:
    """``(owned, paid)``: the businesses that are not deleted which the caller owns, and those it pays for without
    owning them, as ``[{id, name}]``, from ``hubs.business.list``.

    A business has one owner (PLAN-SAAS §3.6 point 8), and its row says what that owner may do: ``can.delete`` is
    «the owner, not deleted». ``is_payer`` says the account owns the business's payer. A deleted business in its
    90 days of recovery holds nobody (``deletion_requested_at``).
    """
    business_list = operations.get(BUSINESS_LIST)
    owned: list[dict] = []
    paid: list[dict] = []
    offset = 0
    while True:
        page = business_list(ctx, business_list.input(limit=100, offset=offset))
        for row in page.rows:
            entry = {"id": str(row.id), "name": row.name}
            if row.can.delete:
                owned.append(entry)
            elif row.is_payer and row.deletion_requested_at is None:
                paid.append(entry)
        offset += page.limit
        if offset >= page.total:
            return owned, paid


def forget_in_outbox(user) -> int:
    """GDPR: the outbox rows whose actor is ``user`` keep its id instead of its email.

    ``live.outbox.record_event`` writes ``str(ctx.actor)``, an account's email, as the actor. The proper fix is
    the actor's id in ``live`` itself (the pending list of accounts/README.md); until then, a deleted account's events
    keep no trace of its address. Called in the deletion's transaction, after its own event is recorded.
    """
    from live.models import OutboxEvent

    actor = str(user)[: OutboxEvent._meta.get_field("actor").max_length]
    return OutboxEvent.objects.filter(actor=actor).update(actor=str(user.pk))


def end_every_session(user) -> int:
    """End every session of ``user`` in the SaaS (``allauth.usersessions``); how many there were."""
    from allauth.usersessions.models import UserSession

    sessions = list(UserSession.objects.filter(user=user))
    for session in sessions:
        session.end()
    return len(sessions)


@operation(
    "accounts.profile.delete", kind="command", permission="accounts.manage", input=ProfileDeleteIn, output=ProfileDeletedOut
)
def profile_delete(ctx: OperationContext, data: ProfileDeleteIn) -> dict:
    """Delete the signed-in account (GDPR, art. 17; Google Play asks for it in the apps too).

    In this order: no owned business and none it pays for (409, before any password is asked), a recent sign-in
    (401), then, in
    one transaction, every business is asked to end its sessions (``signals``), every session of the SaaS
    ends (the caller's too: the answer signs it out) and the account goes, with what hangs from it.
    """
    user = queries.account_of(ctx)
    owned, paid = businesses_holding(ctx)
    if owned:
        raise HoldsBusinesses(
            gettext("You own businesses: transfer or delete them before deleting your account."),
            code="accounts.owns_businesses",
            businesses=owned,
        )
    if paid:
        raise HoldsBusinesses(
            gettext(
                "You pay for businesses of other people: ask their owner to enter their own payment details before "
                "deleting your account."
            ),
            code="accounts.pays_businesses",
            businesses=paid,
        )
    require_recent_authentication(ctx)
    user_id = user.pk
    signals.account_deleting.send(sender=get_user_model(), user_id=user_id)
    signals.sessions_ended.send(sender=get_user_model(), user_id=user_id)
    record_event(ctx, events.PROFILE_DELETED)
    forget_in_outbox(user)
    logout(ctx.request)
    end_every_session(user)
    user.delete()
    logger.info("accounts.account_deleted user=%s", user_id)
    return {"deleted": True}


# --- Account → Profile → «Change» the email --------------------------------------------------------


def _email_refused(message: str) -> InvalidPayload:
    return InvalidPayload(gettext("Invalid payload"), fields={"email": message})


def email_belongs_to_another_account(user, email: str) -> bool:
    """Whether another account answers to ``email``, in any letter case: its sign-in email or an address on
    record. allauth's own lookup matches the lowercased address, and older accounts keep their capitals."""
    from allauth.account.models import EmailAddress

    return (
        get_user_model().objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
        or EmailAddress.objects.filter(email__iexact=email).exclude(user=user).exists()
    )


#: Tries a code has (a wrong one each), counted in the database.
EMAIL_CODE_ATTEMPTS = 3
#: Seconds before asking again for the same address sends a new code (a double click sends one).
EMAIL_CODE_RESEND_AFTER = 60
#: Tries an account may make, whatever the code (django-ratelimit, over the cache).
EMAIL_CODE_TRIES_PER_MINUTE = "5/m"
EMAIL_CODE_TRIES_PER_HOUR = "20/h"
#: Codes an address may get, whoever asks for them: nobody's inbox to flood.
EMAIL_CODES_PER_ADDRESS = "3/h"


def _new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _no_email_change() -> Conflict:
    return Conflict(
        gettext("There is no change of email waiting for a code: ask for a new one."), code="accounts.no_email_change"
    )


def _spent(rate: str, group: str, key: str) -> bool:
    from django_ratelimit.core import is_ratelimited

    return is_ratelimited(None, group=group, key=lambda group, request: key, rate=rate, increment=True)


@operation("accounts.email.change", kind="command", permission="accounts.manage", input=EmailChangeIn, output=ProfileOut)
def email_change(ctx: OperationContext, data: EmailChangeIn) -> dict:
    """Mail a 6-digit code to the new address; the account switches to it once the code is typed in this same
    session (``accounts.email.verify``), and until then it keeps answering to the old one (saas#2536). The change
    waits in ``EmailChangeRequest`` (bound to this session, the code kept as its hash). The account's own address,
    if it never proved it, is proven the same way.

    For another address, a password first (409 ``accounts.password_required``: without one, the session alone
    would change it) and a recent sign-in (401); a code to the account's own address hands nothing over and asks
    for neither. Always allauth's budget for an account's addresses (429 ``accounts.too_many_attempts``) and three
    codes an hour per address (429 ``accounts.too_many_codes``).
    """
    from allauth.account.adapter import get_adapter
    from allauth.core import ratelimit
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    user = queries.account_of(ctx)
    if data.email.strip().lower() != user.email.lower():
        if not user.has_usable_password():
            raise Conflict(
                gettext(
                    "Your account has no password yet: set one with «Forgot your password?» before changing your email."
                ),
                code="accounts.password_required",
            )
        require_recent_authentication(ctx)
    request = ctx.request
    if not ratelimit.consume(request, action="manage_email", user=user):
        raise too_many_attempts()
    email = data.email.strip().lower()
    try:
        validate_email(email)
        email = get_adapter(request).clean_email(email)
    except ValidationError:
        raise _email_refused(gettext("Enter a valid email address.")) from None
    if len(email) > get_user_model()._meta.get_field("email").max_length:
        raise _email_refused(gettext("Enter a valid email address."))
    if email == user.email.lower() and queries.email_is_proven(user, user.email):
        raise _email_refused(gettext("That is already your email."))
    if email_belongs_to_another_account(user, email):
        raise _email_refused(gettext("This email is already used by another account."))
    pending = queries.email_change_of(user, request)
    if (
        pending is not None
        and pending.email == email
        and time.time() - pending.created_at.timestamp() < EMAIL_CODE_RESEND_AFTER
    ):
        return queries.profile_of(user, request)
    if _spent(EMAIL_CODES_PER_ADDRESS, "accounts.email_code.address", f"to:{email}"):
        raise OperationError(
            gettext("That address already got several codes in the last hour: try again later."),
            code="accounts.too_many_codes",
            status=429,
        )
    code = _new_code()
    EmailChangeRequest.objects.update_or_create(
        user=user,
        defaults={
            "session_key": queries.current_session_key(request),
            "email": email,
            "code_hash": _hash_code(code),
            "attempts": 0,
            "created_at": datetime.fromtimestamp(time.time(), tz=UTC),
        },
    )
    if not emails.send_email_code(email, code, language=user.language):
        raise OperationError(
            gettext("We could not send the code. Please try again in a few minutes."),
            code="accounts.code_not_sent",
            status=503,
        )
    logger.info("accounts.email_code_sent user=%s", user.pk)
    record_event(ctx, events.EMAIL_CHANGE_REQUESTED)
    return queries.profile_of(user, request)


@operation(
    "accounts.email.verify", kind="command", permission="accounts.manage", input=EmailVerifyIn, output=EmailVerifyOut
)
def email_verify(ctx: OperationContext, data: EmailVerifyIn) -> dict:
    """The code mailed by ``accounts.email.change``, typed in the session that asked for it: the account answers to
    the new address from now on, proven (its only address on record), and the old one is told.

    Each try is consumed by one conditional ``UPDATE`` before the code is compared, and a wrong code answers
    ``verified: false`` (not an error, which would roll the spent try back); the third wrong one ends the change.
    An account has a budget of tries a minute and an hour besides (429). An address another account took meanwhile
    is refused (409 ``accounts.email_taken``), also when the database finds it first. allauth's ``email_changed``
    is sent, for whoever keeps a copy of the address.
    """
    from allauth.account.models import EmailAddress
    from allauth.account.signals import email_changed
    from django.db import IntegrityError
    from django.db.models import F

    user = queries.account_of(ctx)
    request = ctx.request
    change = queries.email_change_of(user, request)
    if change is None:
        raise _no_email_change()
    for rate in (EMAIL_CODE_TRIES_PER_MINUTE, EMAIL_CODE_TRIES_PER_HOUR):
        if _spent(rate, f"accounts.email_code.tries.{rate}", f"user:{user.pk}"):
            raise too_many_attempts()
    tries = EmailChangeRequest.objects.filter(pk=change.pk, attempts__lt=EMAIL_CODE_ATTEMPTS)
    if not tries.update(attempts=F("attempts") + 1):
        EmailChangeRequest.objects.filter(pk=change.pk).delete()
        raise _no_email_change()
    attempts = EmailChangeRequest.objects.filter(pk=change.pk).values_list("attempts", flat=True).get()
    if not hmac.compare_digest(change.code_hash, _hash_code(data.code.strip())):
        left = max(EMAIL_CODE_ATTEMPTS - attempts, 0)
        if not left:
            EmailChangeRequest.objects.filter(pk=change.pk).delete()
        return {"verified": False, "attempts_left": left, "profile": queries.profile_of(user, request)}
    email = change.email
    if email_belongs_to_another_account(user, email):
        raise Conflict(gettext("This email is already used by another account."), code="accounts.email_taken")
    old_email = user.email
    previous = EmailAddress.objects.filter(user=user, email__iexact=old_email).first()
    changed = email != old_email.lower()
    try:
        with transaction.atomic():
            EmailAddress.objects.filter(user=user).exclude(email__iexact=email).delete()
            address, _ = EmailAddress.objects.update_or_create(
                user=user, email__iexact=email, defaults={"email": email, "verified": True, "primary": True}
            )
            if changed:
                user.email = email
                user.save(update_fields=["email"])
            EmailChangeRequest.objects.filter(pk=change.pk).delete()
    except IntegrityError:
        raise Conflict(
            gettext("This email is already used by another account."), code="accounts.email_taken"
        ) from None
    if changed:
        email_changed.send(
            sender=EmailAddress, request=request, user=user, from_email_address=previous, to_email_address=address
        )
        transaction.on_commit(partial(emails.send_email_changed, old_email, email, language=user.language), robust=True)
    logger.info("accounts.email_verified user=%s changed=%s", user.pk, changed)
    record_event(ctx, events.PROFILE_UPDATED)
    return {
        "verified": True,
        "attempts_left": max(EMAIL_CODE_ATTEMPTS - attempts, 0),
        "profile": queries.profile_of(user, request),
    }


# --- Account → Profile → «Change photo» -------------------------------------------------------------


def _photo_refusal(code: str) -> str:
    return {
        "unsupported": gettext("Upload a JPEG, PNG or WebP image."),
        "too_large": gettext("The photo is too big: at most %(size)s KB. Try a smaller one.")
        % {"size": photos.MAX_PHOTO_BYTES // 1000},
        "dimensions": gettext("The photo is too large: at most %(side)s × %(side)s pixels.") % {"side": photos.MAX_SIDE},
        "animated": gettext("Upload a still image, not an animation."),
    }.get(code, gettext("The image could not be read. Try another one."))


def too_many_attempts() -> OperationError:
    return OperationError(
        gettext("Too many attempts. Please try again in a few minutes."), code="accounts.too_many_attempts", status=429
    )


@operation("accounts.photo.upload", kind="command", permission="accounts.manage", input=PhotoUploadIn, output=ProfileOut)
def photo_upload(ctx: OperationContext, data: PhotoUploadIn) -> dict:
    """Keep the account's photo, cleaned (``accounts.photos``), in place of the one it had."""
    from django_ratelimit.core import is_ratelimited

    user = queries.account_of(ctx)
    try:
        cleaned, content_type = photos.clean_photo(photos.decode_upload(data.image))
    except photos.PhotoRejected as refused:
        raise InvalidPayload(gettext("Invalid payload"), fields={"image": _photo_refusal(refused.code)}) from None
    if is_ratelimited(
        None,
        group="accounts.photo.upload",
        key=lambda group, request: f"user:{user.pk}",
        rate=f"{photos.UPLOADS_PER_HOUR}/h",
        increment=True,
    ):
        raise too_many_attempts()
    ProfilePhoto.objects.update_or_create(user=user, defaults={"content_type": content_type, "data": cleaned})
    record_event(ctx, events.PROFILE_UPDATED)
    return queries.profile_of(user, ctx.request)


@operation("accounts.photo.remove", kind="command", permission="accounts.manage", input=PhotoRemoveIn, output=ProfileOut)
def photo_remove(ctx: OperationContext, data: PhotoRemoveIn) -> dict:
    """Remove the account's photo (the panel paints its initials). Without one, nothing changes."""
    user = queries.account_of(ctx)
    ProfilePhoto.objects.filter(user=user).delete()
    record_event(ctx, events.PROFILE_UPDATED)
    return queries.profile_of(user, ctx.request)


# --- Account → Security → Active sessions --------------------------------------------------------


def track_session(request) -> None:
    """Record the session of a signed-in request: its address, browser and last use (allauth.usersessions).
    A request whose address cannot be told (allauth refuses it) is not recorded, and the request goes on."""
    from allauth.usersessions.models import UserSession
    from django.core.exceptions import PermissionDenied

    try:
        UserSession.objects.create_from_request(request)
    except PermissionDenied:
        logger.warning("accounts.session_not_tracked user=%s: no client address", request.user.pk)


def end_sessions(sessions: list, *, user=None) -> None:
    """End ``sessions`` of the SaaS and ask the businesses of each account (and of ``user``, even with no
    session to end) to end theirs (``signals.sessions_ended``, PLAN-SAAS §2.1)."""
    accounts = [user.pk] if user is not None else []
    for session in sessions:
        session.end()
        if session.user_id not in accounts:
            accounts.append(session.user_id)
    for user_id in accounts:
        signals.sessions_ended.send(sender=get_user_model(), user_id=user_id)


def _end_and_sign_out(ctx: OperationContext, sessions: list, *, user=None) -> None:
    current = queries.current_session_key(ctx.request)
    end_sessions(sessions, user=user)
    if any(session.session_key == current for session in sessions):
        logout(ctx.request)


@operation(
    "accounts.session.close", kind="command", permission="accounts.manage", input=SessionCloseIn, output=SessionsClosedOut
)
def session_close(ctx: OperationContext, data: SessionCloseIn) -> dict:
    """End one session of the account (this one too: the answer signs it out)."""
    from allauth.usersessions.models import UserSession

    user = queries.account_of(ctx)
    session = UserSession.objects.filter(user=user, pk=data.id).first()
    if session is None:
        raise NotFound(gettext("That session does not exist or has already ended."))
    _end_and_sign_out(ctx, [session])
    record_event(ctx, events.SESSION_CLOSED)
    return {"closed": 1}


@operation(
    "accounts.session.close_others",
    kind="command",
    permission="accounts.manage",
    input=SessionCloseOthersIn,
    output=SessionsClosedOut,
)
def session_close_others(ctx: OperationContext, data: SessionCloseOthersIn) -> dict:
    """End every session of the account but this one; the businesses are asked even when none was left here
    (the apps' sessions in them may outlive their session in the SaaS)."""
    from allauth.usersessions.models import UserSession

    user = queries.account_of(ctx)
    current = queries.current_session_key(ctx.request)
    others = [session for session in UserSession.objects.filter(user=user) if session.session_key != current]
    closed = sum(1 for _, key in queries.live_sessions(user) if key != current)
    _end_and_sign_out(ctx, others, user=user)
    record_event(ctx, events.SESSION_CLOSED)
    return {"closed": closed}


# --- Account → API keys -----------------------------------------------------------------------

#: Keys an account may have that still work (not revoked nor expired).
MAX_ACTIVE_API_KEYS = 50
#: ``last_used_at`` is rewritten at most this often (GitLab batches usage the same way): no write per call.
API_KEY_LAST_USED_RESOLUTION = timedelta(minutes=10)


@operation(
    "accounts.apikey.create", kind="command", permission="accounts.manage", input=ApiKeyCreateIn, output=ApiKeyCreatedOut
)
def apikey_create(ctx: OperationContext, data: ApiKeyCreateIn) -> dict:
    """A new key of the account, bounded by its scopes: the answer carries the whole key, the only time it exists
    in clear (only its hash is kept). Creating access asks for a recent sign-in, as GitHub and Stripe do."""
    from django.db.models import Q

    user = queries.account_of(ctx)
    require_recent_authentication(ctx)
    now = timezone.now()
    # One creation at a time per account, so the ceiling holds.
    get_user_model().objects.select_for_update().filter(pk=user.pk).exists()
    active = ApiKey.objects.filter(user=user, revoked_at__isnull=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )
    if active.count() >= MAX_ACTIVE_API_KEYS:
        raise Conflict(
            gettext("You already have %(limit)s API keys: revoke one you no longer use.") % {"limit": MAX_ACTIVE_API_KEYS},
            code="accounts.api_key_limit",
        )
    secret, prefix, key_hash = ApiKey.new_secret()
    key = ApiKey.objects.create(
        user=user,
        name=data.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=data.scopes,
        created_at=now,
        expires_at=now + timedelta(days=data.expires_in_days) if data.expires_in_days else None,
    )
    logger.info("accounts.api_key_created user=%s key=%s scopes=%s", user.pk, key.pk, ",".join(key.scopes))
    record_event(ctx, events.APIKEY_CREATED)
    transaction.on_commit(
        partial(emails.send_api_key_created, user.email, key.name, list(key.scopes), language=user.language),
        robust=True,
    )
    return {"key": queries.api_key_row(key, now), "secret": secret}


@operation("accounts.apikey.revoke", kind="command", permission="accounts.manage", input=ApiKeyRevokeIn, output=ApiKeyRowOut)
def apikey_revoke(ctx: OperationContext, data: ApiKeyRevokeIn) -> dict:
    """Cut a key of the account on the spot. Revoking is the audit trail: the row stays. Twice changes nothing."""
    user = queries.account_of(ctx)
    now = timezone.now()
    key = ApiKey.objects.select_for_update().filter(user=user, pk=data.id).first()
    if key is None:
        raise NotFound(gettext("That API key does not exist."))
    if key.revoked_at is None:
        key.revoked_at = now
        key.save(update_fields=["revoked_at"])
        logger.info("accounts.api_key_revoked user=%s key=%s", user.pk, key.pk)
        record_event(ctx, events.APIKEY_REVOKED)
    return queries.api_key_row(key, now)


def record_api_key_use(key: ApiKey, now) -> None:
    """Remember the key was used now, at most once every ``API_KEY_LAST_USED_RESOLUTION``."""
    if key.last_used_at is not None and now - key.last_used_at < API_KEY_LAST_USED_RESOLUTION:
        return
    ApiKey.objects.filter(pk=key.pk).update(last_used_at=now)
    key.last_used_at = now


#: The admin's revocation: a system context only (no role grants it), on the owner's channel.
REVOKE_ANY_KEY = "accounts.revoke_any_key"


@operation("accounts.apikey.revoke_any", kind="command", permission=REVOKE_ANY_KEY, input=ApiKeyRevokeIn, output=ApiKeyRowOut)
def apikey_revoke_any(ctx: OperationContext, data: ApiKeyRevokeIn) -> dict:
    """Cut any account's key (the admin's «Revoke»), as its owner would: the event goes to the owner's channel
    (the context's scope), so its live list refreshes. Called only by ``revoke_api_keys``; no route."""
    now = timezone.now()
    key = ApiKey.objects.select_for_update().filter(pk=data.id).first()
    if key is None:
        raise NotFound(gettext("That API key does not exist."))
    if ctx.scope.key != str(key.user_id):
        raise LiveMisuse(f"accounts.apikey.revoke_any runs on the key owner's channel, not {ctx.scope.key!r}.")
    if key.revoked_at is None:
        key.revoked_at = now
        key.save(update_fields=["revoked_at"])
        record_event(ctx, events.APIKEY_REVOKED)
    return queries.api_key_row(key, now)


def revoke_api_keys(keys, *, by) -> int:
    """Revoke ``keys`` (a queryset) that still work, from the admin; how many were cut."""
    from live.context import Scope, system_context

    count = 0
    for key in keys.filter(revoked_at__isnull=True).only("pk", "user_id"):
        apikey_revoke_any(system_context(Scope("user", str(key.user_id))), ApiKeyRevokeIn(id=key.pk))
        count += 1
    logger.warning("accounts.api_keys_revoked_by_staff staff=%s count=%s", by.pk, count)
    return count


def password_changed_ends_sessions(sender, request=None, user=None, **kwargs) -> None:
    """allauth's ``password_changed``, ``password_set`` and ``password_reset``: a new password ends the account's
    other sessions here (Django), and in every business too (PLAN-SAAS §2.1, ``signals.sessions_ended``)."""
    if user is None:
        return
    signals.sessions_ended.send(sender=get_user_model(), user_id=user.pk)
