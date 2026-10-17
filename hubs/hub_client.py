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
- ``post_platform_invoice`` → ``POST /internal/platform/invoices``: an invoice of ERPlora to a customer, to
  issue in ERPlora's platform hub (PLAN-SAAS §4; billing, lot L3-C), idempotent by its ``id``;
  ``platform_invoicing_health`` → ``GET /internal/platform/invoices/health`` (the gate of live charging);
  ``get_platform_invoice`` → ``GET /internal/platform/invoices/{id}`` (its status and QR) and
  ``get_platform_invoice_pdf`` → ``GET /internal/platform/invoices/{id}/pdf`` (the PDF's bytes, round 17
  §2.14).
- ``get_usage`` → ``GET /internal/usage?day=YYYY-MM-DD[&cursor=…]``: one page of what the Hub measured that
  day of every business (PLAN-SAAS §5; ``collect_hub_usage``, lot L4-A). The cursor goes back as it came.
- ``create_demo`` → ``POST /internal/demos``: a demo hub for one browser (PLAN-SAAS §3.5, round 2026-10-17;
  ``public/demo.py``); ``create_demo_code`` → ``POST /internal/demos/{slug}/codes``: the one-time code that
  browser posts to the demo's ``/auth/callback``.

A 4xx raises ``HubRefused`` (with the Hub's error code); a 5xx, a timeout or no connection raises
``HubUnavailable``. One 5xx is a refusal too: ``503 base.demo_full`` of ``create_demo``, the Hub's cap of live
demos, which the visitor is told about («full») instead of «not available». Production reaches the Hub by its private name (``HUB_INTERNAL_URL``, aws-next
Cloud Map: ``http://hub.erplora.internal:8000``); the ALB answers 404 to ``/internal`` from outside.
"""

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from django.conf import settings

from accounts.signing import signed_headers as _signed

#: A slow Hub costs the request that pushed after its COMMIT this much at most; the work stays
#: pending and ``reconcile_hub_states`` retries it.
TIMEOUT_SECONDS = 5.0

#: The 5xx codes of ``POST /internal/demos`` that are the Hub refusing, not the Hub being away.
DEMO_REFUSALS = frozenset({"base.demo_full"})


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


def post_platform_invoice(invoice: dict[str, Any]) -> HubAnswer:
    return _call("POST", "/internal/platform/invoices", invoice)


def platform_invoicing_health() -> HubAnswer:
    """Whether the platform hub issues invoices now: 200 ``{"status": "ok"}``."""
    return _call("GET", "/internal/platform/invoices/health", None)


def get_platform_invoice(invoice_id: str) -> HubAnswer:
    return _call("GET", f"/internal/platform/invoices/{invoice_id}", None)


def get_platform_invoice_pdf(invoice_id: str) -> bytes:
    """The PDF of an invoice the platform hub issued, as it sends it."""
    return _exchange("GET", f"/internal/platform/invoices/{invoice_id}/pdf", None)[1]


def get_usage(day: date, cursor: str | None = None) -> HubAnswer:
    """One page of the usage of ``day``: ``{day, hubs: [...], next_cursor}`` (``hubs/README.md``)."""
    query = {"day": day.isoformat()} if cursor is None else {"day": day.isoformat(), "cursor": cursor}
    return _call("GET", f"/internal/usage?{urlencode(query)}", None)


def create_demo(session_key: str, vertical: str | None, language: str) -> HubAnswer:
    """A demo hub for the browser ``session_key`` names (a sha256 hex, never a cookie).

    201 ``{id, slug, expires_at, created: true}`` for a new one; 200 with ``created: false`` when that browser
    already has a live one, which costs the Hub's cap nothing. ``HubRefused(503, "base.demo_full")`` when the
    cap of live demos is reached.
    """
    body = {"session_key": session_key, "vertical": vertical, "language": language}
    return _call("POST", "/internal/demos", body, refusals=DEMO_REFUSALS)


def create_demo_code(slug: str, session_key: str, language: str) -> HubAnswer:
    """201 ``{code, expires_at}``: a one-time code into the demo ``slug`` for the browser that owns it.

    The Hub refuses with 404 (no such demo), 410 ``base.hub_gone`` (it ended) or 403 ``base.demo_not_owner``
    (another browser's).
    """
    return _call("POST", f"/internal/demos/{slug}/codes", {"session_key": session_key, "language": language})


def _call(method: str, path: str, payload: Any, *, refusals: frozenset[str] = frozenset()) -> HubAnswer:
    status, raw = _exchange(method, path, payload, refusals=refusals)
    return HubAnswer(status, _json(raw))


def _exchange(
    method: str, path: str, payload: Any, *, refusals: frozenset[str] = frozenset()
) -> tuple[int, bytes]:
    """The status and body of the call; ``refusals``: the 5xx error codes that are a ``HubRefused`` too."""
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
            return response.status, response.read()
    except urllib.error.HTTPError as failed:
        answer = _json(failed.read())
        error = answer.get("error", {}) if isinstance(answer, dict) else {}
        error = error if isinstance(error, dict) else {}
        if 400 <= failed.code < 500 or error.get("code") in refusals:
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
