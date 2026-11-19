import re

import pytest

from config.tests.production_settings import AWS_ENV, PRODUCTION_ENV, TASKS, _run, check_deploy, task_settings


# The deploy checklist: `manage.py check --deploy` has nothing to say about production.


def test_check_deploy_is_clean_in_production():
    # AWS_ENV carries SES_REGION as ECS sets it: the SES backend must not trip mail.E001.
    result = _run(
        "from django.core.management import execute_from_command_line\n"
        "execute_from_command_line(['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'])",
        {**PRODUCTION_ENV, **AWS_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


# What step 16 fills by hand: Google's client and Stripe's keys.
FILLED_BY_HAND = {
    "GOOGLE_OAUTH_CLIENT_ID": "prod-client.apps.googleusercontent.com",
    "GOOGLE_OAUTH_CLIENT_SECRET": "prod-secret",
    # A RESTRICTED live key: the account's secret key fails the deploy check (billing.E001).
    "STRIPE_SECRET_KEY": "rk_live_dummy",
    "STRIPE_PUBLISHABLE_KEY": "pk_live_dummy",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy",
    # WhatsApp (whatsapp/): born empty like Google until its secrets reach the infrastructure.
    "WHATSAPP_APP_ID": "1234567890",
    "WHATSAPP_APP_SECRET": "prod-meta-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "prod-verify-token",
    "WHATSAPP_CONFIG_ID": "987654321",
    "FERNET_KEY": "yh5h4Yur2lIgWp9ZxkyLt1BrQfFVrwLH4WhIHCRwXXA=",
}


@pytest.mark.parametrize("task", TASKS)
def test_every_saas_task_loads_its_settings(task):
    assert task_settings(
        "(s.DEBUG, s.ALLOWED_HOSTS, s.AWS_REGION, s.DATABASES['default']['OPTIONS']['application_name'],"
        " s.FISCAL_SEAL_CURRENT_P12_BASE64, s.FISCAL_SEAL_CURRENT_PASSWORD,"
        " s.FISCAL_SEAL_NEXT_P12_BASE64, s.FISCAL_SEAL_NEXT_PASSWORD)",
        task,
    ) == (
        False,
        ["erplora.com", "saas.erplora.internal"],
        "eu-west-1",
        task,
        # An empty slot is an empty slot; saas-migrate gets none at all.
        "",
        "",
        "",
        "",
    )


@pytest.mark.parametrize("task", TASKS)
def test_check_deploy_has_nothing_to_say_about_any_saas_task(task):
    """Born with Google and WhatsApp empty, the only lines are accounts.I001 and whatsapp.I001 (Infos: «Continue
    with Google» is hidden until step 16, and WhatsApp is off until its secrets come); never a warning, never
    mail.E001."""
    result = check_deploy(TASKS[task])
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "mail.E001" not in output
    assert "WARNINGS:" not in output and "ERRORS:" not in output, output
    assert set(re.findall(r"\(([a-z_]+\.[A-Z]\d{3})\)", output)) <= {"accounts.I001", "whatsapp.I001"}


@pytest.mark.parametrize("task", TASKS)
def test_check_deploy_identifies_no_issues_once_the_keys_are_filled(task):
    result = check_deploy({**TASKS[task], **FILLED_BY_HAND})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


def test_check_deploy_refuses_the_stripe_accounts_live_secret_key():
    result = check_deploy({**TASKS["saas"], **FILLED_BY_HAND, "STRIPE_SECRET_KEY": "sk_live_dummy"})

    assert result.returncode != 0
    assert "billing.E001" in result.stdout + result.stderr
