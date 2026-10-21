"""ACCOUNTS-G96: whoever tries passwords, codes or reset links is stopped, the same for an account as for none.

allauth's own limits (``ACCOUNT_RATE_LIMITS``, over its defaults) on the shared cache (Valkey, Django's cache
only), as the old SaaS's (old-saas:SAAS_AUTH-F14): failed passwords spend the account's budget (5 in 5 minutes)
and the address's (10 a minute), the right one gives its attempt back, so failures alone never lock the owner
out within the budget; the sign-in itself, 30 a minute per address; a reset link, 5 a minute per account and 20
per address; the mailed codes, 3 tries (``test_sign_in_code``). The answers never tell which addresses hold an
account (``test_unified_login``: the throttle reaches a known and an unknown address at the same attempt).
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


def test_one_address_is_stopped_after_ten_failures_a_minute_whatever_the_accounts():
    client = Client(HTTP_HOST=HOST, REMOTE_ADDR="10.8.0.1")
    answers = [
        _codes(_post_without_csrf(client, LOGIN, {"email": f"guess-{n}@example.com", "password": "a guess"}))
        for n in range(11)
    ]

    assert answers[:10] == [["email_password_mismatch"]] * 10
    assert answers[10] == ["too_many_login_attempts"]


def test_reset_links_are_limited_per_account_the_same_with_or_without_one(verified):
    held = [_from_new_address(RESET, {"email": verified.email})[1].status_code for _ in range(6)]
    nobody = [_from_new_address(RESET, {"email": "nobody@example.com"})[1].status_code for _ in range(6)]

    assert held == nobody == [200, 200, 200, 200, 200, 429]


def test_the_limits_are_allauths_on_the_shared_cache():
    from allauth.account import app_settings

    limits = app_settings.RATE_LIMITS
    assert (limits["login_failed"], limits["reset_password"], limits["login"]) == ("10/m/ip,5/300s/key", "20/m/ip,5/m/key", "30/m/ip")
    assert settings.CACHES["default"]["BACKEND"] in {
        "base.cache.FailSoftRedisCache",
        "django.core.cache.backends.locmem.LocMemCache",
    }
