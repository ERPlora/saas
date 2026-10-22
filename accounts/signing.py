"""HMAC-SHA256 + timestamp of the internal calls between hub-next and saas-next (PLAN-SAAS §2, §2.1).

Every call carries ``X-Erplora-Timestamp`` (unix seconds) and up to two signatures, hex HMAC-SHA256
keyed with the shared secret (the scheme of Stripe's webhook signatures):

- ``X-Erplora-Signature`` (v1) over ``f"{timestamp}.{raw_body}"``: the body only. It is what hub-next
  signs today (``hub-next/base/auth.py``, its call to ``/internal/auth/redeem``), so it is still heard.
- ``X-Erplora-Signature-V2`` (v2) over ``f"v2\\n{timestamp}\\n{METHOD}\\n{path}\\n"`` + the raw body,
  where ``path`` is the one requested, with its query string: also the method and the route, so a
  signed body cannot be replayed on another route within the window. The separators are newlines,
  which a request path never holds raw.

The SaaS signs every call it makes with both (``signed_headers``), keyed with the current secret
only. A call is verified (``verify_signed``, ``verify_request``) by v2 when it carries it, and then
by v2 alone: naming v2 and failing it is refused even if v1 passes (no downgrade); without v2, by v1,
and only for a path without a query string (``query_needs_v2``): v1 never signs the query, so a captured v1
signature would let anybody ask, within its window, for any query on that door.
Each signature is checked against every live secret (``live_secrets``): ``INTERNAL_SHARED_SECRET``
and, during a rotation, ``INTERNAL_SHARED_SECRET_PREVIOUS`` (empty otherwise). A timestamp more than
``INTERNAL_SIGNATURE_MAX_AGE_SECONDS`` (five minutes) away is refused, and so is one that is not 1 to 20
ASCII digits (``int()`` raises beyond 4300: a 500 on every door). ``may_be_signed`` judges the headers
alone, so a view that reads a large body itself refuses before reading it what can never verify.

Rotation, with hub-next taking the same steps (each one deployed to both projects before the next):
1. ``INTERNAL_SHARED_SECRET_PREVIOUS`` = the new secret: both accept it, both still sign with the old.
2. ``INTERNAL_SHARED_SECRET`` = the new one and ``…_PREVIOUS`` = the old: both sign with the new and
   still accept a call of the other side signed before it moved.
3. ``…_PREVIOUS`` empty: the old secret opens nothing any more.

Migration to v2 only: hub-next verifies v2 when present and signs its own calls with it too (Hub
lane); once both sides sign v2, a call without it is refused (v1 dropped here and in the Hub).
"""

import hashlib
import hmac
import re
import time
from collections.abc import Iterable, Mapping

from django.conf import settings

DEFAULT_MAX_AGE_SECONDS = 300
# A unix time in seconds, ASCII digits only (``str.isdigit`` would take other scripts' digits).
_TIMESTAMP = re.compile(r"[0-9]{1,20}")
TIMESTAMP_HEADER = "X-Erplora-Timestamp"
SIGNATURE_HEADER = "X-Erplora-Signature"
SIGNATURE_V2_HEADER = "X-Erplora-Signature-V2"


def sign(body: bytes, timestamp: int, secret: str) -> str:
    """The v1 hex signature of ``body`` sent at ``timestamp`` (the body only)."""
    message = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def sign_v2(method: str, path: str, body: bytes, timestamp: int, secret: str) -> str:
    """The v2 hex signature of ``method`` on ``path`` (with its query) with ``body``, sent at ``timestamp``."""
    message = f"v2\n{timestamp}\n{method.upper()}\n{path}\n".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signed_headers(
    method: str, path: str, body: bytes, timestamp: int, secret: str
) -> dict[str, str]:
    """The headers that sign a call: the timestamp, v1 and v2, all with ``secret``."""
    return {
        TIMESTAMP_HEADER: str(timestamp),
        SIGNATURE_HEADER: sign(body, timestamp, secret),
        SIGNATURE_V2_HEADER: sign_v2(method, path, body, timestamp, secret),
    }


def live_secrets() -> tuple[str, ...]:
    """The secrets a call may be signed with: the current one and, during a rotation, the previous."""
    candidates = (
        settings.INTERNAL_SHARED_SECRET,
        getattr(settings, "INTERNAL_SHARED_SECRET_PREVIOUS", ""),
    )
    return tuple(secret for secret in candidates if secret)


def _sent_at(timestamp: str | None, now: int, max_age: int) -> int | None:
    """The timestamp as an int, or ``None`` if it is missing, malformed or outside the window."""
    if not timestamp or not _TIMESTAMP.fullmatch(timestamp):
        return None
    sent_at = int(timestamp)
    return sent_at if abs(now - sent_at) <= max_age else None


def _matches(expected_by_secret, signature: str | None, secrets: Iterable[str]) -> bool:
    if not signature or not signature.isascii():
        return False
    return any(
        hmac.compare_digest(expected_by_secret(secret), signature)
        for secret in secrets
        if secret
    )


def _as_secrets(secret: str | Iterable[str]) -> list[str]:
    return [secret] if isinstance(secret, str) else list(secret)


def verify(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    *,
    secret: str | Iterable[str],
    now: int,
    max_age: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    """Whether the v1 ``signature`` signs ``body`` at ``timestamp`` with ``secret`` (one or several),
    within ``max_age`` of ``now``."""
    sent_at = _sent_at(timestamp, now, max_age)
    if sent_at is None:
        return False
    return _matches(
        lambda key: sign(body, sent_at, key), signature, _as_secrets(secret)
    )


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """``headers[name]`` whatever the case of the key (a ``dict`` from an HTTP server keeps the sender's)."""
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def query_needs_v2(path: str, headers: Mapping[str, str]) -> bool:
    """Whether a call to ``path`` (with its query string) is refused because it carries a query and no v2: v1
    signs the body only, never the query. A view may say so in its answer."""
    return "?" in path and _header(headers, SIGNATURE_V2_HEADER) is None


def verify_signed(
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    *,
    secrets: Iterable[str],
    now: int,
    max_age: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    """Whether a call of ``method`` on ``path`` with ``body`` and ``headers`` is signed with one of
    ``secrets`` within ``max_age`` of ``now``: by v2 if it carries it (v2 alone decides), else by v1, which
    is refused on a path with a query (``query_needs_v2``)."""
    secrets = list(secrets)
    timestamp = _header(headers, TIMESTAMP_HEADER)
    signature_v2 = _header(headers, SIGNATURE_V2_HEADER)
    if query_needs_v2(path, headers):
        return False
    if signature_v2 is None:
        return verify(
            body,
            timestamp,
            _header(headers, SIGNATURE_HEADER),
            secret=secrets,
            now=now,
            max_age=max_age,
        )
    sent_at = _sent_at(timestamp, now, max_age)
    if sent_at is None:
        return False
    return _matches(
        lambda key: sign_v2(method, path, body, sent_at, key), signature_v2, secrets
    )


def may_be_signed(headers: Mapping[str, str], *, now: int, max_age: int = DEFAULT_MAX_AGE_SECONDS) -> bool:
    """Whether ``headers`` leave room for a valid signature: a timestamp within ``max_age`` of ``now`` and
    a signature, v1 or v2. Only the body can prove it; this spares reading the body when they cannot."""
    if _sent_at(_header(headers, TIMESTAMP_HEADER), now, max_age) is None:
        return False
    return bool(_header(headers, SIGNATURE_HEADER) or _header(headers, SIGNATURE_V2_HEADER))


def verify_request(request, *, now: int | None = None) -> bool:
    """Whether a Django ``request`` to ``/internal`` is signed with a live secret (``verify_signed``)."""
    return verify_signed(
        request.method,
        request.get_full_path(),
        request.body,
        request.headers,
        secrets=live_secrets(),
        now=int(time.time()) if now is None else now,
        max_age=settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS,
    )
