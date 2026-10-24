"""``/industries/`` and ``/industries/<slug>/``: the business types the product serves (spec §8.1).

Ported from ERPlora/saas ``apps/public/industries/tests/`` (origin/develop c5ca8ca):
``test_detail_answers_the_buyer_question.py`` (18), ``test_sitemap.py`` (5) and ``test_views.py`` (2).
What changed, and why:

* the taxonomy lives in ``hubs`` (plan §3.m) and the pages read it through ``hubs.sector.list`` and
  ``hubs.business_type.list``; the tests still create the rows with the ORM of ``hubs``;
* the apps block reads ``apps.app.list`` with the business type's ``vertical`` (spec §8.1, decision
  13): ONE list, «apps included out of the box», instead of «essential» (free) and «recommended»
  (paid) modules matched by sector or business type. Without a vertical there is no block (§5.3);
* the onward links point at ``/pricing/``, ``/apps/`` (the store, which replaces ``/modules/``,
  decision 19) and ``/features/``. ``/compliance/`` was out of the port (plan §7) and is back with its card (PUBLIC-F09, test_compliance.py);
* the cards are the ``ep-*`` partials (``ok-feature-card`` is gone, PLAN §16.11), so the «real link,
  not an undeclared slot» check looks for the ``<a class="ep-feature-card">`` itself;
* the footer control of ``test_the_link_check_ignores_the_footer`` reads ``/industries/``: it is the
  footer link of every public page this lot owns (``/pricing/`` arrives with L7).

The price of the entry plan comes from ``Plan`` through ``hubs.plan.list`` (``public`` imports no
model, plan §3.m): the cheapest plan a visitor can sign up for (``cheapest_slug``).
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from django.conf import settings
from django.db import DatabaseError
from django.urls import reverse

from apps.tests.factories import CUBE_SVG, make_app
from hubs.models import BusinessType, Plan, Sector
from public import industries
from public.sitemaps import SITEMAPS, IndustryDetailSitemap, StaticPagesSitemap
from public.templatetags import icons

pytestmark = [pytest.mark.django_db]

HOST = "localhost:8001"
INDEX = "/industries/"


def make_sector(code: str = "beauty", **fields) -> Sector:
    defaults = {"name_en": code.replace("_", " ").title(), "is_active": True}
    return Sector.objects.create(code=code, **{**defaults, **fields})


def make_business_type(code: str = "hair_salon", **fields) -> BusinessType:
    defaults = {"name_en": code.replace("_", " ").title(), "is_active": True}
    return BusinessType.objects.create(code=code, **{**defaults, **fields})


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


@pytest.fixture
def sector():
    return make_sector(
        "beauty",
        name_en="Beauty",
        name_es="Belleza",
        description_en="Salons and studios",
    )


@pytest.fixture
def salon(sector):
    """No description on purpose: the taxonomy usually has none, and the page still owes the reader
    an answer in its first two sentences."""
    return make_business_type(
        "hair_salon", name_en="Hair salon", name_es="Peluquería", sector=sector
    )


@pytest.fixture
def entry_plan():
    return Plan.objects.create(
        slug="entry-sentinel",
        name_en="Entry Sentinel",
        price_monthly=Decimal("29.99"),
        display_order=-20,
    )


def _page(client, slug="hair_salon", **headers):
    response = client.get(f"/industries/{slug}/", HTTP_HOST=HOST, **headers)
    assert response.status_code == 200
    return response


def _blocks(html: str) -> list[dict]:
    """Every JSON-LD block on the page, PARSED: a block that does not parse is not markup."""
    marker = '<script type="application/ld+json">'
    blocks, cursor = [], 0
    while (start := html.find(marker, cursor)) != -1:
        start += len(marker)
        end = html.index("</script>", start)
        blocks.append(json.loads(html[start:end]))
        cursor = end
    return blocks


def _main(html: str) -> str:
    """Only the page's own content: the footer links to /industries/ from EVERY page, so asserting
    against the whole document proves nothing."""
    return html[html.index("<main>") : html.index("</main>")]


def _of_type(html: str, wanted: str) -> dict:
    for block in _blocks(html):
        if block.get("@type") == wanted:
            return block
    raise AssertionError(f"no {wanted} JSON-LD on the page")


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
    """No degraded mode (spec §5.3): the taxonomy lives in the database every page depends on."""
    settings.DEBUG = False

    def broken(*args, **kwargs):
        raise DatabaseError("the database is gone")

    monkeypatch.setattr(industries, "run_operation_sync", broken)
    client.raise_request_exception = False

    response = client.get(INDEX, HTTP_HOST=HOST)

    assert response.status_code == 500
    assert "Something went wrong" in response.content.decode()


# --- The detail: the answer to the buyer's question (port of the 18) ---------------------------


def test_the_h1_asks_the_buyers_question_and_not_just_the_business_name(client, salon):
    html = _main(_page(client).content.decode())
    heading = html[html.index("<h1") : html.index("</h1>")]

    assert "Hair salon" in heading or "hair salon" in heading, (
        "the business type must still be named"
    )
    assert "POS" in heading and "ERP" in heading, (
        f"the H1 is still the bare catalogue label — nobody searches for it: {heading!r}"
    )


def test_the_heading_check_would_catch_the_bare_label(client, salon):
    """Control: prove the assertion above is not vacuous — a bare-label heading fails it."""
    bare = "<h1 class='ep-hero__title'>Hair salon</h1>"

    assert not ("POS" in bare and "ERP" in bare)


def test_the_lead_answers_before_any_marketing(client, salon, entry_plan):
    response = _page(client)
    lead = response.context["industry"]["lead"]

    assert lead, (
        "the taxonomy has no description for this type and the page said nothing"
    )
    assert "Hair salon" in lead or "hair salon" in lead
    assert lead in response.content.decode(), "the lead is computed but never rendered"


def test_the_lead_is_also_the_meta_description(client, salon, entry_plan):
    response = _page(client)
    html = response.content.decode()
    lead = response.context["industry"]["lead"]

    assert f'name="description" content="{lead}"' in html, (
        "meta description still comes from the (usually empty) taxonomy field"
    )


def test_the_offer_price_comes_from_the_plan_table(no_plans, client, salon, entry_plan):
    offer = _of_type(_page(client).content.decode(), "SoftwareApplication")["offers"]

    assert offer["price"] == "29.99", (
        f"the industry page advertises {offer['price']} and Plan says 29.99"
    )
    assert offer["priceCurrency"] == "EUR"


def test_a_second_price_in_the_plan_table_moves_the_page(no_plans, client, salon, entry_plan):
    """Positive control for the test above: if the page were still hardcoding a number, changing
    the cheapest plan would not move it."""
    Plan.objects.create(
        slug="cheaper-sentinel",
        name_en="Cheaper",
        price_monthly=Decimal("9.99"),
        display_order=-30,
    )

    offer = _of_type(_page(client).content.decode(), "SoftwareApplication")["offers"]

    assert offer["price"] == "9.99"


def test_with_no_listable_plan_the_page_advertises_no_price_at_all(no_plans, client, salon):
    """Advertising a price we do not charge is worse than none: the old template emitted
    ``"price": "0"`` unconditionally."""
    block = _of_type(_page(client).content.decode(), "SoftwareApplication")

    assert "offers" not in block, (
        f"a price was invented with no Plan in the table: {block.get('offers')}"
    )


def test_internal_and_upgrade_only_plans_are_not_the_advertised_entry_price(
    no_plans, client, salon, entry_plan
):
    """The advertised price must be one a visitor can actually buy — the same door `/pricing/`
    lists through."""
    Plan.objects.create(
        slug="internal-sentinel",
        name_en="Internal",
        price_monthly=Decimal("0.01"),
        display_order=-99,
        internal_only=True,
    )
    Plan.objects.create(
        slug="upgrade-sentinel",
        name_en="Upgrade",
        price_monthly=Decimal("0.02"),
        display_order=-98,
        upgrade_only=True,
    )

    offer = _of_type(_page(client).content.decode(), "SoftwareApplication")["offers"]

    assert offer["price"] == "29.99"


def test_the_lead_and_the_faq_state_the_entry_price(no_plans, client, salon, entry_plan):
    response = _page(client)
    lead = response.context["industry"]["lead"]
    price_answers = [
        str(item["answer"])
        for item in response.context["faq_items"]
        if item["key"] == "price"
    ]

    assert "Plans start at €29.99 per month per hub, VAT excluded." in lead
    assert len(price_answers) == 1
    assert price_answers[0].startswith("Plans start at €29.99")


@pytest.mark.parametrize(
    ("language", "answer"),
    [
        (
            "en",
            "Plans start at €29.99 per month per hub, VAT excluded. One subscription covers the "
            "whole business — every device and every user in it — and every plan includes all the "
            "apps; you never pay per transaction.",
        ),
        (
            "es",
            "Los planes empiezan en 29.99 € al mes por hub, IVA no incluido. Una suscripción cubre "
            "todo el negocio —todos sus dispositivos y todos sus usuarios— y todos los planes "
            "incluyen todas las apps; nunca pagas por transacción.",
        ),
    ],
)
def test_the_price_answer_puts_every_app_on_every_plan(
    no_plans, client, salon, entry_plan, language, answer
):
    """Ronda 2026-10-24b (PLAN §32): it said «the premium apps are included in the paid plans»."""
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = _page(client)
    (price,) = [
        str(item["answer"]) for item in response.context["faq_items"] if item["key"] == "price"
    ]

    assert price == answer
    assert "premium" not in response.content.decode().lower()


def test_a_free_entry_plan_is_announced_as_free_and_permanent(no_plans, client, salon):
    Plan.objects.create(
        slug="free", name_en="Free", price_monthly=Decimal("0"), display_order=0
    )

    response = _page(client)

    assert (
        "The Free plan is free and permanent, with no card."
        in response.context["industry"]["lead"]
    )
    offer = _of_type(response.content.decode(), "SoftwareApplication")["offers"]
    assert offer["price"] == "0.00"


def test_a_quote_in_the_business_name_does_not_break_the_markup(
    client, sector, entry_plan
):
    make_business_type(
        "quoted", name_en='Salon "Le Chic" & Co </script>', sector=sector
    )

    html = _page(client, "quoted").content.decode()

    block = _of_type(
        html, "SoftwareApplication"
    )  # _blocks raises if any block is invalid JSON
    assert 'Salon "Le Chic" & Co </script>' in block["name"], (
        f"the name reached the JSON-LD HTML-escaped instead of JSON-escaped: {block['name']!r}"
    )


def test_naive_interpolation_would_have_broken_it(client):
    """Control: the name above really is hostile — pasted into a JSON string it is invalid."""
    naive = '{"name": "Salon "Le Chic" & Co </script>"}'

    with pytest.raises(json.JSONDecodeError):
        json.loads(naive)


def test_every_faq_question_is_both_visible_and_marked_up(client, salon, entry_plan):
    response = _page(client)
    html = response.content.decode()
    items = response.context["faq_items"]

    assert len(items) >= 3, "an FAQ of one question is not an FAQ"

    marked_up = {q["name"] for q in _of_type(html, "FAQPage")["mainEntity"]}
    assert marked_up == {str(item["question"]) for item in items}, (
        "the markup and the page disagree"
    )
    for item in items:
        assert str(item["question"]) in html, (
            f"{item['question']!r} is marked up but not on the page"
        )
        assert str(item["answer"]) in html, (
            f"the answer to {item['question']!r} is markup-only"
        )


def test_the_faq_names_the_business_type_it_is_answering_about(
    client, salon, entry_plan
):
    questions = " ".join(
        str(item["question"]) for item in _page(client).context["faq_items"]
    )

    assert "hair salon" in questions.lower(), (
        "a generic FAQ answers nobody's actual question"
    )


@pytest.mark.parametrize("target", ["/pricing/", "/apps/", "/features/"])
def test_the_page_links_onward(client, salon, entry_plan, target):
    assert f'href="{target}' in _main(_page(client).content.decode()), (
        f"no internal link to {target} in the page's own content"
    )


@pytest.mark.parametrize("target", ["/pricing/", "/apps/", "/features/"])
def test_each_onward_link_is_a_real_link_and_not_a_slot_that_does_not_exist(
    client, salon, entry_plan, target
):
    """The old `ok-feature-card` declared no `footer` slot, so an `<a slot="footer">` was never
    rendered. The port's card is the link itself: an `<a class="ep-feature-card">` around the tile."""
    main = _main(_page(client).content.decode())

    assert f'<a class="ep-feature-card" href="{target}"' in main, (
        f"{target} is not the href of a feature card"
    )
    assert 'slot="footer"' not in main


def test_the_link_check_ignores_the_footer(client, salon, entry_plan):
    """Control: the footer links to /industries/ on every public page, so the assertions above
    would pass on an untouched template if they read the whole document."""
    html = _page(client).content.decode()

    assert 'href="/industries/"' in html[html.index("</main>") :], (
        "the footer stopped linking to /industries/"
    )
    assert 'href="/industries/"' not in _main(html)


def test_the_new_copy_stays_pan_european(client, salon, entry_plan):
    """Same contract as `TestTheyStayPanEuropean`, restated where the new copy is written so it
    cannot be reintroduced by an FAQ answer or a link label."""
    assert "verifactu" not in _page(client).content.decode().lower()


def test_the_new_copy_is_translated_to_spanish(client, salon, entry_plan):
    """English is the source string, Spanish a shipped translation: the H1 and the FAQ come out
    different from their English source. `LocaleMiddleware` picks the language per request, so the
    page is asked for in Spanish the way a Spanish reader's browser asks for it."""
    english = _page(client).context["industry"]["headline"]

    spanish_response = _page(client, headers={"accept-language": "es"})
    spanish = spanish_response.context["industry"]["headline"]
    faq_es = [str(item["question"]) for item in spanish_response.context["faq_items"]]

    assert spanish != english, f"the H1 is untranslated: {spanish!r}"
    assert "Software TPV" in spanish
    assert "peluquería" in spanish, "the business type is named in Spanish"
    assert any("¿" in question for question in faq_es), (
        f"the FAQ is untranslated: {faq_es}"
    )


def test_the_translation_check_is_looking_at_a_string_that_can_change(
    client, salon, entry_plan
):
    """Control: the assertion above compares two renders, so prove the English one is what we
    think it is — otherwise `spanish != english` could be true for the wrong reason."""
    assert (
        _page(client).context["industry"]["headline"].startswith("POS and ERP software")
    )


# --- The detail: which slug answers -------------------------------------------------------------


def test_a_retired_code_is_sent_on_for_good_to_its_replacement(client, salon):
    """``peluqueria`` was folded into ``hair_salon`` (saas#2099): an indexed URL keeps working."""
    response = client.get("/industries/peluqueria/", HTTP_HOST=HOST)

    assert response.status_code == 301
    assert response["Location"] == "/industries/hair_salon/"


def test_a_code_in_another_case_is_sent_to_the_canonical_url(client, salon):
    response = client.get("/industries/Hair_Salon/", HTTP_HOST=HOST)

    assert response.status_code == 301
    assert response["Location"] == "/industries/hair_salon/"


def test_an_unknown_or_inactive_business_type_is_a_404(client, sector):
    make_business_type("closed", sector=sector, is_active=False)

    assert client.get("/industries/closed/", HTTP_HOST=HOST).status_code == 404
    assert client.get("/industries/nope/", HTTP_HOST=HOST).status_code == 404


def test_the_url_names_resolve():
    assert reverse("public:industries_index") == "/industries/"
    assert (
        reverse("public:industries_detail", kwargs={"slug": "hair_salon"})
        == "/industries/hair_salon/"
    )


# --- The detail: the apps a business of its vertical comes with (port of test_views.py) ---------


def test_detail_lists_the_listed_apps_of_the_business_types_vertical(client):
    """Port of ``test_detail_recommends_modules_from_business_type_and_sector``: the modules came
    from M2M links to the sector and the business type, split into free and paid. The catalog now
    says which verticals each app serves (``verticals``), and the page lists, in one block, the
    listed apps of the business type's vertical (spec §8.1)."""
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
    # Every plan includes all the apps (PLAN §32): the flagged one too, no «Free» against «paid».
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
    assert "Apps included out of the box" not in response.content.decode()


# --- L8: the page looks like today's ------------------------------------------------------------


def test_a_vertical_with_no_listed_app_says_its_apps_are_on_the_way(client, sector):
    """The old page said «In preparation · Recommended modules are coming soon.» when it had
    nothing to recommend; the port left a gap between the hero and the FAQ (L8). Only with a
    vertical: without one there is nothing to prepare and no block at all (spec §5.3)."""
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
    """L8: the old band said «Start your Hair Salon with ERPlora», the name as it is; the port
    lower-cased it like the question of the H1 («… for your hair salon»)."""
    band = _main(_page(client, headers=headers).content.decode())
    band = band[band.index('class="ep-cta-band') :]

    assert f'<h2 class="ep-cta-band__title">{heading}</h2>' in band


def test_the_faq_is_the_bare_accordion_of_the_pricing_page(client, salon, entry_plan):
    """L8: the old FAQ was a bare ``ion-accordion``, the one /pricing/ still has and that looks as
    it did; the port gave it the help centre's ``ep-accordion`` (a bold question in a padded card)."""
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


# --- Sitemap, llms.txt and footer (port of test_sitemap.py) -------------------------------------


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
        """The industries are for ALL of Europe; VeriFactu is only Spanish (Ioan, 27/08)."""
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
