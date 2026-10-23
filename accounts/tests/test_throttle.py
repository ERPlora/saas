"""ACCOUNTS-G96: whoever tries passwords, codes or reset links is stopped, the same for an account as for none.

allauth's own limits (``ACCOUNT_RATE_LIMITS``, every one written out) on the shared cache (Valkey, Django's cache
only): failed passwords spend the account's budget and the address's, 5 in 5 minutes each (Ioan, 2026-10-22: «que no
intenten sin parar»; before, the address had 10 a minute), the right one gives its attempt back, so failures alone
never lock the owner out within the budget; the sign-in itself, 30 a minute per address; a reset link, 5 an hour per
account and 10 per address; the mailed codes, 3 tries each (``test_sign_in_code``) and, whatever the code, 10 refused
codes in 5 minutes per address (``code_attempts``, accounts/bot_check.py; a right one spends nothing), the authenticator
app's included. The
answers never tell which addresses hold an account (``test_unified_login``: the throttle reaches a known and an unknown
address at the same attempt).
"""

from itertools import count

import pytest
from django.conf import settings
from django.core import mail
from django.test import Client

from accounts.tests.test_unified_login import (  # noqa: F401  (`verified` and `wait` are fixtures)
    BROWSER,
    HOST,
    LOGIN,
    _code,
    _confirm,
    _pending,
    _post_without_csrf,
    verified,
    wait,
)
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

RESET = f"{BROWSER}/auth/password/request"
ips = count(1)


def _from_new_address(path: str, body: dict):
    """A request from an address never seen: an attacker rotating IPs spends only the account's budget."""
    n = next(ips)
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR=f"10.9.{n // 250}.{n % 250 + 1}")
    return client, _post_without_csrf(client, path, body)


def _codes(response) -> list[str]:
    return [error["code"] for error in response.json().get("errors", [])]


def test_five_failed_passwords_close_the_account_even_to_the_right_one(verified):
    for _ in range(5):
        _, response = _from_new_address(LOGIN, {"email": verified.email, "password": "a guess"})
        assert _codes(response) == ["email_password_mismatch"]

    _, response = _from_new_address(LOGIN, {"email": verified.email, "password": PASSWORD})

    assert (response.status_code, _codes(response)) == (400, ["too_many_login_attempts"])
    assert mail.outbox == []


def test_the_account_opens_again_after_five_minutes(verified, wait):
    for _ in range(5):
        _from_new_address(LOGIN, {"email": verified.email, "password": "a guess"})

    wait(5 * 60 + 1)
    client, response = _from_new_address(LOGIN, {"email": verified.email, "password": PASSWORD})

    assert (response.status_code, _pending(response)) == (401, ["login_by_code"])


def test_the_right_password_gives_its_attempt_back(verified):
    """Four failures, then the owner signs in as often as needed: the budget stays at four."""
    for _ in range(4):
        _from_new_address(LOGIN, {"email": verified.email, "password": "a guess"})

    for _ in range(3):
        _, response = _from_new_address(LOGIN, {"email": verified.email, "password": PASSWORD})
        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])


def test_one_address_is_stopped_after_five_failures_in_five_minutes_whatever_the_accounts():
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.0.1")
    answers = [
        _codes(_post_without_csrf(client, LOGIN, {"email": f"guess-{n}@example.com", "password": "a guess"}))
        for n in range(6)
    ]

    assert answers[:5] == [["email_password_mismatch"]] * 5
    assert answers[5] == ["too_many_login_attempts"]


def test_the_address_may_try_again_after_five_minutes(wait):
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.0.2")
    for n in range(5):
        _post_without_csrf(client, LOGIN, {"email": f"guess-{n}@example.com", "password": "a guess"})

    wait(5 * 60 + 1)
    response = _post_without_csrf(client, LOGIN, {"email": "guess-again@example.com", "password": "a guess"})

    assert _codes(response) == ["email_password_mismatch"]


def test_another_address_keeps_its_own_budget():
    stopped = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.0.3")
    for n in range(6):
        _post_without_csrf(stopped, LOGIN, {"email": f"guess-{n}@example.com", "password": "a guess"})

    other = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.0.4")
    response = _post_without_csrf(other, LOGIN, {"email": "guess-other@example.com", "password": "a guess"})

    assert _codes(response) == ["email_password_mismatch"]


def test_one_address_asks_for_ten_reset_links_an_hour_at_most():
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.1.1")
    answers = [
        _post_without_csrf(client, RESET, {"email": f"someone-{n}@example.com"}).status_code for n in range(11)
    ]

    assert answers == [200] * 10 + [429]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (f"{BROWSER}/auth/code/confirm", {"code": "000000"}),
        (f"{BROWSER}/auth/email/verify", {"key": "000000"}),
    ],
    ids=["sign-in-code", "address-code"],
)
def test_one_address_types_ten_codes_in_five_minutes_at_most(wait, path, body):
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.2.1")
    answers = [_post_without_csrf(client, path, body) for _ in range(11)]

    assert [answer.status_code == 429 for answer in answers] == [False] * 10 + [True]
    assert answers[10].json() == {
        "status": 429,
        "errors": [{"code": "too_many_requests", "message": "Too many attempts. Please try again in a few minutes."}],
    }
    wait(5 * 60 + 1)
    assert _post_without_csrf(client, path, body).status_code != 429


def test_the_authenticator_apps_refused_codes_count_too(settings, ana):
    """A sign-in waiting for the app's code: each wrong code is refused (400) and counted; the 11th is held."""
    from accounts.tests.test_mfa import _activate_totp, _first_factors
    from accounts.tests.conftest import prove_address

    settings.ACCOUNTS_MFA_ENABLED = True
    prove_address(ana.email)
    _activate_totp(ana)
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.2.2")
    client.get(f"{BROWSER}/auth/session")
    assert _first_factors(client, ana.email, PASSWORD).status_code == 401

    answers = [_post_without_csrf(client, f"{BROWSER}/auth/2fa/authenticate", {"code": "000000"}).status_code for _ in range(11)]

    assert answers == [400] * 10 + [429]


def test_a_sign_in_that_waits_for_no_app_code_counts_nothing(settings):
    """No sign-in waits for the app's code (allauth answers 401): no code was refused, nothing is spent."""
    settings.ACCOUNTS_MFA_ENABLED = True
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.2.3")

    answers = [_post_without_csrf(client, f"{BROWSER}/auth/2fa/authenticate", {"code": "000000"}).status_code for _ in range(12)]

    assert answers == [401] * 12


def test_a_right_code_spends_nothing_of_the_address_budget(verified):
    """Only refused codes count (a 400 or a 409): the owner signing in again and again from the office's address never
    uses up what a guesser at the same address would have."""
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.4.1")
    confirm = f"{BROWSER}/auth/code/confirm"
    for _ in range(9):
        assert _post_without_csrf(client, confirm, {"code": "000000"}).status_code in {400, 409}

    for _ in range(3):
        _post_without_csrf(client, LOGIN, {"email": verified.email, "password": PASSWORD})
        right = _post_without_csrf(client, confirm, {"code": _code(mail.outbox[-1])})
        assert right.status_code == 200, right.content
        client.delete(f"{BROWSER}/auth/session")

    assert _post_without_csrf(client, confirm, {"code": "000000"}).status_code != 429
    assert _post_without_csrf(client, confirm, {"code": "000000"}).status_code == 429


def test_the_code_limit_is_per_address():
    stopped = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.3.1")
    for _ in range(11):
        _post_without_csrf(stopped, f"{BROWSER}/auth/code/confirm", {"code": "000000"})

    other = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.3.2")

    assert _post_without_csrf(other, f"{BROWSER}/auth/code/confirm", {"code": "000000"}).status_code != 429


def test_reset_links_are_limited_per_account_the_same_with_or_without_one(verified):
    held = [_from_new_address(RESET, {"email": verified.email})[1].status_code for _ in range(6)]
    nobody = [_from_new_address(RESET, {"email": "nobody@example.com"})[1].status_code for _ in range(6)]

    assert held == nobody == [200, 200, 200, 200, 200, 429]


def test_the_limits_are_allauths_on_the_shared_cache():
    from allauth.account import app_settings

    limits = app_settings.RATE_LIMITS
    assert (limits["login_failed"], limits["reset_password"], limits["login"]) == ("5/5m/ip,5/5m/key", "10/h/ip,5/h/key", "30/m/ip")
    assert settings.CACHES["default"]["BACKEND"] in {
        "base.cache.FailSoftRedisCache",
        "django.core.cache.backends.locmem.LocMemCache",
    }
