"""The launcher's sign-in (``/launch``): two tabs over one form, «Sign in» (the default) and «Create account»
(FIX-LAUNCH-TABS, PLAN-SAAS §3.7, 2026-10-15), each on its own allauth.headless call.

- «Sign in» posts ``{email, password}`` to ``POST /_allauth/browser/v1/auth/login``, allauth's login: it never
  creates an account. An email no account holds answers exactly as a wrong password does (gh:saas#1018: no
  account oracle, neither in the answer nor in the throttle), and a known one then waits for the code mailed to
  the account (``login_by_code``, the second factor by email of ``test_sign_in_code``), or for the code that
  proves an address never proven (``verify_email``, gh:saas#2541).
- «Create account» posts it to ``POST …/auth/signup``, allauth's signup: it never signs in. A new address gets
  its account and a 6-digit code that proves the address (``POST …/auth/email/verify``, ADR-0159; gh:saas#2536:
  nobody holds an address they never proved); one an account already holds gets the same answer and a mail to
  its holder instead (allauth's enumeration prevention), and no session.

The answers are allauth's own: 200 with the session, 401 with the pending flow, 400 with
``errors[{param, code, message}]``, 429 when the sign-ups of an address run out (10 an hour,
``UNIFIED_SIGNUP_RATELIMIT`` of today's SaaS). The old sign-up addresses open the «Create account» tab.

Ported from ERPlora/saas ``apps/auth/users/tests/test_unified_auth.py`` (``TestUnifiedRegisterOrLogin``,
``TestImplicitSignupRateLimit``, ``TestWeakPasswordRejected``), ``test_signup_api.py`` and
``test_login_throttle_oracle.py``, on the headless API instead of the template page, with the implicit
sign-up of ADR-0154 split into its own tab.
"""

import re
import time
from itertools import count
from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from allauth.core.internal import ratelimit
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

from conftest import PASSWORD

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
BROWSER = "/_allauth/browser/v1"
LOGIN = f"{BROWSER}/auth/login"
SIGNUP = f"{BROWSER}/auth/signup"
SESSION = f"{BROWSER}/auth/session"
VERIFY_EMAIL = f"{BROWSER}/auth/email/verify"
RESEND_CODE = f"{BROWSER}/auth/email/verify/resend"
CONFIRM_CODE = f"{BROWSER}/auth/code/confirm"
NEWCOMER = "new@example.com"
#: The sign-ups one address may start in an hour (ERPlora/saas ``UNIFIED_SIGNUP_RATELIMIT``).
SIGNUPS_AN_HOUR = 10

User = get_user_model()


def _browser():
    """A browser: Django checks the CSRF token as in production (the SPA's HTML sets the cookie)."""
    client = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
    client.get(SESSION)
    return client


@pytest.fixture
def browser():
    return _browser()


@pytest.fixture
def verified(ana):
    """``ana`` once she proved her mailbox: her address is on record, verified."""
    EmailAddress.objects.create(user=ana, email=ana.email, verified=True, primary=True)
    return ana


@pytest.fixture
def unverified(ana):
    """``ana`` signed up but never typed the code: her address is on record, unverified."""
    EmailAddress.objects.create(user=ana, email=ana.email, verified=False, primary=True)
    return ana


@pytest.fixture
def invited(db):
    """An account an invitation made: no password until the mailbox's owner claims it."""
    return User.objects.create_user(email="invited@example.com", password=None)


@pytest.fixture
def wait(monkeypatch):
    """``wait(seconds)`` moves the clock of allauth's rate limits forward, as if that long went by."""
    offset = 0.0
    clock = SimpleNamespace(
        time=lambda: time.time() + offset, monotonic=time.monotonic, sleep=time.sleep
    )
    monkeypatch.setattr(ratelimit, "time", clock)

    def advance(seconds: float) -> None:
        nonlocal offset
        offset += seconds

    return advance


def _post(client, path, body=None, **extra):
    return client.post(
        path,
        body or {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        **extra,
    )


def _sign_in(client, email, password=PASSWORD, **extra):
    """«Sign in» on the launcher's «Sign in» tab."""
    return _post(client, LOGIN, {"email": email, "password": password}, **extra)


def _create_account(client, email, password=PASSWORD, **extra):
    """«Create account» on the launcher's «Create account» tab."""
    return _post(client, SIGNUP, {"email": email, "password": password}, **extra)


def _post_without_csrf(client, path, body):
    """A script's request: no browser, no CSRF check (Django's test client skips it)."""
    return client.post(path, body, content_type="application/json")


def _pending(response) -> list[str]:
    return [
        flow["id"]
        for flow in response.json()["data"]["flows"]
        if flow.get("is_pending")
    ]


def _code(message) -> str:
    return re.search(r"^\s*(\d{6})\s*$", message.body, re.MULTILINE).group(1)


def _confirm(client):
    """The second step of a password sign-in: the code of the newest mail (``test_sign_in_code``)."""
    return _post(client, CONFIRM_CODE, {"code": _code(mail.outbox[-1])})


def _signed_in_email(client):
    response = client.get(SESSION)
    return (
        response.json()["data"]["user"]["email"]
        if response.status_code == 200
        else None
    )


class TestSignInNeverCreatesAnAccount:
    def test_an_unknown_email_is_a_mismatch_and_creates_nothing(self, browser):
        response = _sign_in(browser, NEWCOMER)

        assert response.status_code == 400
        [error] = response.json()["errors"]
        assert (error["param"], error["code"]) == ("password", "email_password_mismatch")
        assert not User.objects.exists()
        assert not EmailAddress.objects.exists()
        assert mail.outbox == []
        assert _signed_in_email(browser) is None

    def test_an_unknown_email_answers_exactly_as_a_wrong_password(self, browser, verified):
        """gh:saas#1018: the answer says nothing about whether the address has an account."""
        unknown = _sign_in(browser, NEWCOMER)
        wrong = _sign_in(browser, verified.email, password="not her password")

        assert (unknown.status_code, unknown.json()) == (wrong.status_code, wrong.json())

    def test_the_throttle_stops_an_unknown_email_at_the_same_attempt_as_a_known_one(self, verified):
        """gh:saas#1018: a 429 (or allauth's «too many attempts») that only a known address ever reached told
        whether the account exists. From a new address each time, as an attacker rotating IPs."""
        ips = count(1)

        def attempts(email):
            answers = []
            for _ in range(8):
                client = Client(HTTP_HOST=HOST, REMOTE_ADDR=f"10.0.0.{next(ips)}")
                response = _post_without_csrf(client, LOGIN, {"email": email, "password": "123"})
                answers.append((response.status_code, [error["code"] for error in response.json().get("errors", [])]))
            return answers

        known = attempts(verified.email)
        unknown = attempts(NEWCOMER)

        assert ("too_many_login_attempts" in str(known)) is True
        assert unknown == known
        assert not User.objects.filter(email=NEWCOMER).exists()

    def test_an_invalid_email_is_400_on_the_email(self, browser):
        response = _sign_in(browser, "not-an-email")

        assert response.status_code == 400
        assert [error["param"] for error in response.json()["errors"]] == ["email"]
        assert not User.objects.exists()

    def test_an_email_with_a_nul_character_is_400_on_the_email(self, browser):
        """Postgres refuses a NUL in text: looked up as typed, it was a 500 before any check or rate limit."""
        response = _sign_in(browser, "a\x00b@example.com")

        assert response.status_code == 400
        assert {error["param"] for error in response.json()["errors"]} == {"email"}
        assert not User.objects.exists()
        assert mail.outbox == []

    def test_a_missing_password_is_400_on_the_password(self, browser):
        response = _post(browser, LOGIN, {"email": NEWCOMER})

        assert response.status_code == 400
        assert [error["param"] for error in response.json()["errors"]] == ["password"]
        assert not User.objects.exists()

    def test_without_the_csrf_token_it_is_refused(self, browser):
        response = browser.post(
            LOGIN, {"email": NEWCOMER, "password": PASSWORD}, content_type="application/json"
        )

        assert response.status_code == 403
        assert not User.objects.exists()


class TestAKnownEmailSignsIn:
    def test_a_proven_address_and_the_right_password_wait_for_the_mailed_code(
        self, browser, verified
    ):
        """The second factor by email (``test_sign_in_code``): no account is created, the code signs in."""
        response = _sign_in(browser, verified.email)

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
        [message] = mail.outbox
        assert message.to == [verified.email]
        response = _confirm(browser)
        assert response.status_code == 200
        assert response.json()["data"]["user"]["email"] == verified.email

    def test_a_wrong_password_never_creates_an_account(self, browser, verified):
        response = _sign_in(browser, verified.email, password="wrong")

        assert response.status_code == 400
        [error] = response.json()["errors"]
        assert (error["param"], error["code"]) == (
            "password",
            "email_password_mismatch",
        )
        assert User.objects.count() == 1
        assert _signed_in_email(browser) is None

    def test_an_email_in_another_case_than_an_accounts_signs_in_to_it(
        self, browser, verified
    ):
        response = _sign_in(browser, "Ana@Example.COM")

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
        assert User.objects.count() == 1
        assert _confirm(browser).status_code == 200
        assert _signed_in_email(browser) == verified.email

    def test_a_fullwidth_look_alike_of_an_accounts_email_signs_in_to_it(self, browser, verified):
        """ACCOUNTS-G83 (ERPlora/saas#1018): the compatibility forms of the letters (NFKC) are the account's
        own address, as in today's SaaS, not an unknown one."""
        response = _sign_in(browser, "ana@\uff45xample.com")

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
        assert _confirm(browser).status_code == 200
        assert _signed_in_email(browser) == verified.email

    def test_an_address_never_proven_asks_for_the_code_first(self, browser, unverified):
        """gh:saas#2541. Not a dead end: the right password mails a code and the same screen asks for it."""
        response = _sign_in(browser, unverified.email)

        assert response.status_code == 401
        assert _pending(response) == ["verify_email"]
        [message] = mail.outbox
        assert message.to == [unverified.email]
        assert _post(browser, VERIFY_EMAIL, {"key": _code(message)}).status_code == 200
        assert _signed_in_email(browser) == unverified.email

    def test_an_invited_account_without_a_password_is_a_mismatch_like_any_wrong_password(
        self, browser, invited
    ):
        """Whoever types an invited address learns nothing more than «mismatch», and no second account
        is made for it: the mailbox's owner claims it with «Forgot your password?» or Google."""
        response = _sign_in(browser, invited.email)

        assert response.status_code == 400
        [error] = response.json()["errors"]
        assert (error["param"], error["code"]) == (
            "password",
            "email_password_mismatch",
        )
        assert User.objects.filter(email__iexact=invited.email).count() == 1
        assert not EmailAddress.objects.exists()
        assert mail.outbox == []

    def test_an_account_known_only_by_an_address_on_record_signs_in(
        self, browser, verified
    ):
        EmailAddress.objects.create(
            user=verified, email="ana.old@example.com", verified=True, primary=False
        )

        response = _sign_in(browser, "ana.old@example.com")

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
        assert mail.outbox[0].to == ["ana.old@example.com"]
        assert _confirm(browser).status_code == 200
        assert User.objects.count() == 1
        assert _signed_in_email(browser) == verified.email


class TestCreateAccountCreatesTheAccount:
    def test_it_answers_401_with_the_email_verification_pending(self, browser):
        response = _create_account(browser, NEWCOMER)

        assert response.status_code == 401
        assert _pending(response) == ["verify_email"]
        assert response.json()["meta"]["is_authenticated"] is False

    def test_the_account_is_created_with_the_password_and_its_address_unproven(
        self, browser
    ):
        """gh:saas#2536: the address is not the account's until its code comes back."""
        _create_account(browser, NEWCOMER)

        user = User.objects.get(email=NEWCOMER)
        assert user.check_password(PASSWORD)
        assert list(
            EmailAddress.objects.filter(user=user).values_list(
                "email", "verified", "primary"
            )
        ) == [(NEWCOMER, False, True)]
        assert _signed_in_email(browser) is None

    def test_one_mail_carries_a_six_digit_code(self, browser):
        _create_account(browser, NEWCOMER)

        [message] = mail.outbox
        assert message.to == [NEWCOMER]
        assert re.fullmatch(r"\d{6}", _code(message))

    def test_the_code_signs_in_and_proves_the_address(self, browser):
        _create_account(browser, NEWCOMER)

        response = _post(browser, VERIFY_EMAIL, {"key": _code(mail.outbox[0])})

        assert response.status_code == 200
        assert response.json()["data"]["user"]["email"] == NEWCOMER
        assert response.json()["meta"]["is_authenticated"] is True
        assert EmailAddress.objects.get(email=NEWCOMER).verified is True
        assert _signed_in_email(browser) == NEWCOMER

    def test_a_wrong_code_is_400_and_signs_nobody_in(self, browser):
        _create_account(browser, NEWCOMER)
        code = _code(mail.outbox[0])
        wrong = "000000" if code != "000000" else "111111"

        response = _post(browser, VERIFY_EMAIL, {"key": wrong})

        assert response.status_code == 400
        assert [error["param"] for error in response.json()["errors"]] == ["key"]
        assert EmailAddress.objects.get(email=NEWCOMER).verified is False
        assert _signed_in_email(browser) is None

    def test_another_code_can_be_asked_for_once_the_cooldown_is_over(
        self, browser, wait
    ):
        """Without a resend a lost mail strands the person on the code screen (as today's SaaS,
        ``ACCOUNT_EMAIL_VERIFICATION_SUPPORTS_RESEND``); allauth keeps 10 s between two codes."""
        _create_account(browser, NEWCOMER)
        assert _post(browser, RESEND_CODE).status_code == 429
        wait(11)

        response = _post(browser, RESEND_CODE)

        assert response.status_code == 200
        assert len(mail.outbox) == 2
        assert _post(browser, VERIFY_EMAIL, {"key": _code(mail.outbox[1])}).status_code == 200


class TestCreateAccountNeverSignsIn:
    """An address an account already holds: the same answer as a new one (gh:saas#1018), no second account,
    no session, and a mail to the holder (allauth's «an account using that email address already exists»)."""

    def test_a_held_address_answers_as_a_new_one(self, verified):
        new = _create_account(_browser(), NEWCOMER)
        held = _create_account(_browser(), verified.email)

        assert (held.status_code, _pending(held)) == (new.status_code, _pending(new)) == (401, ["verify_email"])
        assert held.json()["meta"] == new.json()["meta"]

    def test_it_creates_no_account_signs_nobody_in_and_keeps_the_password(self, browser, verified):
        response = _create_account(browser, verified.email, password="another long password 2026")

        assert response.status_code == 401
        assert User.objects.count() == 1
        verified.refresh_from_db()
        assert verified.check_password(PASSWORD)
        assert _signed_in_email(browser) is None

    def test_the_holder_is_told_by_mail_with_no_code_to_sign_in(self, browser, verified):
        _create_account(browser, verified.email)

        [message] = mail.outbox
        assert message.to == [verified.email]
        assert "an account using that email address already exists" in message.body
        assert f"http://{HOST}/password/reset" in message.body
        assert not re.search(r"^\s*\d{6}\s*$", message.body, re.MULTILINE)

    def test_an_email_in_another_case_creates_no_second_account(self, browser, verified):
        response = _create_account(browser, "Ana@Example.COM")

        assert response.status_code == 401
        assert User.objects.count() == 1
        assert _signed_in_email(browser) is None

    def test_a_fullwidth_look_alike_creates_no_second_account(self, browser, verified):
        """ACCOUNTS-G83 (ERPlora/saas#1018): «ana@ｅxample.com» reads as Ana's address, so it never becomes a
        second account that looks the same; her mailbox is told, as for her own address."""
        response = _create_account(browser, "ana@\uff45xample.com")

        assert response.status_code == 401
        assert list(User.objects.values_list("email", flat=True)) == [verified.email]
        [message] = mail.outbox
        assert message.to == [verified.email]
        assert _signed_in_email(browser) is None

    def test_a_new_address_is_kept_in_its_plain_form(self, browser):
        _create_account(browser, " New@\uff25xample.com ")

        assert list(User.objects.values_list("email", flat=True)) == [NEWCOMER]
        assert list(EmailAddress.objects.values_list("email", flat=True)) == [NEWCOMER]

    def test_an_address_never_proven_is_not_taken_over(self, browser, unverified):
        """gh:saas#2541 from the other side: typing a held, unproven address again gives nobody its account."""
        response = _create_account(browser, unverified.email, password="another long password 2026")

        assert response.status_code == 401
        assert User.objects.count() == 1
        unverified.refresh_from_db()
        assert unverified.check_password(PASSWORD)
        assert _signed_in_email(browser) is None

    def test_an_invited_account_gets_no_password_and_no_second_account(self, browser, invited):
        response = _create_account(browser, invited.email)

        assert response.status_code == 401
        assert User.objects.filter(email__iexact=invited.email).count() == 1
        invited.refresh_from_db()
        assert not invited.has_usable_password()
        assert _signed_in_email(browser) is None

    def test_an_invited_person_is_mailed_the_way_to_set_a_password(self, browser, invited):
        """ERPlora/saas#2560: the invited person who types their address on «Create account» gets, in their own
        mailbox, the link that sets the password their account does not have yet."""
        _create_account(browser, invited.email)

        [message] = mail.outbox
        assert message.to == [invited.email]
        assert f"http://{HOST}/password/reset" in message.body


class TestAnInvalidSignUpCreatesNothing:
    def test_a_password_the_validators_refuse_is_400_on_the_password(self, browser):
        response = _create_account(browser, NEWCOMER, password="123")

        assert response.status_code == 400
        errors = response.json()["errors"]
        assert {error["param"] for error in errors} == {"password"}
        assert "password_too_short" in {error["code"] for error in errors}
        assert not User.objects.filter(email=NEWCOMER).exists()
        assert mail.outbox == []

    def test_an_invalid_email_is_400_on_the_email(self, browser):
        response = _create_account(browser, "not-an-email")

        assert response.status_code == 400
        assert [error["param"] for error in response.json()["errors"]] == ["email"]
        assert not User.objects.exists()

    def test_fullwidth_letters_before_the_at_are_400_on_the_email(self, browser, verified):
        """ACCOUNTS-G83: Django's address rules take only plain letters before the @, so «ａna@example.com» is an
        invalid address, never a second Ana."""
        response = _create_account(browser, "ａna@example.com")

        assert response.status_code == 400
        assert [error["param"] for error in response.json()["errors"]] == ["email"]
        assert list(User.objects.values_list("email", flat=True)) == [verified.email]

    def test_an_email_with_a_nul_character_is_400_on_the_email(self, browser):
        response = _create_account(browser, "a\x00b@example.com")

        assert response.status_code == 400
        assert {error["param"] for error in response.json()["errors"]} == {"email"}
        assert not User.objects.exists()
        assert mail.outbox == []

    def test_a_missing_password_is_400_on_the_password(self, browser):
        response = _post(browser, SIGNUP, {"email": NEWCOMER})

        assert response.status_code == 400
        assert [error["param"] for error in response.json()["errors"]] == ["password"]
        assert not User.objects.exists()

    def test_without_the_csrf_token_it_is_refused(self, browser):
        response = browser.post(
            SIGNUP, {"email": NEWCOMER, "password": PASSWORD}, content_type="application/json"
        )

        assert response.status_code == 403
        assert not User.objects.exists()


class TestTheSignUpsOfAnAddressAreLimited:
    """Creating an account mails a code: one address creating accounts is a spam vector."""

    def _sign_up(self, browser, n):
        return _create_account(browser, f"new{n}@example.com")

    def test_the_eleventh_sign_up_in_an_hour_is_429_and_creates_nothing(self, browser):
        for n in range(SIGNUPS_AN_HOUR):
            assert self._sign_up(browser, n).status_code == 401

        response = self._sign_up(browser, SIGNUPS_AN_HOUR)

        assert response.status_code == 429
        assert User.objects.count() == SIGNUPS_AN_HOUR
        assert not User.objects.filter(
            email=f"new{SIGNUPS_AN_HOUR}@example.com"
        ).exists()

    def test_the_limit_never_locks_an_account_out_of_its_sign_in(
        self, browser, verified
    ):
        for n in range(SIGNUPS_AN_HOUR + 1):
            self._sign_up(browser, n)

        response = _sign_in(browser, verified.email)

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])

    def test_the_limit_is_allauths_signup_one(self):
        assert settings.ACCOUNT_RATE_LIMITS["signup"] == f"{SIGNUPS_AN_HOUR}/h/ip"


class TestTheWaysToTheSignUpOpenTheCreateAccountTab:
    """gh:saas#943 and gh:saas#894: the sign-up has an address, and the old ones reach it in one hop."""

    def test_the_old_signup_page_leads_to_the_create_account_tab_for_good_keeping_next(self, client):
        response = client.get("/accounts/signup/?next=/launch", HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (301, "/launch?tab=signup&next=/launch")

    def test_without_a_query_it_is_the_tab_alone(self, client):
        response = client.get("/accounts/signup/", HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (301, "/launch?tab=signup")

    def test_a_tab_in_the_old_query_never_wins_over_the_create_account_one(self, client):
        response = client.get("/accounts/signup/?tab=signin&next=/account", HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (301, "/launch?tab=signup&next=/account")

    def test_posting_the_old_signup_page_creates_no_account(self, client):
        response = client.post(
            "/accounts/signup/",
            {"email": NEWCOMER, "password1": PASSWORD},
            HTTP_HOST=HOST,
        )

        assert response.status_code == 301
        assert not User.objects.exists()
        assert mail.outbox == []

    def test_allauths_mail_to_an_unknown_address_links_to_the_create_account_tab(self, browser):
        """«Forgot your password?» with an address no account holds mails how to sign up instead."""
        _post(browser, f"{BROWSER}/auth/password/request", {"email": NEWCOMER})

        [message] = mail.outbox
        assert f"http://{HOST}/launch?tab=signup" in message.body


class TestTheSessionIsRemembered:
    """Every sign-in lasts ``SESSION_COOKIE_AGE``, not until the browser closes: the sign-in asks nothing
    about it (allauth.headless takes no ``remember``)."""

    def _assert_remembered(self, client, response):
        assert client.session.get_expire_at_browser_close() is False
        assert response.cookies["sessionid"]["max-age"] == settings.SESSION_COOKIE_AGE

    def test_a_password_sign_in(self, browser, verified):
        _sign_in(browser, verified.email)

        response = _confirm(browser)

        self._assert_remembered(browser, response)

    def test_the_sign_in_of_a_new_account_by_its_code(self, browser):
        _create_account(browser, NEWCOMER)

        response = _post(browser, VERIFY_EMAIL, {"key": _code(mail.outbox[0])})

        self._assert_remembered(browser, response)


class TestTheCodeMail:
    """allauth names the host the address was given on from the ``Site`` row (``example.com``): the first mail
    ERPlora sends would read like phishing. It names ``PUBLIC_HOST``, as ERPlora/saas ``brand_context``."""

    def test_it_names_erplora_com_not_the_site_row(self, browser):
        _create_account(browser, NEWCOMER)

        [message] = mail.outbox
        assert "register an account on erplora.com." in message.body
        assert "account on example.com" not in message.body

    def test_the_host_comes_from_the_setting(self, browser, settings):
        settings.PUBLIC_HOST = "pre.erplora.com"

        _create_account(browser, NEWCOMER)

        assert "register an account on pre.erplora.com." in mail.outbox[0].body
