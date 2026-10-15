"""``/hub-login/`` and ``/launch/``: the jump from the SaaS to a hub (PLAN-SAAS §3.1 steps 4-5).

The code travels in an auto-submitted POST form to the hub's callback (OIDC
``response_mode=form_post``), never in a URL. Every other answer is a Vue page of the SPA: the
launcher at ``/launch`` and the errors at ``/login/error?code=…``.

The Hub binds every jump to the browser that started it: it sends ``state`` in the query and the
form hands it back verbatim next to ``code`` (login CSRF). ``audience=hub-admin`` is the staff's jump
to the Hub admin at ``hubs.erplora.com``, which also starts at the Hub (ronda 13, PLAN §18).
"""

import re
import secrets
import time
from html import unescape
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.totp.internal import auth as totp_auth

from accounts import services
from accounts.models import AuthExchangeCode, HubMembership

pytestmark = pytest.mark.django_db

HUB_LOGIN = "/hub-login/"
#: What the Hub mints for each jump (``secrets.token_urlsafe(32)``) and keeps in a cookie.
STATE = secrets.token_urlsafe(32)
REAUTHENTICATE_WITH_THE_CODE = "/_allauth/browser/v1/auth/2fa/reauthenticate"


def _hidden(html: str, name: str) -> str:
    match = re.search(rf'<input type="hidden" name="{name}" value="([^"]*)"', html)
    assert match, f"no hidden input {name!r} in the page"
    return unescape(match.group(1))


@pytest.fixture
def member(client, ana):
    HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.ADMIN)
    client.force_login(ana)
    return ana


class TestHubLogin:
    def test_without_a_session_it_goes_to_the_login_and_comes_back(self, client):
        response = client.get(HUB_LOGIN + "?hub=a&next=/demo/items")

        assert response.status_code == 302
        assert response.url == "/launch?next=" + quote(
            "/hub-login/?hub=a&next=/demo/items", safe="/"
        )

    def test_a_member_gets_a_form_that_posts_the_code_to_the_hub_callback(
        self, client, member
    ):
        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/demo/items"})

        html = response.content.decode()
        assert response.status_code == 200
        assert (
            '<form id="hub-login-form" method="post" action="http://a.localhost:8000/auth/callback">'
            in html
        )
        assert _hidden(html, "next") == "/demo/items"
        code = _hidden(html, "code")
        row = AuthExchangeCode.objects.get()
        assert row.code_hash == AuthExchangeCode.hash_code(code)
        assert (row.user, row.hub_slug) == (member, "a")

    def test_the_form_submits_itself_with_a_nonced_script(self, client, member):
        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/"})

        html = response.content.decode()
        nonce = re.search(
            r"'nonce-([^']+)'", response["Content-Security-Policy"]
        ).group(1)
        assert f'<script nonce="{nonce}">' in html
        assert 'getElementById("hub-login-form").submit()' in html
        assert "<noscript>" in html

    def test_the_page_is_never_cached_nor_leaks_a_referrer(self, client, member):
        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/"})

        assert "no-store" in response["Cache-Control"]
        assert response["Referrer-Policy"] == "no-referrer"

    def test_the_callback_comes_from_the_setting(self, client, member, settings):
        settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"

        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/"})

        assert (
            'action="https://a.erplora.com/auth/callback"' in response.content.decode()
        )

    @pytest.mark.parametrize(
        "next_url",
        [
            "",
            "//evil.example/x",
            "https://evil.example/x",
            "javascript:alert(1)",
            "/\\evil",
        ],
    )
    def test_a_next_that_is_not_a_local_path_becomes_the_hub_home(
        self, client, member, next_url
    ):
        response = client.get(HUB_LOGIN, {"hub": "a", "next": next_url})

        assert _hidden(response.content.decode(), "next") == "/"

    def test_a_signed_in_stranger_goes_to_the_error_page_naming_the_hub_and_gets_no_code(
        self, client, ana
    ):
        client.force_login(ana)

        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/"})

        assert response.status_code == 302
        assert response.url == "/login/error?code=not_a_member&hub=a"
        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize(
        "hub",
        [
            None,
            "",
            "A",
            "a_b",
            "1a",
            "ab",
            "a-",
            "xn--bcher-kva",
            "a\n",
            "evil.example/x",
            "a" * 64,
        ],
    )
    def test_a_hub_that_is_not_a_slug_goes_to_the_error_page_without_echoing_it(
        self, client, member, hub
    ):
        params = {"next": "/"} if hub is None else {"hub": hub, "next": "/"}

        response = client.get(HUB_LOGIN, params)

        assert response.status_code == 302
        assert response.url == "/login/error?code=invalid_hub"
        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("hub", ["www", "hub", "hubs", "admin", "WWW"])
    def test_a_reserved_name_is_no_hub_even_with_a_membership_row(
        self, client, member, hub
    ):
        # `hubs` is the Hub's staff admin host (ronda 13, PLAN §18) and `hub` stays reserved: never
        # a customer's hub.
        HubMembership.objects.create(
            user=member, hub_slug=hub, role=HubMembership.Role.OWNER
        )

        response = client.get(HUB_LOGIN, {"hub": hub, "next": "/"})

        assert response.status_code == 302
        assert response.url == "/login/error?code=invalid_hub"
        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("hub", ["www", "hubs"])
    def test_a_reserved_name_is_refused_before_asking_for_a_session(self, client, hub):
        response = client.get(HUB_LOGIN, {"hub": hub})

        assert response.url == "/login/error?code=invalid_hub"

    def test_a_hub_slug_may_start_with_a_digit(self, client, member):
        HubMembership.objects.create(
            user=member, hub_slug="0day", role=HubMembership.Role.OWNER
        )

        response = client.get(HUB_LOGIN, {"hub": "0day", "next": "/"})

        assert response.status_code == 200
        assert (
            'action="http://0day.localhost:8000/auth/callback"'
            in response.content.decode()
        )

    def test_an_invalid_hub_is_refused_before_asking_for_a_session(self, client):
        response = client.get(HUB_LOGIN, {"hub": "INVALID"})

        assert response.url == "/login/error?code=invalid_hub"

    def test_only_get_is_allowed(self, client, member):
        assert client.post(HUB_LOGIN, {"hub": "a"}).status_code == 405


def _no_state_field(html: str) -> bool:
    return 'name="state"' not in html


class TestTheStateOfTheJump:
    """``state``: the Hub's token of the browser that started the jump, handed back as it came."""

    @pytest.mark.parametrize(
        "state",
        [STATE, "s" * 128, "\"><script>alert(1)</script>&amp;"],
        ids=["the-hubs-token", "the-longest-accepted", "escaped-not-interpreted"],
    )
    def test_the_form_hands_the_state_back_verbatim_next_to_the_code(self, client, member, caplog, state):
        caplog.set_level("DEBUG")

        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/demo/items", "state": state})

        html = response.content.decode()
        assert response.status_code == 200
        assert _hidden(html, "state") == state
        assert AuthExchangeCode.objects.get().code_hash == AuthExchangeCode.hash_code(_hidden(html, "code"))
        # Opaque to the SaaS: never logged, never stored with the one-time code.
        assert state not in caplog.text
        assert state not in repr(AuthExchangeCode.objects.values().get())

    @pytest.mark.parametrize("params", [{}, {"state": ""}], ids=["absent", "empty"])
    def test_without_a_state_the_form_has_no_state_field(self, client, member, params):
        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/", **params})

        html = response.content.decode()
        assert response.status_code == 200
        assert _hidden(html, "code")
        assert _no_state_field(html)

    @pytest.mark.parametrize("signed_in", [True, False])
    def test_a_state_longer_than_128_characters_is_an_invalid_link_and_mints_no_code(
        self, client, ana, signed_in
    ):
        # No state the Hub mints is that long: the link is refused as a broken one, before the
        # login, without echoing it.
        HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.ADMIN)
        if signed_in:
            client.force_login(ana)

        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/", "state": "s" * 129})

        assert response.status_code == 302
        assert response.url == "/login/error?code=invalid_hub"
        assert not AuthExchangeCode.objects.exists()

    def test_the_sign_in_keeps_the_state_for_the_way_back(self, client):
        response = client.get(HUB_LOGIN, {"hub": "a", "next": "/demo/items", "state": STATE})

        assert response.status_code == 302
        assert response.url == "/launch?next=" + quote(
            f"/hub-login/?hub=a&next=%2Fdemo%2Fitems&state={STATE}", safe="/"
        )

    def test_the_second_factor_detour_keeps_the_state(self, client, member, settings):
        settings.ACCOUNTS_MFA_ENABLED = True
        secret = totp_auth.generate_totp_secret()
        totp_auth.TOTP.activate(member, secret)
        # Django's own login records no second factor: the jump asks for the app's code first.
        client.force_login(member)

        detour = client.get(HUB_LOGIN, {"hub": "a", "next": "/demo/items", "state": STATE})

        assert detour.status_code == 302
        assert urlsplit(detour.url).path == "/reauthenticate"
        back = parse_qs(urlsplit(detour.url).query)["next"][0]
        assert parse_qs(urlsplit(back).query)["state"] == [STATE]
        assert not AuthExchangeCode.objects.exists()

        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = totp_auth.format_hotp_value(totp_auth.hotp_value(secret, counter))
        assert client.post(REAUTHENTICATE_WITH_THE_CODE, {"code": code}, content_type="application/json").status_code == 200

        response = client.get(back)

        assert response.status_code == 200
        assert _hidden(response.content.decode(), "state") == STATE


class TestTheJumpToTheHubAdmin:
    """``audience=hub-admin``: the staff's «Open in the Hub admin» (ronda 13, PLAN §18), started at
    ``hubs.erplora.com/auth/login``, which sends the browser here with its ``state``. A one-time
    ``hub-admin`` code is auto-posted to ``HUB_ADMIN_CALLBACK_URL`` with ``next`` and ``state``."""

    JUMP = {"hub": "a", "audience": "hub-admin", "next": "/admin/hub/a/", "state": STATE}

    @pytest.fixture
    def platform(self, client, password):
        user, _ = services.create_platform_user("boss@erplora.com", "admin", password)
        client.force_login(user)
        return user

    @pytest.fixture
    def support(self, client, password):
        user, _ = services.create_platform_user("help@erplora.com", "support", password)
        client.force_login(user)
        return user

    def test_staff_get_a_form_that_posts_code_next_and_state_to_the_hub_admin(self, client, platform):
        response = client.get(HUB_LOGIN, self.JUMP)

        html = response.content.decode()
        assert response.status_code == 200
        assert '<form id="hub-login-form" method="post" action="http://hubs.localhost:8000/auth/callback">' in html
        assert _hidden(html, "next") == "/admin/hub/a/"
        assert _hidden(html, "state") == STATE
        assert "Opening the Hub admin…" in html
        row = AuthExchangeCode.objects.get()
        assert (row.user, row.hub_slug, row.audience) == (platform, "a", "hub-admin")
        assert row.code_hash == AuthExchangeCode.hash_code(_hidden(html, "code"))

    def test_the_code_redeems_as_hub_admin_with_the_platform_role(self, client, platform):
        code = _hidden(client.get(HUB_LOGIN, self.JUMP).content.decode(), "code")

        identity = services.redeem_code(code, "a", audience="hub-admin")

        assert (identity.email, identity.role) == ("boss@erplora.com", "platform_admin")

    def test_support_jumps_with_the_support_role(self, client, support):
        code = _hidden(client.get(HUB_LOGIN, {**self.JUMP, "hub": "b"}).content.decode(), "code")

        assert services.redeem_code(code, "b", audience="hub-admin").role == "platform_support"

    def test_without_a_state_the_form_has_no_state_field(self, client, platform):
        params = {key: value for key, value in self.JUMP.items() if key != "state"}

        assert _no_state_field(client.get(HUB_LOGIN, params).content.decode())

    def test_the_page_submits_itself_and_is_never_cached_nor_leaks_a_referrer(self, client, platform):
        response = client.get(HUB_LOGIN, self.JUMP)

        html = response.content.decode()
        nonce = re.search(r"'nonce-([^']+)'", response["Content-Security-Policy"]).group(1)
        assert f'<script nonce="{nonce}">' in html
        assert 'getElementById("hub-login-form").submit()' in html
        assert "no-store" in response["Cache-Control"]
        assert response["Referrer-Policy"] == "no-referrer"

    def test_the_csp_lets_the_form_post_to_the_hub_admin(self, client, platform):
        policy = client.get(HUB_LOGIN, self.JUMP)["Content-Security-Policy"]

        form_action = next(part for part in policy.split("; ") if part.startswith("form-action "))
        assert "http://hubs.localhost:8000" in form_action.split()

    def test_the_callback_comes_from_the_setting(self, client, platform, settings):
        settings.HUB_ADMIN_CALLBACK_URL = "https://hubs.erplora.com/auth/callback"

        response = client.get(HUB_LOGIN, self.JUMP)

        assert 'action="https://hubs.erplora.com/auth/callback"' in response.content.decode()

    def test_without_a_session_it_is_the_login_and_back_with_the_state(self, client, db):
        response = client.get(HUB_LOGIN, self.JUMP)

        assert response.status_code == 302
        assert response.url.startswith("/launch?next=")
        assert parse_qs(urlsplit(parse_qs(urlsplit(response.url).query)["next"][0]).query)["state"] == [STATE]
        assert not AuthExchangeCode.objects.exists()

    def test_a_customer_is_forbidden_never_sent_to_a_login(self, client, member):
        response = client.get(HUB_LOGIN, self.JUMP)

        assert response.status_code == 403
        assert not AuthExchangeCode.objects.exists()

    def test_staff_without_a_platform_role_are_forbidden(self, client, ana):
        ana.is_staff = True
        ana.save()
        client.force_login(ana)

        assert client.get(HUB_LOGIN, self.JUMP).status_code == 403
        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("hub", ["hubs", "hub", "www", "admin", "A", "ab"])
    def test_the_platform_host_and_reserved_or_invalid_slugs_are_an_invalid_link(self, client, platform, hub):
        response = client.get(HUB_LOGIN, {**self.JUMP, "hub": hub})

        assert response.url == "/login/error?code=invalid_hub"
        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("audience", ["", "HUB-ADMIN", "hub-everything"])
    def test_an_unknown_audience_is_an_invalid_link(self, client, platform, audience):
        response = client.get(HUB_LOGIN, {**self.JUMP, "audience": audience})

        assert response.url == "/login/error?code=invalid_hub"
        assert not AuthExchangeCode.objects.exists()

    def test_the_jump_page_is_translated_to_spanish(self, client, platform):
        response = client.get(HUB_LOGIN, self.JUMP, headers={"Accept-Language": "es"})

        assert "Abriendo el admin del Hub…" in response.content.decode()


class TestLaunch:
    """The launcher is the Vue page ``/launch`` (accounts.hub.list); ``/launch/`` only leads there."""

    def test_it_leads_to_the_vue_launcher(self, client, member):
        response = client.get("/launch/")

        assert response.status_code == 302
        assert response.url == "/launch"

    def test_without_a_session_too_the_spa_gate_sends_to_the_login(self, client):
        response = client.get("/launch/")

        assert (response.status_code, response.url) == (302, "/launch")

    def test_only_get_is_allowed(self, client, member):
        assert client.post("/launch/").status_code == 405
