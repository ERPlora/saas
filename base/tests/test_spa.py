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
    assert [item["path"] for item in section["items"]] == ["/dashboard/businesses", "/dashboard/store", "/dashboard/billing", "/dashboard/account"]


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

    _, config = json_block(client.get("/dashboard/account/security", HTTP_HOST=HOST), "spa-config")

    assert config["mfaEnabled"] is enabled


def test_spa_config_hands_the_sign_in_pages_recaptchas_site_key(client, recaptcha):
    """The sign-in's pages ask Google's enterprise.js for a token with it (accounts/frontend/recaptcha.ts)."""
    _, config = json_block(client.get("/launch", HTTP_HOST=HOST), "spa-config")

    assert config["recaptchaSiteKey"] == "test-site-key"


def test_spa_config_without_recaptcha_names_no_site_key(client):
    """Off (the default since 2026-10-23): the page says nothing of reCAPTCHA, so its pages load no Google script."""
    response = client.get("/launch", HTTP_HOST=HOST)
    _, config = json_block(response, "spa-config")

    assert "recaptchaSiteKey" not in config
    assert "recaptcha" not in response.content.decode().lower()


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


# flow: saas-spa-icon (FIX-SAAS-SPA-NO-TAB-ICON) — the panel's tab and home-screen icons are the public web's
# (public/templates/public/public_base.html), static files of the SaaS linked by its static storage (live.spa,
# LIVE["spa"]["icons"]), never a URL of elsewhere: without them the tab has no ERPlora logo.
PANEL_ICONS = [
    ("icon", "img/favicon.ico", ' sizes="any"'),
    ("apple-touch-icon", "public/img/apple-touch-icon.png", ""),
]


@pytest.mark.parametrize(("path", "signed_in"), [("/launch", False), ("/dashboard/businesses", True)])
def test_the_panel_declares_the_public_web_s_icons_from_its_static_files(client, ana, path, signed_in):
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    if signed_in:
        client.force_login(ana)
    response = client.get(path, HTTP_HOST=HOST, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    html = response.content.decode()
    head = html[: html.index("</head>")]
    for rel, static_path, sizes in PANEL_ICONS:
        assert finders.find(static_path), f"{static_path} is no static file of the SaaS"
        assert static(static_path).startswith("/static/")
        assert f'<link rel="{rel}" href="{static(static_path)}"{sizes}>' in head


# flow: saas-spa-static-probes (FIX-SAAS-SPA-STATIC-PROBES-SET-CSRF-COOKIE) — a path that names a file (its last segment
# has an extension) and has no URL of its own is no page of the SPA: a crawler's or a browser's /favicon.ico, a
# scanner's /wp-login.php get Django's plain 404, with no shell and no `csrftoken`, signed in or not and whatever they
# accept. The public web's files with a URL of their own (robots.txt, llms.txt, sitemap.xml, IndexNow's key) and every
# page of the SPA answer as before.
BROWSER_PAGE = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
BROWSER_IMAGE = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
FILE_PROBES = [
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/wp-login.php",
    "/.env",
    "/dashboard/businesses/main.js.map",
    # With a trailing slash too: APPEND_SLASH must not send a file's path to the shell at the one with a slash.
    "/favicon.ico/",
    "/humans.txt/",
]
DEEP_LINK = "/dashboard/businesses/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e10"


def is_the_shell(response) -> bool:
    return 'id="spa-config"' in response.content.decode()


@pytest.mark.parametrize("path", FILE_PROBES)
@pytest.mark.parametrize("accept", ["*/*", BROWSER_PAGE, BROWSER_IMAGE])
def test_a_probe_for_a_file_without_a_session_gets_a_plain_404_with_no_cookie(client, path, accept):
    response = client.get(path, HTTP_HOST=HOST, HTTP_ACCEPT=accept)

    assert (response.status_code, dict(response.cookies)) == (404, {})
    assert not is_the_shell(response)


@pytest.mark.parametrize("path", FILE_PROBES)
@pytest.mark.parametrize("accept", [BROWSER_PAGE, BROWSER_IMAGE])
def test_a_signed_in_probe_for_a_file_gets_the_404_and_no_csrf_cookie(client, settings, ana, path, accept):
    # With a session, the CSRF middleware must neither set nor rotate the token on it.
    client.force_login(ana)

    response = client.get(path, HTTP_HOST=HOST, HTTP_ACCEPT=accept)

    assert response.status_code == 404
    assert settings.CSRF_COOKIE_NAME not in response.cookies
    assert not is_the_shell(response)


def test_a_public_file_s_path_with_a_trailing_slash_is_the_public_web_s_404_never_the_shell(client):
    # /robots.txt/ is under a first segment of the public web (public.urls.PUBLIC_PREFIXES): its 404 is the public
    # web's page, as for /pricing/nope/, whose footer's language form sets `csrftoken` like every public page.
    response = client.get("/robots.txt/", HTTP_HOST=HOST, HTTP_ACCEPT=BROWSER_PAGE)

    assert response.status_code == 404
    assert "public/404.html" in [template.name for template in response.templates]
    assert not is_the_shell(response)


def test_a_head_of_the_favicon_is_the_same_404(client):
    response = client.head("/favicon.ico", HTTP_HOST=HOST, HTTP_ACCEPT="*/*")

    assert (response.status_code, dict(response.cookies)) == (404, {})


@pytest.mark.parametrize(
    ("path", "content_type"),
    [("/robots.txt", "text/plain"), ("/llms.txt", "text/plain"), ("/sitemap.xml", "application/xml")],
)
def test_the_public_web_s_own_files_still_answer_with_their_view(client, path, content_type):
    response = client.get(path, HTTP_HOST=HOST, HTTP_ACCEPT="*/*")

    assert response.status_code == 200
    assert response["Content-Type"].startswith(content_type)
    assert not is_the_shell(response)


def test_indexnow_s_key_file_still_answers_with_its_view(client, settings):
    settings.INDEXNOW_KEY = "0123456789abcdef0123456789abcdef"

    response = client.get(f"/{settings.INDEXNOW_KEY}.txt", HTTP_HOST=HOST, HTTP_ACCEPT="*/*")

    assert (response.status_code, response.content.decode()) == (200, settings.INDEXNOW_KEY)


def reset_link_path(user) -> str:
    """The path of the reset link allauth mails (`password_reset.request_password_reset`): `<uid>-<token>`."""
    from allauth.account import app_settings as allauth_settings
    from allauth.account.utils import user_pk_to_url_str
    from django.conf import settings

    key = f"{user_pk_to_url_str(user)}-{allauth_settings.PASSWORD_RESET_TOKEN_GENERATOR().make_token(user)}"
    return settings.HEADLESS_FRONTEND_URLS["account_reset_password_from_key"].format(key=key)


@pytest.mark.parametrize("signed_in", [False, True])
@pytest.mark.parametrize("accept", ["*/*", BROWSER_PAGE])
def test_every_page_of_the_spa_still_gets_the_shell_and_its_csrf_cookie(client, settings, ana, signed_in, accept):
    # No page of the SPA names a file: its parameters are ids (UUIDv7) and allauth's reset key (hex and base 36).
    # Without the cookie the SDK's first write is refused (403): every page load of the SPA sets it.
    if signed_in:
        client.force_login(ana)
    paths = [
        "/launch",
        "/login/error",
        "/password/reset",
        reset_link_path(ana),
        "/dashboard/businesses",
        DEEP_LINK,
        f"{DEEP_LINK}/members",
        "/dashboard/billing/invoices/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e11",
        "/invitations/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e12",
    ]
    for path in paths:
        response = client.get(path, HTTP_HOST=HOST, HTTP_ACCEPT=accept)
        assert response.status_code == 200 and is_the_shell(response), path
        assert settings.CSRF_COOKIE_NAME in response.cookies, path
