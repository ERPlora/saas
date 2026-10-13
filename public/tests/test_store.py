"""The app store of the public web: ``/apps/``, ``/apps/<id>/`` and ``/apps/<id>/docs/`` (spec §5,
§8.1–§8.3, decisions 17 and 19).

The store reads the catalog the Hub registers in ``shared.app`` through the operations of apps
(``apps.app.list``, ``apps.app.get``, ``apps.app.doc``): the rows below are set up with
``apps/tests/factories.py``, as the Hub's ``register_apps`` would write them.

Ported and adapted from ERPlora/saas (origin/develop c5ca8ca):

- ``modules/tests/test_detail_docs_from_db.py`` (3): the documentation is the markdown of
  ``shared.app_doc``, rendered by ``apps.app.doc`` (it was README/CHANGELOG on the Module row). There
  is no changelog any more (spec §8.1), so that case became «no changelog, reviews, tiers or payment».
- ``modules/tests/test_detail_install_cta.py`` (16): the button follows who is looking. The three
  audiences are two now: the SaaS no longer links a hub's own apps page (the Hub turns apps on, the
  panel picks the hub), so a visitor is offered «Start free» (the sign-in, where the account is
  created) and a customer «Go to dashboard» (the launcher). The tombstone cases are gone with the
  publication states: an unlisted app is a 404 (spec §9, ``test_module_detail_serves_a_tombstone_
  not_a_hole.py`` is not ported).
- ``tests/unit/modules/test_module_detail_structured_data.py`` (18), to the JSON-LD of spec §8.2:
  ``0`` for a free app; a premium one at the cheapest paid plan's monthly price (L7), none without one;
  tiers, intervals, one-time and pay-as-you-go prices are gone with ``ModuleTier``; the author is
  always ERPlora (every app is ours); the block stays valid JSON.
- ``tests/unit/modules/test_required_modules_card.py`` (4): the «Required apps» card, one linked
  ``ion-item`` per listed app with its icon and its translated access pill.
- ``tests/unit/modules/test_marketplace_and_solutions_es_titles.py`` (5): without the solutions
  half (``/solutions/`` is a 301 now). There is no «Related Modules» section any more, so the title
  is checked against its own Spanish, not against that one.
- ``landing/tests/test_llms_txt.py``: the apps section of ``llms.txt``, from the listed apps.
"""

import ast
import json
import logging
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext

from accounts.handoff import LAUNCHER
from apps.tests.factories import CUBE_SVG, make_app, make_doc
from hubs.models import BusinessType
from public import seo, sitemaps
from public.sitemaps import SITEMAPS

pytestmark = pytest.mark.django_db

STORE_PY = Path(settings.BASE_DIR) / "public" / "store.py"
JSON_LD = '<script type="application/ld+json">'
SPANISH = {"HTTP_ACCEPT_LANGUAGE": "es-ES,es;q=0.9"}
RETIRED_PATHS = ("/marketplace/", "/solutions/", "/modules/")


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def get_html(client, path, status=200, **headers) -> str:
    response = client.get(path, **headers)
    assert response.status_code == status, (path, response.status_code)
    return response.content.decode()


def section_titles(html: str) -> list[str]:
    return [
        text_of(title)
        for title in re.findall(
            r'<h2 class="ep-store__group-title">(.*?)</h2>', html, re.S
        )
    ]


def cards(html: str) -> list[str]:
    return re.findall(r'<a class="ep-product-card".*?</a>', html, re.S)


def card_of(html: str, app_id: str) -> str:
    (card,) = [card for card in cards(html) if f'href="/apps/{app_id}/"' in card]
    return card


def card_ids(html: str) -> list[str]:
    return re.findall(r'<a class="ep-product-card" href="/apps/([^/"]+)/">', html)


def hero_of(html: str) -> str:
    begin = html.index('<section class="ep-hero')
    return html[begin : html.index("</section>", begin)]


@pytest.fixture
def catalog():
    """Four listed apps in three categories, and a retired one."""
    return {
        "invoice": make_app(
            "invoice",
            name_en="Invoices",
            name_es="Facturas",
            summary_en="Bill your customers.",
            summary_es="Factura a tus clientes.",
            description_en="Invoices with VeriFactu.",
            description_es="Facturas con VeriFactu.",
            category="sales",
            verticals=["hair_salon"],
        ),
        "inventory": make_app(
            "inventory",
            name_en="Stock",
            name_es="Almacén",
            summary_en="Count what you have.",
            summary_es="Cuenta lo que tienes.",
            category="catalog",
        ),
        "tables": make_app(
            "tables",
            name_en="Tables",
            name_es="Mesas",
            summary_en="Seat your guests.",
            summary_es="Sienta a tus clientes.",
            category="restaurant",
            requires=["inventory", "loyalty"],
        ),
        "whatsapp_inbox": make_app(
            "whatsapp_inbox",
            name_en="WhatsApp Inbox",
            name_es="Bandeja de WhatsApp",
            summary_en="Answer your chats.",
            summary_es="Responde tus chats.",
            category="organization",
            premium=True,
        ),
        "loyalty": make_app(
            "loyalty",
            name_en="Loyalty",
            name_es="Fidelización",
            category="people",
            listed=False,
        ),
    }


# --- The list: /apps/ ----------------------------------------------------------------------------


def test_the_store_lists_each_listed_app_as_a_card(client, catalog):
    html = get_html(client, "/apps/")

    card = card_of(html, "invoice")
    assert "<svg" in card and "<path" in card  # the icon, inline
    assert "Sales, payments and tax" in card  # its category
    assert '<h3 class="ep-product-card__name">Invoices</h3>' in card
    assert "Bill your customers." in card
    assert '<span class="ep-product-card__price">Free</span>' in card
    assert 'class="ep-product-card__badge"' not in card


def test_a_premium_app_carries_the_premium_badge_and_is_included_in_the_paid_plans(
    client, catalog
):
    """Decision 17: a premium app is not sold on its own, it comes with the paid plans."""
    card = card_of(get_html(client, "/apps/"), "whatsapp_inbox")

    assert '<span class="ep-product-card__badge">Premium</span>' in card
    assert "Included in the paid plans" in card


def test_an_unlisted_app_is_never_in_the_store(client, catalog):
    html = get_html(client, "/apps/")

    assert "loyalty" not in card_ids(html)
    assert "Loyalty" not in text_of(html)
    get_html(client, "/apps/loyalty/", status=404)
    get_html(client, "/apps/loyalty/docs/", status=404)


def test_the_apps_are_grouped_by_category_in_the_order_of_live_meta(client, catalog):
    html = get_html(client, "/apps/")

    assert section_titles(html) == [
        "Sales, payments and tax 1",
        "Catalog and stock 1",
        "Restaurant 1",
        "Organization and communication 1",
    ]
    assert card_ids(html) == ["invoice", "inventory", "tables", "whatsapp_inbox"]


def test_a_spanish_visitor_reads_the_store_in_spanish(client, catalog):
    html = get_html(client, "/apps/", **SPANISH)

    assert section_titles(html)[0] == "Venta, cobro y fiscalidad 1"
    card = card_of(html, "invoice")
    assert "Facturas" in card and "Factura a tus clientes." in card
    assert '<span class="ep-product-card__price">Gratis</span>' in card
    assert "Incluida en los planes de pago" in card_of(html, "whatsapp_inbox")


def test_the_search_finds_apps_by_name_and_summary(client, catalog):
    assert card_ids(get_html(client, "/apps/?q=stock")) == ["inventory"]
    assert card_ids(get_html(client, "/apps/?q=chats")) == ["whatsapp_inbox"]


def test_the_category_filter(client, catalog):
    html = get_html(client, "/apps/?category=restaurant")

    assert card_ids(html) == ["tables"]
    assert section_titles(html) == ["Restaurant 1"]


@pytest.mark.parametrize(
    ("premium", "expected"),
    [("1", ["whatsapp_inbox"]), ("0", ["invoice", "inventory", "tables"])],
)
def test_the_premium_filter(client, catalog, premium, expected):
    assert card_ids(get_html(client, f"/apps/?premium={premium}")) == expected


def test_the_filters_combine(client, catalog):
    assert card_ids(get_html(client, "/apps/?q=s&category=catalog&premium=0")) == [
        "inventory"
    ]


@pytest.mark.parametrize(
    "query", ["?category=kitchen", "?premium=maybe", "?category=&premium=", "?q=%20"]
)
def test_a_filter_it_does_not_understand_is_ignored(client, catalog, query):
    """Spec §5.1: an old or mistyped link still lists the apps, never a 422 or an empty page."""
    assert card_ids(get_html(client, f"/apps/{query}")) == [
        "invoice",
        "inventory",
        "tables",
        "whatsapp_inbox",
    ]


def test_the_filter_links_keep_the_other_filters(client, catalog):
    html = get_html(client, "/apps/?q=s&premium=0")

    category_bar = html[html.index('aria-label="Filter by category"') :]
    assert 'href="/apps/?q=s&amp;category=catalog&amp;premium=0"' in category_bar
    assert 'href="/apps/?q=s&amp;premium=0"' in category_bar  # «All»
    access_bar = html[html.index('aria-label="Filter by access"') :]
    # The active access filter turns off; the other one replaces it.
    assert 'href="/apps/?q=s"' in access_bar
    assert 'href="/apps/?q=s&amp;premium=1"' in access_bar


def test_the_active_filters_are_marked_and_the_search_keeps_its_text(client, catalog):
    html = get_html(client, "/apps/?q=stock&category=catalog")

    assert re.search(
        r'<a class="ep-store-filters__chip" href="/apps/\?q=stock&amp;category=catalog" aria-current="true">',
        html,
    )
    assert re.search(r'<ion-searchbar[^>]*name="q"[^>]*value="stock"', html)
    # The search keeps the category it was typed under.
    form = html[html.index('<form class="ep-store-search"') :]
    form = form[: form.index("</form>")]
    assert '<input type="hidden" name="category" value="catalog">' in form


def test_an_app_of_a_category_this_saas_does_not_know_is_listed_without_a_section(
    client, catalog, caplog
):
    """Spec §5.3: the Hub went ahead of this SaaS's live.meta; the app is not lost."""
    make_app("kitchen_display", name_en="Kitchen Display", category="kitchen")

    with caplog.at_level(logging.WARNING, logger="apps.queries"):
        html = get_html(client, "/apps/")

    card = card_of(html, "kitchen_display")
    assert "ep-product-card__category" not in card
    assert card_ids(html)[-1] == "kitchen_display"
    assert len(section_titles(html)) == 4  # no section of its own
    assert "kitchen_display (kitchen)" in caplog.text
    assert card_ids(get_html(client, "/apps/?category=kitchen")) != ["kitchen_display"]


def test_the_icon_is_painted_clean_or_falls_back(client):
    make_app(
        "risky",
        icon_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" onload="alert(1)">'
            '<script>alert(2)</script><path d="M1 1h10"/></svg>'
        ),
    )
    make_app("blank", icon_svg="")

    html = get_html(client, "/apps/")

    risky = card_of(html, "risky")
    assert '<path d="M1 1h10"' in risky
    assert "onload" not in risky and "<script" not in risky and "alert" not in risky
    # The fallback, ion:apps-outline: nine rounded squares.
    assert card_of(html, "blank").count("<rect") == 9


def test_the_page_title_and_hero_count_the_apps(client, catalog):
    html = get_html(client, "/apps/")

    assert "<title>Apps · ERPlora</title>" in html
    assert "4 apps" in hero_of(html)
    assert '<meta name="robots"' not in html


def test_without_any_listed_app_the_store_says_so_and_is_not_indexed(client):
    """Spec §5.3: a new database, before any release of the Hub is registered."""
    make_app("retired", listed=False)

    response = client.get("/apps/?q=anything")
    html = response.content.decode()

    assert response.status_code == 200
    assert "No apps published yet." in html
    assert '<meta name="robots" content="noindex">' in html
    assert "Clear filters" not in html
    assert cards(html) == []


def test_the_empty_store_in_spanish(client):
    html = get_html(client, "/apps/", **SPANISH)

    assert "Todavía no hay apps publicadas." in html


def test_filters_without_results_offer_to_clear_them(client, catalog):
    html = get_html(client, "/apps/?q=zzz-nothing&premium=1")

    assert cards(html) == []
    assert "No app matches your search." in html
    assert "Clear filters" in html
    assert 'href="/apps/"' in html[html.index("ep-empty-state") :]
    # The store has apps: it stays indexable.
    assert '<meta name="robots"' not in html


def test_filters_without_results_in_spanish(client, catalog):
    html = get_html(client, "/apps/?q=zzz-nothing", **SPANISH)

    assert "Ninguna app coincide con tu búsqueda." in html
    assert "Quitar filtros" in html


# --- The app page: /apps/<id>/ (the «Overview» tab) ----------------------------------------------


def test_the_app_page_shows_its_overview(client, catalog):
    html = get_html(client, "/apps/invoice/")
    hero = hero_of(html)

    assert "<title>Invoices · ERPlora apps</title>" in html
    assert '<h1 class="ep-hero__title">Invoices</h1>' in hero
    assert "Bill your customers." in hero
    assert "Sales, payments and tax" in hero
    assert "<svg" in hero  # the icon, inline
    assert "Invoices with VeriFactu." in html  # the description
    assert re.search(r'aria-current="page"[^>]*>\s*Overview', html)
    details = text_of(html[html.index("Details") :])
    assert "Category Sales, payments and tax" in details
    assert "Access Free" in details


def test_a_premium_app_page_says_it_comes_with_the_paid_plans(client, catalog):
    html = get_html(client, "/apps/whatsapp_inbox/")

    assert "Access Included in the paid plans" in text_of(html[html.index("Details") :])
    assert "Premium" in hero_of(html)
    with translation.override("es"):
        assert gettext("Included in the paid plans") == "Incluida en los planes de pago"


def test_the_app_page_names_the_business_types_it_is_built_for(client, catalog):
    BusinessType.objects.create(
        code="hair_salon",
        name_en="Hair salon",
        name_es="Peluquería",
        vertical="hair_salon",
    )
    BusinessType.objects.create(
        code="barbershop",
        name_en="Barbershop",
        name_es="Barbería",
        vertical="hair_salon",
    )
    BusinessType.objects.create(
        code="bar", name_en="Bar", name_es="Bar", vertical="restaurant"
    )

    english = text_of(get_html(client, "/apps/invoice/"))
    spanish = text_of(get_html(client, "/apps/invoice/", **SPANISH))

    assert "Built for Barbershop, Hair salon" in english
    assert "Pensada para Barbería, Peluquería" in spanish
    assert "Bar," not in english
    # An app with no vertical has no such row.
    assert "Built for" not in text_of(get_html(client, "/apps/inventory/"))


def test_an_unknown_app_is_a_404_of_the_public_web(client, catalog):
    html = get_html(client, "/apps/nope/", status=404)

    assert 'class="ep-navbar"' in html


def test_the_app_page_has_no_reviews_changelog_tiers_nor_payment(client, catalog):
    """Spec §8.1: what the marketplace had and the store does not."""
    html = get_html(client, "/apps/whatsapp_inbox/")
    visible = text_of(re.sub(r"<script\b.*?</script>", "", html, flags=re.S)).lower()

    for gone in ("review", "changelog", "rating", "buy for", "cart", "/month", "tier"):
        assert not re.search(rf"\b{re.escape(gone)}", visible), gone


# The button (port of test_detail_install_cta.py)


def test_a_visitor_is_offered_to_start_free(client, catalog):
    hero = hero_of(get_html(client, "/apps/invoice/"))

    assert "Start free" in hero
    assert 'href="/accounts/login/"' in hero
    assert f'href="{LAUNCHER}"' not in hero
    assert "Create your free account" in hero


def test_a_customer_with_a_session_goes_to_the_dashboard(client, catalog, ana):
    client.force_login(ana)

    response = client.get("/apps/invoice/")
    hero = hero_of(response.content.decode())

    assert "Go to dashboard" in hero
    assert f'href="{LAUNCHER}"' in hero
    assert "Start free" not in hero
    assert 'href="/accounts/login/"' not in hero
    assert "Cookie" in response.headers.get("Vary", "")


def test_the_button_on_a_free_app_too(client, catalog, ana):
    """The old page left a signed-in visitor of a free module with no action at all."""
    client.force_login(ana)

    assert "<ion-button" in hero_of(get_html(client, "/apps/inventory/"))


def test_the_button_is_translated(client, catalog, ana):
    hero = hero_of(get_html(client, "/apps/invoice/", **SPANISH))
    assert "Empieza gratis" in hero
    assert "Actívala desde tu Hub" in hero

    client.force_login(ana)
    assert "Ir al panel" in hero_of(get_html(client, "/apps/invoice/", **SPANISH))


# The «Required apps» card (port of test_required_modules_card.py)


def required_card(html: str) -> str:
    begin = html.index('<ion-card class="ep-store-required"')
    return html[begin : html.index("</ion-card>", begin)]


def rows(card: str) -> list[str]:
    return re.findall(r"<ion-item\b.*?</ion-item>", card, re.S)


def test_each_listed_required_app_is_a_linked_row_with_icon_name_and_access(
    client, catalog
):
    card = required_card(get_html(client, "/apps/tables/"))

    assert re.search(r"<ion-list\b", card)
    inventory, loyalty = rows(card)
    opening = re.match(r"<ion-item\b[^>]*>", inventory).group(0)
    assert 'href="/apps/inventory/"' in opening
    assert re.search(r"\bbutton\b", opening)
    assert re.search(r'<span slot="start"[^>]*>\s*<svg', inventory)
    assert (
        text_of(re.search(r"<ion-label>(.*?)</ion-label>", inventory, re.S).group(1))
        == "Stock"
    )
    assert re.search(r'<span slot="end">\s*<span class="ep-status-pill', inventory)
    assert "Free" in text_of(inventory)
    # A required app that is not listed: its name, and no page to link to.
    assert "href" not in loyalty
    assert "Loyalty" in text_of(loyalty)


@pytest.mark.parametrize(
    ("headers", "title", "free"),
    [({}, "Required apps", "Free"), (SPANISH, "Apps necesarias", "Gratis")],
)
def test_the_required_apps_card_is_translated(client, catalog, headers, title, free):
    card = required_card(get_html(client, "/apps/tables/", **headers))

    assert re.search(rf"<ion-card-title>\s*{title}\s*</ion-card-title>", card)
    assert free in text_of(rows(card)[0])


def test_an_app_without_requirements_has_no_required_card(client, catalog):
    assert "ep-store-required" not in get_html(client, "/apps/invoice/")


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_required_apps_title_is_its_own(language):
    """Port of saas#2635: the title said «related», and a visitor installed without them."""
    with translation.override(language):
        title = gettext("Required apps")
    assert title == ("Apps necesarias" if language == "es" else "Required apps")


# JSON-LD (port of test_module_detail_structured_data.py, to spec §8.2)


def application(client, app_id: str) -> dict:
    html = get_html(client, f"/apps/{app_id}/")
    blocks = []
    cursor = 0
    while (start := html.find(JSON_LD, cursor)) != -1:
        start += len(JSON_LD)
        end = html.index("</script>", start)
        blocks.append(json.loads(html[start:end]))
        cursor = end
    (block,) = [b for b in blocks if b.get("@type") == "SoftwareApplication"]
    return block


def test_a_free_app_is_offered_at_zero_on_its_page(client, catalog):
    block = application(client, "invoice")

    assert block["name"] == "Invoices"
    assert block["description"] == "Invoices with VeriFactu."
    assert block["url"] == "https://testserver/apps/invoice/"
    assert block["offers"] == {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "EUR",
        "url": "https://testserver/apps/invoice/",
        "availability": "https://schema.org/InStock",
    }


def test_a_premium_app_is_offered_at_the_cheapest_paid_plan(client, catalog):
    """Decision 17: a premium app is included in the paid plans, so its offer is the monthly price
    of the cheapest paid plan a visitor can sign up for (L7, through hubs.plan.list): never the Free
    plan, an upgrade-only one, an internal one or one off sale."""
    from decimal import Decimal

    from hubs.models import Plan

    for slug, price, extra in (
        ("free", "0", {}),
        ("starter", "19.99", {}),
        ("standard", "39.99", {}),
        ("pro", "9.00", {"upgrade_only": True}),
        ("payment-test", "1.00", {"internal_only": True}),
        ("retired", "2.00", {"is_active": False}),
    ):
        Plan.objects.create(slug=slug, name_en=slug.title(), price_monthly=Decimal(price), **extra)

    assert application(client, "whatsapp_inbox")["offers"] == {
        "@type": "Offer",
        "price": "19.99",
        "priceCurrency": "EUR",
        "url": "https://testserver/pricing/",
        "availability": "https://schema.org/InStock",
    }


def test_a_premium_app_without_a_paid_plan_on_sale_has_no_offer(client, catalog):
    """Advertising a price we do not charge is worse than advertising none."""
    from decimal import Decimal

    from hubs.models import Plan

    Plan.objects.create(slug="free", name_en="Free", price_monthly=Decimal("0"))

    assert "offers" not in application(client, "whatsapp_inbox")


def test_the_block_names_erplora_as_the_author_and_has_no_rating(client, catalog):
    block = application(client, "invoice")

    assert block["author"] == {"@type": "Organization", "name": "ERPlora"}
    assert "aggregateRating" not in block


def test_the_block_stays_valid_json_with_quotes_line_breaks_and_a_script_tag(client):
    description = 'Takes "orders"\nand bookings </script><b>bold</b> & more'
    make_app("escaping", name_en='The "Best" app', description_en=description)

    block = application(client, "escaping")

    assert block["name"] == 'The "Best" app'
    assert block["description"] == description


# --- The documentation: /apps/<id>/docs/ ---------------------------------------------------------


def test_the_documentation_comes_from_shared_app_doc(client, catalog):
    """Port of test_detail_docs_from_db.py: the markdown of the row, rendered (spec §5.2)."""
    make_doc(
        catalog["invoice"],
        "en",
        "# Invoices\n\nBill your **customers** from the POS.\n",
    )
    make_doc(catalog["invoice"], "es", "# Facturas\n\nFactura a tus **clientes**.\n")

    english = get_html(client, "/apps/invoice/docs/")
    spanish = get_html(client, "/apps/invoice/docs/", **SPANISH)

    assert "<strong>customers</strong>" in english
    assert "<strong>clientes</strong>" in spanish
    assert re.search(r'aria-current="page"[^>]*>\s*Documentation', english)
    assert "Invoices documentation · ERPlora apps" in english
    assert "Documentación de Facturas" in spanish
    assert '<h1 class="ep-hero__title">Invoices</h1>' in english  # the same header
    assert "This documentation is only available in Spanish." not in english


def test_without_english_the_documentation_is_the_spanish_one_with_a_notice(
    client, catalog
):
    make_doc(catalog["invoice"], "es", "# Facturas\n\nFactura a tus **clientes**.\n")

    html = get_html(client, "/apps/invoice/docs/")

    assert "This documentation is only available in Spanish." in html
    assert re.search(r'<article class="ep-prose ep-store-docs" lang="es">', html)
    assert "<strong>clientes</strong>" in html


def test_the_notice_is_never_shown_to_a_spanish_reader(client, catalog):
    make_doc(catalog["invoice"], "es", "# Facturas\n\nTexto.\n")

    html = get_html(client, "/apps/invoice/docs/", **SPANISH)

    assert "Esta documentación solo está disponible en español." not in html
    assert "This documentation is only available in Spanish." not in html


def test_the_notice_in_spanish():
    with translation.override("es"):
        assert (
            gettext("This documentation is only available in Spanish.")
            == "Esta documentación solo está disponible en español."
        )


def test_an_app_without_documentation_has_no_docs_tab_and_no_docs_page(client, catalog):
    assert "/apps/invoice/docs/" not in get_html(client, "/apps/invoice/")
    get_html(client, "/apps/invoice/docs/", status=404)
    get_html(client, "/apps/nope/docs/", status=404)


def test_an_app_with_documentation_links_its_docs_tab(client, catalog):
    make_doc(catalog["invoice"], "es")

    assert 'href="/apps/invoice/docs/"' in get_html(client, "/apps/invoice/")


def test_a_diagram_reaches_the_page_as_a_mermaid_block(client, catalog):
    """Spec §6: frontend/public.ts paints `pre.mermaid` in the browser (tests/e2e/store-docs.spec.ts)."""
    make_doc(catalog["invoice"], "es", "```mermaid\ngraph TD; A-->B;\n```\n")

    html = get_html(client, "/apps/invoice/docs/")

    assert '<pre class="mermaid">' in html


def test_the_documentation_may_show_images_of_the_hubs_static_origin(
    client, catalog, settings
):
    """Spec §9 (test_csp): the documentation's images live on the Hub's static origin."""
    settings.HUB_STATIC_BASE_URL = "https://hubs.erplora.com/static/"
    make_doc(catalog["invoice"], "es", "![Cash](docs/img/cash.png)\n")

    response = client.get("/apps/invoice/docs/")

    assert 'src="https://hubs.erplora.com/static/catalog/invoice/img/cash.png"' in (
        response.content.decode()
    )
    img_src = re.search(r"img-src ([^;]+)", response.headers["Content-Security-Policy"])
    assert "https://hubs.erplora.com" in img_src.group(1)


# --- The old addresses (decision 19) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("/marketplace/", "/apps/"),
        ("/marketplace/?q=stock&category=catalog", "/apps/?q=stock&category=catalog"),
        ("/marketplace/inventory/", "/apps/inventory/"),
        ("/marketplace/inventory/?ref=mail", "/apps/inventory/?ref=mail"),
        ("/solutions/", "/apps/"),
        ("/solutions/restaurant/", "/apps/"),
        ("/modules/", "/apps/"),
    ],
)
def test_the_old_addresses_move_permanently_to_the_store(client, old, new):
    response = client.get(old)

    assert response.status_code == 301
    assert response["Location"] == new


# --- Sitemap and llms.txt ------------------------------------------------------------------------


def sitemap_locations(client) -> list[str]:
    return re.findall(r"<loc>([^<]+)</loc>", get_html(client, "/sitemap.xml"))


def test_the_sitemap_lists_the_store_its_apps_and_their_documentation(client, catalog):
    make_doc(catalog["invoice"], "es")

    locations = sitemap_locations(client)

    for path in (
        "/apps/",
        "/apps/invoice/",
        "/apps/invoice/docs/",
        "/apps/inventory/",
        "/apps/tables/",
        "/apps/whatsapp_inbox/",
    ):
        assert f"https://testserver{path}" in locations, path
    assert (
        "https://testserver/apps/inventory/docs/" not in locations
    )  # no documentation
    assert not [location for location in locations if "loyalty" in location]


def test_the_old_addresses_are_never_in_the_sitemap(client, catalog):
    for location in sitemap_locations(client):
        assert not location.removeprefix("https://testserver").startswith(
            RETIRED_PATHS
        ), location


def test_without_listed_apps_the_sitemap_has_no_store_entries(client):
    """Spec §5.3: the store is `noindex` then, and a sitemap never lists a page it hides."""
    make_app("retired", listed=False)

    assert not [
        location for location in sitemap_locations(client) if "/apps/" in location
    ]


def test_every_store_entry_of_the_sitemap_answers_200(client, catalog):
    make_doc(catalog["invoice"], "es")
    for name in ("store", "apps"):
        sitemap = SITEMAPS[name]("testserver")
        for item in sitemap.items():
            assert client.get(sitemap.location(item)).status_code == 200, item


def test_the_sitemap_registry_has_the_store_and_its_apps():
    assert SITEMAPS["store"] is sitemaps.StoreSitemap
    assert SITEMAPS["apps"] is sitemaps.AppDetailSitemap


def test_llms_txt_lists_the_listed_apps_in_english(client, catalog):
    body = get_html(client, "/llms.txt", **SPANISH)

    assert "## Apps" in body
    assert (
        "- [Invoices](https://testserver/apps/invoice/): Bill your customers." in body
    )
    assert (
        "- [WhatsApp Inbox](https://testserver/apps/whatsapp_inbox/): Answer your chats."
        in body
    )
    assert "Loyalty" not in body and "/apps/loyalty/" not in body
    assert "Facturas" not in body


def test_llms_txt_puts_the_apps_between_start_here_and_optional(
    client, catalog, monkeypatch
):
    """The order of the original: what ERPlora is, the catalog, then the optional reading."""
    monkeypatch.setattr(
        seo,
        "LLMS_SECTIONS",
        (
            ("Start here", (("public:robots_txt", "Robots", "who may crawl."),)),
            ("Optional", (("public:sitemap", "Sitemap", "every page."),)),
        ),
    )

    body = get_html(client, "/llms.txt")

    assert (
        body.index("## Start here") < body.index("## Apps") < body.index("## Optional")
    )


def test_llms_txt_has_no_apps_section_without_listed_apps(client):
    make_app("retired", listed=False)

    assert "## Apps" not in get_html(client, "/llms.txt")


def test_every_app_linked_by_llms_txt_answers_200(client, catalog):
    body = get_html(client, "/llms.txt")
    links = re.findall(r"\]\(https://testserver(/apps/[^)]+)\)", body)

    assert links
    for link in links:
        assert client.get(link).status_code == 200, link


# --- Navigation ----------------------------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, SPANISH])
def test_the_menu_and_the_footer_link_the_store_as_apps(client, catalog, headers):
    """Decision 19: «Apps» in English and in Spanish."""
    html = get_html(client, "/apps/", **headers)
    navbar = html[html.index('<nav class="ep-navbar"') : html.index("</nav>")]
    footer = html[html.index('<footer class="ep-footer"') :]

    assert re.search(r'<a href="/apps/"[^>]*>\s*Apps\s*</a>', navbar)
    assert re.search(r'<a href="/apps/"[^>]*>\s*Apps\s*</a>', footer)


# --- The views read through operations, never the ORM --------------------------------------------


def test_the_store_imports_no_model():
    """Spec §5.1 and plan §6: only queries.py and services.py touch the ORM."""
    tree = ast.parse(STORE_PY.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert not [
        name for name in imported if name.endswith(".models") or ".models." in name
    ]
    assert not [name for name in imported if name.startswith("django.db")]
    assert ".objects" not in STORE_PY.read_text(encoding="utf-8")


def test_the_lint_would_catch_a_model_import(tmp_path, monkeypatch):
    """Positive control of the check above."""
    offender = tmp_path / "store.py"
    offender.write_text("from apps.models import App\n", encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.STORE_PY", offender)

    with pytest.raises(AssertionError):
        test_the_store_imports_no_model()


def test_the_pages_run_the_operations_of_apps(client, catalog, monkeypatch):
    from live import ninja

    ran = []
    real = ninja.run_operation_sync

    def spy(request, op, data=None):
        ran.append(op if isinstance(op, str) else op.name)
        return real(request, op, data)

    monkeypatch.setattr("public.store.run_operation_sync", spy)
    make_doc(catalog["invoice"], "es")

    client.get("/apps/")
    assert "apps.app.list" in ran
    ran.clear()
    client.get("/apps/invoice/")
    assert "apps.app.get" in ran
    ran.clear()
    client.get("/apps/invoice/docs/")
    assert {"apps.app.get", "apps.app.doc"} <= set(ran)


def test_the_store_card_paints_the_icon_it_was_given(client):
    """The icon comes from the operation, already clean: the card paints it, unescaped."""
    make_app("cube", icon_svg=CUBE_SVG)

    assert '<svg xmlns="http://www.w3.org/2000/svg"' in card_of(
        get_html(client, "/apps/"), "cube"
    )
