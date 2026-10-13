"""allauth.headless, browser client: the login API of the Vue pages (PLAN-SAAS §6, ronda 11).

Same-origin session cookie plus Django's CSRF: the SPA's HTML sets the ``csrftoken`` cookie and the
SDK sends it back in ``X-CSRFToken`` (``GET …/auth/session`` sets it as well). Errors come as
``errors[{param, code, message}]``; an anonymous session answers 401 with the ``flows`` it can take.
The template login keeps working next to it until every account page is a Vue page.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
BROWSER = "/_allauth/browser/v1"
LOGIN = f"{BROWSER}/auth/login"
SESSION = f"{BROWSER}/auth/session"


@pytest.fixture
def owner():
    """The account `demo_seed` creates for local development."""
    return get_user_model().objects.create_user(
        email="owner@example.com", password="owner", first_name="Owner"
    )


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


def test_the_right_password_signs_in_with_a_session_cookie(browser, owner):
    response = _post_login(browser, "owner@example.com", "owner")

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


def test_the_template_password_reset_still_mails_its_own_page(client, owner):
    """Regression guard: HEADLESS_FRONTEND_URLS would point this mail at a SPA page not built yet."""
    client.post(
        "/accounts/password/reset/", {"email": "owner@example.com"}, HTTP_HOST=HOST
    )

    [message] = mail.outbox
    assert re.search(
        r"http://localhost:8001/accounts/password/reset/key/\S+/", message.body
    )
