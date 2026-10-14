"""Which Stripe mode a secret key belongs to (``billing.stripe_keys``).

Ported from ERPlora/saas ``apps/core/stripe_keys.py`` (origin/develop; saas#2177), whose guard asked about
one prefix: a restricted test key (``rk_test_``) passed for live and a legitimate one was refused. Guards
that protect money ask about the MODE of a secret (``sk_``) or restricted (``rk_``) key; anything else is
UNKNOWN, never «probably live».
"""

import pytest

from billing.stripe_keys import StripeKeyMode, stripe_key_mode


@pytest.mark.parametrize(
    "key, mode",
    [
        ("sk_test_51abc", StripeKeyMode.TEST),
        ("rk_test_51abc", StripeKeyMode.TEST),
        ("sk_live_51abc", StripeKeyMode.LIVE),
        ("rk_live_51abc", StripeKeyMode.LIVE),
    ],
)
def test_secret_and_restricted_keys_say_their_mode(key, mode):
    assert stripe_key_mode(key) is mode


@pytest.mark.parametrize(
    "key",
    [
        "",
        None,
        "pk_live_51abc",  # a publishable key is not a secret
        "whsec_abc",  # nor a webhook secret
        "sk_prod_51abc",
        "sk_live_",  # no body
        " sk_live_51abc",
        "sk_live_51 abc",
    ],
)
def test_anything_else_is_unknown(key):
    assert stripe_key_mode(key) is StripeKeyMode.UNKNOWN
