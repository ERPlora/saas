"""An account's API key opens ``/api/`` (plan 2026-10-13, L3-A; PLAN-SAAS §2.4, ADR-0467).

A key (``erps_live_…``, ``accounts.models.ApiKey``) makes the request act as its account, bounded by its scopes,
and only on the operations declared with ``expose_api=True`` (opt-in, as in hub-next): ``<app>.read`` opens that
app's queries and ``<app>.write`` its commands. Every other route of the API refuses a key with 403
``api_key_not_allowed``, so a key never manages the account, its sessions or its keys. Routes open to anonymous
visitors (``auth=None``) ignore it.

Two headers are read: ``Authorization: Bearer erps_live_…`` (Stripe's, GitHub's and OpenAI's convention) and
``X-Api-Key`` (the hubs' header, PLAN-SAAS §6, and the old SaaS's). A browser never sends either by itself, so a
request with a key needs no CSRF token. Wrong keys are counted per address and a key's calls per minute; a key is
never logged whole.

``install_api_key_auth`` puts the checks in front of each route's own authentication (the session), once the
routers are mounted (``config/api.py``).
"""

import logging

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.utils.translation import gettext
from django_ratelimit.core import is_ratelimited
from live.errors import OperationError
from live.operations import Operation, registry
from ninja import NinjaAPI
from ninja.security import APIKeyHeader, HttpBearer

from accounts import queries, services
from accounts.models import API_KEY_PREFIX, API_KEY_SCOPES

logger = logging.getLogger(__name__)

#: Calls one key may make in a minute.
API_KEY_RATE = "600/m"
#: Wrong keys one address may send in a minute; past it, every key from there waits.
INVALID_KEY_RATE = "30/m"
HEADER = "X-Api-Key"


def scope_for(op: Operation) -> str:
    """The scope ``op`` asks of a key: ``<app>.read`` for a query, ``<app>.write`` for a command."""
    return f"{op.app_label}.{'read' if op.kind == 'query' else 'write'}"


def _redacted(raw: str) -> str:
    """Enough of a refused key to find it in the list, never enough to use it."""
    return f"{raw[: len(API_KEY_PREFIX) + 4]}…" if raw.startswith(API_KEY_PREFIX) else "(malformed)"


def _too_many() -> OperationError:
    return OperationError(gettext("Too many requests. Try again in a minute."), code="rate_limited", status=429)


def authenticate(request, raw: str, op: Operation):
    """The key ``raw`` for ``op``, or the refusal: 401 ``api_key_invalid``, 403 ``api_key_missing_scope``, 429."""
    address = request.META.get("REMOTE_ADDR", "")

    def wrong_keys(group, request):
        return f"ip:{address}"

    if is_ratelimited(None, group="accounts.api_key.invalid", key=wrong_keys, rate=INVALID_KEY_RATE, increment=False):
        raise _too_many()
    now = timezone.now()
    key = queries.api_key_for(raw, now)
    if key is None:
        logger.info("accounts.api_key_refused key=%s ip=%s", _redacted(raw), address)
        if is_ratelimited(None, group="accounts.api_key.invalid", key=wrong_keys, rate=INVALID_KEY_RATE, increment=True):
            raise _too_many()
        raise OperationError(gettext("Invalid API key."), code="api_key_invalid", status=401)
    scope = scope_for(op)
    if scope not in (key.scopes or []):
        raise OperationError(
            gettext("This API key is missing the permission this operation needs: %(scope)s.") % {"scope": scope},
            code="api_key_missing_scope",
            status=403,
        )
    if is_ratelimited(
        None, group="accounts.api_key", key=lambda group, request: f"key:{key.pk}", rate=API_KEY_RATE, increment=True
    ):
        raise _too_many()
    services.record_api_key_use(key, now)
    request.user = key.user
    return key


class ApiKeyBearer(HttpBearer):
    """``Authorization: Bearer erps_live_…`` on an exposed operation. Another scheme is no key of ours."""

    def __init__(self, operation: Operation) -> None:
        self.operation = operation
        super().__init__()

    def __call__(self, request):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return self.authenticate(request, token.strip())

    def authenticate(self, request, token):
        return authenticate(request, token, self.operation)


class ApiKeyHeader(APIKeyHeader):
    """``X-Api-Key: erps_live_…`` on an exposed operation. Empty is no key (Postman sends unset variables)."""

    param_name = HEADER

    def __init__(self, operation: Operation) -> None:
        self.operation = operation
        super().__init__()

    def authenticate(self, request, key):
        if not (key or "").strip():
            return None
        return authenticate(request, key.strip(), self.operation)


def _carries_key(request) -> bool:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return bool(request.headers.get(HEADER, "").strip()) or (scheme.lower() == "bearer" and bool(token.strip()))


def refuse_api_keys(request) -> None:
    """In front of the routes not exposed to keys: a key is refused (403), its absence lets the session answer."""
    if _carries_key(request):
        raise OperationError(
            gettext("API keys cannot be used here: this operation is only for signed-in people."),
            code="api_key_not_allowed",
            status=403,
        )
    return None


def install_api_key_auth(api: NinjaAPI) -> list[str]:
    """Put the key checks in front of every route of ``api`` that has authentication; return the operations a key
    may open. Raises ``ImproperlyConfigured`` when an exposed operation asks for a scope no key can carry."""
    exposed = []
    for bound_router in api._get_bound_routers():
        for path_view in bound_router.path_operations.values():
            for route in path_view.operations:
                callbacks = list(route.auth_callbacks)
                if not callbacks or callbacks[0] is refuse_api_keys or isinstance(callbacks[0], ApiKeyBearer):
                    continue  # open to anonymous visitors, or already installed
                op = registry.get(route.operation_id) if route.operation_id else None
                if op is None or not op.expose_api:
                    route.auth_callbacks = [refuse_api_keys, *callbacks]
                    continue
                scope = scope_for(op)
                if scope not in API_KEY_SCOPES:
                    raise ImproperlyConfigured(
                        f"{op.name} is exposed to API keys, but no key can carry {scope!r}: add it to "
                        "accounts.models.API_KEY_SCOPES (with its label) or do not expose the operation."
                    )
                route.auth_callbacks = [ApiKeyBearer(op), ApiKeyHeader(op), *callbacks]
                exposed.append(op.name)
    return exposed
