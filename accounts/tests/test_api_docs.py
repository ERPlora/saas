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
    assert '<div id="redoc-ui"></div>' in html
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
    assert re.search(r'<script nonce="[^"]+" src="/static/ninja/redoc\.standalone\.js', html)


def test_only_this_page_goes_without_trusted_types_and_its_search_runs_in_a_worker(client, ana):
    client.force_login(ana)

    policy = _csp(client.get(DOCS, HTTP_HOST=HOST))

    assert "require-trusted-types-for" not in policy
    assert "'strict-dynamic'" in policy["script-src"] and any(value.startswith("'nonce-") for value in policy["script-src"])
    assert policy["worker-src"] == ["'self'", "blob:"]
    assert policy["frame-ancestors"] == ["'none'"]
    assert policy["object-src"] == ["'none'"]


def test_it_speaks_spanish_when_the_schema_does_not_load(client, ana):
    client.force_login(ana)

    html = client.get(DOCS, HTTP_HOST=HOST, headers={"Accept-Language": "es"}).content.decode()

    assert "No hemos podido cargar la documentación de la API. Recarga la página para volver a intentarlo." in html


def test_the_schema_stays_open_for_postman_and_the_suites(client):
    response = client.get("/api/openapi.json", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ERPlora Cloud API"
