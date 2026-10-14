"""The SaaS's calls to hub-next's ``/internal`` (PLAN-SAAS §2, §2.2, §3.1, §3.4; round 17 §2.14).

Plain HTTP, no ORM: callers hand in the payloads (``hubs.queries`` builds them) and record the
answers (``hubs.services``). Every request is signed with the current ``INTERNAL_SHARED_SECRET``
(``accounts.signing.signed_headers``): ``X-Erplora-Timestamp``, the body-only v1 ``X-Erplora-Signature``
and ``X-Erplora-Signature-V2``, which also covers the method and the path. While the Hub may still
verify v1 only, every body names the hub of its path (``id`` or ``hub_id``) and the Hub compares them.

- ``put_hub`` → ``PUT /internal/hubs/{id}``: the registry (slug, name, country, time zone, language,
  vertical); 202 while the Hub provisions it, 200 when it already knew it.
- ``put_state`` → ``PUT /internal/hubs/{id}/state``: the snapshot of §2.2 with its monotonic version.
- ``get_hub`` → ``GET /internal/hubs/{id}``: the registry's status, to poll an sign-up stuck without its
  ``ready`` callback.
- ``delete_hub`` → ``DELETE /internal/hubs/{id}``; ``restore_hub`` → ``POST /internal/hubs/{id}/restore``.
- ``revoke_sessions`` → ``POST /internal/sessions/revoke`` (``{user_id, hub_id?}``, §2.1).

A 4xx raises ``HubRefused`` (with the Hub's error code); a 5xx, a timeout or no connection raises
``HubUnavailable``. Production reaches the Hub by its private name (``HUB_INTERNAL_URL``, aws-next
Cloud Map: ``http://hub.erplora.internal:8000``); the ALB answers 404 to ``/internal`` from outside.
"""

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from accounts.signing import signed_headers as _signed

#: A slow Hub costs the request that pushed after its COMMIT this much at most; the work stays
#: pending and ``reconcile_hub_states`` retries it.
TIMEOUT_SECONDS = 5.0


class HubUnavailable(Exception):
    """The Hub did not answer, timed out or failed (5xx): try again later."""


class HubRefused(Exception):
    """The Hub answered 4xx: it refuses the call as it is (``code`` is its error code)."""

    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HubAnswer:
    status: int
    body: Any


def signed_headers(method: str, path: str, body: bytes, timestamp: int) -> dict[str, str]:
    """The headers of ``method`` on ``path`` with ``body`` sent at ``timestamp``: JSON, signed v1 and v2."""
    return {
        "Content-Type": "application/json",
        **_signed(method, path, body, timestamp, settings.INTERNAL_SHARED_SECRET),
    }


def put_hub(registry: dict[str, Any]) -> HubAnswer:
    return _call("PUT", f"/internal/hubs/{registry['id']}", registry)


def put_state(hub_id: str, snapshot: dict[str, Any]) -> HubAnswer:
    return _call("PUT", f"/internal/hubs/{hub_id}/state", snapshot)


def get_hub(hub_id: str) -> HubAnswer:
    return _call("GET", f"/internal/hubs/{hub_id}", None)


def delete_hub(hub_id: str) -> HubAnswer:
    return _call("DELETE", f"/internal/hubs/{hub_id}", {"id": hub_id})


def restore_hub(hub_id: str) -> HubAnswer:
    return _call("POST", f"/internal/hubs/{hub_id}/restore", {"id": hub_id})


def revoke_sessions(user_id: str, hub_id: str | None = None) -> HubAnswer:
    body = (
        {"user_id": user_id}
        if hub_id is None
        else {"user_id": user_id, "hub_id": hub_id}
    )
    return _call("POST", "/internal/sessions/revoke", body)


def _call(method: str, path: str, payload: Any) -> HubAnswer:
    body = (
        b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    )
    request = urllib.request.Request(
        settings.HUB_INTERNAL_URL.rstrip("/") + path,
        data=body if method != "GET" else None,
        method=method,
        headers=signed_headers(method, path, body, int(time.time())),
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return HubAnswer(response.status, _json(response.read()))
    except urllib.error.HTTPError as failed:
        answer = _json(failed.read())
        if 400 <= failed.code < 500:
            error = answer.get("error", {}) if isinstance(answer, dict) else {}
            raise HubRefused(
                failed.code,
                str(error.get("code") or "refused"),
                str(error.get("message") or ""),
            ) from None
        raise HubUnavailable(f"{method} {path}: HTTP {failed.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, OSError) as failed:
        raise HubUnavailable(f"{method} {path}: {failed}") from None


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}
