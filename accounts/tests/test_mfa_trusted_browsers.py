"""«Trust this browser for 14 days» after the authenticator app's code (``allauth.mfa``'s own trust, ACCOUNTS-F05), and
what Security → Two-factor authentication says and does about it (ACCOUNTS-F17), behind ``ACCOUNTS_MFA_ENABLED``."""

from datetime import datetime, timedelta

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal import auth as totp_auth
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from accounts.tests.conftest import HOST, SESSION, _activate_totp, prove_address
from accounts.tests.mfa_steps import (
    AUTHENTICATE,
    FOURTEEN_DAYS,
    HUB_LOGIN,
    TRUST,
    TRUST_COOKIE,
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


@pytest.fixture
def ana(ana):
    """Ana once she proved her address, as every account does before its first session: her sign-ins
    here stop at the second factor alone."""
    prove_address(ana.email)
    return ana


def _app_code(client, secret):
    """The app's code at the login's second step: the answer asks whether to trust this browser."""
    return _post(client, AUTHENTICATE, {"code": _live_code(secret)})


def _sign_out(client):
    response = client.delete(SESSION, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 401, response.content


class TestTrustThisBrowser:
    """ACCOUNTS-F05: after the app's code the login asks whether to trust this browser for 14 days; there, the next
    sign-ins skip the app's code (never the mailed one) until the password or the authenticator app changes."""

    def test_after_the_apps_code_the_login_waits_for_the_answer(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)

        response = _app_code(browser, secret)

        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_trust"])
        assert browser.get(SESSION).status_code == 401

    def test_trusting_signs_in_and_leaves_the_cookie_for_14_days(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)

        response = _post(browser, TRUST, {"trust": True})

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True
        cookie = response.cookies[TRUST_COOKIE]
        assert int(cookie["max-age"]) == FOURTEEN_DAYS
        assert (cookie["domain"], cookie["path"], cookie["httponly"]) == ("", "/", True)

    def test_not_now_signs_in_and_leaves_no_cookie(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)

        response = _post(browser, TRUST, {"trust": False})

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True
        assert TRUST_COOKIE not in response.cookies

    def test_a_trusted_browser_signs_in_with_the_password_and_the_mailed_code_only(
        self, mfa_on, browser, ana, secret, password
    ):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)
        _post(browser, TRUST, {"trust": True})
        _sign_out(browser)

        # _first_factors checks the mailed code is still asked first.
        response = _first_factors(browser, ana.email, password)

        assert response.status_code == 200
        assert response.json()["meta"]["is_authenticated"] is True

    def test_a_browser_left_untrusted_is_asked_again(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)
        _post(browser, TRUST, {"trust": False})
        _sign_out(browser)

        response = _first_factors(browser, ana.email, password)

        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])

    def test_another_browser_is_still_asked(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)
        _post(browser, TRUST, {"trust": True})
        other = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
        other.get(SESSION)

        response = _first_factors(other, ana.email, password)

        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])

    def test_a_new_password_ends_the_trust(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)
        _post(browser, TRUST, {"trust": True})
        _sign_out(browser)
        ana.set_password(f"{password}-new")
        ana.save()

        response = _first_factors(browser, ana.email, f"{password}-new")

        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])

    def test_a_new_authenticator_app_ends_the_trust(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _app_code(browser, secret)
        _post(browser, TRUST, {"trust": True})
        _sign_out(browser)
        Authenticator.objects.filter(user=ana).delete()
        _activate_totp(ana)

        response = _first_factors(browser, ana.email, password)

        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])

    def test_after_14_days_the_app_is_asked_again(self, mfa_on, browser, ana, secret, password):
        browser.cookies[TRUST_COOKIE] = _trust_cookie(ana, age=FOURTEEN_DAYS + 1)

        response = _first_factors(browser, ana.email, password)

        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])

    def test_a_trusted_browser_jumps_to_its_business_without_the_code(self, mfa_on, browser, member, secret, password):
        _sign_in(browser, member.email, password)
        _app_code(browser, secret)
        _post(browser, TRUST, {"trust": True})
        _sign_out(browser)
        _first_factors(browser, member.email, password)

        response = browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items&state=a-state")

        assert response.status_code == 200
        assert _hidden(response.content.decode(), "code")


class TestTrustWithTheFlagOff:
    def test_no_login_asks_whether_to_trust_the_browser(self, browser, ana, secret, password):
        response = _first_factors(browser, ana.email, password)

        assert response.status_code == 200
        assert _pending_flows(response) == []


BROWSER_TRUST = "/api/accounts/browser-trust"
REVOKE_TRUST = "/api/accounts/browser-trust/revoke"


def _api(client, method: str, path: str, body=None):
    if method == "GET":
        return client.get(path, HTTP_HOST=HOST)
    return client.post(path, body or {}, content_type="application/json", HTTP_HOST=HOST)


def _until(response):
    raw = response.json()["trusted_until"]
    return None if raw is None else datetime.fromisoformat(raw)


class TestTheTrustOfThisBrowser:
    """ACCOUNTS-F17 (the current browser marked): Security →
    Two-factor authentication says whether this browser is trusted, and until when. erplora.com keeps no list of the
    trusted browsers (the trust lives in each one, signed, as allauth gives it), so only this one can be told."""

    def test_a_trusted_browser_is_told_until_when(self, mfa_on, client, ana, secret):
        client.force_login(ana)
        client.cookies[TRUST_COOKIE] = _trust_cookie(ana, age=3600)

        response = _api(client, "GET", BROWSER_TRUST)

        assert response.status_code == 200
        expected = timezone.now() + timedelta(days=14) - timedelta(hours=1)
        assert abs(_until(response) - expected) < timedelta(minutes=1)

    def test_a_browser_never_trusted_has_no_date(self, mfa_on, client, ana, secret):
        client.force_login(ana)

        assert _until(_api(client, "GET", BROWSER_TRUST)) is None

    def test_a_trust_given_before_a_new_password_is_not_shown(self, mfa_on, client, ana, secret, password):
        client.cookies[TRUST_COOKIE] = _trust_cookie(ana)
        ana.set_password(f"{password}-new")
        ana.save()
        client.force_login(ana)

        assert _until(_api(client, "GET", BROWSER_TRUST)) is None

    def test_the_trust_of_another_account_is_not_shown(self, mfa_on, client, ana, secret, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _activate_totp(bo)
        client.cookies[TRUST_COOKIE] = _trust_cookie(bo)
        client.force_login(ana)

        assert _until(_api(client, "GET", BROWSER_TRUST)) is None

    def test_with_the_flag_off_no_browser_is_trusted(self, client, ana, secret):
        client.force_login(ana)
        client.cookies[TRUST_COOKIE] = _trust_cookie(ana)

        assert _until(_api(client, "GET", BROWSER_TRUST)) is None

    @pytest.mark.parametrize("method,path", [("GET", BROWSER_TRUST), ("POST", REVOKE_TRUST)])
    def test_an_anonymous_visitor_gets_the_401_envelope(self, mfa_on, client, method, path):
        response = _api(client, method, path)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


class TestStopTrustingEveryBrowser:
    """ACCOUNTS-F17: «Stop trusting all browsers» ends the trust of every browser at once, as Google's and
    Microsoft's «Revoke all trusted devices». allauth keeps no list to cut from: the trust is bound to the account's
    password and authenticators, so the authenticators get new ids with the same secret and codes (nobody sets the app
    up again, nor loses the codes written down)."""

    def test_every_trusted_browser_is_asked_for_the_apps_code_again(self, mfa_on, browser, ana, secret, password):
        _sign_in(browser, ana.email, password)
        _second_step(browser, _live_code(secret), trust=True)
        laptop = Client(HTTP_HOST=HOST)
        laptop.force_login(ana)

        response = _api(laptop, "POST", REVOKE_TRUST)

        assert response.status_code == 200
        assert response.json() == {"trusted_until": None}
        _sign_out(browser)
        response = _first_factors(browser, ana.email, password)
        assert (response.status_code, _pending_flows(response)) == (401, ["mfa_authenticate"])

    def test_the_app_and_the_recovery_codes_keep_working(self, mfa_on, client, ana, secret):
        unused = RecoveryCodes.activate(ana).get_unused_codes()
        before = {row.type: (row.data, row.created_at) for row in Authenticator.objects.filter(user=ana)}
        client.force_login(ana)

        _api(client, "POST", REVOKE_TRUST)

        after = {row.type: (row.data, row.created_at) for row in Authenticator.objects.filter(user=ana)}
        assert after == before
        assert RecoveryCodes(Authenticator.objects.get(user=ana, type="recovery_codes")).get_unused_codes() == unused
        totp = Authenticator.objects.get(user=ana, type=Authenticator.Type.TOTP)
        assert totp_auth.TOTP(totp).validate_code(_live_code(secret)) is True

    def test_this_session_keeps_the_code_it_gave_and_jumps_to_its_business(self, mfa_on, browser, member, secret, password):
        _sign_in(browser, member.email, password)
        _second_step(browser, _live_code(secret), trust=True)

        response = _post(browser, REVOKE_TRUST, {})

        assert response.status_code == 200
        response = browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items&state=a-state")
        assert response.status_code == 200
        assert _hidden(response.content.decode(), "code")

    def test_a_session_that_signed_in_on_a_trusted_browser_gives_the_code_to_jump(
        self, mfa_on, browser, member, secret, password
    ):
        _sign_in(browser, member.email, password)
        _second_step(browser, _live_code(secret), trust=True)
        _sign_out(browser)
        _first_factors(browser, member.email, password)
        laptop = Client(HTTP_HOST=HOST)
        laptop.force_login(member)
        _api(laptop, "POST", REVOKE_TRUST)

        response = browser.get(f"{HUB_LOGIN}?hub=a&next=/demo/items&state=a-state")

        assert response.status_code == 302
        assert response["Location"].startswith("/reauthenticate?method=totp")

    def test_an_account_without_the_app_has_nothing_to_stop(self, mfa_on, client, ana):
        client.force_login(ana)

        response = _api(client, "POST", REVOKE_TRUST)

        assert (response.status_code, response.json()) == (200, {"trusted_until": None})
        assert Authenticator.objects.filter(user=ana).count() == 0

    def test_only_the_accounts_own_authenticators_change(self, mfa_on, client, ana, secret, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _activate_totp(bo)
        RecoveryCodes.activate(bo)
        theirs = list(Authenticator.objects.filter(user=bo).order_by("pk").values_list("pk", "type"))
        mine = set(Authenticator.objects.filter(user=ana).values_list("pk", flat=True))
        client.force_login(ana)

        response = _api(client, "POST", REVOKE_TRUST)

        assert response.status_code == 200
        assert list(Authenticator.objects.filter(user=bo).order_by("pk").values_list("pk", "type")) == theirs
        assert set(Authenticator.objects.filter(user=ana).values_list("pk", flat=True)).isdisjoint(mine)

    def test_the_event_is_recorded(self, mfa_on, client, ana, secret):
        from live.models import OutboxEvent

        client.force_login(ana)
        _api(client, "POST", REVOKE_TRUST)

        assert list(OutboxEvent.objects.values_list("name", flat=True)) == ["accounts.browser_trust.revoked"]
