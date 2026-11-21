"""Second factor of saas-next: TOTP and recovery codes (``allauth.mfa``), behind ``ACCOUNTS_MFA_ENABLED``.

``allauth.mfa`` is always installed (its table always exists); the flag decides whether it is in use.
Off (the default): no login asks for a code, not even for an account with a TOTP row, and
the 2FA endpoints answer 404 (JSON under ``/_allauth/``, which is how the Vue pages know). On: an
account with an authenticator app is asked for the app's code after the password and the code mailed
at every sign-in (or after Google), the jump to a hub needs that second factor in the session if the
account has one and the staff's jump to the Hub admin (``hub-admin``) always needs it. Either way
``/admin/login/`` hands over to allauth's login (the launcher's).

A «wrong» code is chosen so it cannot be the live one.
"""

import asyncio
import json
import time
from datetime import timedelta
from io import StringIO

import pytest
from allauth.account import app_settings as account_settings
from allauth.account.authentication import get_authentication_records
from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from accounts import mfa
from accounts.models import AuthExchangeCode
from accounts.services import hub_jump, platform_staff
from accounts.tests.conftest import BROWSER, HOST, SESSION, _activate_totp, prove_address
from accounts.tests.mfa_steps import (
    AUTHENTICATE,
    FOURTEEN_DAYS,
    HUB_LOGIN,
    TRUST,
    TRUST_COOKIE,
    _code_at,
    _counter,
    _first_factors,
    _hidden,
    _live_code,
    _pending_flows,
    _post,
    _second_step,
    _sign_in,
    _trust_cookie,
)

pytestmark = pytest.mark.django_db

REAUTHENTICATE = f"{BROWSER}/auth/2fa/reauthenticate"
AUTHENTICATORS = f"{BROWSER}/account/authenticators"
#: Where ``/hub-login/?hub=a&next=/demo/items`` sends a session that owes its second factor: the Vue
#: page asks for a code of the app (``method=totp``) and offers no other way (``flows``).
REAUTHENTICATE_FOR_THE_JUMP = (
    "/reauthenticate?method=totp&flows=mfa_reauthenticate&next=/hub-login/%3Fhub%3Da%26next%3D/demo/items"
)
#: «Open in the Hub admin» starts at the Hub, which sends the browser here with its ``state``.
JUMP = "/hub-login/?hub={slug}&audience=hub-admin&next=/admin/hub/{slug}/&state=a-state"
#: «Hubs»: the page «Open in the Hub admin» starts from, where a refused jump comes back.
CHANGELIST = "/admin/accounts/hubs/"
REFUSED_JUMP = "Turn on two-factor authentication and sign in again before opening the Hub admin."


def _wrong_code(secret: str) -> str:
    """A six-digit code the authenticator rejects now and for the next periods the test may still run in.

    Never a fixed literal: ``"000000"`` is the live code once every million periods.
    """
    live = {_code_at(secret, _counter() + n) for n in range(-3, 4)}
    return next(code for code in (str(digit) * 6 for digit in range(10)) if code not in live)


@pytest.fixture
def ana(ana):
    """Ana once she proved her address, as every account does before its first session: her sign-ins
    here stop at the second factor alone."""
    prove_address(ana.email)
    return ana


def _request(user, records):
    request = RequestFactory().get("/")
    request.user = user
    request.session = {"account_authentication_methods": records}
    return request


def _mfa_record(authenticator):
    return {"method": "mfa", "at": time.time(), "id": authenticator.pk, "type": authenticator.type}


@pytest.fixture
def platform():
    """The platform administrator of ``demo_seed`` (superuser, member of no hub): password ``platform``."""
    # demo_seed runs only with DEBUG on (local development); pytest-django turns it off.
    with override_settings(DEBUG=True):
        call_command("demo_seed", stdout=StringIO())
    return get_user_model().objects.get(email="platform@example.com")


PASSWORD_RECORD = {"method": "password", "at": 0.0, "email": "ana@example.com"}


class TestSettings:
    def test_allauth_mfa_is_installed_whatever_the_flag(self):
        assert "allauth.mfa" in django_settings.INSTALLED_APPS

    def test_totp_and_recovery_codes_only_without_passkeys(self):
        assert django_settings.MFA_SUPPORTED_TYPES == ["totp", "recovery_codes"]
        assert django_settings.MFA_PASSKEY_LOGIN_ENABLED is False

    def test_the_authenticator_app_shows_erplora(self):
        assert django_settings.MFA_TOTP_ISSUER == "ERPlora"

    def test_one_period_of_clock_drift_is_accepted_as_in_todays_saas(self):
        assert django_settings.MFA_TOTP_TOLERANCE == 1

    def test_our_adapter_decides_when_the_second_factor_applies(self):
        assert django_settings.MFA_ADAPTER == "accounts.mfa.MFAAdapter"

    def test_the_second_factor_is_off_by_default_in_phase_1(self):
        assert django_settings.ACCOUNTS_MFA_ENABLED is False

    def test_the_flag_middleware_is_installed(self):
        assert "accounts.mfa.MFAFlagMiddleware" in django_settings.MIDDLEWARE

    def test_a_browser_is_trusted_for_14_days_and_only_by_erplora_com(self, settings):
        """ACCOUNTS-F05: «Trust this browser», allauth's own: a signed cookie, never sent to the businesses'
        subdomains even if the session cookie one day is."""
        settings.SESSION_COOKIE_DOMAIN = ".erplora.com"

        assert mfa_settings.TRUST_ENABLED is True
        assert mfa_settings.TRUST_COOKIE_AGE == timedelta(days=14)
        assert mfa_settings.TRUST_COOKIE_DOMAIN is None
        assert mfa_settings.TRUST_COOKIE_HTTPONLY is True
        # Not the mailed code: only the app's is skipped (the code by mail asks every sign-in, ACCOUNTS-F04).
        assert account_settings.LOGIN_BY_CODE_TRUST_ENABLED is False

    def test_the_authenticator_table_exists(self):
        assert Authenticator.objects.count() == 0


class TestAdapter:
    """``MFAAdapter.is_mfa_enabled`` is what allauth's login stage asks before it wants a code."""

    def test_with_the_flag_off_no_account_has_the_second_factor_even_with_an_authenticator(self, ana, secret):
        assert isinstance(get_mfa_adapter(), mfa.MFAAdapter)
        assert is_mfa_enabled(ana) is False
        assert is_mfa_enabled(ana, [Authenticator.Type.TOTP]) is False

    def test_with_the_flag_on_an_account_with_an_authenticator_has_it(self, mfa_on, ana, secret):
        assert is_mfa_enabled(ana) is True
        assert is_mfa_enabled(ana, [Authenticator.Type.TOTP]) is True

    def test_with_the_flag_on_an_account_without_an_authenticator_has_not(self, mfa_on, ana):
        assert is_mfa_enabled(ana) is False


class TestFlagMiddleware:
    """With the flag off the 2FA endpoints do not exist; with it on the middleware is transparent."""

    HEADLESS_PATHS = [
        AUTHENTICATORS,
        f"{AUTHENTICATORS}/totp",
        f"{AUTHENTICATORS}/recovery-codes",
        AUTHENTICATE,
        REAUTHENTICATE,
        TRUST,
    ]

    @pytest.mark.parametrize("path", HEADLESS_PATHS)
    def test_with_the_flag_off_the_headless_endpoints_answer_a_json_404(self, client, ana, path):
        # JSON, not Django's HTML 404: the SDK of the Vue pages reads it as «2FA is off».
        client.force_login(ana)

        for response in (client.get(path, HTTP_HOST=HOST), client.post(path, {}, HTTP_HOST=HOST)):
            assert response.status_code == 404
            assert response["Content-Type"] == "application/json"
            assert response.json() == {"status": 404}

    def test_with_the_flag_off_the_rest_of_allauth_is_untouched(self, client):
        assert client.get(SESSION, HTTP_HOST=HOST).status_code == 401
        assert client.get(f"{BROWSER}/config", HTTP_HOST=HOST).status_code == 200

    def test_under_asgi_too(self):
        """daphne runs the middleware chain asynchronously."""

        async def view(request):
            return HttpResponse("through")

        middleware = mfa.MFAFlagMiddleware(view)
        refused = asyncio.run(middleware(RequestFactory().get(AUTHENTICATORS)))
        through = asyncio.run(middleware(RequestFactory().get(SESSION)))

        assert (refused.status_code, json.loads(refused.content)) == (404, {"status": 404})
        assert through.content == b"through"

    def test_with_the_flag_on_the_endpoints_answer(self, mfa_on, client, ana, secret):
        client.force_login(ana)

        response = client.get(AUTHENTICATORS, HTTP_HOST=HOST)

        assert response.status_code == 200
        assert [item["type"] for item in response.json()["data"]] == ["totp"]

    @pytest.mark.usefixtures("spa_manifest")
    @pytest.mark.parametrize("path", ["/accounts/2fa/", "/accounts/2fa/authenticate/", "/accounts/2fa/reauthenticate/"])
    def test_with_the_flag_on_allauths_template_pages_still_do_not_exist(self, mfa_on, client, ana, secret, path):
        """Headless only: the Vue pages /2fa, /2fa/authenticate and /reauthenticate are the only ones."""
        client.force_login(ana)

        assert client.get(path, HTTP_HOST=HOST).status_code == 404

    def test_with_the_flag_on_an_account_without_an_authenticator_gets_the_secret_to_set_it_up(
        self, mfa_on, client, ana
    ):
        client.force_login(ana)

        response = client.get(f"{AUTHENTICATORS}/totp", HTTP_HOST=HOST)

        assert response.status_code == 404
        meta = response.json()["meta"]
        assert meta["secret"]
        assert meta["totp_url"].startswith("otpauth://totp/ana%40example.com?")
        assert "issuer=ERPlora" in meta["totp_url"]


class TestMfaCompleted:
    """«MFA completed»: an authenticator app, and a code of this account given in this session."""

    def test_a_code_given_in_this_session_completes_it(self, ana, secret):
        totp = Authenticator.objects.get(user=ana, type=Authenticator.Type.TOTP)

        assert mfa.mfa_completed(_request(ana, [PASSWORD_RECORD, _mfa_record(totp)])) is True

    def test_a_recovery_code_given_in_this_session_completes_it(self, ana, secret):
        codes = RecoveryCodes.activate(ana).instance

        assert mfa.mfa_completed(_request(ana, [PASSWORD_RECORD, _mfa_record(codes)])) is True

    def test_the_password_alone_does_not(self, ana, secret):
        assert mfa.mfa_completed(_request(ana, [PASSWORD_RECORD])) is False

    def test_a_session_with_no_records_does_not(self, ana, secret):
        assert mfa.mfa_completed(_request(ana, [])) is False

    def test_without_an_authenticator_app_nothing_is_completed(self, ana):
        codes = RecoveryCodes.activate(ana).instance

        assert mfa.mfa_completed(_request(ana, [PASSWORD_RECORD, _mfa_record(codes)])) is False

    def test_a_code_of_another_account_does_not_count(self, ana, secret, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _activate_totp(bo)
        theirs = Authenticator.objects.get(user=bo, type=Authenticator.Type.TOTP)

        assert mfa.mfa_completed(_request(ana, [PASSWORD_RECORD, _mfa_record(theirs)])) is False

    def test_an_anonymous_visitor_has_not_completed_it(self):
        assert mfa.mfa_completed(_request(AnonymousUser(), [])) is False

    def test_a_browser_the_account_trusts_completes_it(self, ana, secret):
        """ACCOUNTS-F05: the trust was given right after a good code in this browser, so its sign-in skipped the code;
        the jump to a business must not ask for it again (the trust would be worth nothing)."""
        request = _request(ana, [PASSWORD_RECORD])
        request.COOKIES[TRUST_COOKIE] = _trust_cookie(ana)

        assert mfa.mfa_completed(request) is True

    def test_a_trust_given_before_a_new_password_does_not(self, ana, secret, password):
        cookie = _trust_cookie(ana)
        ana.set_password(f"{password}-new")
        ana.save()
        request = _request(ana, [PASSWORD_RECORD])
        request.COOKIES[TRUST_COOKIE] = cookie

        assert mfa.mfa_completed(request) is False

    def test_a_trust_older_than_14_days_does_not(self, ana, secret):
        request = _request(ana, [PASSWORD_RECORD])
        request.COOKIES[TRUST_COOKIE] = _trust_cookie(ana, age=FOURTEEN_DAYS + 1)

        assert mfa.mfa_completed(request) is False

    def test_the_trust_of_another_account_does_not(self, ana, secret, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _activate_totp(bo)
        request = _request(ana, [PASSWORD_RECORD])
        request.COOKIES[TRUST_COOKIE] = _trust_cookie(bo)

        assert mfa.mfa_completed(request) is False

    def test_it_reads_allauths_records_of_the_session(self, ana, secret):
        request = _request(ana, [PASSWORD_RECORD])

        assert get_authentication_records(request) == [PASSWORD_RECORD]


class TestLoginWithTheFlagOn:
    """The app's code comes after the password and the code mailed to the account, in allauth's order of stages."""

    def test_an_account_with_an_authenticator_app_is_asked_for_its_code_and_not_signed_in_yet(
        self, mfa_on, browser, ana, secret, password
    ):
        response = _first_factors(browser, "ana@example.com", password)

        assert response.status_code == 401
        assert response.json()["meta"]["is_authenticated"] is False
        assert _pending_flows(response) == ["mfa_authenticate"]
        assert browser.get(SESSION).status_code == 401

    def test_the_code_of_the_app_completes_the_login(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, "ana@example.com", password)

        response = _second_step(browser, _live_code(secret))

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True
        session = browser.get(SESSION).json()
        assert session["data"]["user"]["email"] == "ana@example.com"
        assert [method["method"] for method in session["data"]["methods"]] == ["password", "code", "mfa"]

    def test_a_wrong_code_is_400_and_leaves_the_login_at_the_code_step(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, "ana@example.com", password)

        response = _post(browser, AUTHENTICATE, {"code": _wrong_code(secret)})

        assert response.status_code == 400
        [error] = response.json()["errors"]
        assert (error["param"], error["code"]) == ("code", "incorrect_code")
        session = browser.get(SESSION)
        assert session.status_code == 401
        assert _pending_flows(session) == ["mfa_authenticate"]

    def test_a_recovery_code_also_completes_the_login(self, mfa_on, browser, ana, secret, password):
        recovery_code = RecoveryCodes.activate(ana).get_unused_codes()[0]
        _sign_in(browser, "ana@example.com", password)

        response = _second_step(browser, recovery_code)

        assert response.status_code == 200
        assert recovery_code not in RecoveryCodes.activate(ana).get_unused_codes()

    def test_an_account_without_an_authenticator_app_is_never_asked(self, mfa_on, browser, ana, password):
        RecoveryCodes.activate(ana)

        response = _first_factors(browser, "ana@example.com", password)

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True

    def test_the_staff_get_no_exception_either(self, mfa_on, browser, platform):
        _activate_totp(platform)

        response = _first_factors(browser, "platform@example.com", "platform")

        assert response.status_code == 401
        assert _pending_flows(response) == ["mfa_authenticate"]


class TestLoginWithTheFlagOff:
    def test_an_account_with_an_authenticator_app_signs_in_without_the_apps_code(
        self, browser, ana, secret, password
    ):
        # The default: a TOTP row kept from a time the flag was on asks for nothing more than the
        # password and the mailed code.
        response = _first_factors(browser, "ana@example.com", password)

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True
        assert _pending_flows(response) == []


class TestIssueCode:
    """``hub_jump.issue_code(…, second_factor=mfa.mfa_completed(request))``: only with the flag on."""

    def test_hub_admin_needs_the_second_factor(self, mfa_on, platform):
        with pytest.raises(hub_jump.SecondFactorRequired):
            hub_jump.issue_code(platform, "a", audience=AuthExchangeCode.HUB_ADMIN_AUDIENCE)

        assert not AuthExchangeCode.objects.exists()

    def test_hub_admin_with_the_second_factor_gets_its_code(self, mfa_on, platform):
        _activate_totp(platform)

        hub_jump.issue_code(platform, "a", audience=AuthExchangeCode.HUB_ADMIN_AUDIENCE, second_factor=True)

        assert AuthExchangeCode.objects.get().audience == "hub-admin"

    def test_a_member_with_an_authenticator_app_needs_the_second_factor(self, mfa_on, member, secret):
        with pytest.raises(hub_jump.SecondFactorRequired):
            hub_jump.issue_code(member, "a")

        assert not AuthExchangeCode.objects.exists()
        hub_jump.issue_code(member, "a", second_factor=True)
        assert AuthExchangeCode.objects.count() == 1

    def test_a_member_without_an_authenticator_app_jumps_as_today(self, mfa_on, member):
        hub_jump.issue_code(member, "a")

        assert AuthExchangeCode.objects.count() == 1

    def test_a_stranger_is_refused_as_a_stranger_before_any_second_factor(self, mfa_on, ana, secret):
        with pytest.raises(hub_jump.HubAccessDenied) as refused:
            hub_jump.issue_code(ana, "a")

        assert not isinstance(refused.value, hub_jump.SecondFactorRequired)

    def test_a_missing_second_factor_is_an_access_denied_for_callers_that_do_not_know_it(self):
        assert issubclass(hub_jump.SecondFactorRequired, hub_jump.HubAccessDenied)

    def test_with_the_flag_off_nothing_changes(self, platform, member, secret):
        hub_jump.issue_code(platform, "a", audience=AuthExchangeCode.HUB_ADMIN_AUDIENCE)
        hub_jump.issue_code(member, "a")

        assert AuthExchangeCode.objects.count() == 2


class TestHubLoginWithTheFlagOn:
    """``/hub-login/`` mints a code only once the session holds the account's second factor."""

    def test_while_the_code_is_pending_the_jump_waits_for_the_login(self, mfa_on, browser, member, secret, password):
        _sign_in(browser, "ana@example.com", password)

        response = browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items")

        assert response.status_code == 302
        assert response.url.startswith("/launch?next=")
        assert not AuthExchangeCode.objects.exists()

    def test_after_the_code_the_member_jumps(self, mfa_on, browser, member, secret, password):
        _sign_in(browser, "ana@example.com", password)
        _second_step(browser, _live_code(secret))

        response = browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items")

        assert response.status_code == 200
        code = _hidden(response.content.decode(), "code")
        assert AuthExchangeCode.objects.get().code_hash == AuthExchangeCode.hash_code(code)

    def test_a_session_without_the_code_is_sent_to_reauthenticate_and_back(self, mfa_on, client, member, secret):
        # Django's own login (``/admin/login/`` before the flag, ``force_login``) records no code.
        client.force_login(member)

        response = client.get(f"{HUB_LOGIN}?hub=a&next=/demo/items")

        assert response.status_code == 302
        assert response.url == REAUTHENTICATE_FOR_THE_JUMP
        assert not AuthExchangeCode.objects.exists()

    def test_reauthenticating_with_the_code_opens_the_jump(self, mfa_on, browser, member, secret):
        browser.force_login(member)

        response = _post(browser, REAUTHENTICATE, {"code": _live_code(secret)})

        assert response.status_code == 200
        assert browser.get(f"{HUB_LOGIN}?hub=a&next=/").status_code == 200
        assert AuthExchangeCode.objects.count() == 1

    def test_a_wrong_code_does_not_open_it(self, mfa_on, browser, member, secret):
        browser.force_login(member)

        assert _post(browser, REAUTHENTICATE, {"code": _wrong_code(secret)}).status_code == 400
        assert browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items").url == REAUTHENTICATE_FOR_THE_JUMP
        assert not AuthExchangeCode.objects.exists()

    def test_reauthenticating_with_the_password_alone_does_not_open_it(self, mfa_on, browser, member, secret, password):
        # Regression: a password reauthentication records `method == "password"`, never `mfa`, so the
        # page must ask for the code; sent without a method it started on the password and looped.
        browser.force_login(member)

        assert _post(browser, f"{BROWSER}/auth/reauthenticate", {"password": password}).status_code == 200
        assert browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items").url == REAUTHENTICATE_FOR_THE_JUMP
        assert not AuthExchangeCode.objects.exists()

        assert _post(browser, REAUTHENTICATE, {"code": _live_code(secret)}).status_code == 200
        assert browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items").status_code == 200
        assert AuthExchangeCode.objects.count() == 1

    def test_a_member_without_an_authenticator_app_jumps_as_today(self, mfa_on, client, member):
        client.force_login(member)

        assert client.get(HUB_LOGIN, {"hub": "a", "next": "/"}).status_code == 200

    def test_a_stranger_is_told_they_are_no_member(self, mfa_on, client, ana, secret):
        client.force_login(ana)

        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/"})

        assert response.url == "/login/error?code=not_a_member&hub=a"


class TestHubLoginWithTheFlagOff:
    def test_a_member_with_an_authenticator_app_jumps_without_the_code(self, client, member, secret):
        client.force_login(member)

        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/"})

        assert response.status_code == 200
        assert AuthExchangeCode.objects.count() == 1


class TestOpenInTheHubAdminWithTheFlagOn:
    """The staff's jump to the Hub admin (``hub-admin``) always needs the second factor in the session."""

    def test_staff_without_an_authenticator_app_are_sent_back_with_a_message(self, mfa_on, client, platform):
        client.force_login(platform)

        response = client.get(JUMP.format(slug="a"))

        assert response.status_code == 302
        assert response.url == CHANGELIST
        assert not AuthExchangeCode.objects.exists()
        # The admin itself needs the app (ACCOUNTS-F20): set up on /2fa, the staff come back to the message.
        assert client.get(CHANGELIST).url == f"/admin/login/?next={CHANGELIST}"
        _activate_totp(platform)
        assert REFUSED_JUMP in client.get(CHANGELIST).content.decode()

    def test_staff_with_an_app_but_no_code_in_this_session_are_sent_back(self, mfa_on, client, platform):
        _activate_totp(platform)
        client.force_login(platform)

        response = client.get(JUMP.format(slug="a"))

        assert (response.status_code, response.url) == (302, CHANGELIST)
        assert not AuthExchangeCode.objects.exists()

    def test_staff_who_signed_in_with_the_code_jump(self, mfa_on, browser, platform):
        secret = _activate_totp(platform)
        _sign_in(browser, "platform@example.com", "platform")
        _second_step(browser, _live_code(secret))

        response = browser.get(JUMP.format(slug="a"))

        assert response.status_code == 200
        assert _hidden(response.content.decode(), "next") == "/admin/hub/a/"
        assert _hidden(response.content.decode(), "state") == "a-state"
        assert AuthExchangeCode.objects.get().audience == "hub-admin"

    def test_the_message_is_translated_to_spanish(self, mfa_on, client, platform):
        client.force_login(platform)

        # A message is stored as text in the language of the request that adds it.
        client.get(JUMP.format(slug="a"), headers={"Accept-Language": "es"})
        _activate_totp(platform)
        html = client.get(CHANGELIST, headers={"Accept-Language": "es"}).content.decode()

        assert "Activa la verificación en dos pasos y vuelve a iniciar sesión antes de abrir el admin del Hub." in html

    def test_a_reserved_slug_is_still_refused(self, mfa_on, client, platform):
        client.force_login(platform)

        assert client.get(JUMP.format(slug="hubs")).url == "/login/error?code=invalid_hub"
        assert not AuthExchangeCode.objects.exists()


class TestAdminLoginWithTheFlagOn:
    """Django's admin login skips allauth's stages (no code),
    so every way into the admin is the SaaS's sign-in (the launcher's, ``/launch``, allauth.headless)."""

    def test_it_hands_over_to_the_sign_in_keeping_where_the_staff_were_going(self, mfa_on, client):
        response = client.get("/admin/login/", {"next": "/admin/accounts/user/"})

        assert response.status_code == 302
        assert response.url == "/launch?next=/admin/accounts/user/"

    def test_without_next_it_comes_back_to_the_admin_index(self, mfa_on, client):
        assert client.get("/admin/login/").url == "/launch?next=/admin/"

    @pytest.mark.usefixtures("spa_manifest")
    def test_the_admin_sends_a_visitor_through_it(self, mfa_on, client):
        response = client.get("/admin/", follow=True)

        assert [url for url, _ in response.redirect_chain] == [
            "/admin/login/?next=/admin/",
            "/launch?next=/admin/",
        ]

    @pytest.mark.parametrize("next_url", ["https://evil.example/", "//evil.example/x", "/admin/login/"])
    def test_a_next_elsewhere_or_back_to_itself_becomes_the_index(self, mfa_on, client, next_url):
        assert client.get("/admin/login/", {"next": next_url}).url == "/launch?next=/admin/"

    def test_posting_the_password_to_it_signs_nobody_in(self, mfa_on, client, platform):
        response = client.post("/admin/login/", {"username": "platform@example.com", "password": "platform"})

        assert response.status_code == 302
        assert response.url == "/launch?next=/admin/"
        assert client.get("/admin/").status_code == 302

    def test_signed_in_staff_go_where_they_were_going(self, mfa_on, client, platform):
        _activate_totp(platform)
        client.force_login(platform)

        response = client.get("/admin/login/", {"next": "/admin/accounts/user/"})

        assert (response.status_code, response.url) == (302, "/admin/accounts/user/")

    def test_a_signed_in_customer_is_forbidden_never_sent_to_the_login(self, mfa_on, client, member):
        # The sign-in sends a signed-in account straight to `next` (/admin/): it would loop.
        client.force_login(member)

        assert client.get("/admin/login/", {"next": "/admin/"}).status_code == 403

    def test_the_staff_reach_the_admin_with_their_password_and_their_code(self, mfa_on, browser, platform):
        """What /launch, /verify-email and /2fa/authenticate post (allauth.headless); then the page loads
        ``next``, /admin/."""
        secret = _activate_totp(platform)

        response = _first_factors(browser, "platform@example.com", "platform")
        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])
        assert browser.get("/admin/").status_code == 302

        response = _second_step(browser, _live_code(secret))

        assert response.status_code == 200
        assert browser.get("/admin/").status_code == 200

    def test_it_is_never_cached(self, mfa_on, client):
        assert "no-store" in client.get("/admin/login/")["Cache-Control"]


class TestTheAdminAsksTheStaffForTheApp:
    """With the second factor on, the staff enter the admin only with an authenticator app (the sign-in then asks its
    code, or a browser they trust skips it); without one, the admin takes them to set it up, keeping where they were
    going, never a 403. The account is what is checked: the code was asked at the sign-in."""

    def test_staff_without_the_app_are_taken_to_set_it_up_keeping_where_they_were_going(self, mfa_on, client, platform):
        client.force_login(platform)

        response = client.get("/admin/accounts/user/")
        assert (response.status_code, response.url) == (302, "/admin/login/?next=/admin/accounts/user/")
        response = client.get(response.url)

        assert (response.status_code, response.url) == (302, "/2fa?next=/admin/accounts/user/")

    def test_support_without_the_app_too(self, mfa_on, client, password):
        support, _ = platform_staff.create_platform_user("help@erplora.com", "support", password)
        client.force_login(support)

        assert client.get("/admin/login/", {"next": "/admin/"}).url == "/2fa?next=/admin/"
        assert client.get("/admin/").status_code == 302

    def test_the_hubs_page_too(self, mfa_on, client, platform):
        client.force_login(platform)

        response = client.get("/admin/accounts/hubs/")

        assert (response.status_code, response.url) == (302, "/admin/login/?next=/admin/accounts/hubs/")

    def test_staff_with_the_app_enter(self, mfa_on, client, platform):
        _activate_totp(platform)
        client.force_login(platform)

        assert client.get("/admin/").status_code == 200
        assert client.get("/admin/accounts/hubs/").status_code == 200

    def test_recovery_codes_alone_are_no_second_factor(self, mfa_on, client, platform):
        RecoveryCodes.activate(platform)
        client.force_login(platform)

        assert client.get("/admin/").status_code == 302

    def test_with_the_flag_off_staff_without_the_app_enter_as_today(self, client, platform):
        client.force_login(platform)

        assert client.get("/admin/").status_code == 200

    def test_a_customer_is_still_forbidden_never_sent_to_set_it_up(self, mfa_on, client, member):
        client.force_login(member)

        assert client.get("/admin/login/", {"next": "/admin/"}).status_code == 403


class TestAdminLoginWithTheFlagOff:
    """Without the authenticator app the admin's own login would still skip the code mailed at every
    sign-in (``test_sign_in_code``): it hands over to the SaaS's sign-in all the same."""

    def test_it_hands_over_to_the_sign_in_keeping_where_the_staff_were_going(self, client):
        response = client.get("/admin/login/", {"next": "/admin/accounts/user/"})

        assert (response.status_code, response.url) == (302, "/launch?next=/admin/accounts/user/")

    def test_posting_the_password_to_it_signs_nobody_in(self, client, platform):
        response = client.post("/admin/login/", {"username": "platform@example.com", "password": "platform"})

        assert (response.status_code, response.url) == (302, "/launch?next=/admin/")
        assert client.get("/admin/").status_code == 302

    def test_the_staff_reach_the_admin_with_their_password_and_the_mailed_code(self, browser, platform):
        response = _first_factors(browser, "platform@example.com", "platform")

        assert response.status_code == 200
        assert browser.get("/admin/").status_code == 200
