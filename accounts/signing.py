"""HMAC-SHA256 + timestamp of the internal calls between hub-next and saas-next (PLAN-SAAS §2).

The caller sends ``X-Erplora-Timestamp`` (unix seconds) and ``X-Erplora-Signature``, the hex
HMAC-SHA256 of ``f"{timestamp}.{raw_body}"`` keyed with ``INTERNAL_SHARED_SECRET`` (the scheme
of Stripe's webhook signatures). A timestamp more than five minutes away is refused.
"""

import hashlib
import hmac

DEFAULT_MAX_AGE_SECONDS = 300


def sign(body: bytes, timestamp: int, secret: str) -> str:
    """The hex signature of ``body`` sent at ``timestamp``."""
    message = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    *,
    secret: str,
    now: int,
    max_age: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    """Whether ``signature`` signs ``body`` at ``timestamp`` with ``secret``, within ``max_age`` of ``now``."""
    if not secret or not timestamp or not signature:
        return False
    if not (timestamp.isascii() and timestamp.isdigit() and signature.isascii()):
        return False
    sent_at = int(timestamp)
    if abs(now - sent_at) > max_age:
        return False
    return hmac.compare_digest(sign(body, sent_at, secret), signature)
