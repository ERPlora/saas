"""The sign-in lives in the launcher, the SPA's ``/launch`` (``hubs/frontend/pages/LaunchPage.vue`` with
``accounts/frontend/components/SignInForm.vue``), over allauth.headless.

allauth runs headless only (``HEADLESS_ONLY``, PLAN-SAAS §2): none of its template pages exists. The old
addresses of the sign-in and of the sign-up (bookmarks, links of the public web cached elsewhere) and
``/login``, the SPA's sign-in page until the form moved into the launcher (Ioan, 2026-10-15), lead to
``/launch`` for good, keeping where the person was going, in one hop. ``/login/error`` stays a page of the
SPA. Logging in through the API is ``test_headless``'s, ``test_unified_login``'s and
``test_sign_in_code``'s; the Google round trip is ``test_google``'s.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from accounts.tests.conftest import prove_address

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
LAUNCHER = "/launch"
SHELL_MARK = '<div id="app"></div>'


@pytest.mark.usefixtures("spa_manifest")
def test_the_sign_in_is_the_launcher_a_page_of_the_spa(client):
    response = client.get(LAUNCHER, {"next": "/hub-login/?hub=a"}, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert SHELL_MARK in response.content.decode()


@pytest.mark.usefixtures("spa_manifest")
def test_its_error_page_stays_a_page_of_the_spa(client):
    response = client.get("/login/error", {"code": "invalid_hub"}, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert SHELL_MARK in response.content.decode()


def test_django_sends_a_visitor_without_a_session_to_it():
    assert settings.LOGIN_URL == LAUNCHER


@pytest.mark.parametrize("old", ["/login", "/accounts/login/", "/accounts/signup/"])
def test_the_old_addresses_lead_to_it_for_good_keeping_next(client, old):
    response = client.get(f"{old}?next=/hub-login/%3Fhub%3Da%26next%3D/sales/", HTTP_HOST=HOST)

    assert response.status_code == 301
    assert response.url == "/launch?next=/hub-login/%3Fhub%3Da%26next%3D/sales/"


@pytest.mark.parametrize("old", ["/login", "/accounts/login/", "/accounts/signup/"])
def test_the_old_addresses_without_a_query_lead_to_the_bare_launcher(client, old):
    response = client.get(old, HTTP_HOST=HOST)

    assert (response.status_code, response.url) == (301, LAUNCHER)


def test_the_old_addresses_keep_every_parameter(client):
    """``?notice=password_reset`` of the reset page, ``?surface=account`` of the app."""
    response = client.get("/login?notice=password_reset&surface=account", HTTP_HOST=HOST)

    assert response.url == "/launch?notice=password_reset&surface=account"


@pytest.mark.parametrize("old", ["/login", "/accounts/login/"])
def test_posting_an_old_sign_in_signs_nobody_in(client, password, old):
    get_user_model().objects.create_user(email="ana@example.com", password=password)
    prove_address("ana@example.com")

    response = client.post(
        old,
        {"login": "ana@example.com", "email": "ana@example.com", "password": password},
        HTTP_HOST=HOST,
    )

    assert response.status_code == 301
    assert "_auth_user_id" not in client.session


# A 404 of Django renders the public web's page, which links the Vite build.
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize(
    "page",
    [
        "/accounts/",
        "/accounts/logout/",
        "/accounts/password/reset/",
        "/accounts/password/reset/done/",
        "/accounts/password/reset/key/1-set-password/",
        "/accounts/password/change/",
        "/accounts/password/set/",
        "/accounts/email/",
        "/accounts/confirm-email/",
        "/accounts/reauthenticate/",
        "/accounts/2fa/",
        "/accounts/2fa/authenticate/",
        "/accounts/sessions/",
        "/accounts/3rdparty/",
        "/accounts/3rdparty/login/cancelled/",
        "/accounts/3rdparty/login/error/",
        "/accounts/google/login/",
        "/accounts/google/login/callback/",
    ],
)
def test_allauths_template_pages_are_gone(client, page):
    assert client.get(page, HTTP_HOST=HOST).status_code == 404
