"""Settings of saas-next that a page relies on: the CSP and where the hub's callback lives."""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.http.request import validate_host
from live.csp import base_policy, debug_policy
from live.meta import LiveAppConfig

from config.tests.test_production_settings import IGNORE_DOTENV


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
    [
        "hubs.localhost",
        "hub.localhost",
        "a.localhost",
        "erplora.com",
        "hubs.erplora.com",
        "hub.erplora.com",
    ],
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
@pytest.mark.usefixtures("spa_manifest")
def test_every_page_has_a_csp_with_a_nonce_and_form_action_to_the_hubs(client):
    response = client.get("/launch")

    policy = response["Content-Security-Policy"]
    directives = {part.split()[0]: part.split()[1:] for part in policy.split("; ")}
    assert re.search(r"'nonce-[^']+'", " ".join(directives["script-src"]))
    assert "'strict-dynamic'" in directives["script-src"]
    # Google: «Continue with Google» posts allauth.headless's provider redirect, which answers 302 to
    # accounts.google.com, and `form-action` filters the whole redirect chain of a form post (ported
    # from ERPlora/saas, saas#945).
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


def test_no_page_may_create_the_policy_of_iconify():
    """The Iconify web component (and its `iconify` policy) loaded only on the template sign-in's pages:
    the SPA and the public web bake their icons, so nothing may create that policy any more."""
    assert "iconify" not in settings.SECURE_CSP["trusted-types"]
    assert "default" in settings.SECURE_CSP["trusted-types"]


# Production settings are read in a fresh interpreter: `config.settings` is evaluated once per
# process, from the environment and `saas-next/.env`. That interpreter ignores `saas-next/.env`
# (IGNORE_DOTENV), so a developer's file never leaks in and these tests always run.

SAAS_NEXT = Path(__file__).resolve().parents[2]
PRODUCTION_ENV = {
    "DEBUG": "False",
    "SECRET_KEY": "a-production-secret-key",
    "INTERNAL_SHARED_SECRET": "a-production-internal-secret",
    "FISCAL_DOCUMENTS_KEY": "2EBDB2KSnvz5lBG1RHG5ldNq34ZjWvGZ_t5r4wl5Mpw=",
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
        [
            sys.executable,
            "-c",
            f"{IGNORE_DOTENV}\nimport config.settings as s; print({expression})",
        ],
        cwd=SAAS_NEXT,
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_debug_is_off_unless_the_environment_turns_it_on():
    """A deploy that forgets DEBUG must not serve debug pages nor fall back to the local secrets:
    production is the default, development opts in (saas-next/.env, `DEBUG=True`)."""
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "DEBUG"}

    result = _settings_in_a_fresh_process(env, "s.DEBUG")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.parametrize(
    "missing", ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
)
def test_production_refuses_to_start_without_google_credentials(missing):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != missing}

    result = _settings_in_a_fresh_process(env, "s.GOOGLE_OAUTH_ENABLED")

    assert result.returncode != 0
    assert missing in result.stderr


def test_production_hands_google_an_https_callback():
    """Behind the load balancer the request arrives as http: the redirect_uri must still be https."""
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV, "s.GOOGLE_OAUTH_ENABLED, s.ACCOUNT_DEFAULT_HTTP_PROTOCOL"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["True", "https"]


def test_production_answers_only_on_erplora_com_and_wants_three_letter_hubs():
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV, "(s.ALLOWED_HOSTS, s.LIVE['hub_slug_min_length'])"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str((["erplora.com"], 3))


def test_production_sends_the_staff_to_hubs_erplora_com_without_serving_it():
    """`hubs.erplora.com` is the Hub's alone (ronda 13, PLAN §18): the SaaS only posts there."""
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV,
        "(s.HUB_ADMIN_CALLBACK_URL, [str(source) for source in s.SECURE_CSP['form-action']], s.ALLOWED_HOSTS)",
    )

    assert result.returncode == 0, result.stderr
    callback, form_action, allowed_hosts = ast.literal_eval(result.stdout.strip())
    assert callback == "https://hubs.erplora.com/auth/callback"
    assert "https://hubs.erplora.com" in form_action
    assert not validate_host("hubs.erplora.com", allowed_hosts)
    assert not validate_host("hub.erplora.com", allowed_hosts)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [({}, "test_saas_next"), ({"TEST_DB_NAME": "test_saas_l2a"}, "test_saas_l2a")],
)
def test_the_test_database_name_comes_from_the_environment(environment, expected):
    """Several sessions run pytest at once against the same Postgres: each one names its own test
    database (``TEST_DB_NAME``) so they do not drop each other's. The environment wins over
    saas-next/.env, so this runs in a fresh process even when that file exists."""
    base = {key: value for key, value in os.environ.items() if key != "TEST_DB_NAME"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.settings as s; print(s.DATABASES['default']['TEST']['NAME'])",
        ],
        cwd=SAAS_NEXT,
        env={**base, "DEBUG": "True", **environment},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_development_keeps_http_for_the_local_callback(settings):
    assert settings.ACCOUNT_DEFAULT_HTTP_PROTOCOL == "http"


def test_google_is_configured_as_in_todays_saas_plus_pkce(settings):
    google = settings.SOCIALACCOUNT_PROVIDERS["google"]

    assert google["SCOPE"] == ["profile", "email"]
    assert google["AUTH_PARAMS"] == {"access_type": "online"}
    assert google["OAUTH_PKCE_ENABLED"] is True
    # Google's own `email_verified` claim decides; no blanket «every Google email is verified».
    assert "VERIFIED_EMAIL" not in google
    assert settings.SOCIALACCOUNT_STORE_TOKENS is False
    assert settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION is True
    assert settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT is True


# The SPA (packages/live): Vite on 5174, the debug CSP open to it, the user as the scope.

VITE_DEV_SERVER = "http://localhost:5174"


def test_live_precedes_daphne_so_its_runserver_starts_vite_too():
    installed = settings.INSTALLED_APPS
    assert installed.index("live") < installed.index("daphne")
    assert {"ninja", "base", "accounts", "allauth.headless"} <= set(installed)


def module_folders(path: Path) -> list[str]:
    """The subfolders of ``path`` that hold an app of their own (an ``apps.py``), as hub-next's
    ``apps/<id>/`` modules do; ``migrations`` and ``tests`` are never one."""
    return sorted(
        child.name
        for child in path.iterdir()
        if child.is_dir()
        and child.name not in {"migrations", "tests"}
        and (child / "apps.py").is_file()
    )


def test_saas_next_apps_is_the_platform_app_of_the_catalog_not_a_folder_of_modules():
    """``saas-next/apps/`` is the platform app of the app catalog (round 16, PLAN §21.1 point 10,
    spec decision 18): the owner of the ``shared`` schema (``App``, ``AppDoc``) and of ``Module``,
    with ``label = "apps"`` and ``kind = "platform"``. It is not a folder of modules as hub-next's
    ``apps/<id>/`` (round 15, PLAN §20.2): the SaaS turns nothing on or off, so it has no modules
    and no subfolder of ``apps/`` is an app of its own."""
    config = django_apps.get_app_config("apps")

    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == ("apps", "apps", "platform")
    assert Path(config.path) == settings.BASE_DIR / "apps"
    assert module_folders(settings.BASE_DIR / "apps") == []


def test_a_subfolder_with_its_own_apps_py_is_a_folder_of_modules(tmp_path):
    """The guardrail above catches a module folder (positive) and ignores the rest (negative)."""
    (tmp_path / "inventory").mkdir()
    (tmp_path / "inventory" / "apps.py").write_text("")
    for name in ("migrations", "tests", "locale"):
        (tmp_path / name).mkdir()
    (tmp_path / "tests" / "apps.py").write_text("")

    assert module_folders(tmp_path) == ["inventory"]


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


# allauth.headless: the login API of the Vue pages, headless only (PLAN-SAAS §2).


def test_headless_serves_the_browser_client_only():
    assert settings.HEADLESS_CLIENTS == ("browser",)


def test_allauth_serves_no_template_page():
    """Every account page is a Vue page: allauth's template pages are gone (``accounts/tests/test_login.py``)."""
    assert settings.HEADLESS_ONLY is True


def test_the_specification_is_served_in_development_without_a_cdn_page():
    """allauth's openapi.html loads Redoc from a CDN, which the CSP blocks: only the YAML/JSON.
    Production does not serve it (``test_production_has_the_base_csp_and_no_dev_server``)."""
    assert settings.HEADLESS_SERVE_SPECIFICATION is True
    assert settings.HEADLESS_SPECIFICATION_TEMPLATE_NAME is None


def test_after_signing_in_the_person_lands_on_the_vue_launcher():
    assert settings.LOGIN_REDIRECT_URL == "/launch"


def test_the_mails_link_the_pages_of_the_spa():
    """allauth builds the links of its mails from HEADLESS_FRONTEND_URLS; each one is a route of the SPA
    (``accounts/tests/test_headless.py``). No confirmation link: the address is proven by a code."""
    assert settings.HEADLESS_FRONTEND_URLS == {
        "account_reset_password": "/password/reset",
        "account_reset_password_from_key": "/password/reset/key/{key}",
        # The launcher's «Create account» tab (FIX-LAUNCH-TABS).
        "account_signup": "/launch?tab=signup",
    }


# The public web (round 16, public/): its apps, middlewares and settings.


def test_the_public_web_is_installed_with_its_sitemaps_and_cookie_consent():
    installed = settings.INSTALLED_APPS
    assert "django.contrib.sitemaps" in installed
    # `public` first: its templates override django-cookie-consent's.
    assert installed.index("public") < installed.index("cookie_consent")


def test_the_public_middlewares_are_installed():
    middleware = settings.MIDDLEWARE
    assert middleware.index("public.csp.PublicCSPMiddleware") > middleware.index(
        "django.middleware.csp.ContentSecurityPolicyMiddleware"
    )
    assert "public.crawlers.NoIndexPrivatePathsMiddleware" in middleware
    assert "public.cookies.CleanCookiesMiddleware" in middleware


def test_every_template_knows_the_public_site():
    processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
    assert "public.context_processors.public_site" in processors


def test_every_template_knows_the_shells_colour_mode():
    """The template pages (errors, the public web) paint light or dark from the `theme` cookie
    (base/context_processors.py)."""
    processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
    assert "base.context_processors.theme" in processors


def test_no_template_reads_a_switch_of_the_retired_sign_in_page():
    """The sign-in is the SPA's: «Continue with Google» reads `googleEnabled` from spa-config
    (base/spa.py), so no template needs Google's switch nor the `next` its form posted."""
    processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
    assert not [processor for processor in processors if processor.startswith("accounts.")]


def test_development_takes_the_apps_images_from_the_local_hub():
    assert settings.HUB_STATIC_BASE_URL == "http://hubs.localhost:8000/static/"


def test_the_public_web_defaults():
    assert (settings.GA_MEASUREMENT_ID, settings.CLARITY_PROJECT_ID) == ("", "")
    assert settings.CONTACT_FORM_RATELIMIT == "10/h"
    assert settings.PUBLIC_HOST == "erplora.com"
    assert settings.INDEXNOW_KEY == "1e00b99c5f72af2baaba3e383f91725b"
    assert (settings.COOKIE_CONSENT_NAME, settings.COOKIE_CONSENT_MAX_AGE) == (
        "cookie_consent",
        31536000,
    )
    # A written promise of the legal terms: the exit package of a deleted hub lasts 90 days.
    assert settings.HUB_EXIT_PACKAGE_TTL_DAYS == 90


def test_the_app_downloads_and_the_stores_defaults():
    assert settings.DOWNLOADS_BUCKET == "erplora-saas"
    assert settings.APP_DOWNLOAD_PREFIX == "downloads/app/latest"
    assert settings.DOWNLOAD_URL_TTL == 300
    assert settings.MICROSOFT_STORE_APP_ID == ""
    assert settings.GOOGLE_PLAY_APP_ID == ""
    # The Google Play listing is live (2026-10-01): the default that does not lie.
    assert settings.GOOGLE_PLAY_LISTING_LIVE is True
    # A private S3 bucket on AWS, Ireland region; credentials from the task's role, never keys.
    assert settings.DOWNLOADS_REGION == "eu-west-1"
    assert settings.DOWNLOADS_ENDPOINT_URL == ""
    assert not any(name.startswith("HETZNER_") for name in dir(settings))


def test_development_cookies_need_no_https():
    assert settings.COOKIE_CONSENT_SECURE is False
    assert settings.LANGUAGE_COOKIE_SECURE is False


def test_production_takes_the_apps_images_from_hubs_erplora_com_and_secures_its_cookies():
    result = _settings_in_a_fresh_process(
        PRODUCTION_ENV,
        "(s.HUB_STATIC_BASE_URL, s.PUBLIC_HOST, s.COOKIE_CONSENT_SECURE, s.LANGUAGE_COOKIE_SECURE)",
    )

    assert result.returncode == 0, result.stderr
    assert ast.literal_eval(result.stdout.strip()) == (
        "https://hubs.erplora.com/static/",
        "erplora.com",
        True,
        True,
    )
