"""``/industries/<slug>/``: the apps a business of its vertical comes with and the page's look."""

from __future__ import annotations

import pytest

from apps.tests.factories import CUBE_SVG, make_app
from public.tests.industry_pages import _main, _page, make_business_type, make_sector

pytestmark = [pytest.mark.django_db]


# --- The detail: the apps a business of its vertical comes with ---------------------------------


def test_detail_lists_the_listed_apps_of_the_business_types_vertical(client):
    """The catalog says which verticals each app serves (``verticals``), and the page lists, in one block, the listed
    apps of the business type's vertical."""
    hospitality = make_sector("hospitality", name_en="Hospitality")
    make_business_type(
        "pizzeria", name_en="Pizzeria", sector=hospitality, vertical="restaurant"
    )
    make_app("kitchen", name_en="Kitchen Display", verticals=["restaurant"])
    make_app(
        "tables", name_en="Tables", verticals=["restaurant", "hotel"], premium=True
    )
    make_app("bookings", name_en="Bookings", verticals=["hair_salon"])
    make_app("draft_menu", name_en="Draft Menu", verticals=["restaurant"], listed=False)

    response = _page(client, "pizzeria")

    assert [app["id"] for app in response.context["apps"]] == ["kitchen", "tables"]
    main = _main(response.content.decode())
    assert "Kitchen Display" in main and "Tables" in main
    assert "Draft Menu" not in main
    assert "Bookings" not in main


def test_each_app_card_links_to_the_store_and_paints_the_cleaned_icon(client):
    make_business_type("pizzeria", vertical="restaurant")
    make_app(
        "kitchen",
        name_en="Kitchen Display",
        summary_en="Orders on a kitchen screen.",
        verticals=["restaurant"],
    )
    make_app("tables", name_en="Tables", verticals=["restaurant"], premium=True)

    main = _main(_page(client, "pizzeria").content.decode())

    assert '<a class="ep-product-card" href="/apps/kitchen/">' in main
    assert "Orders on a kitchen screen." in main
    assert CUBE_SVG.split(">", 1)[0] in main, (
        "the app's icon is painted inline, not escaped"
    )
    assert "&lt;svg" not in main
    # Every plan includes all the apps: the flagged one too, no «Free» against «paid».
    assert main.count('<span class="ep-product-card__price">Included in every plan</span>') == 2
    assert "Included in the paid plans" not in main
    assert '<span class="ep-product-card__price">Free</span>' not in main


def test_without_a_vertical_there_is_no_apps_block(client, salon):
    make_app("bookings", name_en="Bookings", verticals=["hair_salon"])

    response = _page(client)

    assert response.context["apps"] == []
    assert "ep-product-card" not in _main(response.content.decode())


def test_a_vertical_with_no_listed_app_shows_no_apps_block(client, sector):
    make_business_type("barber_shop", sector=sector, vertical="hair_salon")

    response = _page(client, "barber_shop")

    assert response.context["apps"] == []
    assert "Apps made for your" not in response.content.decode()


# --- The page's look: an empty apps block, the closing band and the FAQ -------------------------


def test_a_vertical_with_no_listed_app_says_its_apps_are_on_the_way(client, sector):
    """With nothing to list, the block says the apps are on the way instead of leaving a gap between the hero and the
    FAQ. Only with a vertical: without one there is nothing to prepare and no block at all."""
    make_business_type("barber_shop", sector=sector, vertical="hair_salon")

    main = _main(_page(client, "barber_shop").content.decode())

    assert '<span class="ep-eyebrow">In preparation</span>' in main
    assert "Recommended apps are coming soon." in main
    assert (
        "We are preparing the best starting configuration for this business type."
        in main
    )


def test_the_apps_on_the_way_are_announced_in_spanish(client, sector):
    make_business_type("barber_shop", sector=sector, vertical="hair_salon")

    response = _page(client, "barber_shop", headers={"accept-language": "es"})
    main = _main(response.content.decode())

    assert '<span class="ep-eyebrow">En preparación</span>' in main
    assert "Las apps recomendadas llegarán pronto." in main
    assert "Estamos preparando la mejor configuración de partida" in main


def test_without_a_vertical_nothing_is_said_to_be_on_the_way(client, salon):
    assert "In preparation" not in _main(_page(client).content.decode())


def test_with_apps_nothing_is_said_to_be_on_the_way(client):
    make_business_type("pizzeria", vertical="restaurant")
    make_app("kitchen", name_en="Kitchen Display", verticals=["restaurant"])

    assert "In preparation" not in _main(_page(client, "pizzeria").content.decode())


@pytest.mark.parametrize(
    ("headers", "heading"),
    [
        ({}, "Start your Hair salon with ERPlora"),
        ({"accept-language": "es"}, "Arranca tu Peluquería con ERPlora"),
    ],
)
def test_the_closing_band_names_the_business_type_as_the_taxonomy_writes_it(
    client, salon, headers, heading
):
    """The band says «Start your Hair Salon with ERPlora», the name as it is, not lower-cased like the question of
    the H1 («… for your hair salon»)."""
    band = _main(_page(client, headers=headers).content.decode())
    band = band[band.index('class="ep-cta-band') :]

    assert f'<h2 class="ep-cta-band__title">{heading}</h2>' in band


def test_the_faq_is_the_bare_accordion_of_the_pricing_page(client, salon, entry_plan):
    """The FAQ is a bare ``ion-accordion``, as on /pricing/, not the help centre's ``ep-accordion`` (a bold question
    in a padded card)."""
    main = _main(_page(client).content.decode())
    faq = main[main.index('id="faq"') :]
    faq = faq[: faq.index("</section>")]

    assert '<ion-item slot="header">' in faq
    assert '<div class="ion-padding" slot="content">' in faq
    assert "ep-accordion" not in faq


def test_the_lead_counts_the_listed_apps_of_the_catalog(client, salon):
    make_app("kitchen", verticals=["restaurant"])
    make_app("bookings", verticals=["hair_salon"])
    make_app("draft", listed=False)

    assert "2 in the catalogue" in _page(client).context["industry"]["lead"]


def test_the_lead_says_no_count_with_an_empty_catalog(client, salon):
    """A lead that boasts «0 apps» is worse than a shorter one."""
    lead = _page(client).context["industry"]["lead"]

    assert "in the catalogue" not in lead
    assert "You turn on only the apps you need, and they share one database" in lead


def test_the_detail_offers_its_sector_siblings(client, sector, salon):
    make_business_type("barber_shop", name_en="Barbershop", sector=sector)
    make_business_type("bar", name_en="Bar", sector=make_sector("hospitality"))

    response = _page(client)

    assert [entry["slug"] for entry in response.context["related"]] == ["barber_shop"]
    assert 'href="/industries/barber_shop/"' in _main(response.content.decode())


def test_the_detail_closes_with_sign_up_and_the_store(client, salon):
    main = _main(_page(client).content.decode())

    assert 'href="/launch"' in main
    assert "Browse apps" in main
    assert "marketplace" not in main.lower()
