"""Every public door of allauth.headless asks reCAPTCHA first (accounts/bot_check.py; Ioan, 2026-10-22).

The launcher's sign-in and sign-up, «Forgot your password?» and its link, the mailed codes (the one that proves the
address, its «Send another code», and the sign-in's) and the authenticator app's code: a POST to any of them carries
``recaptcha_token``, made by Google's ``enterprise.js`` for that door's action, and the server asks Google before
allauth sees the request (``live.recaptcha.verify_or_raise``). Refused: allauth's own envelope, 400
``recaptcha_failed`` with a message for the whole form, so the SPA's client paints it. Google is played by
``FakeGoogleRecaptcha`` (conftest.py).
"""

import pytest
from django.core import mail
from django.test import Client
from django.utils import translation

from accounts.bot_check import RECAPTCHA_DOORS
from accounts.tests.conftest import BROWSER, HOST
from accounts.tests.test_unified_login import _pending, verified  # noqa: F401  (`verified` is a fixture)
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

#: Each door, the action its token is made for, and a body allauth would read.
DOORS = [
    (f"{BROWSER}/auth/login", "login", {"email": "ana@example.com", "password": PASSWORD}),
    (f"{BROWSER}/auth/signup", "signup", {"email": "new@example.com", "password": "a long new password 42"}),
    (f"{BROWSER}/auth/password/request", "password_reset", {"email": "ana@example.com"}),
    (f"{BROWSER}/auth/password/reset", "password_reset_confirm", {"key": "not-a-key", "password": "a long new one 42"}),
    (f"{BROWSER}/auth/email/verify", "verify_email", {"key": "123456"}),
    (f"{BROWSER}/auth/email/verify/resend", "verify_email_resend", {}),
    (f"{BROWSER}/auth/code/confirm", "login_code", {"code": "123456"}),
    (f"{BROWSER}/auth/2fa/authenticate", "mfa_authenticate", {"code": "123456"}),
]
DOOR_IDS = [action for _, action, _ in DOORS]


@pytest.fixture(autouse=True)
def _second_factor_served(settings):
    """The authenticator app's door answers 404 while ACCOUNTS_MFA_ENABLED is off: switched on to be asked."""
    settings.ACCOUNTS_MFA_ENABLED = True


def _post(path, body, *, token=None, client=None):
    client = client or Client(HTTP_HOST=HOST)
    payload = dict(body)
    if token is not None:
        payload["recaptcha_token"] = token
    return client.post(path, payload, content_type="application/json")


def _refused(response) -> bool:
    return response.status_code == 400 and [error["code"] for error in response.json().get("errors", [])] == [
        "recaptcha_failed"
    ]


def test_the_doors_are_these_with_one_action_each():
    assert RECAPTCHA_DOORS == {path: action for path, action, _ in DOORS}


@pytest.mark.parametrize(("path", "action", "body"), DOORS, ids=DOOR_IDS)
def test_a_post_without_a_token_is_refused_in_allauths_envelope_without_asking_google(recaptcha, path, action, body):
    response = _post(path, body)

    assert response.json() == {
        "status": 400,
        "errors": [{"code": "recaptcha_failed", "message": "We could not check that you are a person. Try again."}],
    }
    assert recaptcha.asked == []


@pytest.mark.parametrize(("path", "action", "body"), DOORS, ids=DOOR_IDS)
def test_a_bots_token_is_refused(recaptcha, path, action, body):
    response = _post(path, body, token=f"bot:{action}")

    assert _refused(response)
    assert recaptcha.asked == [(f"bot:{action}", action)]


@pytest.mark.parametrize(("path", "action", "body"), DOORS, ids=DOOR_IDS)
def test_a_persons_token_reaches_allauth(recaptcha, path, action, body):
    response = _post(path, body, token=f"human:{action}")

    assert not _refused(response)
    assert recaptcha.asked == [(f"human:{action}", action)]


@pytest.mark.parametrize(("path", "action", "body"), DOORS, ids=DOOR_IDS)
def test_a_token_made_for_another_door_is_refused(recaptcha, path, action, body):
    other = "signup" if action == "login" else "login"

    assert _refused(_post(path, body, token=f"human:{other}"))


@pytest.mark.parametrize(("path", "action", "body"), DOORS, ids=DOOR_IDS)
def test_a_malformed_token_is_refused(recaptcha, path, action, body):
    assert _refused(_post(path, body, token="forged"))


def test_google_down_refuses_the_form(recaptcha, verified):
    recaptcha.down = True

    response = _post(f"{BROWSER}/auth/login", {"email": verified.email, "password": PASSWORD}, token="human:login")

    assert _refused(response)
    assert mail.outbox == []


def test_a_person_signs_in_as_before(recaptcha, verified):
    response = _post(f"{BROWSER}/auth/login", {"email": verified.email, "password": PASSWORD}, token="human:login")

    assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
    assert len(mail.outbox) == 1


def test_a_refused_sign_in_mails_nothing_and_spends_no_attempt(recaptcha, verified):
    for _ in range(6):
        _post(f"{BROWSER}/auth/login", {"email": verified.email, "password": "a guess"}, token="bot:login")

    response = _post(f"{BROWSER}/auth/login", {"email": verified.email, "password": PASSWORD}, token="human:login")

    assert (response.status_code, _pending(response)) == (401, ["login_by_code"])


def test_the_refusal_speaks_spanish(recaptcha):
    with translation.override("es"):
        response = Client(HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").post(
            f"{BROWSER}/auth/login", {"email": "a@example.com", "password": "x"}, content_type="application/json"
        )

    assert response.json()["errors"][0]["message"] == "No hemos podido comprobar que eres una persona. Vuelve a intentarlo."


def test_a_body_that_is_not_json_is_refused_without_asking_google(recaptcha):
    response = Client(HTTP_HOST=HOST).post(f"{BROWSER}/auth/login", "not json", content_type="application/json")

    assert _refused(response)
    assert recaptcha.asked == []


def test_reading_a_door_needs_no_token(recaptcha):
    response = Client(HTTP_HOST=HOST).get(f"{BROWSER}/auth/password/reset", HTTP_X_PASSWORD_RESET_KEY="not-a-key")

    assert not _refused(response)
    assert recaptcha.asked == []


def test_the_rest_of_allauth_needs_no_token(recaptcha):
    response = Client(HTTP_HOST=HOST).delete(f"{BROWSER}/auth/session")

    assert not _refused(response)
    assert recaptcha.asked == []


def test_the_csrf_check_comes_first_and_google_is_not_asked(recaptcha):
    browser = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)

    response = browser.post(
        f"{BROWSER}/auth/login",
        {"email": "a@example.com", "password": "x", "recaptcha_token": "human:login"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert recaptcha.asked == []


def test_switched_off_the_doors_need_no_token(verified):
    response = _post(f"{BROWSER}/auth/login", {"email": verified.email, "password": PASSWORD})

    assert (response.status_code, _pending(response)) == (401, ["login_by_code"])
