"""URLconf of saas-next: Django's own prefixes first (allauth and its headless API, the jump to a hub,
the internal redeem, the API, admin, health), then the SPA for every other path."""

import json

import pytest
from django.urls import resolve, reverse
from live.live_view import live_stream

HOST = "localhost:8001"
SHELL_MARK = '<div id="app"></div>'


def is_shell(response) -> bool:
    return SHELL_MARK in response.content.decode(errors="replace")


def test_healthz_answers_without_the_database(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
def test_the_root_is_the_public_landing_not_the_launcher(client):
    """Plan §3.c: the landing takes `/` (L7); until then it redirected to `/launch`. The name
    `home` stays the project's way to reverse `/` (allauth's templates, the error pages)."""
    response = client.get("/", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert not is_shell(response)
    assert resolve("/").view_name == "public:home"
    assert reverse("home") == "/"


def test_the_django_launcher_address_leads_to_the_vue_launcher(client):
    """``/launch/`` keeps answering (bookmarks, LOGIN_REDIRECT_URL of old sessions): the page is the SPA's."""
    response = client.get("/launch/")

    assert (response.status_code, response.url) == (302, "/launch")


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/accounts/login/", "account_login"),
        ("/accounts/logout/", "account_logout"),
        ("/hub-login/", "hub_login"),
        ("/launch/", "launch"),
        ("/internal/auth/redeem", "internal_auth_redeem"),
        ("/csp-report/", "csp-report"),
        ("/auth/google/login/", "google_login"),
        ("/auth/google/callback/", "google_callback"),
        ("/accounts/3rdparty/", "socialaccount_connections"),
        ("/accounts/3rdparty/login/cancelled/", "socialaccount_login_cancelled"),
        ("/accounts/3rdparty/login/error/", "socialaccount_login_error"),
        ("/_allauth/browser/v1/auth/login", "login"),
        ("/_allauth/browser/v1/auth/session", "current_session"),
        # The public web (public/urls.py) and its cookie consent, before the SPA's catch-all.
        ("/robots.txt", "robots_txt"),
        ("/set-language/", "set_language"),
        ("/cookies/", "cookie_consent_cookie_group_list"),
    ],
)
def test_routes(path, name):
    assert resolve(path).url_name == name


@pytest.mark.django_db
def test_the_admin_is_mounted(client):
    response = client.get("/admin/")

    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/login/error",
        "/launch",
        "/launchpad",
        "/password/reset",
        "/signup",
        "/accountsx",
        "/apiary",
    ],
)
def test_spa_paths_get_the_shell(client, path):
    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert is_shell(response)


@pytest.mark.django_db
# A 404 of the public web renders its page, which links the Vite build.
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize(
    "path",
    [
        "/api/nope",
        "/internal/nope",
        "/static/nope.js",
        "/csp-report/x",
        "/accounts/nope/",
        "/auth/nope",
        "/hub-login/nope",
        "/_allauth/nope",
        "/admin/nope/",
        # The public web's segments, served now or by a later batch, and the retired ones.
        "/pricing/nope/",
        "/help/nope/",
        "/developers/",
        "/marketplace/",
    ],
)
def test_django_prefixes_never_get_the_shell(client, path):
    response = client.get(path, HTTP_HOST=HOST)

    # 301: `/marketplace/` moved for good to the store, `/apps/` (decision 19).
    assert response.status_code in (301, 302, 404)
    assert not is_shell(response)


@pytest.mark.django_db
def test_an_unknown_api_path_is_the_json_error_envelope(client):
    response = client.get("/api/nope", HTTP_HOST=HOST)

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not found"}}


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
def test_the_built_shell_links_the_vite_build_with_nonces(client):
    response = client.get("/login", HTTP_HOST=HOST)

    html = response.content.decode()
    csp = response["Content-Security-Policy"]
    nonce = csp.split("'nonce-", 1)[1].split("'", 1)[0]
    assert (
        f'<script type="module" src="/static/spa/assets/main-abc123.js" nonce="{nonce}">'
        in html
    )
    assert (
        f'<link rel="modulepreload" href="/static/spa/assets/vendor-789.js" nonce="{nonce}">'
        in html
    )
    assert '<link rel="stylesheet" href="/static/spa/assets/main-def456.css">' in html


@pytest.mark.django_db
def test_the_debug_shell_loads_from_the_saas_vite_dev_server(client, settings):
    """Port 5174: hub-next's Vite owns 5173 and both run at once in development."""
    settings.DEBUG = True

    html = client.get("/login", HTTP_HOST=HOST).content.decode()

    assert 'src="http://localhost:5174/static/spa/@vite/client"' in html
    assert 'src="http://localhost:5174/static/spa/frontend/main.ts"' in html


def test_api_live_is_the_live_stream_and_wins_over_the_api():
    assert resolve("/api/live").func is live_stream


@pytest.mark.django_db
def test_api_live_without_a_session_is_the_401_envelope(client):
    response = client.get("/api/live", HTTP_HOST=HOST)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_csp_report(client):
    response = client.post(
        "/csp-report/",
        json.dumps({"csp-report": {"violated-directive": "script-src"}}),
        content_type="application/json",
    )

    assert response.status_code == 204


# /webhooks/ is Django's (Stripe's single webhook, `/webhooks/stripe/`, PLAN-SAAS §4 and block 4): the
# SPA must never swallow it. Until block 4 mounts the route, Stripe's POST gets a plain 404, not the
# SPA's 405 (it only answers GET/HEAD) nor its shell.


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("method", ["get", "post"])
def test_the_webhooks_prefix_is_reserved_for_django(client, method):
    response = getattr(client, method)("/webhooks/stripe/", HTTP_HOST=HOST)

    assert response.status_code == 404
    assert not is_shell(response)


def test_readyz_is_a_django_route():
    assert resolve("/readyz").url_name == "readyz"
