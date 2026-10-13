"""``/sitemap.xml`` (spec §8.2), ported from ERPlora/saas ``landing/sitemaps.py`` (origin/develop
c5ca8ca). It lists only pages that exist: each batch of the port adds its own to
``StaticPagesSitemap.pages`` (and the store its sitemaps to ``SITEMAPS``), and the guard below
fails the day an entry points to a page that does not answer 200.
"""

import re
from datetime import UTC, datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.tests.factories import make_app, make_doc
from public.crawlers import private_prefixes
from public.sitemaps import SITEMAPS, AppDetailSitemap, StaticPagesSitemap

HOST = "localhost:8001"


@pytest.fixture
def a_registered_page(monkeypatch):
    """A page in the static sitemap: llms.txt stands in for any public page."""
    monkeypatch.setattr(StaticPagesSitemap, "pages", (("public:llms_txt", 0.7),))


@pytest.mark.django_db
def test_the_sitemap_is_xml(client):
    response = client.get("/sitemap.xml", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    assert "<urlset" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("a_registered_page")
def test_a_page_is_listed_on_the_requests_host_over_https_with_its_priority(client):
    body = client.get("/sitemap.xml", HTTP_HOST=HOST).content.decode()

    assert "<loc>https://localhost:8001/llms.txt</loc>" in body
    assert "<priority>0.7</priority>" in body
    assert "<changefreq>monthly</changefreq>" in body


@pytest.mark.usefixtures("a_registered_page")
def test_without_a_request_the_host_is_the_public_one(settings):
    settings.PUBLIC_HOST = "erplora.com"
    sitemap = StaticPagesSitemap()

    assert [url["location"] for url in sitemap.get_urls()] == [
        "https://erplora.com/llms.txt"
    ]


def _locations():
    for sitemap_class in SITEMAPS.values():
        sitemap = sitemap_class(HOST)
        for item in sitemap.items():
            yield sitemap.location(item)


@pytest.mark.django_db
def test_every_listed_page_exists(client):
    """A sitemap entry is a promise to the crawler: it must answer 200."""
    for location in _locations():
        assert client.get(location, HTTP_HOST=HOST).status_code == 200, location


@pytest.mark.django_db
def test_no_listed_page_is_private():
    for location in _locations():
        assert not location.startswith(private_prefixes()), location


def test_the_sitemap_is_built_from_the_registry():
    # Each batch registers its section; the store's (L6) are tested in test_store.py.
    assert SITEMAPS["static"] is StaticPagesSitemap
    assert reverse("public:sitemap") == "/sitemap.xml"


def _lastmods(body: str) -> dict[str, str | None]:
    """``{loc: lastmod}`` of every ``<url>`` of the sitemap; ``None`` for one without a date."""
    entries = {}
    for url in re.findall(r"<url>(.*?)</url>", body, re.DOTALL):
        lastmod = re.search(r"<lastmod>([^<]+)</lastmod>", url)
        entries[re.search(r"<loc>([^<]+)</loc>", url).group(1)] = (
            lastmod.group(1) if lastmod else None
        )
    return entries


@pytest.mark.django_db
def test_an_apps_pages_are_dated_by_its_spanish_documentation(client):
    """Spec §8.2: ``lastmod`` of ``/apps/<id>/`` and its ``docs/`` = ``updated_at`` of the app's
    Spanish ``app_doc``; an app without documentation goes in undated."""
    invoice = make_app("invoice")
    make_doc(invoice, "es", updated_at=datetime(2026, 10, 1, 9, 30, tzinfo=UTC))
    make_app("inventory")

    lastmods = _lastmods(client.get("/sitemap.xml", HTTP_HOST=HOST).content.decode())

    assert lastmods[f"https://{HOST}/apps/invoice/"] == "2026-10-01"
    assert lastmods[f"https://{HOST}/apps/invoice/docs/"] == "2026-10-01"
    assert lastmods[f"https://{HOST}/apps/inventory/"] is None
    assert f"https://{HOST}/apps/inventory/docs/" not in lastmods


@pytest.mark.django_db
def test_the_apps_section_reads_the_catalog_at_once():
    """No read per app: the section costs the same with one app as with five."""
    make_doc(make_app("app_0"), "es")
    with CaptureQueriesContext(connection) as one_app:
        AppDetailSitemap(HOST).get_urls()
    for number in range(1, 5):
        make_doc(make_app(f"app_{number}"), "es")

    with CaptureQueriesContext(connection) as five_apps:
        assert len(AppDetailSitemap(HOST).get_urls()) == 10

    assert len(five_apps.captured_queries) == len(one_app.captured_queries)
