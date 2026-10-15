"""«Continue with Google»: the round trip to Google and back (ported from ERPlora/saas ADR-0154).

Ported from ERPlora/saas origin/develop: ``apps/auth/users/views.py`` (``google_login`` and
``google_callback`` at the paths registered with Google), ``tests/test_unified_auth.py``
(``TestGoogleConfig``), ``tests/test_google_login_csp.py`` and ``tests/test_google_login_next.py``.
Changes of saas-next: the authorization carries PKCE, and Google's own ``email_verified`` claim
decides whether the address is proven (no ``VERIFIED_EMAIL`` override): an unknown email creates its
account only when Google vouches for it. allauth runs headless only (PLAN-SAAS §2): the Vue sign-in
posts allauth.headless's provider redirect with the page to come back to (``callback_url``: its
``next``, else the launcher), and Google comes back to ``/auth/google/callback/``, the URI registered
with it.

Only the network is faked: Google's token endpoint answers the code exchange with an id_token.
"""

import base64
import hashlib
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal import auth as totp_auth
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse

from accounts.tests.conftest import BROWSER
from conftest import GOOGLE_CLIENT_ID

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
#: What «Continue with Google» on the launcher posts (accounts/frontend/components/SignInForm.vue).
PROVIDER_REDIRECT = f"{BROWSER}/auth/provider/redirect"
GOOGLE_CALLBACK = "/auth/google/callback/"
#: Where the sign-in sends a visitor with no ``next``: the callback_url it posts then.
LAUNCHER = "/launch"
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
ANA_UID = "108000000000000000001"
STRANGER_UID = "108000000000000000002"


def _claims(uid: str, email: str, verified: bool = True) -> dict:
    """The id_token Google hands back for one of its accounts."""
    now = int(time.time())
    return {
        "iss": "https://accounts.google.com",
        "aud": GOOGLE_CLIENT_ID,
        "sub": uid,
        "email": email,
        "email_verified": verified,
        "given_name": "",
        "family_name": "",
        "iat": now,
        "exp": now + 3600,
    }


class _TokenResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def __init__(self, body: dict):
        self._body = body
        self.text = str(body)
        self.content = self.text.encode()

    def json(self):
        return self._body


class _GoogleTokenEndpoint:
    """A requests session whose only peer is Google's token endpoint."""

    def __init__(self, claims: dict):
        self.claims = claims
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        id_token = jwt.encode(self.claims, "unused-the-signature-is-not-checked", algorithm="HS256")
        return _TokenResponse({"access_token": "ya29.test", "expires_in": 3599, "id_token": id_token})


@contextmanager
def _google_answers(claims: dict):
    endpoint = _GoogleTokenEndpoint(claims)
    original = DefaultSocialAccountAdapter.get_requests_session
    DefaultSocialAccountAdapter.get_requests_session = lambda self: endpoint
    try:
        yield endpoint
    finally:
        DefaultSocialAccountAdapter.get_requests_session = original


def _start(client, next_path: str | None = None):
    """«Continue with Google» on /login: back to ``next``, else to the launcher."""
    data = {"provider": "google", "process": "login", "callback_url": next_path or LAUNCHER}
    return client.post(PROVIDER_REDIRECT, data, HTTP_HOST=HOST)


def _query(url: str) -> dict:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _sign_in_with_google(client, claims: dict, next_path: str | None = None, **extra):
    """The whole round trip: our POST, Google's consent (skipped) and its redirect back."""
    started = _start(client, next_path)
    authorization = _query(started["Location"])
    with _google_answers(claims) as endpoint:
        response = client.get(
            GOOGLE_CALLBACK, {"state": authorization["state"], "code": "4/the-code"}, HTTP_HOST=HOST, **extra
        )
    return response, authorization, endpoint


def _signed_in_user_id(client):
    return client.session.get("_auth_user_id")


def _form_action(response) -> list[str]:
    policy = response["Content-Security-Policy"]
    directives = {part.split()[0]: part.split()[1:] for part in policy.split("; ")}
    return directives["form-action"]


class TestTheRoutes:
    def test_allauths_own_name_leads_to_the_registered_path(self):
        """allauth builds the authorization's redirect_uri from ``reverse("google_callback")``: in today's
        SaaS (allauth 65.18) Google came back to /accounts/google/login/callback/, not to the
        /auth/google/callback/ its view pinned. Taking allauth's name pins the URI registered with Google."""
        assert reverse("google_callback") == GOOGLE_CALLBACK

    def test_without_credentials_google_is_not_served(self, client):
        assert client.get(GOOGLE_CALLBACK, HTTP_HOST=HOST).status_code == 404
        response = client.post(
            PROVIDER_REDIRECT, {"provider": "google", "process": "login", "callback_url": LAUNCHER}, HTTP_HOST=HOST
        )
        assert response.status_code == 404
        assert response.json()["errors"][0]["code"] == "not_found"

    @pytest.mark.usefixtures("spa_manifest")
    def test_the_old_start_of_the_round_trip_is_gone(self, client, google):
        """``/auth/google/login/`` (a form post of the template login) and its interstitial page."""
        assert client.post("/auth/google/login/", {"process": "login"}, HTTP_HOST=HOST).status_code == 404


class TestStartingTheSignIn:
    def test_a_bare_get_never_leaves_for_google(self, client, google):
        """Only the button's POST starts it: a link cannot sign anybody in (login CSRF)."""
        response = client.get(
            PROVIDER_REDIRECT, {"provider": "google", "process": "login", "callback_url": LAUNCHER}, HTTP_HOST=HOST
        )

        assert response.status_code == 405
        assert "Location" not in response

    def test_a_post_without_the_csrf_token_never_leaves_for_google(self, google):
        browser = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)

        response = _start(browser)

        assert response.status_code == 403
        assert "Location" not in response

    def test_a_way_back_to_another_site_is_refused(self, client, google):
        response = _start(client, "https://evil.example/steal")

        assert (response.status_code, response.url) == (302, "/login/error?code=authentication_error")

    def test_the_post_goes_to_google_with_pkce_and_the_registered_callback(self, client, google):
        response = _start(client)

        assert response.status_code == 302
        assert response["Location"].startswith(GOOGLE_AUTHORIZE + "?")
        params = _query(response["Location"])
        assert params["client_id"] == GOOGLE_CLIENT_ID
        assert params["redirect_uri"] == f"http://{HOST}{GOOGLE_CALLBACK}"
        assert params["response_type"] == "code"
        assert set(params["scope"].split()) == {"profile", "email"}
        assert params["access_type"] == "online"
        assert params["code_challenge_method"] == "S256"
        assert params["code_challenge"]
        assert params["state"]

    @pytest.mark.usefixtures("spa_manifest")
    def test_the_csp_lets_the_form_leave_for_the_host_it_redirects_to(self, client, google):
        """`form-action` filters the whole redirect chain of a form post (saas#945): the sign-in's."""
        page = client.get("/launch", HTTP_HOST=HOST)
        google_host = urlsplit(_start(client)["Location"]).netloc

        assert f"https://{google_host}" in _form_action(page)

    @pytest.mark.usefixtures("spa_manifest")
    def test_google_adds_no_script_nor_connection_source(self, client, google):
        """The sign-in is a redirect, not a Google script: nothing external may run or be fetched."""
        policy = client.get("/launch", HTTP_HOST=HOST)["Content-Security-Policy"]
        directives = {part.split()[0]: part.split()[1:] for part in policy.split("; ")}

        for directive in ("script-src", "connect-src", "frame-src", "img-src"):
            assert not any("google" in source for source in directives.get(directive, []))


class TestComingBackFromGoogle:
    def test_a_known_email_signs_in_and_continues_to_next(self, client, google, ana):
        next_path = "/hub-login/?hub=a&next=/sales/"

        response, _, _ = _sign_in_with_google(client, _claims(ANA_UID, ana.email), next_path)

        assert response.status_code == 302
        assert response.url == next_path
        assert _signed_in_user_id(client) == str(ana.pk)

    def test_without_next_it_lands_on_the_launcher(self, client, google, ana):
        response, _, _ = _sign_in_with_google(client, _claims(ANA_UID, ana.email))

        assert response.url == LAUNCHER

    def test_with_two_factor_authentication_the_login_waits_for_the_code(self, client, google, ana, settings):
        """Back on the page it came from, the sign-in sends it on to /2fa/authenticate (SignInForm.vue)."""
        settings.ACCOUNTS_MFA_ENABLED = True
        totp_auth.TOTP.activate(ana, totp_auth.generate_totp_secret())

        response, _, _ = _sign_in_with_google(client, _claims(ANA_UID, ana.email))

        assert (response.status_code, response.url) == (302, LAUNCHER)
        assert _signed_in_user_id(client) is None
        session = client.get(f"{BROWSER}/auth/session", HTTP_HOST=HOST)
        assert session.status_code == 401
        assert [flow["id"] for flow in session.json()["data"]["flows"] if flow.get("is_pending")] == [
            "mfa_authenticate"
        ]

    def test_signing_in_again_while_signed_in_is_a_fresh_sign_in_back_on_the_page(self, client, google, ana):
        """«Confirm it's you» of an account that only signs in with Google (ReauthModal.vue): allauth records it."""
        SocialAccount.objects.create(user=ana, provider="google", uid=ANA_UID)
        client.force_login(ana)

        response, _, _ = _sign_in_with_google(client, _claims(ANA_UID, ana.email), "/account/api-keys")

        assert (response.status_code, response.url) == (302, "/account/api-keys")
        assert [record["method"] for record in client.session["account_authentication_methods"]] == ["socialaccount"]

    def test_the_email_matches_whatever_its_case(self, client, google, ana):
        _sign_in_with_google(client, _claims(ANA_UID, "Ana@Example.com"))

        assert _signed_in_user_id(client) == str(ana.pk)

    def test_the_code_is_exchanged_with_the_pkce_verifier_of_the_challenge(self, client, google, ana):
        _, authorization, endpoint = _sign_in_with_google(client, _claims(ANA_UID, ana.email))

        (call,) = endpoint.calls
        assert call["method"] == "POST"
        assert call["url"] == "https://oauth2.googleapis.com/token"
        sent = call["data"]
        assert sent["code"] == "4/the-code"
        assert sent["redirect_uri"] == f"http://{HOST}{GOOGLE_CALLBACK}"
        digest = hashlib.sha256(sent["code_verifier"].encode()).digest()
        assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == authorization["code_challenge"]

    def test_the_google_account_is_linked_to_the_account(self, client, google, ana):
        _sign_in_with_google(client, _claims(ANA_UID, ana.email))

        assert list(SocialAccount.objects.filter(user=ana).values_list("provider", "uid")) == [("google", ANA_UID)]

    def test_an_unknown_email_creates_the_account_and_lands_on_the_launcher(self, client, google, ana):
        """Sign-up is open (ADR-0154): Google vouches for the address, so no code is asked for."""
        response, _, _ = _sign_in_with_google(client, _claims(STRANGER_UID, "stranger@gmail.com"))

        stranger = get_user_model().objects.get(email="stranger@gmail.com")
        assert (response.status_code, response.url) == (302, "/launch")
        assert _signed_in_user_id(client) == str(stranger.pk)
        assert list(EmailAddress.objects.filter(user=stranger).values_list("email", "verified", "primary")) == [
            ("stranger@gmail.com", True, True)
        ]
        assert list(SocialAccount.objects.filter(user=stranger).values_list("provider", "uid")) == [
            ("google", STRANGER_UID)
        ]
        assert not stranger.has_usable_password()

    def test_a_new_account_continues_to_next(self, client, google):
        next_path = "/hub-login/?hub=a&next=/sales/"

        response, _, _ = _sign_in_with_google(client, _claims(STRANGER_UID, "stranger@gmail.com"), next_path)

        assert response.url == next_path
        assert _signed_in_user_id(client) == str(get_user_model().objects.get(email="stranger@gmail.com").pk)

    def test_an_unknown_address_google_does_not_vouch_for_creates_no_account(self, client, google):
        """Otherwise whoever holds that Google would get a session for an address they never proved, and
        keep the Google link once the mailbox's owner claims the account with «Forgot your password?»."""
        response, _, _ = _sign_in_with_google(
            client, _claims(STRANGER_UID, "stranger@gmail.com", verified=False), "/launch"
        )

        assert (response.status_code, response.url) == (302, "/login/error?code=authentication_error&next=/launch")
        assert not get_user_model().objects.exists()
        assert not SocialAccount.objects.exists()
        assert _signed_in_user_id(client) is None

    def test_an_address_google_does_not_vouch_for_signs_nobody_in(self, client, google, ana):
        """Google's `email_verified` decides; an unproven address must not open Ana's account."""
        response, _, _ = _sign_in_with_google(client, _claims(STRANGER_UID, ana.email, verified=False))

        assert (response.status_code, response.url) == (302, "/login/error?code=authentication_error&next=/launch")
        assert _signed_in_user_id(client) is None
        assert not SocialAccount.objects.exists()
        assert get_user_model().objects.count() == 1
        assert mail.outbox == []

    def test_a_state_that_was_not_issued_signs_nobody_in(self, client, google, ana):
        with _google_answers(_claims(ANA_UID, ana.email)) as endpoint:
            response = client.get(GOOGLE_CALLBACK, {"state": "forged", "code": "4/the-code"}, HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (302, "/login/error?code=authentication_error")
        assert endpoint.calls == []
        assert _signed_in_user_id(client) is None

    def test_cancelling_at_google_goes_back_to_the_sign_in_keeping_next(self, client, google):
        """Like Slack, Notion or Atlassian: «Cancel» on Google's screen returns to our login."""
        state = _query(_start(client, "/hub-login/?hub=a&next=/sales/")["Location"])["state"]

        response = client.get(GOOGLE_CALLBACK, {"state": state, "error": "access_denied"}, HTTP_HOST=HOST)

        assert response.status_code == 302
        assert response.url == "/launch?next=/hub-login/%3Fhub%3Da%26next%3D/sales/"
        assert _signed_in_user_id(client) is None

    def test_cancelling_without_next_goes_back_to_the_bare_launcher(self, client, google):
        """The sign-in is the launcher's: coming back to it, it needs no ``next`` to itself."""
        state = _query(_start(client)["Location"])["state"]

        response = client.get(GOOGLE_CALLBACK, {"state": state, "error": "access_denied"}, HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (302, "/launch")

    def test_an_error_at_google_lands_on_the_vue_page_keeping_next(self, client, google):
        state = _query(_start(client, "/launch")["Location"])["state"]

        response = client.get(GOOGLE_CALLBACK, {"state": state, "error": "server_error"}, HTTP_HOST=HOST)

        assert response.status_code == 302
        assert response.url == "/login/error?code=authentication_error&next=/launch"
        assert _signed_in_user_id(client) is None


class TestConnectingGoogleToTheOpenSession:
    """allauth's «connect» (``process=connect``) is refused (``SocialAccountAdapter.pre_social_login``): ERPlora
    has no screen that connects a provider, Google is linked by signing in with it. One posted anyway (an old tab,
    a crafted form) ends on the Vue error page that says so, never on the launcher with a Django message the SPA
    does not show."""

    def _connect(self, client, claims, next_path="/account/security"):
        """The round trip of a ``process=connect`` post: allauth.headless's redirect, then Google's way back."""
        data = {"provider": "google", "process": "connect", "callback_url": next_path}
        state = _query(client.post(PROVIDER_REDIRECT, data, HTTP_HOST=HOST)["Location"])["state"]
        with _google_answers(claims):
            return client.get(GOOGLE_CALLBACK, {"state": state, "code": "4/the-code"}, HTTP_HOST=HOST)

    def test_it_lands_on_the_vue_error_page_that_says_how_google_is_linked(self, client, google, ana):
        client.force_login(ana)

        response = self._connect(client, _claims(STRANGER_UID, "stranger@gmail.com"))

        assert (response.status_code, response.url) == (
            302,
            "/login/error?code=google_link_refused&next=/account/security",
        )

    def test_nothing_is_linked_and_the_session_stays_the_owners(self, client, google, ana):
        client.force_login(ana)

        self._connect(client, _claims(STRANGER_UID, "stranger@gmail.com"))

        assert not SocialAccount.objects.exists()
        assert _signed_in_user_id(client) == str(ana.pk)
        assert mail.outbox == []

    def test_no_message_is_left_for_a_page_that_never_shows_it(self, client, google, ana):
        client.force_login(ana)

        self._connect(client, _claims(STRANGER_UID, "stranger@gmail.com"))

        assert "_messages" not in client.session
        assert not client.cookies.get("messages")
