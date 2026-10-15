"""allauth's doors around the account's addresses and password that the SaaS closes (``accounts.doors``,
``config/urls.py``), as Google's «connections» are closed (saas#2552).

- ``/_allauth/browser/v1/account/email`` (allauth's API: add an address, make it the primary one): the sign-in
  email changes only through ``accounts.email.change`` and its code (saas#2536). The API answers 404, whatever
  the method; allauth's page ``/accounts/email/`` no longer exists (headless only).
- ``account/password/change`` for an account without a password: the session alone would give it one (and
  with it every door a password opens). «Forgot your password?» gives it one, proving the mailbox; allauth's
  page ``/accounts/password/set/`` no longer exists. An account with a password still changes it
  (``test_password_change``).

Each is shown closed with a sign-in of a moment ago: closed, not just behind allauth's reauthentication.

allauth's own sign-up (``auth/signup``) is open since the launcher's «Create account» tab (FIX-LAUNCH-TABS;
its contract is ``test_unified_login``'s): that one door, none of allauth's other ways in.
"""

import time

import pytest
from allauth.account.models import EmailAddress
from django.core import mail

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
    @pytest.mark.usefixtures("spa_manifest")
    def test_allauths_page_is_gone_and_adds_nothing(self, signed_in, ana):
        response = signed_in.post(
            "/accounts/email/", {"action_add": "", "email": "ana@new.example"}, HTTP_HOST=HOST
        )

        assert response.status_code == 404
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

    @pytest.mark.usefixtures("spa_manifest")
    def test_allauths_set_password_page_is_gone_and_sets_nothing(self, google_only, ana):
        response = google_only.post(
            "/accounts/password/set/",
            {"password1": "a brand new pass phrase 2026", "password2": "a brand new pass phrase 2026"},
            HTTP_HOST=HOST,
        )

        assert response.status_code == 404
        ana.refresh_from_db()
        assert not ana.has_usable_password()

    def test_forgot_your_password_still_reaches_it(self, client, ana):
        ana.set_unusable_password()
        ana.save()

        client.post(
            f"{BROWSER}/auth/password/request", {"email": ana.email}, content_type="application/json", HTTP_HOST=HOST
        )

        assert [message for message in mail.outbox if f"http://{HOST}/password/reset/key/" in message.body]


class TestOnlyTheSignUpIsOpen:
    def test_allauths_signup_answers_the_create_account_tab(self, client):
        response = client.post(
            f"{BROWSER}/auth/signup",
            {"email": "new@example.com", "password": "a brand new pass phrase 2026"},
            content_type="application/json",
            HTTP_HOST=HOST,
        )

        assert response.status_code == 401
        assert [flow["id"] for flow in response.json()["data"]["flows"] if flow.get("is_pending")] == ["verify_email"]

    @pytest.mark.parametrize(
        "door",
        [
            # A sign-in with the mailed code alone, no password (ACCOUNT_LOGIN_BY_CODE_ENABLED is off).
            "auth/code/request",
            # A sign-up with a passkey and no password (MFA_PASSKEY_SIGNUP_ENABLED is off).
            "auth/passkey/signup",
        ],
    )
    def test_allauths_other_ways_in_stay_closed(self, client, door):
        response = client.post(
            f"{BROWSER}/{door}", {"email": "new@example.com"}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 404
        assert mail.outbox == []
