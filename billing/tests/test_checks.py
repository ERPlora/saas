"""System checks of billing: production never holds the Stripe account's live SECRET key (PLAN-SAAS §4).

A restricted live key (``rk_live_``) has only the permissions the SaaS needs; the account's secret key
(``sk_live_``) can do everything a thief would want. ``manage.py check --deploy`` refuses it (``billing.E001``)
and the gateway does not use it either (``billing.stripe_service.key_mode``).
"""

import pytest
from django.core import checks


def deploy_errors(settings, key):
    settings.STRIPE_SECRET_KEY = key
    return [message.id for message in checks.run_checks(include_deployment_checks=True) if message.id.startswith("billing.")]


def test_a_live_secret_key_fails_the_deploy_check(settings):
    assert deploy_errors(settings, "sk_live_dummy") == ["billing.E001"]


@pytest.mark.parametrize("key", ["rk_live_dummy", "sk_test_dummy", "rk_test_dummy", ""])
def test_any_other_key_passes(settings, key):
    assert deploy_errors(settings, key) == []


def test_the_check_runs_only_on_deploy(settings):
    settings.STRIPE_SECRET_KEY = "sk_live_dummy"

    assert not [message for message in checks.run_checks() if message.id == "billing.E001"]
