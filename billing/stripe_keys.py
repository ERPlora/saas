"""Which Stripe mode a secret key belongs to (saas#2177).

Ported from ERPlora/saas ``apps/core/stripe_keys.py`` (origin/develop). Guards that protect money ask
about the MODE, not about one prefix: Stripe secret keys come as ``sk_<mode>_…`` and, for least
privilege, as restricted ``rk_<mode>_…`` (production uses a restricted live key, PLAN-SAAS §4). A guard
that only knew ``sk_test_`` let a restricted test key into production and refused a legitimate one.
"""

import enum
import re


class StripeKeyMode(enum.Enum):
    TEST = "test"
    LIVE = "live"
    #: Not a secret or restricted key (empty, publishable, a webhook secret, a typo…). Callers treat it as
    #: an error of its own, never as «probably live».
    UNKNOWN = "unknown"


_SECRET_KEY_SHAPE = re.compile(r"^(?:sk|rk)_(test|live)_\S+$")


def stripe_key_mode(key: str | None) -> StripeKeyMode:
    """The mode encoded in the second segment of a secret (``sk_``) or restricted (``rk_``) key."""
    match = _SECRET_KEY_SHAPE.match(key or "")
    if match is None:
        return StripeKeyMode.UNKNOWN
    return StripeKeyMode(match.group(1))
