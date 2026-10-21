"""System checks of billing: production never holds the Stripe account's live SECRET key (PLAN-SAAS §4).

A restricted live key (``rk_live_``) has only the permissions the SaaS needs; the account's secret key
(``sk_live_``) can do everything a thief would want. ``manage.py check --deploy`` refuses it (``billing.E001``)
and the gateway does not use it either (``billing.stripe_service.key_mode``).

Outside prod (``ERPLORA_ENVIRONMENT=pre``, plan 2026-10-14-entorno-pre) Stripe runs in test mode only:
whoever pushes to the pre branch runs code with pre's secrets, so a live key there fails the deploy
(``billing.E002``).
"""

import pytest
from django.core import checks


def deploy_errors(settings, key, publishable=""):
    settings.STRIPE_SECRET_KEY = key
    settings.STRIPE_PUBLISHABLE_KEY = publishable
    return [message.id for message in checks.run_checks(include_deployment_checks=True) if message.id.startswith("billing.")]


def test_a_live_secret_key_fails_the_deploy_check(settings):
    assert deploy_errors(settings, "sk_live_dummy") == ["billing.E001"]


@pytest.mark.parametrize("key", ["rk_live_dummy", "sk_test_dummy", "rk_test_dummy", ""])
def test_any_other_key_passes(settings, key):
    assert deploy_errors(settings, key) == []


def test_the_check_runs_only_on_deploy(settings):
    settings.STRIPE_SECRET_KEY = "sk_live_dummy"

    assert not [message for message in checks.run_checks() if message.id == "billing.E001"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [("rk_live_dummy", ["billing.E002"]), ("sk_live_dummy", ["billing.E001", "billing.E002"])],
)
def test_a_live_key_outside_prod_fails_the_deploy_check(settings, key, expected):
    settings.ERPLORA_ENVIRONMENT = "pre"

    assert sorted(deploy_errors(settings, key)) == expected


def test_a_live_publishable_key_outside_prod_fails_the_deploy_check(settings):
    settings.ERPLORA_ENVIRONMENT = "pre"

    assert deploy_errors(settings, "rk_test_dummy", publishable="pk_live_dummy") == ["billing.E002"]


@pytest.mark.parametrize("key", ["rk_test_dummy", "sk_test_dummy", ""])
def test_outside_prod_a_test_key_passes(settings, key):
    settings.ERPLORA_ENVIRONMENT = "pre"

    assert deploy_errors(settings, key, publishable="pk_test_dummy" if key else "") == []


def test_prod_keeps_its_live_keys(settings):
    assert deploy_errors(settings, "rk_live_dummy", publishable="pk_live_dummy") == []


@pytest.mark.parametrize("key", ["sk_test_dummy", "rk_test_dummy"])
def test_a_test_key_in_production_fails_the_deploy_check(settings, key):
    """BILLING-F30: a test key in production (DEBUG off) would sell paid plans for test cards, so the deploy
    refuses it; development keeps its test keys (DEBUG on)."""
    settings.STRIPE_TEST_KEYS_ALLOWED = False

    assert deploy_errors(settings, key, publishable="pk_test_dummy") == ["billing.E003"]


def test_a_test_publishable_key_in_production_fails_the_deploy_check(settings):
    settings.STRIPE_TEST_KEYS_ALLOWED = False

    assert deploy_errors(settings, "rk_live_dummy", publishable="pk_test_dummy") == ["billing.E003"]


@pytest.mark.parametrize(
    ("debug", "environment", "allowed"), [(True, "prod", True), (False, "pre", True), (True, "pre", True), (False, "prod", False)]
)
def test_only_production_without_debug_refuses_test_keys(debug, environment, allowed):
    """``settings.STRIPE_TEST_KEYS_ALLOWED`` comes from here when the settings load: development (prod with DEBUG
    on) and pre keep their test keys; deployed production does not."""
    from billing.stripe_keys import test_keys_allowed

    assert test_keys_allowed(debug=debug, environment=environment) is allowed


def test_the_settings_work_it_out_from_debug_and_the_environment():
    from django.conf import settings

    from billing.stripe_keys import test_keys_allowed

    # pytest-django turns DEBUG off after the settings load; they loaded with DEBUG on (config.settings_pytest).
    assert settings.STRIPE_TEST_KEYS_ALLOWED is test_keys_allowed(debug=True, environment=settings.ERPLORA_ENVIRONMENT)
