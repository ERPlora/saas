"""Settings of saas-next that a page relies on: the CSP and where the hub's callback lives."""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.http.request import validate_host
from live.csp import base_policy, debug_policy


def test_the_hub_origin_pattern_is_derived_from_the_callback_template():
    assert (
        settings.HUB_CALLBACK_TEMPLATE == "http://{slug}.localhost:8000/auth/callback"
    )
    assert settings.HUB_ORIGIN_PATTERN == "http://*.localhost:8000"


# Hosts (Ioan, 2026-10-13; ronda 13, PLAN §18): customers sign in at `erplora.com` (locally
# `localhost:8001`); hubs are `<slug>.erplora.com` (locally `a.localhost:8000`) and `hubs.erplora.com`
# (locally `hubs.localhost:8000`) is the Hub's staff admin host, served only by the Hub. No host of
# a hub is the SaaS's.


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_development_answers_on_localhost(host):
    assert validate_host(host, settings.ALLOWED_HOSTS)


@pytest.mark.parametrize(
    "host",
    ["hubs.localhost", "hub.localhost", "a.localhost", "erplora.com", "hubs.erplora.com", "hub.erplora.com"],
)
def test_development_does_not_answer_on_a_hubs_host(host):
    assert not validate_host(host, settings.ALLOWED_HOSTS)


def test_staff_jump_to_the_hub_admin_on_its_own_host():
    """The `hub-admin` jump posts to the platform host's callback (ronda 13, PLAN §18), never a hub's."""
    assert settings.HUB_ADMIN_CALLBACK_URL == "http://hubs.localhost:8000/auth/callback"


def test_development_opens_one_letter_hubs():
    """The demo hubs `a` and `b` (``demo_seed``) are one letter: only development admits them."""
    assert settings.LIVE["hub_slug_min_length"] == 1


@pytest.mark.django_db
def test_every_page_has_a_csp_with_a_nonce_and_form_action_to_the_hubs(client):
    response = client.get("/accounts/login/")

    policy = response["Content-Security-Policy"]
    directives = {part.split()[0]: part.split()[1:] for part in policy.split("; ")}
    assert re.search(r"'nonce-[^']+'", " ".join(directives["script-src"]))
    assert "'strict-dynamic'" in directives["script-src"]
    # Google: `POST /auth/google/login/` answers 302 to accounts.google.com, and `form-action`
    # filters the whole redirect chain of a form post (ported from ERPlora/saas, saas#945).
    # The hubs (`/hub-login/`) and the Hub admin of the staff (`hubs.localhost:8000`, ronda 13).
    assert directives["form-action"] == [
        "'self'",
        "https://accounts.google.com",
        "http://*.localhost:8000",
        "http://hubs.localhost:8000",
    ]
    # The Tauri bridge; with DEBUG (the default of the tests) also the Vite dev server and its HMR socket.
    assert directives["connect-src"][:3] == ["'self'", "ipc:", "http://ipc.localhost"]
    assert "cdn.jsdelivr.net" not in policy


def test_iconify_may_create_its_trusted_types_policy():
    """iconify-icon creates a policy named `iconify`; without it the browser blocks it and reports
    a violation on every page (allowed in today's SaaS too, `config/settings.py`)."""
    assert "iconify" in settings.SECURE_CSP["trusted-types"]
    assert "default" in settings.SECURE_CSP["trusted-types"]


# Production settings are read in a fresh interpreter: `config.settings` is evaluated once per
# process, from the environment and `saas-next/.env`.

SAAS_NEXT = Path(__file__).resolve().parents[2]
PRODUCTION_ENV = {
    "DEBUG": "False",
    "SECRET_KEY": "a-production-secret-key",
    "INTERNAL_SHARED_SECRET": "a-production-internal-secret",
    "GOOGLE_OAUTH_CLIENT_ID": "prod-client.apps.googleusercontent.com",
    "GOOGLE_OAUTH_CLIENT_SECRET": "prod-secret",
}


def _settings_in_a_fresh_process(
    env: dict[str, str], expression: str
) -> subprocess.CompletedProcess:
    # DEBUG too: the test run turns it on (config/settings_pytest.py), the fresh process must not inherit it.
    base = {
        key: value
        for key, value in os.environ.items()
        if key != "DEBUG" and not key.startswith(("GOOGLE_", "DJANGO_"))
    }
    return subprocess.run(
        [sys.executable, "-c", f"import config.settings as s; print({expression})"],
        cwd=SAAS_NEXT,
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(
    (SAAS_NEXT / ".env").is_file(),
    reason="saas-next/.env would leak into the fresh process",
)
def test_debug_is_off_unless_the_environment_turns_it_on():
    """A deploy that forgets DEBUG must not serve debug pages nor fall back to the local secrets:
    production is the default, development opts in (saas-next/.env, `DEBUG=True`)."""
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "DEBUG"}

    result = _settings_in_a_fresh_process(env, "s.DEBUG")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.skipif(
    (SAAS_NEXT / ".env").is_file(),
    reason="saas-next/.env would leak into the fresh process",
)
@pytest.mark.parametrize(
    "missing", ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
)
def test_production_refuses_to_start_without_google_credentials(missing):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != missing}

    result = _settings_in_a_fresh_process(env, "s.GOOGLE_OAUTH_ENABLED")

    assert result.returncode != 0
    assert missing in result.stderr


@pytest.mark.skipif(
    (SAAS_NEXT / ".env").is_file(),
    reason="saas-next/.env would leak into the fresh process",
)
def test_production_hands_google_an_https_callback():
    """Behind the load balancer the request arrives as http: the redirect_uri must still be https."""
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV, "s.GOOGLE_OAUTH_ENABLED, s.ACCOUNT_DEFAULT_HTTP_PROTOCOL"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["True", "https"]


@pytest.mark.skipif(
    (SAAS_NEXT / ".env").is_file(),
    reason="saas-next/.env would leak into the fresh process",
)
def test_production_answers_only_on_erplora_com_and_wants_three_letter_hubs():
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV, "(s.ALLOWED_HOSTS, s.LIVE['hub_slug_min_length'])"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str((["erplora.com"], 3))


@pytest.mark.skipif(
    (SAAS_NEXT / ".env").is_file(),
    reason="saas-next/.env would leak into the fresh process",
)
def test_production_sends_the_staff_to_hubs_erplora_com_without_serving_it():
    """`hubs.erplora.com` is the Hub's alone (ronda 13, PLAN §18): the SaaS only posts there."""
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV,
        "(s.HUB_ADMIN_CALLBACK_URL, [str(source) for source in s.SECURE_CSP['form-action']], s.ALLOWED_HOSTS)"
    )

    assert result.returncode == 0, result.stderr
    callback, form_action, allowed_hosts = ast.literal_eval(result.stdout.strip())
    assert callback == "https://hubs.erplora.com/auth/callback"
    assert "https://hubs.erplora.com" in form_action
    assert not validate_host("hubs.erplora.com", allowed_hosts)
    assert not validate_host("hub.erplora.com", allowed_hosts)


def test_development_keeps_http_for_the_local_callback(settings):
    assert settings.ACCOUNT_DEFAULT_HTTP_PROTOCOL == "http"


def test_google_is_configured_as_in_todays_saas_plus_pkce(settings):
    google = settings.SOCIALACCOUNT_PROVIDERS["google"]

    assert google["SCOPE"] == ["profile", "email"]
    assert google["AUTH_PARAMS"] == {"access_type": "online"}
    assert google["OAUTH_PKCE_ENABLED"] is True
    # Google's own `email_verified` claim decides; no blanket «every Google email is verified».
    assert "VERIFIED_EMAIL" not in google
    assert settings.SOCIALACCOUNT_LOGIN_ON_GET is False
    assert settings.SOCIALACCOUNT_STORE_TOKENS is False
    assert settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION is True
    assert settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT is True


# The SPA (packages/live): Vite on 5174, the debug CSP open to it, the user as the scope.

VITE_DEV_SERVER = "http://localhost:5174"


def test_live_precedes_daphne_so_its_runserver_starts_vite_too():
    installed = settings.INSTALLED_APPS
    assert installed.index("live") < installed.index("daphne")
    assert {"ninja", "base", "accounts", "allauth.headless"} <= set(installed)


def test_saas_next_has_no_apps_directory():
    """``apps/`` only holds the modules a hub turns on and off; the SaaS has none, so its platform
    apps live at the project root next to ``base/`` (round 15, PLAN §20.2)."""
    assert not (settings.BASE_DIR / "apps").exists()


def test_the_debug_csp_lets_the_saas_vite_dev_server_in():
    """Port 5174, not hub-next's 5173: both dev servers run at once."""
    expected = debug_policy(VITE_DEV_SERVER)
    for directive in ("connect-src", "style-src", "font-src", "img-src"):
        assert VITE_DEV_SERVER in settings.SECURE_CSP[directive]
    assert "ws://localhost:5174" in settings.SECURE_CSP["connect-src"]
    assert settings.SECURE_CSP["connect-src"] == expected["connect-src"]
    assert "require-trusted-types-for" not in settings.SECURE_CSP


def test_live_serves_the_spa_of_this_project():
    live = settings.LIVE
    assert live["context_builder"] == "base.operations.UserContextBuilder"
    assert live["control_alias"] == "default"
    assert live["spa"]["entry"] == "frontend/main.ts"
    assert (
        live["spa"]["manifest"]
        == settings.BASE_DIR / "frontend" / "dist" / ".vite" / "manifest.json"
    )
    assert live["spa"]["dev_server"] == VITE_DEV_SERVER
    assert live["spa"]["title"] == "ERPlora Cloud"
    # The repo is its own pnpm workspace (packages/ui is a submodule inside it): Vite starts from here.
    assert live["vite"] == {
        "command": ["pnpm", "run", "dev"],
        "cwd": str(settings.BASE_DIR),
    }


def test_the_spa_build_is_served_under_static_spa():
    assert settings.WHITENOISE_IMMUTABLE_FILE_TEST == r"^/static/spa/assets/"


@pytest.mark.skipif(
    (SAAS_NEXT / ".env").is_file(),
    reason="saas-next/.env would leak into the fresh process",
)
def test_production_has_the_base_csp_and_no_dev_server():
    expression = (
        "(s.SECURE_CSP['connect-src'], s.LIVE['spa']['dev_server'], 'require-trusted-types-for' in s.SECURE_CSP,"
        " s.HEADLESS_SERVE_SPECIFICATION)"
    )
    result = _settings_in_a_fresh_process(PRODUCTION_ENV, expression)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(
        (base_policy()["connect-src"], None, True, False)
    )


# allauth.headless: the login API of the Vue pages, next to the template login until every page exists.


def test_headless_serves_the_browser_client_only():
    assert settings.HEADLESS_CLIENTS == ("browser",)


def test_the_template_pages_stay_during_the_transition():
    """HEADLESS_ONLY flips to True once every account page is a Vue page."""
    assert settings.HEADLESS_ONLY is False


def test_the_specification_is_served_in_development_without_a_cdn_page():
    """allauth's openapi.html loads Redoc from a CDN, which the CSP blocks: only the YAML/JSON.
    Production does not serve it (``test_production_has_the_base_csp_and_no_dev_server``)."""
    assert settings.HEADLESS_SERVE_SPECIFICATION is True
    assert settings.HEADLESS_SPECIFICATION_TEMPLATE_NAME is None


def test_after_signing_in_the_person_lands_on_the_vue_launcher():
    assert settings.LOGIN_REDIRECT_URL == "/launch"


def test_no_mail_links_a_vue_page_that_does_not_exist_yet():
    """allauth builds the links of its mails from HEADLESS_FRONTEND_URLS even with HEADLESS_ONLY off:
    each key enters with its page, or the template flows would mail dead links."""
    assert settings.HEADLESS_FRONTEND_URLS == {}
