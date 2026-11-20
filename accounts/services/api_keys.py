"""Account → API keys, and the keys the admin issues and revokes for any account."""

import logging
from datetime import timedelta
from functools import partial

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, LiveMisuse, NotFound
from live.operations import AI, INTERNAL, operation
from live.outbox import record_event

from accounts import emails, events
from accounts.models import ApiKey
from accounts.queries import account_api_keys, account_lookup
from accounts.schemas import ApiKeyCreatedOut, ApiKeyCreateIn, ApiKeyIssueIn, ApiKeyRevokeIn, ApiKeyRowOut
from accounts.services.reauthentication import require_recent_authentication

logger = logging.getLogger("accounts.services")


#: Keys an account may have that still work (not revoked nor expired).
MAX_ACTIVE_API_KEYS = 50
#: ``last_used_at`` is rewritten at most this often (GitLab batches usage the same way): no write per call.
API_KEY_LAST_USED_RESOLUTION = timedelta(minutes=10)


@operation(
    "accounts.apikey.create",
    kind="command",
    permission="accounts.manage",
    input=ApiKeyCreateIn,
    output=ApiKeyCreatedOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=INTERNAL,  # secret
)
def apikey_create(ctx: OperationContext, data: ApiKeyCreateIn) -> dict:
    """A new key of the account, bounded by its scopes: the answer carries the whole key, the only time it exists
    in clear (only its hash is kept). Creating access asks for a recent sign-in, as GitHub and Stripe do."""
    user = account_lookup.account_of(ctx)
    require_recent_authentication(ctx)
    return _new_api_key(ctx, user, data)


def _new_api_key(ctx: OperationContext, user, data: ApiKeyCreateIn) -> dict:
    """A key of ``user`` within the ceiling: the row (its hash only), the event on the context's channel and the
    mail that tells the account. Returns the row and the whole key, the only time it exists in clear."""
    from django.db.models import Q

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
    return {"key": account_api_keys.api_key_row(key, now), "secret": secret}


@operation(
    "accounts.apikey.revoke",
    kind="command",
    permission="accounts.manage",
    input=ApiKeyRevokeIn,
    output=ApiKeyRowOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Revokes an API key of the account at once: what uses it stops working.",
        asks={
            "en": ("revoke the Zapier key", "kill that API key, it leaked", "disable my old API key"),
            "es": (
                "revoca la clave de Zapier",
                "anula esa clave de la API, se ha filtrado",
                "quita la clave de API vieja",
            ),
        },
    ),
)
def apikey_revoke(ctx: OperationContext, data: ApiKeyRevokeIn) -> dict:
    """Cut a key of the account on the spot. Revoking is the audit trail: the row stays. Twice changes nothing."""
    user = account_lookup.account_of(ctx)
    now = timezone.now()
    key = ApiKey.objects.select_for_update().filter(user=user, pk=data.id).first()
    if key is None:
        raise NotFound(gettext("That API key does not exist."))
    if key.revoked_at is None:
        key.revoked_at = now
        key.save(update_fields=["revoked_at"])
        logger.info("accounts.api_key_revoked user=%s key=%s", user.pk, key.pk)
        record_event(ctx, events.APIKEY_REVOKED)
    return account_api_keys.api_key_row(key, now)


def record_api_key_use(key: ApiKey, now) -> None:
    """Remember the key was used now, at most once every ``API_KEY_LAST_USED_RESOLUTION``."""
    if key.last_used_at is not None and now - key.last_used_at < API_KEY_LAST_USED_RESOLUTION:
        return
    ApiKey.objects.filter(pk=key.pk).update(last_used_at=now)
    key.last_used_at = now


#: The admin's revocation: a system context only (no role grants it), on the owner's channel.
REVOKE_ANY_KEY = "accounts.revoke_any_key"
#: The admin's «Add API key» for a team account: a system context only, on the owner's channel.
ISSUE_ANY_KEY = "accounts.issue_any_key"


@operation(
    "accounts.apikey.issue_any",
    kind="command",
    permission=ISSUE_ANY_KEY,
    input=ApiKeyIssueIn,
    output=ApiKeyCreatedOut,
    ai=INTERNAL,  # staff
)
def apikey_issue_any(ctx: OperationContext, data: ApiKeyIssueIn) -> dict:
    """A key for a team account, issued by a superuser from the admin. Only an active staff account: a customer's keys
    are the customer's own. The event goes to the owner's channel, so its live list refreshes, and the owner is told
    by mail. Called only by ``issue_api_key``; no route."""
    if ctx.scope.key != str(data.user_id):
        raise LiveMisuse(f"accounts.apikey.issue_any runs on the key owner's channel, not {ctx.scope.key!r}.")
    user = get_user_model().objects.filter(pk=data.user_id, is_active=True, is_staff=True).first()
    if user is None:
        raise NotFound(gettext("API keys are issued here for team accounts only."))
    return _new_api_key(ctx, user, data)


def issue_api_key(user, *, name: str, scopes: list[str], expires_in_days: int | None, by) -> ApiKeyCreatedOut:
    """The admin's «Add API key»: a key of the team account ``user``, issued by the superuser ``by``; the answer carries
    the whole key (``secret``), the only time it exists in clear."""
    from live.context import Scope, system_context

    issued = apikey_issue_any(
        system_context(Scope("user", str(user.pk))),
        ApiKeyIssueIn(user_id=user.pk, name=name, scopes=scopes, expires_in_days=expires_in_days),
    )
    logger.warning("accounts.api_key_issued_by_staff staff=%s user=%s key=%s", by.pk, user.pk, issued.key.id)
    return issued


@operation(
    "accounts.apikey.revoke_any",
    kind="command",
    permission=REVOKE_ANY_KEY,
    input=ApiKeyRevokeIn,
    output=ApiKeyRowOut,
    ai=INTERNAL,  # staff
)
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
    return account_api_keys.api_key_row(key, now)


def revoke_api_keys(keys, *, by) -> int:
    """Revoke ``keys`` (a queryset) that still work, from the admin; how many were cut."""
    from live.context import Scope, system_context

    count = 0
    for key in keys.filter(revoked_at__isnull=True).only("pk", "user_id"):
        apikey_revoke_any(system_context(Scope("user", str(key.user_id))), ApiKeyRevokeIn(id=key.pk))
        count += 1
    logger.warning("accounts.api_keys_revoked_by_staff staff=%s count=%s", by.pk, count)
    return count
