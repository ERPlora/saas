"""allauth.headless, browser client: the login API of the Vue pages (PLAN-SAAS §6, ronda 11).

Same-origin session cookie plus Django's CSRF: the SPA's HTML sets the ``csrftoken`` cookie and the
SDK sends it back in ``X-CSRFToken`` (``GET …/auth/session`` sets it as well). Errors come as
``errors[{param, code, message}]``; an anonymous session answers 401 with the ``flows`` it can take.
Headless only (``HEADLESS_ONLY``): every link allauth mails leads to a page of the SPA
(``HEADLESS_FRONTEND_URLS``), and allauth has no template page left (``test_login``).
"""

import re

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import resolve

from accounts.tests.conftest import CONFIRM_CODE, prove_address, take_mailed_code

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
BROWSER = "/_allauth/browser/v1"
LOGIN = f"{BROWSER}/auth/login"
SESSION = f"{BROWSER}/auth/session"


@pytest.fixture
def owner():
    """The account `demo_seed` creates for local development, its address proven."""
    user = get_user_model().objects.create_user(
        email="owner@example.com", password="owner", first_name="Owner"
    )
    prove_address(user.email)
    return user


@pytest.fixture
def browser():
    """A browser: Django checks the CSRF token as it would in production."""
    client = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
    client.get(SESSION)
    return client


def _post_login(client, email, password):
    return client.post(
        LOGIN,
        {"email": email, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )


def test_an_anonymous_session_is_401_with_the_password_flow_and_sets_the_csrf_cookie(
    client,
):
    response = client.get(SESSION, HTTP_HOST=HOST)

    assert response.status_code == 401
    body = response.json()
    assert body["meta"]["is_authenticated"] is False
    assert {"id": "login"} in body["data"]["flows"]
    assert "csrftoken" in response.cookies


def test_the_right_password_and_the_mailed_code_sign_in_with_a_session_cookie(browser, owner):
    """The password waits for the code mailed to the account (``test_sign_in_code``), which signs in."""
    waiting = _post_login(browser, "owner@example.com", "owner")
    assert waiting.status_code == 401

    response = browser.post(
        CONFIRM_CODE,
        {"code": take_mailed_code("owner@example.com")},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["user"]["email"] == "owner@example.com"
    assert body["meta"]["is_authenticated"] is True
    assert "sessionid" in response.cookies
    assert browser.get(SESSION).json()["data"]["user"]["email"] == "owner@example.com"


def test_a_wrong_password_is_400_with_the_error_on_the_password(browser, owner):
    response = _post_login(browser, "owner@example.com", "wrong")

    assert response.status_code == 400
    [error] = response.json()["errors"]
    assert (error["param"], error["code"]) == ("password", "email_password_mismatch")
    assert error["message"]
    assert "sessionid" not in response.cookies


def test_a_missing_email_is_400_on_the_email(browser):
    response = _post_login(browser, "", "owner")

    assert response.status_code == 400
    assert [error["param"] for error in response.json()["errors"]] == ["email"]


def test_the_errors_speak_the_language_of_the_request(browser, owner):
    response = browser.post(
        LOGIN,
        {"email": "owner@example.com", "password": "wrong"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value,
        HTTP_ACCEPT_LANGUAGE="es",
    )

    assert "no son correctas" in response.json()["errors"][0]["message"]


def test_a_login_without_the_csrf_token_is_refused(browser, owner):
    response = browser.post(
        LOGIN,
        {"email": "owner@example.com", "password": "owner"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert "sessionid" not in response.cookies


def test_signing_out_ends_the_session(browser, owner):
    _post_login(browser, "owner@example.com", "owner")

    response = browser.delete(
        SESSION, HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value
    )

    assert response.status_code == 401
    assert browser.get(SESSION).status_code == 401


def _reset_link(message) -> str:
    [link] = re.findall(r"http://localhost:8001/password/reset/key/\S+", message.body)
    return link


def test_the_password_reset_mail_links_the_spa_page_and_its_key_opens_the_reset(client, owner):
    response = client.post(
        f"{BROWSER}/auth/password/request", {"email": "owner@example.com"}, content_type="application/json", HTTP_HOST=HOST
    )

    assert response.status_code == 200
    [message] = mail.outbox
    key = _reset_link(message).removeprefix("http://localhost:8001/password/reset/key/")
    answer = client.get(f"{BROWSER}/auth/password/reset", HTTP_HOST=HOST, HTTP_X_PASSWORD_RESET_KEY=key)
    assert answer.status_code == 200
    assert answer.json()["data"]["user"]["email"] == "owner@example.com"


def test_a_reset_asked_for_an_unknown_address_mails_the_create_account_tab(client):
    client.post(
        f"{BROWSER}/auth/password/request", {"email": "nobody@example.com"}, content_type="application/json", HTTP_HOST=HOST
    )

    [message] = mail.outbox
    assert "http://localhost:8001/launch?tab=signup\n" in message.body


def test_the_code_of_a_new_account_is_mailed_without_a_link(client):
    """Verification is by code (ADR-0159): allauth builds no confirmation link, so none is named."""
    client.post(
        f"{BROWSER}/auth/signup",
        {"email": "new@example.com", "password": "a long pass phrase 2026"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )

    [message] = mail.outbox
    assert re.search(r"^\d{6}$", message.body, re.M)
    assert re.findall(r"https?://\S+", message.body) == ["https://erplora.com"]


@pytest.mark.parametrize("urlname", sorted(settings.HEADLESS_FRONTEND_URLS))
def test_every_mailed_link_is_a_page_of_the_spa(urlname):
    path = settings.HEADLESS_FRONTEND_URLS[urlname].replace("{key}", "a-key")

    assert path.startswith("/")
    assert resolve(path.partition("?")[0]).url_name == "spa"


def test_the_template_password_reset_is_gone(client, owner):
    response = client.post("/accounts/password/reset/", {"email": "owner@example.com"}, HTTP_HOST=HOST)

    assert response.status_code == 404
    assert mail.outbox == []
