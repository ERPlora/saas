"""URLconf of saas-next: Django's own prefixes first (allauth's headless API, Google's redirect URI, the jump
to a hub, the internal redeem, the API, admin, health), then the SPA for every other path."""

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
    `home` stays the project's way to reverse `/` (the public web's navbar, footer and error pages)."""
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
        ("/hub-login/", "hub_login"),
        ("/launch/", "launch"),
        ("/internal/auth/redeem", "internal_auth_redeem"),
        ("/internal/hubs/0199c3a0-0000-7000-8000-000000000001/representation", "internal_hub_representation"),
        ("/internal/representation/model", "internal_representation_model"),
        ("/csp-report/", "csp-report"),
        ("/auth/google/callback/", "google_callback"),
        ("/_allauth/browser/v1/auth/login", "login"),
        ("/_allauth/browser/v1/auth/signup", "signup"),
        ("/_allauth/browser/v1/auth/session", "current_session"),
        ("/_allauth/browser/v1/auth/provider/redirect", "redirect_to_provider"),
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
    response = client.get("/launch", HTTP_HOST=HOST)

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

    html = client.get("/launch", HTTP_HOST=HOST).content.decode()

    assert 'src="http://localhost:5174/static/spa/@vite/client"' in html
    assert 'src="http://localhost:5174/static/spa/frontend/main.ts"' in html


@pytest.mark.django_db
def test_the_debug_shell_loads_from_the_vite_of_vite_dev_port(client, settings):
    """VITE_DEV_PORT=5224 (config/settings.py) moves the dev shell's scripts to that Vite, never 5174."""
    settings.DEBUG = True
    settings.LIVE = {
        **settings.LIVE,
        "spa": {**settings.LIVE["spa"], "dev_server": "http://localhost:5224"},
    }

    html = client.get("/launch", HTTP_HOST=HOST).content.decode()

    assert 'src="http://localhost:5224/static/spa/@vite/client"' in html
    assert 'src="http://localhost:5224/static/spa/frontend/main.ts"' in html
    assert "localhost:5174" not in html


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


# /webhooks/ is Django's (Stripe's single webhook, `/webhooks/stripe/`, PLAN-SAAS §4; lot L2-B): the SPA
# must never swallow it. Stripe's POST reaches billing's view (an unsigned one is refused, 400), anything
# else is 405; never the SPA's shell. Any other path under it is a plain 404.


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("method, status", [("get", 405), ("post", 400)])
def test_the_webhooks_prefix_is_reserved_for_django(client, settings, method, status):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

    response = getattr(client, method)("/webhooks/stripe/", HTTP_HOST=HOST)

    assert response.status_code == status
    assert not is_shell(response)


def test_stripes_webhook_is_billings():
    assert resolve("/webhooks/stripe/").url_name == "stripe_webhook"


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
def test_another_path_under_webhooks_is_not_the_spa(client):
    response = client.get("/webhooks/other/", HTTP_HOST=HOST)

    assert response.status_code == 404
    assert not is_shell(response)


def test_readyz_is_a_django_route():
    assert resolve("/readyz").url_name == "readyz"


# ACCOUNTS-G30: the admin of erplora.com says it is ERPlora's (the old SaaS's ADMIN_SITE_HEADER, _TITLE and
# _INDEX_TITLE), never «Django administration».


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "index_title"), [("en", "Administration"), ("es", "Administración")]
)
def test_the_admin_bears_erploras_name(client, django_user_model, language, index_title):
    staff = django_user_model.objects.create_superuser(email="staff@example.com", password="x", language=language)
    client.force_login(staff)

    page = client.get("/admin/", HTTP_ACCEPT_LANGUAGE=language).content.decode()

    assert f"<title>{index_title} | ERPlora Admin</title>" in page
    assert ">ERPlora Cloud</a>" in page
    assert "Django" not in page
