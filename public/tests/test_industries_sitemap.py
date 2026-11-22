"""The industries in the sitemap, in ``llms.txt`` and in the footer of every public page."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest

from public.sitemaps import SITEMAPS, IndustryDetailSitemap, StaticPagesSitemap
from public.tests.industry_pages import HOST, INDEX, make_business_type

pytestmark = [pytest.mark.django_db]


# --- Sitemap, llms.txt and footer ---------------------------------------------------------------


@pytest.fixture
def active_type(sector):
    return make_business_type(
        "hair_salon", name_en="Hair salon", name_es="Peluquería", sector=sector
    )


@pytest.fixture
def inactive_type(sector):
    return make_business_type(
        "retirado", name_en="Retired", sector=sector, is_active=False
    )


def _sitemap(client) -> str:
    response = client.get("/sitemap.xml", HTTP_HOST=HOST)
    assert response.status_code == 200
    return response.content.decode()


class TestTheDetailPagesAreAnnounced:
    def test_an_active_business_type_is_in_the_sitemap(self, client, active_type):
        assert "/industries/hair_salon/" in _sitemap(client), (
            "the page exists and answers, but the sitemap does not name it: published and invisible"
        )

    def test_the_index_is_still_there(self, client, active_type):
        """The details are added; the index is not replaced."""
        assert "/industries/</loc>" in _sitemap(client)


class TestOnlyWhatIsServed:
    def test_an_inactive_business_type_is_NOT_announced(
        self, client, active_type, inactive_type
    ):
        """Announcing a URL that answers 404 spends crawl budget and fills the reports with our own
        errors."""
        assert "/industries/retirado/" not in _sitemap(client)

    def test_every_announced_url_actually_answers_200(self, client, active_type):
        """A sitemap is a promise; this checks it end to end, by path (the host is the request's)."""
        locs = re.findall(r"<loc>([^<]+)</loc>", _sitemap(client))
        paths = [urlparse(url).path for url in locs if "/industries/" in url]
        assert paths, "no industries URL in the sitemap"
        for path in paths:
            assert client.get(path, HTTP_HOST=HOST).status_code == 200, (
                f"{path} is in the sitemap and does not answer 200"
            )


class TestTheyStayPanEuropean:
    def test_the_detail_page_does_not_talk_about_verifactu(self, client, active_type):
        """The industries are for ALL of Europe; VeriFactu is only Spanish."""
        body = (
            client.get("/industries/hair_salon/", HTTP_HOST=HOST)
            .content.decode()
            .lower()
        )
        assert "verifactu" not in body


def test_the_detail_sitemap_is_registered_and_works_without_a_request(
    settings, active_type, inactive_type
):
    """``indexnow_submit`` reads the sitemaps outside any request, on ``PUBLIC_HOST``."""
    settings.PUBLIC_HOST = "erplora.com"

    assert SITEMAPS["industries"] is IndustryDetailSitemap
    assert [url["location"] for url in IndustryDetailSitemap().get_urls()] == [
        "https://erplora.com/industries/hair_salon/"
    ]
    assert ("public:industries_index", 0.7) in StaticPagesSitemap.pages


def test_llms_txt_points_at_the_industries(client):
    body = client.get("/llms.txt", HTTP_HOST=HOST).content.decode()

    assert f"(https://{HOST}/industries/)" in body


def test_the_footer_links_to_the_industries(client):
    html = client.get(INDEX, HTTP_HOST=HOST).content.decode()

    assert 'href="/industries/"' in html[html.index("</main>") :]
