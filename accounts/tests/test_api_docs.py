"""``/api/docs``: the documentation of the SaaS's API, for signed-in accounts (ACCOUNTS-G105, ACCOUNTS-G13; ACCOUNTS-F34).

The reference is django-ninja's ReDoc, read only (the old Swagger's «Try it out» changed real data without a word,
SAAS_DASHBOARD-F197), served from our own static files with the response's nonce: nothing from a CDN (PLAN §14). Its
script writes HTML from strings, so this page alone goes without Trusted Types, and its search runs in a ``blob:``
worker. Signed out, the sign-in, which comes back here. The schema (``/api/openapi.json``) stays open, as Stripe's and
GitHub's are: Postman imports it and every app's suite reads it.
"""

import re

import pytest

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
DOCS = "/api/docs"


def _csp(response) -> dict[str, list[str]]:
    header = response.headers["Content-Security-Policy"]
    return {name: values for name, *values in (part.split() for part in header.split(";") if part.strip())}


def test_signed_out_it_is_the_sign_in_that_comes_back_here(client):
    response = client.get(DOCS, HTTP_HOST=HOST)

    assert (response.status_code, response.url) == (302, "/launch?next=/api/docs")


def test_an_api_key_alone_opens_nothing_here(client):
    response = client.get(DOCS, HTTP_HOST=HOST, HTTP_AUTHORIZATION="Bearer erps_live_" + "a" * 48)

    assert (response.status_code, response.url) == (302, "/launch?next=/api/docs")


def test_signed_in_it_is_the_reference_of_this_api(client, ana):
    client.force_login(ana)

    response = client.get(DOCS, HTTP_HOST=HOST)

    html = response.content.decode()
    assert response.status_code == 200
    assert '<div id="redoc-ui" lang="en"></div>' in html
    assert '"/api/openapi.json"' in html


def test_every_script_carries_the_nonce_and_comes_from_here(client, ana):
    client.force_login(ana)

    response = client.get(DOCS, HTTP_HOST=HOST)

    html = response.content.decode()
    nonce = re.search(r"'nonce-([^']+)'", response.headers["Content-Security-Policy"]).group(1)
    scripts = re.findall(r"<script\b[^>]*>", html)
    assert len(scripts) >= 2
    for tag in scripts:
        assert f'nonce="{nonce}"' in tag or 'type="application/json"' in tag, tag
    assert "https://" not in html and "http://" not in html.replace("http://www.w3.org", "")
    assert re.search(r'<script nonce="[^"]+" src="/api/docs/redoc\.js"', html)


def test_its_redoc_loads_nothing_from_redoclys_cdn(client):
    """ReDoc's side menu loads Redocly's logo from its CDN on every page, with no option to turn it off: the policy
    refused it, but the browser said so in the console and reported it to ``/csp-report/`` on every visit. The copy
    served here has no address of it, and the logo hides itself as when it cannot load."""
    response = client.get("/api/docs/redoc.js", HTTP_HOST=HOST)

    script = b"".join(response.streaming_content) if response.streaming else response.content
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/javascript")
    assert b"cdn.redoc.ly" not in script
    assert b"Redoc" in script and len(script) > 500_000


def test_ninjas_redoc_still_has_exactly_the_one_logo_address_the_copy_blanks():
    """An upgrade of django-ninja that moves or adds an outside address to ReDoc fails here, not in a browser."""
    from pathlib import Path

    from django.contrib.staticfiles import finders

    from accounts.api_docs import REDOCLY_LOGO

    bundle = Path(finders.find("ninja/redoc.standalone.js")).read_text(encoding="utf-8")
    assert bundle.count(REDOCLY_LOGO) == 1
    assert re.findall(r"https://cdn\.[\w.]+", bundle) == [REDOCLY_LOGO.rsplit("/redoc/", 1)[0]]


def test_only_this_page_goes_without_trusted_types_and_its_search_runs_in_a_worker(client, ana, settings, spa_manifest):
    """Production's policy (the tests run with the debug one, which has no Trusted Types): the panel keeps it."""
    from live.csp import base_policy

    settings.SECURE_CSP = base_policy()
    client.force_login(ana)

    policy = _csp(client.get(DOCS, HTTP_HOST=HOST))
    panel = _csp(client.get("/account/profile", HTTP_HOST=HOST))

    assert panel["require-trusted-types-for"] == ["'script'"]
    assert "require-trusted-types-for" not in policy
    assert "'strict-dynamic'" in policy["script-src"] and any(value.startswith("'nonce-") for value in policy["script-src"])
    assert policy["worker-src"] == ["'self'", "blob:"]
    assert policy["frame-ancestors"] == ["'none'"]
    assert policy["object-src"] == ["'none'"]


def test_it_speaks_spanish_when_the_schema_does_not_load(client, ana):
    client.force_login(ana)

    html = client.get(DOCS, HTTP_HOST=HOST, headers={"Accept-Language": "es"}).content.decode()

    assert "No hemos podido cargar la documentación de la API. Recarga la página para volver a intentarlo." in html


def test_the_reference_says_it_is_in_english_on_a_page_in_spanish(client, ana):
    # The reference is the API's own words (its paths, fields and descriptions), in English as Stripe's and GitHub's
    # are; the page around it (its title, its failure) speaks the visitor's language. A reader of the page in Spanish is
    # told the reference is English, not left to read English words as Spanish.
    client.force_login(ana)

    html = client.get(DOCS, HTTP_HOST=HOST, headers={"Accept-Language": "es"}).content.decode()

    assert '<html lang="es">' in html
    assert '<div id="redoc-ui" lang="en"></div>' in html


def test_the_schema_stays_open_for_postman_and_the_suites(client):
    response = client.get("/api/openapi.json", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ERPlora Cloud API"
