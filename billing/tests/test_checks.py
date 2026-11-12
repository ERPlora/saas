"""System checks of billing: production never holds the Stripe account's live SECRET key.

A restricted live key (``rk_live_``) has only the permissions the SaaS needs; the account's secret key
(``sk_live_``) can do everything a thief would want. ``manage.py check --deploy`` refuses it (``billing.E001``)
and the gateway does not use it either (``billing.stripe_service.key_mode``).

STRIPE_EXPECTED_MODE controls both configured keys independently of the deployment label or DEBUG.
"""

import pytest
from django.core import checks


def deploy_errors(settings, key, publishable=""):
    settings.STRIPE_SECRET_KEY = key
    settings.STRIPE_PUBLISHABLE_KEY = publishable
    return [message.id for message in checks.run_checks(include_deployment_checks=True) if message.id.startswith("billing.")]


def test_a_live_secret_key_fails_the_deploy_check(settings):
    settings.STRIPE_EXPECTED_MODE = "live"
    assert deploy_errors(settings, "sk_live_dummy") == ["billing.E001"]


@pytest.mark.parametrize("key", ["rk_live_dummy", "sk_test_dummy", "rk_test_dummy", ""])
def test_any_other_key_passes(settings, key):
    settings.STRIPE_EXPECTED_MODE = "live" if "live" in key else "test"
    assert deploy_errors(settings, key) == []


def test_the_check_runs_only_on_deploy(settings):
    settings.STRIPE_SECRET_KEY = "sk_live_dummy"

    assert not [message for message in checks.run_checks() if message.id == "billing.E001"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [("rk_live_dummy", ["billing.E002"]), ("sk_live_dummy", ["billing.E001", "billing.E002"])],
)
def test_test_mode_refuses_a_live_key(settings, key, expected):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.STRIPE_EXPECTED_MODE = "test"

    assert sorted(deploy_errors(settings, key)) == expected


def test_test_mode_refuses_a_live_publishable_key(settings):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.STRIPE_EXPECTED_MODE = "test"

    assert deploy_errors(settings, "rk_test_dummy", publishable="pk_live_dummy") == ["billing.E002"]


@pytest.mark.parametrize("key", ["rk_test_dummy", "sk_test_dummy", ""])
def test_test_mode_accepts_a_test_key(settings, key):
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.STRIPE_EXPECTED_MODE = "test"

    assert deploy_errors(settings, key, publishable="pk_test_dummy" if key else "") == []


def test_live_mode_accepts_live_keys_independently_of_the_label(settings):
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.STRIPE_EXPECTED_MODE = "live"
    assert deploy_errors(settings, "rk_live_dummy", publishable="pk_live_dummy") == []


@pytest.mark.parametrize("key", ["sk_test_dummy", "rk_test_dummy"])
def test_live_mode_refuses_a_test_key(settings, key):
    """Live mode must not sell paid plans for test cards."""
    settings.STRIPE_EXPECTED_MODE = "live"

    assert deploy_errors(settings, key, publishable="pk_test_dummy") == ["billing.E003"]


def test_live_mode_refuses_a_test_publishable_key(settings):
    settings.STRIPE_EXPECTED_MODE = "live"

    assert deploy_errors(settings, "rk_live_dummy", publishable="pk_test_dummy") == ["billing.E003"]


@pytest.mark.parametrize("debug", [True, False])
def test_debug_does_not_bypass_the_expected_live_mode(settings, debug):
    settings.DEBUG = debug
    settings.STRIPE_EXPECTED_MODE = "live"
    assert deploy_errors(settings, "rk_test_dummy", "pk_test_dummy") == ["billing.E003"]
