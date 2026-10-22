"""The public web's own CSP (spec §8.2), ported from ERPlora/saas ``apps/public/csp.py`` and
``apps/public/tests/test_csp_enforced.py`` (origin/develop c5ca8ca), adapted to the CSP of ``live``.

The account panel (the SPA) and the sign-in pages keep the global policy of ``live.csp``
(``'strict-dynamic'`` and Trusted Types). The public web's pages are server templates with no
dynamic script swap: no ``'strict-dynamic'`` (it would block an edge-injected script with no nonce)
and no Trusted Types (Ionic's ``ion-icon`` writes its SVG through an HTML sink).

Not ported: ``TestTheDefaultIsEnforce`` (``CSP_ENFORCE``) — saas-next has no report-only toggle, the
CSP is always enforced (``test_the_public_policy_is_enforced_not_reported``).
"""

import re

import pytest
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound

from public.csp import is_public, public_policy

ENFORCE_HEADER = "Content-Security-Policy"
REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"
HOST = "localhost:8001"

# Namespace `public` (robots.txt, llms.txt, sitemap.xml) and django-cookie-consent's routes, which
# have no namespace of their own (`cookie_consent_status` answers JSON, no template involved).
PUBLIC_PATHS = ("/robots.txt", "/llms.txt", "/sitemap.xml", "/cookies/status/")
CONTROL_PATH = "/robots.txt"
# Not the public web: the admin's login (a Django template) and the SPA's sign-in keep the global
# policy.
GLOBAL_PATHS = ("/admin/login/", "/launch")
# First segments the public web owns but whose pages do not exist (yet or ever): a real 404.
NONEXISTENT_PATHS = ("/company/contact/", "/pricing/does-not-exist/", "/developers/")


def _directives(policy: str) -> dict[str, list[str]]:
    return {part.split()[0]: part.split()[1:] for part in policy.split("; ")}


def _policy(client, path) -> str:
    """The served policy without its nonce, so two responses can be compared: the nonce changes on
    every response, and Django names it only when the page used it (a page with no script, as
    Django's own 404, has none)."""
    response = client.get(path, HTTP_HOST=HOST)
    policy = response.headers.get(ENFORCE_HEADER) or response.headers.get(
        REPORT_ONLY_HEADER, ""
    )
    assert policy, (
        f"{path} came back with no CSP header at all (status {response.status_code})"
    )
    return re.sub(r" 'nonce-[^']+'", "", policy)


@pytest.mark.django_db
def test_the_public_policy_is_enforced_not_reported(client):
    response = client.get(CONTROL_PATH, HTTP_HOST=HOST)

    assert ENFORCE_HEADER in response.headers
    assert REPORT_ONLY_HEADER not in response.headers


@pytest.mark.django_db
def test_the_public_policy_still_forbids_the_dangerous_directives(client):
    directives = _directives(_policy(client, CONTROL_PATH))

    assert "'unsafe-eval'" not in directives["script-src"]
    assert directives["base-uri"] == ["'self'"]
    assert directives["form-action"] == ["'self'"]
    assert directives["object-src"] == ["'none'"]
    assert directives["report-uri"] == ["/csp-report/"]


# The public web stopped loading anything from a CDN (OutfitKit from jsDelivr, icons from Iconify's
# API) and stopped charging (Stripe): spec §8.2, decision 16. Nothing loads those CDNs anywhere; Stripe
# is retired from the public web only: the panel's policy (the SPA's Store) carries Stripe's origins for
# the Embedded Checkout (`base/csp.py`, plan 2026-10-13 L2-D; PLAN-SAAS §3.6 point 17). reCAPTCHA, retired with
# them (ADR-0154), is back on every public form (Ioan, 2026-10-22): Google's `/recaptcha/` paths only
# (`test_the_public_policy_admits_googles_recaptcha`).
RETIRED_EVERYWHERE = (
    "cdn.jsdelivr.net",
    "api.iconify.design",
)
RETIRED_FROM_PUBLIC = ("stripe.com",)


@pytest.mark.parametrize("debug", [False, True])
def test_the_public_policy_names_no_retired_host(settings, debug):
    settings.DEBUG = debug
    policy = " ".join(" ".join(sources) for sources in public_policy().values())

    for host in (*RETIRED_EVERYWHERE, *RETIRED_FROM_PUBLIC):
        assert host not in policy


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "retired"),
    [
        *((path, (*RETIRED_EVERYWHERE, *RETIRED_FROM_PUBLIC)) for path in PUBLIC_PATHS),
        *((path, RETIRED_EVERYWHERE) for path in GLOBAL_PATHS),
    ],
)
@pytest.mark.usefixtures("spa_manifest")
def test_no_served_page_names_a_retired_host(client, path, retired):
    policy = _policy(client, path)

    for host in retired:
        assert host not in policy


def test_google_analytics_and_clarity_stay_behind_the_consent():
    """The tags load only after the analytical consent (templates); the policy lets them run."""
    policy = public_policy()

    assert {"www.googletagmanager.com", "*.clarity.ms"} <= set(policy["script-src"])
    assert {
        "*.google-analytics.com",
        "*.analytics.google.com",
        "*.clarity.ms",
        "c.bing.com",
    } <= set(policy["connect-src"])


def test_the_hubs_static_origin_may_serve_images(settings):
    """The apps' documentation images live on the Hub (spec decision 10); locally over http, which
    `https:` does not cover."""
    settings.HUB_STATIC_BASE_URL = "http://hubs.localhost:8000/static/"

    assert "http://hubs.localhost:8000" in public_policy()["img-src"]


def test_production_takes_the_hubs_static_origin_from_the_setting(settings):
    settings.HUB_STATIC_BASE_URL = "https://hubs.erplora.com/static/"

    img_src = public_policy()["img-src"]
    assert "https://hubs.erplora.com" in img_src
    assert "http://hubs.localhost:8000" not in img_src


def test_the_tauri_bridge_keeps_its_connection():
    """Without `ipc:` the Tauri app loses the hardware with no visible error (CLAUDE.md)."""
    assert public_policy()["connect-src"][:3] == [
        "'self'",
        "ipc:",
        "http://ipc.localhost",
    ]


def test_with_debug_the_vite_dev_server_may_serve_the_public_entry(settings):
    """No 'strict-dynamic' here, so the dev server's scripts need their own source too."""
    settings.DEBUG = True
    dev_server = settings.LIVE["spa"]["dev_server"]
    policy = public_policy()

    for directive in ("script-src", "connect-src", "style-src", "font-src", "img-src"):
        assert dev_server in policy[directive]
    assert "ws://localhost:5174" in policy["connect-src"]


def test_with_debug_the_public_policy_follows_the_vite_port(settings):
    """VITE_DEV_PORT=5224 (config/settings.py): the public pages open that Vite and its HMR socket, not 5174."""
    settings.DEBUG = True
    settings.LIVE = {
        **settings.LIVE,
        "spa": {**settings.LIVE["spa"], "dev_server": "http://localhost:5224"},
    }
    policy = public_policy()

    for directive in ("script-src", "connect-src", "style-src", "font-src", "img-src"):
        assert "http://localhost:5224" in policy[directive]
    assert "ws://localhost:5224" in policy["connect-src"]
    assert "localhost:5174" not in " ".join(" ".join(sources) for sources in policy.values())


def test_production_opens_nothing_to_a_dev_server(settings):
    settings.DEBUG = False
    joined = " ".join(" ".join(sources) for sources in public_policy().values())

    assert "localhost:5174" not in joined


def test_the_public_policy_is_a_fresh_dict_every_time():
    first = public_policy()
    first["script-src"].append("https://evil.example")

    assert "https://evil.example" not in public_policy()["script-src"]


@pytest.mark.django_db
@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_the_public_pages_do_not_get_strict_dynamic_nor_trusted_types(client, path):
    policy = _policy(client, path)

    assert "'strict-dynamic'" not in policy
    assert "require-trusted-types-for" not in policy


@pytest.mark.django_db
@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_the_public_pages_get_the_very_same_policy(client, path):
    """Whether a page is public is not a property of how its URL happens to be wired (saas#1559)."""
    assert _policy(client, path) == _policy(client, CONTROL_PATH)


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("path", GLOBAL_PATHS)
def test_the_sign_in_pages_and_the_panel_keep_the_global_policy(client, path):
    """The public policy must not widen to pages that never were the public web. (The test run
    builds its settings with DEBUG, whose global policy does not enforce Trusted Types; it still
    names the policies, which the public one never does.)"""
    policy = _policy(client, path)

    assert "'strict-dynamic'" in policy
    assert "trusted-types" in _directives(policy)
    assert policy != _policy(client, CONTROL_PATH)


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("path", NONEXISTENT_PATHS)
def test_an_unmatched_route_is_a_404_with_the_public_policy(client, path):
    """Django sets no ``resolver_match`` when no pattern matched; the 404 page is the public web's
    (saas#1827)."""
    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 404
    assert _policy(client, path) == _policy(client, CONTROL_PATH)


def test_no_resolver_match_and_404_is_public(rf):
    request = rf.get("/whatever-unmatched/")

    assert getattr(request, "resolver_match", None) is None
    assert is_public(request, HttpResponseNotFound()) is True


def test_no_resolver_match_but_200_stays_non_public(rf):
    """An early middleware short-circuit has no resolver_match either; it is not swept in."""
    assert is_public(rf.get("/whatever/"), HttpResponse(status=200)) is False


def test_without_a_response_an_unresolved_request_is_not_public(rf):
    assert is_public(rf.get("/whatever/")) is False


def test_the_public_middleware_runs_before_djangos_builds_the_header():
    """Listed after Django's CSP middleware, so its response hook runs first and leaves the
    override ready when Django's builds the header."""
    middleware = settings.MIDDLEWARE

    assert middleware.index("public.csp.PublicCSPMiddleware") > middleware.index(
        "django.middleware.csp.ContentSecurityPolicyMiddleware"
    )


def test_the_public_policy_admits_googles_recaptcha():
    """reCAPTCHA Enterprise on the contact form and the demo (live.recaptcha): Google's two script origins, its
    frames and its connection (the public pages enforce no Trusted Types)."""
    policy = public_policy()

    assert {"https://www.google.com/recaptcha/", "https://www.gstatic.com/recaptcha/"} <= set(policy["script-src"])
    assert policy["frame-src"] == ["'self'", "https://www.google.com/recaptcha/", "https://recaptcha.google.com/recaptcha/"]
    assert "https://www.google.com/recaptcha/" in policy["connect-src"]
    assert "trusted-types" not in policy


@pytest.mark.parametrize("debug", [False, True])
def test_google_is_admitted_only_under_its_recaptcha_paths(settings, debug):
    settings.DEBUG = debug
    google = [
        source
        for sources in public_policy().values()
        for source in map(str, sources)
        if "google.com" in source or "gstatic.com" in source
    ]

    assert google
    assert all(source.endswith("/recaptcha/") for source in google if "analytics" not in source)
