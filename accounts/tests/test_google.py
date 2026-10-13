"""«Continue with Google»: the round trip to Google and back (ported from ERPlora/saas ADR-0154).

Ported from ERPlora/saas origin/develop: ``apps/auth/users/views.py`` (``google_login`` and
``google_callback`` at the paths registered with Google), ``tests/test_unified_auth.py``
(``TestGoogleConfig``), ``tests/test_google_login_csp.py`` and ``tests/test_google_login_next.py``.
Changes of saas-next: the sign-up is closed (an unknown Google email creates no account), the
authorization carries PKCE, and Google's own ``email_verified`` claim decides whether the address
is proven (no ``VERIFIED_EMAIL`` override).

Only the network is faked: Google's token endpoint answers the code exchange with an id_token.
"""

import base64
import hashlib
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.urls import reverse

from conftest import GOOGLE_CLIENT_ID

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
GOOGLE_LOGIN = "/auth/google/login/"
GOOGLE_CALLBACK = "/auth/google/callback/"
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
    data = {"process": "login"}
    if next_path is not None:
        data["next"] = next_path
    return client.post(GOOGLE_LOGIN, data, HTTP_HOST=HOST)


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
    def test_allauths_own_names_lead_to_the_registered_paths(self):
        """allauth builds the authorization's redirect_uri from ``reverse("google_callback")`` with
        the provider's stock adapter, whatever adapter the view was given: in today's SaaS
        (allauth 65.18) Google came back to /accounts/google/login/callback/, not to the
        /auth/google/callback/ its view pinned. Overriding allauth's names pins both ends."""
        assert reverse("google_login") == GOOGLE_LOGIN
        assert reverse("google_callback") == GOOGLE_CALLBACK

    @pytest.mark.parametrize("path", [GOOGLE_LOGIN, GOOGLE_CALLBACK])
    def test_without_credentials_google_is_not_served(self, client, path):
        assert client.get(path, HTTP_HOST=HOST).status_code == 404
        assert client.post(path, {"process": "login"}, HTTP_HOST=HOST).status_code == 404


class TestStartingTheSignIn:
    def test_a_bare_get_never_leaves_for_google(self, client, google):
        """SOCIALACCOUNT_LOGIN_ON_GET=False: a link cannot sign anybody in (login CSRF)."""
        response = client.get(GOOGLE_LOGIN, {"next": "/launch/", "process": "login"}, HTTP_HOST=HOST)

        assert response.status_code == 200
        assert "socialaccount/login.html" in [t.name for t in response.templates]

    def test_the_interstitial_posts_itself_keeping_next_with_a_nonced_script(self, client, google):
        response = client.get(GOOGLE_LOGIN, {"next": "/launch/", "process": "login"}, HTTP_HOST=HOST)

        html = response.content.decode()
        assert '<form method="post" action="" data-google-autosubmit>' in html
        assert '<input type="hidden" name="next" value="/launch/">' in html
        assert '<input type="hidden" name="process" value="login">' in html
        assert 'data-icon="ion:logo-google"' in html
        nonce = response["Content-Security-Policy"].split("'nonce-")[1].split("'")[0]
        assert f'<script nonce="{nonce}">' in html

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

    def test_the_csp_lets_the_form_leave_for_the_host_it_redirects_to(self, client, google):
        """`form-action` filters the whole redirect chain of a form post (saas#945)."""
        page = client.get(GOOGLE_LOGIN, HTTP_HOST=HOST)
        google_host = urlsplit(_start(client)["Location"]).netloc

        assert f"https://{google_host}" in _form_action(page)

    def test_google_adds_no_script_nor_connection_source(self, client, google):
        """The sign-in is a redirect, not a Google script: nothing external may run or be fetched."""
        policy = client.get(GOOGLE_LOGIN, HTTP_HOST=HOST)["Content-Security-Policy"]
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

        assert response.url == "/launch"

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

    def test_an_unknown_email_creates_no_account_and_goes_to_the_page_that_says_so(self, client, google, ana):
        """The Vue page /login/error names the address, so a person with several Google accounts
        sees which one they picked."""
        users_before = get_user_model().objects.count()

        response, _, _ = _sign_in_with_google(client, _claims(STRANGER_UID, "stranger@gmail.com"))

        assert response.status_code == 302
        assert response.url == "/login/error?code=google_no_account&email=stranger%40gmail.com"
        assert get_user_model().objects.count() == users_before
        assert not SocialAccount.objects.exists()
        assert _signed_in_user_id(client) is None

    def test_the_refusal_keeps_next_for_the_way_back_to_the_sign_in(self, client, google):
        response, _, _ = _sign_in_with_google(client, _claims(STRANGER_UID, "stranger@gmail.com"), "/launch")

        assert _query(response.url) == {"code": "google_no_account", "email": "stranger@gmail.com", "next": "/launch"}

    def test_an_address_google_does_not_vouch_for_signs_nobody_in(self, client, google, ana):
        """Google's `email_verified` decides; an unproven address must not open Ana's account."""
        response, _, _ = _sign_in_with_google(client, _claims(STRANGER_UID, ana.email, verified=False))

        assert response.status_code == 302
        assert _query(response.url)["code"] == "google_no_account"
        assert _signed_in_user_id(client) is None
        assert not SocialAccount.objects.exists()

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
        assert response.url == "/login?next=/hub-login/%3Fhub%3Da%26next%3D/sales/"
        assert _signed_in_user_id(client) is None

    def test_cancelling_without_next_goes_back_to_the_sign_in(self, client, google):
        state = _query(_start(client)["Location"])["state"]

        response = client.get(GOOGLE_CALLBACK, {"state": state, "error": "access_denied"}, HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (302, "/login")

    def test_allauths_cancelled_page_is_the_vue_one(self, client, google):
        response = client.get(reverse("socialaccount_login_cancelled"), HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (302, "/login/error?code=login_cancelled")

    def test_allauths_error_page_is_the_vue_one(self, client, google):
        response = client.get(reverse("socialaccount_login_error"), HTTP_HOST=HOST)

        assert (response.status_code, response.url) == (302, "/login/error?code=authentication_error")

    def test_an_error_at_google_lands_on_the_vue_page_keeping_next(self, client, google):
        state = _query(_start(client, "/launch")["Location"])["state"]

        response = client.get(GOOGLE_CALLBACK, {"state": state, "error": "server_error"}, HTTP_HOST=HOST)

        assert response.status_code == 302
        assert response.url == "/login/error?code=authentication_error&next=/launch"
        assert _signed_in_user_id(client) is None
