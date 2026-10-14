"""allauth's doors around the account's addresses and password that the SaaS closes (``accounts.doors``,
``config/urls.py``), as ``accounts/3rdparty/`` closed Google's «connections» (saas#2552).

- ``/accounts/email/`` (allauth's page) and ``/_allauth/browser/v1/account/email`` (its API: add an address, make
  it the primary one): the sign-in email changes only through ``accounts.email.change`` and its code
  (saas#2536). The page leads to the panel's profile; the API answers 404, whatever the method.
- ``/accounts/password/set/`` and ``account/password/change`` for an account without a password: the session
  alone would give it one (and with it every door a password opens). «Forgot your password?» gives it one,
  proving the mailbox. An account with a password still changes it (``test_password_change``).

Each is shown closed with a sign-in of a moment ago: closed, not just behind allauth's reauthentication.
"""

import time

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.urls import reverse

from accounts.tests.conftest import AUTHENTICATION_RECORDS, BROWSER, HOST

pytestmark = pytest.mark.django_db

EMAIL_API = f"{BROWSER}/account/email"
PASSWORD_API = f"{BROWSER}/account/password/change"


@pytest.fixture
def google_only(client, ana):
    """``ana`` without a password, signed in with Google a moment ago."""
    ana.set_unusable_password()
    ana.save()
    client.force_login(ana)
    session = client.session
    session[AUTHENTICATION_RECORDS] = [{"method": "socialaccount", "at": time.time(), "provider": "google", "uid": "1"}]
    session.save()
    return client


class TestTheAddressDoors:
    def test_allauths_page_leads_to_the_panels_profile(self, signed_in):
        response = signed_in.get("/accounts/email/", HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (302, "/account/profile")
        assert reverse("account_email") == "/accounts/email/"

    def test_adding_an_address_on_allauths_page_does_nothing(self, signed_in, ana):
        response = signed_in.post(
            "/accounts/email/", {"action_add": "", "email": "ana@new.example"}, HTTP_HOST=HOST
        )

        assert response.status_code == 302
        assert not EmailAddress.objects.filter(email="ana@new.example").exists()
        assert mail.outbox == []

    @pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
    def test_the_api_is_closed_whatever_the_method(self, signed_in, ana, method):
        response = getattr(signed_in, method)(
            EMAIL_API, {"email": "ana@new.example"}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 404
        assert response.json()["errors"][0]["code"] == "not_found"
        assert not EmailAddress.objects.filter(email="ana@new.example").exists()
        assert mail.outbox == []


class TestThePasswordOfAnAccountWithoutOne:
    def test_the_api_does_not_give_one_with_the_session_alone(self, google_only, ana):
        response = google_only.post(
            PASSWORD_API, {"new_password": "a brand new pass phrase 2026"}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 403
        assert response.json()["errors"][0]["code"] == "password_required"
        ana.refresh_from_db()
        assert not ana.has_usable_password()

    def test_allauths_set_password_page_leads_to_forgot_your_password(self, google_only, ana):
        response = google_only.post(
            "/accounts/password/set/",
            {"password1": "a brand new pass phrase 2026", "password2": "a brand new pass phrase 2026"},
            HTTP_HOST=HOST,
        )

        assert (response.status_code, response.url) == (302, reverse("account_reset_password"))
        ana.refresh_from_db()
        assert not ana.has_usable_password()

    def test_forgot_your_password_still_reaches_it(self, client, ana):
        ana.set_unusable_password()
        ana.save()

        client.post("/accounts/password/reset/", {"email": ana.email}, HTTP_HOST=HOST)

        assert [message for message in mail.outbox if "/password/reset/key/" in message.body]
