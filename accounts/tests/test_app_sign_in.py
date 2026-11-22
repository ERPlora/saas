"""«Continue with Google» in the installed app (ACCOUNTS-F06): Google in the device's browser, the session back in the app.

Google refuses to sign anybody in inside an embedded web view, and a web view does not see the device's Google
accounts. So the app signs in the way native apps do (OAuth for native apps, with PKCE): its window keeps the
challenge of a secret only the app knows (``/auth/app/start/``), the device's browser goes through Google
(``/auth/app/google/``) and gets a one-time code bound to that challenge (``/auth/app/done/``), which comes back
to the app as ``erplora://signed-in?code=…``. The window spends it with the secret (``/auth/app/finish/``) and
holds the session.

Two clients play the two sides on one device: ``window`` is the app's web view, ``browser`` the system browser.
"""

import base64
import hashlib
import re
import secrets
from datetime import timedelta
from html import unescape
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from accounts.models import AuthExchangeCode
from accounts.services import hub_jump
from accounts.tests.conftest import HOST
from accounts.tests.test_google import ANA_UID, GOOGLE_CALLBACK, _claims, _google_answers, _query
from base.tests.test_locale import spanish
from public.tests.template_messages import template_messages

pytestmark = pytest.mark.django_db

START = "/auth/app/start/"
GOOGLE = "/auth/app/google/"
DONE = "/auth/app/done/"
FINISH = "/auth/app/finish/"
PROVIDER_REDIRECT = "/_allauth/browser/v1/auth/provider/redirect"
REFUSED = "/login/error?code=authentication_error"
LAUNCHER = "/launch"
APP_RETURN = "erplora://signed-in"


def challenge_of(verifier: str) -> str:
    """RFC 7636 ``S256``: BASE64URL without padding of the verifier's SHA-256."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def verifier():
    return secrets.token_urlsafe(32)


@pytest.fixture
def window():
    return Client(HTTP_HOST=HOST)


@pytest.fixture
def browser():
    """The device's browser: Django's CSRF checked as in production."""
    return Client(enforce_csrf_checks=True, HTTP_HOST=HOST)


def _form(response) -> tuple[str, dict]:
    html = response.content.decode()
    action = re.search(r'<form[^>]* action="([^"]*)"', html)
    assert action, "no form in the page"
    fields = {name: unescape(value) for name, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html)}
    return unescape(action.group(1)), fields


def _app_link(response) -> str:
    match = re.search(r'href="(erplora://[^"]+)"', response.content.decode())
    assert match, "no link back to the app in the page"
    return unescape(match.group(1))


def _code_of(app_link: str) -> str:
    return parse_qs(urlsplit(app_link).query)["code"][0]


def _through_google(browser, challenge: str, claims: dict):
    """The browser's leg up to Google's way back: our page, its form, Google's consent (skipped)."""
    action, fields = _form(browser.get(GOOGLE, {"challenge": challenge}))
    authorization = _query(browser.post(action, fields)["Location"])
    with _google_answers(claims):
        return browser.get(GOOGLE_CALLBACK, {"state": authorization["state"], "code": "4/the-code"})


def _code_for(browser, user, challenge: str) -> str:
    browser.force_login(user)
    return _code_of(_app_link(browser.get(DONE, {"challenge": challenge})))


def _signed_in(client) -> str | None:
    return client.session.get("_auth_user_id")


class TestTheWindowStarts:
    def test_it_keeps_the_challenge_and_goes_to_the_browsers_leg(self, window, verifier):
        challenge = challenge_of(verifier)

        response = window.get(START, {"challenge": challenge})

        assert (response.status_code, response.url) == (302, f"{GOOGLE}?{urlencode({'challenge': challenge})}")

    @pytest.mark.parametrize(
        "challenge",
        ["", "short", "a" * 42, "a" * 44, "a" * 42 + "=", "a" * 42 + "+", "a" * 42 + "/"],
    )
    def test_what_is_no_s256_challenge_is_refused(self, window, challenge):
        response = window.get(START, {"challenge": challenge})

        assert (response.status_code, response.url) == (302, REFUSED)


class TestTheBrowsersLeg:
    def test_without_google_configured_it_is_not_served(self, browser, verifier):
        assert browser.get(GOOGLE, {"challenge": challenge_of(verifier)}).status_code == 404

    def test_it_posts_googles_sign_in_with_the_way_back_to_the_code(self, browser, google, verifier):
        challenge = challenge_of(verifier)

        response = browser.get(GOOGLE, {"challenge": challenge})

        assert response.status_code == 200
        action, fields = _form(response)
        assert action == PROVIDER_REDIRECT
        assert fields["provider"] == "google"
        assert fields["process"] == "login"
        assert fields["callback_url"] == f"{DONE}?{urlencode({'challenge': challenge})}"
        assert fields["csrfmiddlewaretoken"]

    def test_the_form_sends_itself_with_the_pages_nonce(self, browser, google, verifier):
        response = browser.get(GOOGLE, {"challenge": challenge_of(verifier)})

        nonce = re.search(r"'nonce-([^']+)'", response["Content-Security-Policy"]).group(1)
        assert f'<script nonce="{nonce}">' in response.content.decode()

    def test_a_broken_challenge_never_leaves_for_google(self, browser, google):
        response = browser.get(GOOGLE, {"challenge": "short"})

        assert (response.status_code, response.url) == (302, REFUSED)

    def test_google_comes_back_to_the_code_signed_in(self, browser, google, ana, verifier):
        challenge = challenge_of(verifier)

        back = _through_google(browser, challenge, _claims(ANA_UID, ana.email))

        assert (back.status_code, back.url) == (302, f"{DONE}?{urlencode({'challenge': challenge})}")
        assert _signed_in(browser) == str(ana.pk)


class TestTheCode:
    def test_signed_in_the_page_opens_the_app_with_a_one_time_code(self, browser, ana, verifier):
        browser.force_login(ana)

        response = browser.get(DONE, {"challenge": challenge_of(verifier)})

        assert response.status_code == 200
        link = _app_link(response)
        assert link.startswith(f"{APP_RETURN}?code=")
        row = AuthExchangeCode.objects.get(user=ana)
        assert row.audience == "app-session"
        assert row.used_at is None
        assert row.expires_at == row.created_at + timedelta(seconds=60)
        assert _code_of(link) not in row.code_hash

    def test_the_page_tries_to_open_the_app_by_itself(self, browser, ana, verifier):
        browser.force_login(ana)

        response = browser.get(DONE, {"challenge": challenge_of(verifier)})

        nonce = re.search(r"'nonce-([^']+)'", response["Content-Security-Policy"]).group(1)
        assert f'<script nonce="{nonce}">' in response.content.decode()

    def test_the_code_hands_nobody_its_address(self, browser, ana, verifier):
        browser.force_login(ana)

        response = browser.get(DONE, {"challenge": challenge_of(verifier)})

        assert response["Referrer-Policy"] == "no-referrer"
        assert "no-store" in response["Cache-Control"]

    def test_without_a_session_it_signs_in_first_and_comes_back(self, browser, verifier):
        path = f"{DONE}?{urlencode({'challenge': challenge_of(verifier)})}"

        response = browser.get(path)

        assert (response.status_code, response.url) == (302, f"{LAUNCHER}?next={quote(path, safe='/')}")
        assert not AuthExchangeCode.objects.exists()

    def test_an_error_of_the_sign_in_mints_no_code(self, browser, ana, verifier):
        browser.force_login(ana)

        response = browser.get(DONE, {"challenge": challenge_of(verifier), "error": "unknown"})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert not AuthExchangeCode.objects.exists()

    def test_a_broken_challenge_mints_no_code(self, browser, ana):
        browser.force_login(ana)

        response = browser.get(DONE, {"challenge": "short"})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert not AuthExchangeCode.objects.exists()


class TestTheWindowFinishes:
    def test_the_whole_round_trip_signs_the_window_in(self, window, browser, google, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge, "next": "/shell/"})
        back = _through_google(browser, challenge, _claims(ANA_UID, ana.email))
        code = _code_of(_app_link(browser.get(back.url)))

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert (response.status_code, response.url) == (302, "/shell/")
        assert _signed_in(window) == str(ana.pk)
        assert response["Referrer-Policy"] == "no-referrer"

    def test_without_next_it_lands_on_the_launcher(self, window, browser, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge})
        code = _code_for(browser, ana, challenge)

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert response.url == LAUNCHER
        assert _signed_in(window) == str(ana.pk)

    def test_a_next_on_another_site_lands_on_this_one(self, window, browser, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge, "next": "https://evil.example/steal"})
        code = _code_for(browser, ana, challenge)

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert response.url == "/"

    def test_the_code_opens_one_session_only(self, window, browser, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge})
        code = _code_for(browser, ana, challenge)
        window.get(FINISH, {"code": code, "verifier": verifier})
        again = Client(HTTP_HOST=HOST)
        again.get(START, {"challenge": challenge})

        response = again.get(FINISH, {"code": code, "verifier": verifier})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert _signed_in(again) is None

    def test_a_code_caught_on_its_way_back_opens_nothing_without_the_apps_secret(self, window, browser, ana, verifier):
        """Another app may claim ``erplora://`` and catch the code: the challenge is public, the secret is not."""
        challenge = challenge_of(verifier)
        code = _code_for(browser, ana, challenge)
        thief = Client(HTTP_HOST=HOST)
        thief.get(START, {"challenge": challenge})

        response = thief.get(FINISH, {"code": code, "verifier": secrets.token_urlsafe(32)})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert _signed_in(thief) is None
        assert AuthExchangeCode.objects.get(user=ana).used_at is None

    def test_a_link_with_someone_elses_code_signs_no_window_in(self, window, browser, ana, verifier):
        """Login CSRF: a link to finish with a code and secret of the attacker's own, in a window that started nothing."""
        code = _code_for(browser, ana, challenge_of(verifier))

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert _signed_in(window) is None

    def test_the_window_gets_one_try_per_start(self, window, browser, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge})
        code = _code_for(browser, ana, challenge)
        window.get(FINISH, {"code": "not-the-code", "verifier": verifier})

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert _signed_in(window) is None

    def test_an_expired_code_opens_nothing(self, window, browser, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge})
        code = _code_for(browser, ana, challenge)
        AuthExchangeCode.objects.filter(user=ana).update(expires_at=timezone.now() - timedelta(seconds=1))

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert _signed_in(window) is None

    def test_an_account_closed_meanwhile_is_not_signed_in(self, window, browser, ana, verifier):
        challenge = challenge_of(verifier)
        window.get(START, {"challenge": challenge})
        code = _code_for(browser, ana, challenge)
        get_user_model().objects.filter(pk=ana.pk).update(is_active=False)

        response = window.get(FINISH, {"code": code, "verifier": verifier})

        assert (response.status_code, response.url) == (302, REFUSED)
        assert _signed_in(window) is None

    def test_no_jump_to_a_hub_spends_it(self, browser, ana, verifier):
        code = _code_for(browser, ana, challenge_of(verifier))

        with pytest.raises(hub_jump.InvalidCode):
            hub_jump.redeem_code(code, "a")
        assert AuthExchangeCode.objects.get(user=ana).used_at is None


@pytest.mark.parametrize("name", ["app_sign_in_google.html", "app_sign_in_done.html"])
def test_every_message_of_its_pages_has_its_spanish_translation(name):
    template = settings.BASE_DIR / "accounts" / "templates" / "accounts" / name
    catalog = spanish()

    assert [message for message in template_messages(template) if not catalog.gettext(message)] == []
