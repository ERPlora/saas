"""The SPA's HTML: live.spa with base.session.me embedded next to spa-config, every script with the nonce.

spa-config also tells the login page whether «Continue with Google» is configured
(``googleEnabled``), the same switch that serves Google's routes (``accounts/google.py``).
"""

import json
import re

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"


def json_block(response, block_id: str) -> tuple[str, dict]:
    match = re.search(
        rf'<script id="{block_id}" type="application/json" nonce="([^"]+)">(.*?)</script>',
        response.content.decode(),
        re.S,
    )
    assert match, f"no {block_id} block"
    return match.group(1), json.loads(match.group(2))


def csp_nonce(response) -> str:
    [nonce] = re.findall(r"'nonce-([^']+)'", response["Content-Security-Policy"])
    return nonce


def test_the_anonymous_shell_embeds_an_empty_session_with_the_nonce(client):
    response = client.get("/launch", HTTP_HOST=HOST)

    assert response.status_code == 200
    nonce, me = json_block(response, "session-me")
    assert nonce == csp_nonce(response)
    assert (me["user"], me["scope"]) == (None, {"kind": "user", "key": "anonymous"})
    config_nonce, config = json_block(response, "spa-config")
    assert config_nonce == nonce
    assert (config["liveUrl"], config["apiBase"]) == ("/api/live", "/api")


def test_a_signed_in_shell_embeds_its_user_and_the_panels_menu(client, ana):
    client.force_login(ana)

    _, me = json_block(client.get("/launch", HTTP_HOST=HOST), "session-me")

    assert me["user"] == {"id": str(ana.pk), "label": "Ana García", "email": "ana@example.com"}
    [section] = me["menu"]
    assert [item["path"] for item in section["items"]] == ["/businesses", "/store", "/billing", "/account"]


def test_the_embedded_json_cannot_close_the_script(client, django_user_model):
    eve = django_user_model.objects.create_user(
        email="eve@example.com", password="x", first_name="</script><script>alert(1)//"
    )
    client.force_login(eve)

    response = client.get("/launch", HTTP_HOST=HOST)

    assert "</script><script>alert(1)" not in response.content.decode()
    assert json_block(response, "session-me")[1]["user"]["label"].startswith(
        "</script>"
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_spa_config_says_whether_google_is_configured(client, settings, enabled):
    settings.GOOGLE_OAUTH_ENABLED = enabled

    _, config = json_block(client.get("/launch", HTTP_HOST=HOST), "spa-config")

    assert config["googleEnabled"] is enabled


@pytest.mark.parametrize("enabled", [True, False])
def test_spa_config_says_whether_two_step_verification_is_switched_on(client, settings, enabled):
    """Off, its endpoints answer 404 (``accounts/mfa.py``): the Account page does not ask them."""
    settings.ACCOUNTS_MFA_ENABLED = enabled

    _, config = json_block(client.get("/account/security", HTTP_HOST=HOST), "spa-config")

    assert config["mfaEnabled"] is enabled


def test_spa_config_hands_the_sign_in_pages_recaptchas_site_key(client, recaptcha):
    """The sign-in's pages ask Google's enterprise.js for a token with it (accounts/frontend/recaptcha.ts)."""
    _, config = json_block(client.get("/launch", HTTP_HOST=HOST), "spa-config")

    assert config["recaptchaSiteKey"] == "test-site-key"


def test_spa_config_without_recaptcha_has_an_empty_site_key(client):
    _, config = json_block(client.get("/launch", HTTP_HOST=HOST), "spa-config")

    assert config["recaptchaSiteKey"] == ""


def test_spa_config_carries_the_origin_of_a_hub_with_its_slug_to_fill_in(client, settings):
    """The error page of the jump names the hub's host and links back to it (/login/error?code=not_a_member)."""
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"

    _, config = json_block(client.get("/login/error", HTTP_HOST=HOST), "spa-config")

    assert config["hubOrigin"] == "https://{slug}.erplora.com"


def test_the_shell_is_never_cached_and_sets_the_csrf_cookie(client, settings):
    """The SDK and allauth.headless's browser client send that cookie back in X-CSRFToken."""
    response = client.get("/launch", HTTP_HOST=HOST)

    assert "no-store" in response["Cache-Control"]
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_only_get_and_head(client):
    assert client.post("/launch", HTTP_HOST=HOST).status_code == 405
    assert client.head("/launch", HTTP_HOST=HOST).status_code == 200


def test_the_title_is_the_saas_one(client):
    assert (
        "<title>ERPlora Cloud</title>"
        in client.get("/launch", HTTP_HOST=HOST).content.decode()
    )


def test_the_web_panel_can_be_zoomed(client):
    """WCAG 1.4.4 (audit R-02): no maximum-scale nor user-scalable=no in the viewport."""
    html = client.get("/launch", HTTP_HOST=HOST).content.decode()

    assert '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' in html
    assert "user-scalable" not in html
    assert "maximum-scale" not in html


def test_the_shell_embeds_the_support_address_of_the_settings(client, settings):
    """The SPA's «Contact Support» writes to ``SUPPORT_EMAIL``, the public web's one source (PUBLIC-F18)."""
    settings.SUPPORT_EMAIL = "help@erplora.test"
    response = client.get("/launch", HTTP_HOST=HOST)

    nonce, email = json_block(response, "support-email")
    assert nonce == csp_nonce(response)
    assert email == "help@erplora.test"
