"""``/compliance/``: where ERPlora meets each country's invoicing rules (PUBLIC-F09, public/compliance.py).

The old page read ``CountryCompliance``, a table a person flipped to «Covered» in the admin, seeded with
mandates «pending human legal review» (SAAS_PUBLIC-F62): Spain read «Verifactu / TicketBAI / Factura-e,
Covered» and no app did TicketBAI or Factura-e. The port left it out (spec §11.1: nothing to read in
saas). Decided with the market (Odoo's list of fiscal localizations, Business Central's country table,
Lightspeed's per-country help, Holded, Shopify POS, Zettle, Mollie and fiskaly; table in the PR): a
fixed list in the code, released with the product, of the countries a business can be created in
(``hubs.schemas.COUNTRIES``) and, for each, the fiscal system the apps connect to today. Only Spain's
VeriFactu does; the Basque Country (TicketBAI) and Navarre are said to be out, and no foreign mandate is
named, because nobody here has checked one.
"""

from __future__ import annotations

import gettext
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from hubs.schemas import COUNTRIES
from public import compliance
from public.tests.test_legal import template_messages

pytestmark = pytest.mark.django_db

ROOT = Path(settings.BASE_DIR)
TEMPLATE = ROOT / "public" / "templates" / "public" / "compliance" / "index.html"
CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
PATH = "/compliance/"


def page(client, path: str = PATH, language: str = "en") -> str:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response.content.decode()


def test_the_route():
    assert reverse("public:compliance") == PATH


def test_the_page_only_answers_safe_methods(client):
    assert client.post(PATH).status_code == 405


def test_the_page_carries_the_brand_the_navbar_and_the_footer(client):
    html = page(client)

    assert "<title>Compliance · ERPlora</title>" in html
    assert 'class="ep-footer"' in html
    assert "ep-navbar" in html


# --- Where the countries come from --------------------------------------------------------------


def test_the_countries_are_the_ones_a_business_can_be_created_in():
    """One list: the markets of the sign-up form. A country added there without a name here fails."""
    assert set(compliance.COUNTRY_NAMES) == set(COUNTRIES)


def test_every_country_is_on_the_page_once(client):
    html = page(client)

    for code in COUNTRIES:
        name = str(compliance.COUNTRY_NAMES[code])
        assert html.count(f'data-country="{code}"') == 1, code
        assert name in html, name


def test_the_figures_count_the_countries_and_the_fiscal_connections(client):
    html = page(client)

    assert f'data-figure="markets">{len(COUNTRIES)}<' in html
    assert 'data-figure="connected">1<' in html
    assert f'data-figure="not-connected">{len(COUNTRIES) - 1}<' in html


# --- What each one says ---------------------------------------------------------------------------


def test_spain_is_the_one_country_connected_to_its_fiscal_system():
    connected = [country for country in compliance.countries() if country["systems"]]

    assert [country["code"] for country in connected] == ["ES"]
    assert [system["name"] for system in connected[0]["systems"]] == ["VeriFactu"]


def test_spain_comes_first_and_the_rest_by_name_in_the_reading_language():
    with translation.override("es"):
        names = [str(country["name"]) for country in compliance.countries()]

    assert names[0] == "España"
    assert names[1:] == sorted(names[1:], key=compliance.collation_key)


def test_the_verifactu_card_says_what_it_does_and_links_the_declaration(client):
    html = page(client)
    spain = html[html.index('data-country="ES"') : html.index("</article>", html.index('data-country="ES"'))]

    assert "VeriFactu" in spain
    assert "AEAT" in spain
    assert f'href="{reverse("public:declaracion_responsable")}"' in spain


@pytest.mark.parametrize(
    ("language", "regions"),
    [("en", ("Basque Country", "Navarre")), ("es", ("País Vasco", "Navarra"))],
)
def test_the_spanish_regions_with_their_own_system_are_said_to_be_out(client, language, regions):
    """TicketBAI and Navarre's system are not connected: the old page marked Spain «Covered» with
    TicketBAI in it."""
    html = page(client, language=language)
    spain = html[html.index('data-country="ES"') : html.index("</article>", html.index('data-country="ES"'))]

    assert all(region in spain for region in regions)
    assert "TicketBAI" in spain


def test_no_foreign_mandate_is_named(client):
    """Nobody here checked Italy's, Germany's or Portugal's rules: the page does not quote them."""
    html = page(client)

    for mandate in ("SdI", "FatturaPA", "KassenSichV", "TSE", "SAF-T", "ATCUD", "KSeF", "myDATA", "Factur-X", "Peppol"):
        assert mandate not in html, mandate


def test_a_country_without_a_connection_says_what_works_and_what_does_not(client):
    html = page(client)
    france = html[html.index('data-country="FR"') : html.index("</li>", html.index('data-country="FR"'))]

    assert "France" in france
    assert "VeriFactu" not in france
    assert "Not connected yet" in html


# --- In Spanish ---------------------------------------------------------------------------------


def test_the_page_in_spanish(client):
    html = page(client, language="es")

    assert "<title>Cumplimiento · ERPlora</title>" in html
    assert "España" in html and "Francia" in html
    assert "Todavía sin conexión" in html


def test_no_spanish_figure_reads_like_a_price_plan(client):
    """saas#2650: «En el plan» over the countries to come read as a pricing plan."""
    assert "En el plan" not in page(client, language="es")


def test_every_message_of_the_page_has_its_spanish_entry():
    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(TEMPLATE)

    assert messages
    assert [message for message in messages if not catalog.get(message)] == []


def test_every_country_and_system_has_its_spanish_name():
    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    texts = [str(name) for name in compliance.COUNTRY_NAMES.values()]
    with translation.override("en"):
        texts += [
            str(system[key])
            for country in compliance.countries()
            for system in country["systems"]
            for key in ("does", "out")
        ]

    assert [text for text in texts if not catalog.get(text)] == []


# --- Back in the menus, the sitemap and llms.txt -------------------------------------------------


def test_the_footer_links_compliance_in_the_company_column(client):
    html = page(client, "/")
    company = html[html.index("Company</h2>") : html.index("</div>", html.index("Company</h2>"))]

    assert f'href="{PATH}"' in company


def test_an_industry_page_points_to_compliance(client):
    from hubs.models import BusinessType, Sector

    sector = Sector.objects.create(code="food", name_en="Food", is_active=True)
    BusinessType.objects.create(code="bakery", name_en="Bakery", sector=sector, is_active=True)

    assert f'href="{PATH}"' in page(client, "/industries/bakery/").split('class="ep-footer"')[0]


def test_the_sitemap_lists_compliance(client):
    assert f"{PATH}</loc>" in client.get("/sitemap.xml").content.decode()


def test_llms_txt_points_to_compliance(client):
    assert f"{PATH})" in client.get("/llms.txt").content.decode()
