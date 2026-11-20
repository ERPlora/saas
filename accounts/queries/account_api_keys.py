"""Account → API keys: the keys the account holds, and the key a request carries (``api_auth``)."""

from typing import Any

from django.utils import timezone, translation
from django.utils.crypto import constant_time_compare
from live.context import OperationContext
from live.operations import AI, operation

from accounts.models import API_KEY_PREFIX_LENGTH, API_KEY_SCOPES, ApiKey
from accounts.queries.account_lookup import account_of
from accounts.schemas import ApiKeyListIn, ApiKeyListOut


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
