"""``/industries/`` and ``/industries/<slug>/``: the business types the product serves.

The pages read the taxonomy of ``hubs`` through ``hubs.sector.list`` and ``hubs.business_type.list``; the tests
create the rows with the ORM of ``hubs``. The apps block reads ``apps.app.list`` with the business type's
``vertical``: ONE list, «apps made for your <business>»; without a vertical there is no block. The onward links point
at ``/pricing/``, ``/apps/`` (the store), ``/features/`` and ``/compliance/``. The cards are the ``ep-*`` partials,
so the «real link, not an undeclared slot» check looks for the ``<a class="ep-feature-card">`` itself.

The price of the entry plan comes from ``Plan`` through ``hubs.plan.list`` (``public`` imports no model): the
cheapest plan a visitor can sign up for (``cheapest_slug``).
"""

from __future__ import annotations

import logging
import re

import pytest
from django.db import DatabaseError

from public import industries
from public.templatetags import icons
from public.tests.industry_pages import HOST, INDEX, _main, make_business_type, make_sector

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def baked(monkeypatch):
    """The real baked icons plus the ones a test names: the page paints only baked icons."""
    real = icons.load_icons()
    extra: dict[str, dict[str, str]] = {}
    monkeypatch.setattr(icons, "load_icons", lambda: {**real, **extra})

    def bake(*keys: str) -> None:
        for key in keys:
            extra[key] = {
                "body": f'<path data-icon="{key}"/>',
                "viewBox": "0 0 512 512",
            }

    return bake


# --- The index ----------------------------------------------------------------------------------


def test_the_index_lists_every_active_business_type_with_a_link_to_its_page(
    client, sector
):
    make_business_type("hair_salon", name_en="Hair salon", sector=sector)
    make_business_type(
        "retired", name_en="Retired type", sector=sector, is_active=False
    )

    response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.status_code == 200
    main = _main(response.content.decode())
    assert 'href="/industries/hair_salon/"' in main
    assert "Hair salon" in main
    assert "Retired type" not in main
    assert response.context["total_count"] == 1


def test_index_exposes_each_sector_icon(client, baked):
    baked("ion:restaurant-outline", "ion:storefront-outline", "ion:pizza-outline")
    hospitality = make_sector(
        "hospitality", name_en="Hospitality", icon="ion:restaurant-outline"
    )
    retail = make_sector("retail", name_en="Retail", icon="ion:storefront-outline")
    make_business_type(
        "pizzeria", name_en="Pizzeria", sector=hospitality, icon="ion:pizza-outline"
    )
    make_business_type("bakery", name_en="Bakery", sector=retail)

    response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.context["sectors"][0]["icon"] == "ion:restaurant-outline"
    html = response.content.decode()
    assert 'data-icon="ion:restaurant-outline"' in html, (
        "the sector chip paints its icon"
    )
    assert 'data-icon="ion:pizza-outline"' in html, (
        "the business type card paints its icon"
    )


def test_each_sector_chip_counts_its_active_business_types(client):
    hospitality = make_sector("hospitality", display_order=1)
    retail = make_sector("retail", display_order=2)
    make_business_type("bar", sector=hospitality)
    make_business_type("pizzeria", sector=hospitality)
    make_business_type("closed", sector=hospitality, is_active=False)
    make_business_type("bakery", sector=retail)

    sectors = client.get(INDEX, HTTP_HOST=HOST).context["sectors"]

    assert [(entry["code"], entry["type_count"]) for entry in sectors] == [
        ("hospitality", 2),
        ("retail", 1),
    ]


def test_the_sector_filter_appears_with_two_sectors_and_its_script_carries_the_nonce(
    client,
):
    make_business_type("bar", sector=make_sector("hospitality"))
    make_business_type("bakery", sector=make_sector("retail"))

    html = client.get(INDEX, HTTP_HOST=HOST).content.decode()

    assert 'class="public-filter-bar' in html
    assert 'data-sector="hospitality"' in html and 'data-sector="retail"' in html
    assert 'class="industry-card" data-sector="hospitality"' in html
    nonce = re.search(r'<script nonce="([^"]+)">\s*function filterBySector', html)
    assert nonce, "the filter script has no CSP nonce: the public CSP blocks it"


def test_a_single_sector_needs_no_filter(client, sector, salon):
    assert "public-filter-bar" not in client.get(INDEX, HTTP_HOST=HOST).content.decode()


def test_without_business_types_the_index_says_so(client):
    response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.status_code == 200
    main = _main(response.content.decode())
    assert "ep-empty-state" in main
    assert "No business types yet" in main
    assert "industry-card" not in main


def test_the_index_closes_with_the_store_and_contact(client, sector, salon):
    main = _main(client.get(INDEX, HTTP_HOST=HOST).content.decode())

    assert 'href="/apps/"' in main, (
        "the CTA that pointed at the marketplace now opens the store"
    )
    assert 'href="/contact/"' in main
    assert "marketplace" not in main.lower()


def test_the_index_speaks_spanish(client, sector, salon):
    response = client.get(INDEX, HTTP_HOST=HOST, headers={"accept-language": "es"})

    main = _main(response.content.decode())
    assert "Peluquería" in main, "the business type is named in the visitor's language"
    assert "Belleza" in main
    assert "ERPlora para tu negocio." in main


def test_a_taxonomy_icon_that_is_not_baked_paints_the_default_and_warns(
    client, settings, caplog
):
    """The taxonomy is data: an icon typed in the admin that no template cites is not in the baked
    JSON. ``{% icon %}`` refuses an unbaked icon with DEBUG (a template mistake); a row of data must
    not take the page down, so the page paints the default and says so in the log."""
    settings.DEBUG = True
    hospitality = make_sector("hospitality", icon="mdi:not-a-baked-icon")
    make_business_type(
        "pizzeria", sector=hospitality, icon="mdi:not-a-baked-icon-either"
    )

    with caplog.at_level(logging.WARNING, logger="public.industries"):
        response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.context["sectors"][0]["icon"] == industries.DEFAULT_ICON
    assert response.context["industries"][0]["icon"] == industries.DEFAULT_ICON
    assert "mdi:not-a-baked-icon" in caplog.text
    assert "mdi:not-a-baked-icon-either" in caplog.text


def test_a_bare_icon_name_is_an_ionicon_and_a_blank_one_the_default(client, baked):
    baked("ion:cafe-outline")
    hospitality = make_sector("hospitality", icon="cafe-outline")
    make_business_type("cafeteria", sector=hospitality, icon="")

    response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.context["sectors"][0]["icon"] == "ion:cafe-outline"
    assert response.context["industries"][0]["icon"] == industries.DEFAULT_ICON


def test_only_a_hex_colour_reaches_the_style_attribute(client, sector):
    make_business_type("bar", sector=sector, color="#ff6b35")
    make_business_type("pub", sector=sector, color="red;x:url(y)")

    cards = {
        entry["slug"]: entry["color"]
        for entry in client.get(INDEX, HTTP_HOST=HOST).context["industries"]
    }

    assert cards == {"bar": "#ff6b35", "pub": ""}


def test_a_database_error_answers_the_public_500(client, monkeypatch, settings):
    """No degraded mode: the taxonomy lives in the database every page depends on."""
    settings.DEBUG = False

    def broken(*args, **kwargs):
        raise DatabaseError("the database is gone")

    monkeypatch.setattr(industries, "run_operation_sync", broken)
    client.raise_request_exception = False

    response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.status_code == 500
    assert "Something went wrong" in response.content.decode()
