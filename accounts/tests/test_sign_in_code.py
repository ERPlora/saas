"""The second factor by email: every sign-in with a password asks for a code mailed to the account.

Ioan's rule (2026-10-15): the code is always mailed and typed in the app, at sign-up and at every sign-in.
It is allauth's own login-by-code stage (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``), scoped to the password
(``{"password"}``): ``POST …/auth/login`` with the right password answers 401 with the pending flow
``login_by_code`` and mails six digits (``ACCOUNT_LOGIN_BY_CODE_FORMAT``, as the email verification's);
``POST …/auth/code/confirm {code}`` signs in. allauth's defaults rule the rest: 3 wrong codes end the
login, a code lasts 3 minutes. There is no «send another code» for this stage: allauth only serves
``auth/code/resend`` with ``ACCOUNT_LOGIN_BY_CODE_ENABLED``, which would also open ``auth/code/request``,
a sign-in with the mailed code alone (no password), so it stays off; signing in again mails a new code.

One code, never two: a sign-up, or an account that never proved its address, gets the code that proves the
address (``verify_email``), which is the same proof of the mailbox (``AccountAdapter.is_login_by_code_required``).
Google already is a strong sign-in and proves the address itself: no code (``test_google``).
With the authenticator app (``ACCOUNTS_MFA_ENABLED``) both are asked, in allauth's order: the mailed
code, then the app's.
"""

import re
import time
from types import SimpleNamespace

import pytest
from allauth.account.internal.flows import code_verification
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal import auth as totp_auth
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
CONFIRM_CODE = f"{BROWSER}/auth/code/confirm"
RESEND_CODE = f"{BROWSER}/auth/code/resend"
REQUEST_CODE = f"{BROWSER}/auth/code/request"
VERIFY_EMAIL = f"{BROWSER}/auth/email/verify"
AUTHENTICATE = f"{BROWSER}/auth/2fa/authenticate"
NEWCOMER = "new@example.com"


@pytest.fixture
def browser():
    """A browser of the Vue pages: Django checks the CSRF token as in production."""
    client = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
    client.get(SESSION)
    return client


@pytest.fixture
def verified(ana):
    """``ana`` once she proved her mailbox."""
    EmailAddress.objects.create(user=ana, email=ana.email, verified=True, primary=True)
    return ana


@pytest.fixture
def unverified(ana):
    """``ana`` signed up but never typed the code."""
    EmailAddress.objects.create(user=ana, email=ana.email, verified=False, primary=True)
    return ana


@pytest.fixture
def later(monkeypatch):
    """``later(seconds)`` moves the clock of allauth's codes forward, as if that long went by."""
    offset = 0.0
    monkeypatch.setattr(
        code_verification, "time", SimpleNamespace(time=lambda: time.time() + offset)
    )

    def advance(seconds: float) -> None:
        nonlocal offset
        offset += seconds

    return advance


def _post(client, path, body=None):
    return client.post(
        path,
        body or {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )


def _continue(client, email, password=PASSWORD):
    return _post(client, LOGIN, {"email": email, "password": password})


def _pending(response) -> list[str]:
    return [
        flow["id"]
        for flow in response.json()["data"].get("flows", [])
        if flow.get("is_pending")
    ]


def _six_digits(message) -> str:
    return re.search(r"^\s*(\d{6})\s*$", message.body, re.MULTILINE).group(1)


def _wrong(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def _signed_in_email(client):
    response = client.get(SESSION)
    return (
        response.json()["data"]["user"]["email"]
        if response.status_code == 200
        else None
    )


def _methods(client) -> list[str]:
    return [
        method["method"] for method in client.get(SESSION).json()["data"]["methods"]
    ]


class TestTheSettings:
    def test_the_code_is_required_for_the_password_sign_in_only(self):
        assert settings.ACCOUNT_LOGIN_BY_CODE_REQUIRED == {"password"}

    def test_the_code_has_six_digits_as_the_email_verifications(self):
        assert settings.ACCOUNT_LOGIN_BY_CODE_FORMAT == {
            "length": 6,
            "numeric": True,
            "dashed": False,
        }
        assert (
            settings.ACCOUNT_LOGIN_BY_CODE_FORMAT
            == settings.ACCOUNT_EMAIL_VERIFICATION_BY_CODE_FORMAT
        )

    def test_signing_in_with_the_code_alone_is_off(self):
        assert getattr(settings, "ACCOUNT_LOGIN_BY_CODE_ENABLED", False) is False


class TestAPasswordSignIn:
    def test_the_right_password_waits_for_the_code_and_signs_nobody_in(
        self, browser, verified
    ):
        response = _continue(browser, verified.email)

        assert response.status_code == 401
        assert _pending(response) == ["login_by_code"]
        assert response.json()["meta"]["is_authenticated"] is False
        assert _signed_in_email(browser) is None

    def test_one_mail_carries_six_digits_to_the_accounts_address(
        self, browser, verified
    ):
        _continue(browser, verified.email)

        [message] = mail.outbox
        assert message.to == [verified.email]
        assert re.fullmatch(r"\d{6}", _six_digits(message))

    def test_the_code_signs_in_after_the_password(self, browser, verified):
        _continue(browser, verified.email)

        response = _post(browser, CONFIRM_CODE, {"code": _six_digits(mail.outbox[0])})

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True
        assert _signed_in_email(browser) == verified.email
        assert _methods(browser) == ["password", "code"]

    def test_the_session_is_remembered(self, browser, verified):
        _continue(browser, verified.email)

        response = _post(browser, CONFIRM_CODE, {"code": _six_digits(mail.outbox[0])})

        assert browser.session.get_expire_at_browser_close() is False
        assert response.cookies["sessionid"]["max-age"] == settings.SESSION_COOKIE_AGE

    def test_a_wrong_password_mails_nothing(self, browser, verified):
        response = _continue(browser, verified.email, password="wrong")

        assert response.status_code == 400
        assert mail.outbox == []

    def test_a_wrong_code_is_400_on_the_code_and_the_login_still_waits(
        self, browser, verified
    ):
        _continue(browser, verified.email)

        response = _post(
            browser, CONFIRM_CODE, {"code": _wrong(_six_digits(mail.outbox[0]))}
        )

        assert response.status_code == 400
        [error] = response.json()["errors"]
        assert (error["param"], error["code"]) == ("code", "incorrect_code")
        session = browser.get(SESSION)
        assert (session.status_code, _pending(session)) == (401, ["login_by_code"])

    def test_the_third_wrong_code_ends_the_login(self, browser, verified):
        """allauth's ``ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS`` (3): the right code no longer counts."""
        _continue(browser, verified.email)
        code = _six_digits(mail.outbox[0])
        for _ in range(3):
            assert (
                _post(browser, CONFIRM_CODE, {"code": _wrong(code)}).status_code == 400
            )

        response = _post(browser, CONFIRM_CODE, {"code": code})

        assert response.status_code == 409
        assert _signed_in_email(browser) is None
        assert _pending(browser.get(SESSION)) == []

    def test_a_code_lasts_three_minutes(self, browser, verified, later):
        """allauth's ``ACCOUNT_LOGIN_BY_CODE_TIMEOUT`` (180 s)."""
        _continue(browser, verified.email)
        later(181)

        response = _post(browser, CONFIRM_CODE, {"code": _six_digits(mail.outbox[0])})

        assert response.status_code == 409
        assert _signed_in_email(browser) is None

    def test_there_is_no_resend_signing_in_again_mails_a_new_code(
        self, browser, verified
    ):
        _continue(browser, verified.email)
        assert _post(browser, RESEND_CODE).status_code == 404

        response = _continue(browser, verified.email)

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
        assert len(mail.outbox) == 2
        assert (
            _post(
                browser, CONFIRM_CODE, {"code": _six_digits(mail.outbox[1])}
            ).status_code
            == 200
        )

    def test_the_code_alone_never_signs_in(self, browser, verified):
        """No passwordless sign-in: requesting a code without the password is not served."""
        response = _post(browser, REQUEST_CODE, {"email": verified.email})

        assert response.status_code == 404
        assert mail.outbox == []

    def test_the_code_is_refused_when_no_login_waits(self, browser, verified):
        response = _post(browser, CONFIRM_CODE, {"code": "123456"})

        assert response.status_code == 409


class TestOneCodeNeverTwo:
    def test_a_sign_up_gets_only_the_code_that_proves_its_address(self, browser):
        response = _post(browser, SIGNUP, {"email": NEWCOMER, "password": PASSWORD})

        assert (response.status_code, _pending(response)) == (401, ["verify_email"])
        [message] = mail.outbox
        response = _post(browser, VERIFY_EMAIL, {"key": _six_digits(message)})

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True
        assert len(mail.outbox) == 1
        assert _signed_in_email(browser) == NEWCOMER

    def test_an_address_never_proven_gets_only_the_code_that_proves_it(
        self, browser, unverified
    ):
        response = _continue(browser, unverified.email)

        assert (response.status_code, _pending(response)) == (401, ["verify_email"])
        [message] = mail.outbox
        assert (
            _post(browser, VERIFY_EMAIL, {"key": _six_digits(message)}).status_code
            == 200
        )
        assert len(mail.outbox) == 1
        assert _signed_in_email(browser) == unverified.email
        assert EmailAddress.objects.get(email=unverified.email).verified is True

    def test_once_proven_the_next_sign_in_asks_for_the_sign_in_code(
        self, browser, unverified
    ):
        _continue(browser, unverified.email)
        _post(browser, VERIFY_EMAIL, {"key": _six_digits(mail.outbox[0])})
        browser.delete(SESSION, HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value)

        response = _continue(browser, unverified.email)

        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])


class TestWithTheAuthenticatorApp:
    """With ``ACCOUNTS_MFA_ENABLED`` both factors on top of the password, in allauth's order."""

    def test_the_mailed_code_comes_first_then_the_apps(
        self, browser, verified, settings
    ):
        settings.ACCOUNTS_MFA_ENABLED = True
        secret = totp_auth.generate_totp_secret()
        totp_auth.TOTP.activate(verified, secret)

        response = _continue(browser, verified.email)
        assert (response.status_code, _pending(response)) == (401, ["login_by_code"])

        response = _post(browser, CONFIRM_CODE, {"code": _six_digits(mail.outbox[0])})
        assert (response.status_code, _pending(response)) == (401, ["mfa_authenticate"])
        assert _signed_in_email(browser) is None

        live = totp_auth.format_hotp_value(
            totp_auth.hotp_value(secret, int(time.time()) // 30)
        )
        response = _post(browser, AUTHENTICATE, {"code": live})

        assert response.status_code == 200
        assert _methods(browser) == ["password", "code", "mfa"]


class TestTheJumpToAHub:
    def test_while_the_code_is_pending_the_jump_waits_for_the_sign_in(
        self, browser, verified
    ):
        _continue(browser, verified.email)

        response = browser.get("/hub-login/?hub=a&next=/sales/")

        assert response.status_code == 302
        assert response.url.startswith("/launch?next=")


def test_the_mail_names_the_sign_in_code():
    """allauth's own mail (``account/email/login_code``), branded ERPlora as every mail of allauth."""
    user = get_user_model().objects.create_user(
        email="ana@example.com", password=PASSWORD
    )
    EmailAddress.objects.create(
        user=user, email=user.email, verified=True, primary=True
    )
    client = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
    client.get(SESSION)

    _continue(client, user.email)

    [message] = mail.outbox
    assert message.subject == "Sign-In Code"
    assert "Your sign-in code is listed below." in message.body
    assert "example.com" not in message.body.replace(user.email, "")
