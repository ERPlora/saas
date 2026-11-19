import ast

import pytest

from config.tests.production_settings import PRODUCTION_ENV, TASKS, _run, development, production


# Sign-in attempts (allauth's rate limits): allauth lays ACCOUNT_RATE_LIMITS over its own defaults, so
# what it enforces is read where allauth reads it (allauth.account.app_settings), never from the dict the
# settings write. Only the e2e's panel server raises the limits per address of the sign-in and of the sign-up
# (E2E_RELAX_LOGIN_RATE_LIMIT): every spec signs in from 127.0.0.1, and one spec repeated (`--repeat-each=6`)
# went past allauth's 30 a minute; the eleventh sign-up of a run, past the 10 an hour.

RATE_LIMITS = (
    "from django.conf import settings\n"
    "from allauth.account import app_settings\n"
    "effective = app_settings.RATE_LIMITS\n"
    "settings.ACCOUNT_RATE_LIMITS = {}\n"
    "print(repr((effective, app_settings.RATE_LIMITS)))"
)


def rate_limits(env: dict[str, str]) -> tuple[dict, dict]:
    """(the rate limits allauth enforces with ``env``, allauth's own defaults with the rest of the settings)."""
    result = _run(RATE_LIMITS, {**env, "DJANGO_SETTINGS_MODULE": "config.settings"})
    assert result.returncode == 0, result.stderr
    return ast.literal_eval(result.stdout.strip())


@pytest.mark.parametrize(
    "env",
    [PRODUCTION_ENV, TASKS["saas"], {"DEBUG": "True"}],
    ids=["production", "saas-task", "development"],
)
def test_the_sign_in_limits_are_written_out(env):
    """Production and development alike (the dev server with DEBUG=True alone): every limit written out
    (config/settings/accounts.py), allauth's sign-in limit kept, and nothing of allauth's left unsaid."""
    effective, allauth = rate_limits(env)

    assert effective["login"] == allauth["login"]
    assert {**allauth, **effective} == {
        **allauth,
        "login": "30/m/ip",
        "login_failed": "5/5m/ip,5/5m/key",
        "signup": "10/h/ip",
        "reset_password": "10/h/ip,5/h/key",
        "reset_password_from_key": "20/m/ip",
        "confirm_email": "1/10s/key",
        "code_attempts": "10/5m/ip",
    }


@pytest.mark.parametrize("off", ["0", "False"])
def test_the_e2e_variable_turned_off_keeps_every_limit(off):
    effective, allauth = rate_limits({"DEBUG": "True", "E2E_RELAX_LOGIN_RATE_LIMIT": off})
    kept, _ = rate_limits({"DEBUG": "True"})

    assert effective["login"] == allauth["login"]
    assert effective["signup"] == "10/h/ip"
    assert effective == kept


# What the e2e variable raises: the budgets per address (`ip`) that every spec, from 127.0.0.1, shares.
E2E_RELAXED = {
    "login": "1000/m/ip",
    "login_failed": "1000/m/ip,5/5m/key",
    "signup": "1000/m/ip",
    "code_attempts": "1000/m/ip",
}


def test_the_e2e_raises_the_limits_per_address_of_the_sign_in_and_of_the_sign_up_and_nothing_else():
    """Every panel spec signs in from 127.0.0.1, password and mailed code, and the specs that create their accounts
    through «Create account» sign up from there too: the address's budgets of the sign-in, of the failed passwords, of
    the typed codes and of the sign-up go out of the e2e's reach (one at a time, each over 0.1 s), still a limit.
    Each account keeps its own (5 wrong passwords in 5 minutes), and so do the reset links and «Send another code»."""
    relaxed, allauth = rate_limits({"DEBUG": "True", "E2E_RELAX_LOGIN_RATE_LIMIT": "True"})
    kept, _ = rate_limits({"DEBUG": "True"})

    assert relaxed["login"] != allauth["login"]
    assert relaxed["signup"] != kept["signup"] == "10/h/ip"
    assert {action: relaxed[action] for action in E2E_RELAXED} == E2E_RELAXED
    assert {**relaxed, **{action: kept[action] for action in E2E_RELAXED}} == kept
    assert (relaxed["reset_password"], relaxed["confirm_email"]) == ("10/h/ip,5/h/key", "1/10s/key")


def test_production_refuses_to_start_with_the_e2e_s_sign_in_limit():
    result = _run("import config.settings", {**PRODUCTION_ENV, "E2E_RELAX_LOGIN_RATE_LIMIT": "True"})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "E2E_RELAX_LOGIN_RATE_LIMIT" in result.stderr


# «Continue with Google»: where the code is exchanged. What comes back from that address is believed without
# checking its signature (allauth trusts its own TLS call to Google), so only a development server may move it:
# the e2e's double of Google (tests/e2e/panel/accounts-google.spec.ts).
GOOGLE_TOKEN_URL = "s.SOCIALACCOUNT_PROVIDERS['google'].get('ACCESS_TOKEN_URL')"
GOOGLE_DOUBLE = "http://127.0.0.1:8015/token"


def test_production_always_exchanges_the_google_code_with_google():
    assert production(GOOGLE_TOKEN_URL, GOOGLE_OAUTH_TOKEN_URL=GOOGLE_DOUBLE) is None


def test_development_exchanges_the_google_code_with_google_unless_moved():
    assert development(GOOGLE_TOKEN_URL) is None
    assert development(GOOGLE_TOKEN_URL, GOOGLE_OAUTH_TOKEN_URL="") is None


def test_development_may_move_the_google_code_exchange_to_a_double():
    assert development(GOOGLE_TOKEN_URL, GOOGLE_OAUTH_TOKEN_URL=GOOGLE_DOUBLE) == GOOGLE_DOUBLE
