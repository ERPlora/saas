"""``/hub-login/`` and ``/launch/``: the jump from the SaaS to a hub (PLAN-SAAS §3.1 steps 4-5).

The code travels in an auto-submitted POST form to the hub's callback (OIDC
``response_mode=form_post``), never in a URL. Every other answer is a Vue page of the SPA: the
launcher at ``/launch`` and the errors at ``/login/error?code=…``.
"""

import re
from html import unescape
from urllib.parse import quote

import pytest

from accounts.models import AuthExchangeCode, HubMembership

pytestmark = pytest.mark.django_db

HUB_LOGIN = "/hub-login/"


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
        assert response.url == "/accounts/login/?next=" + quote(
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
