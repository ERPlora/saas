"""The home ``/`` (public/landing.py): the doors of its hero and closing band, its apps blocks and its JSON-LD.

* «Try the demo» in the hero and the closing band leads to ``/demo/`` (public/demo.py); the hero has three doors:
  sign-up, the demo and downloads.
* The six featured cards and the twelve chips are the first ``listed`` apps by section and name (``apps.app.list``),
  counted as one catalogue; without any listed app the apps blocks are omitted. The chips link to the store filtered
  by section (``/apps/?category=``).
* The ecosystem section is our own catalogue, with no marketplace and no third party, and every plan includes all the
  apps: the home sells no tier of apps, the paid plans add devices, capacity and quotas.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.tests.factories import make_app
from public.tests.landing_pages import html_of, make_plan, page, section
from public.tests.pricing_pages import json_ld_blocks

pytestmark = [pytest.mark.django_db]


def of_type(blocks: list[dict], wanted: str) -> dict | None:
    return next((block for block in blocks if block.get("@type") == wanted), None)


# --- The hero, the navbar and the closing band: their doors, the demo's included ---------------------


def test_the_hero_keeps_the_sign_up_and_the_downloads(client):
    """Asserted on the HERO alone: downloads also live in the footer."""
    hero = html_of(client).split("</section>")[0]

    assert 'href="/launch"' in hero
    assert reverse("public:downloads") in hero


def test_the_home_offers_the_demo_in_the_hero_and_the_closing_band(client):
    """The hero's third door and the closing band's second, both to ``/demo/``."""
    html = html_of(client)
    hero = html.split("</section>")[0]
    closing = html.split("Start today")[-1]

    for part in (hero, closing):
        assert f'href="{reverse("public:demo")}"' in part
        assert "Try the demo" in part


def test_the_closing_band_offers_to_start_free(client):
    closing = html_of(client).split("Start today")[-1]

    assert 'href="/launch"' in closing


MOCKUP_URL = re.compile(r'<span class="url">([^<]*)</span>')


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_browser_mockups_show_a_business_address_not_the_staff_host(client, language):
    """The hero and the bento dashboard paint a made-up hub address, ``my-erp.erplora.com``: ``hub.erplora.com``
    would read as a real host."""
    html = html_of(client, language=language)
    addresses = MOCKUP_URL.findall(html)

    assert addresses == ["my-erp.erplora.com", "my-erp.erplora.com/overview"]
    assert "hub.erplora.com" not in html


def test_a_plan_card_of_the_home_starts_at_the_sign_in(no_plans, client):
    """The SPA's sign-in, which also signs up: no door of the home leads to allauth's old pages."""
    make_plan("starter")

    html = html_of(client)

    assert 'href="/launch"' in section(html, "planes")
    assert "/accounts/login/" not in html


def test_a_paid_plan_card_of_the_home_says_get_started_not_start_free(no_plans, client):
    """Every business starts on Free and is upgraded later, so a paid card does not promise a free start of ITS
    price: it says «Get started», as on /pricing/; the free one keeps «Start free». Both lead to the sign-in, which
    also signs up."""
    make_plan("free", price_monthly=Decimal("0"))
    make_plan("starter")

    plans = section(html_of(client), "planes")
    free, starter = plans.split('class="ep-pricing-card__name">')[1:3]

    assert "Start free" in free and "Get started" not in free
    assert "Get started" in starter and "Start free" not in starter
    assert free.count('href="/launch"') == starter.count('href="/launch"') == 1


# --- The apps blocks --------------------------------------------------------------------------


@pytest.fixture
def catalogue():
    """Fourteen listed apps over three sections, two flagged ``premium`` (reserved, unused
    today), and one that is not listed."""
    apps = [
        make_app(f"sales_{n:02d}", category="sales", name_en=f"Sales {n:02d}")
        for n in range(1, 6)
    ]
    apps += [
        make_app(f"catalog_{n:02d}", category="catalog", name_en=f"Catalog {n:02d}")
        for n in range(1, 6)
    ]
    apps += [
        make_app(
            f"people_{n:02d}",
            category="people",
            name_en=f"People {n:02d}",
            premium=n <= 2,
        )
        for n in range(1, 5)
    ]
    make_app("hidden", listed=False, name_en="Hidden App")
    return apps


def test_the_six_featured_apps_are_the_first_listed_by_section_and_name(
    client, catalogue
):
    response = page(client)

    featured = [app["id"] for app in response.context["featured_apps"]]
    assert featured == [f"sales_{n:02d}" for n in range(1, 6)] + ["catalog_01"]
    html = response.content.decode()
    apps_block = section(html, "modulos")
    assert apps_block.count('<a class="ep-feature-card"') == 6
    assert "Sales 01" in apps_block
    # The app's own icon, cleaned by apps.app.list and painted inline.
    assert "m69 153.99 187 110 187-110" in apps_block
    assert f'href="{reverse("public:store_detail", args=["sales_01"])}"' in apps_block


def test_the_twelve_chips_link_to_the_store_by_section(client, catalogue):
    response = page(client)

    chips = response.context["chip_apps"]
    assert len(chips) == 12
    assert chips[0]["id"] == "sales_01" and chips[-1]["id"] == "people_02"
    html = response.content.decode()
    assert f'href="{reverse("public:store")}?category=sales"' in html
    assert f'href="{reverse("public:store")}?category=people"' in html


def test_the_count_is_every_listed_app_without_a_tier(client, catalogue):
    """Every plan includes all the apps: the home counts them, never free apart from premium."""
    context = page(client).context

    assert context["total_apps"] == 14
    assert [
        key
        for key in ("free_apps", "premium_apps", "premium_app_examples")
        if key in context
    ] == []


def test_the_apps_section_points_to_the_store(client, catalogue):
    apps_block = section(html_of(client), "modulos")

    assert f'href="{reverse("public:store")}"' in apps_block
    assert "See the 14 apps" in apps_block


def test_without_listed_apps_the_apps_blocks_are_omitted(client):
    """A page that reads apps omits its apps block, never «0 apps»."""
    make_app("hidden", listed=False)
    html = html_of(client)

    assert 'id="modulos"' not in html
    assert "?category=" not in html
    assert not re.search(r"(?<!\d)0 apps", html)


def test_the_ecosystem_is_our_catalogue_not_a_marketplace(client, catalogue):
    """No third party, no marketplace: every app is ours."""
    html = html_of(client)
    ecosystem = section(html, "ecosystem")

    assert "Marketplace" not in ecosystem
    assert "marketplace" not in html.lower()


@pytest.mark.parametrize(
    ("language", "sentences"),
    [
        (
            "en",
            (
                "One ecosystem. Every app on every plan.",
                "All the apps",
                "Every app comes with every plan, Free included: turn on the ones your business needs.",
                "Room to grow",
                "When your business grows, a paid plan adds:",
                "Unlimited devices",
                "More capacity",
                "Higher AI and WhatsApp quotas",
            ),
        ),
        (
            "es",
            (
                "Un ecosistema. Todas las apps en todos los planes.",
                "Todas las apps",
                "Todas las apps vienen con todos los planes, también con Gratis: activa las que necesite tu negocio.",
                "Espacio para crecer",
                "Cuando tu negocio crece, un plan de pago añade:",
                "Dispositivos ilimitados",
                "Más capacidad",
                "Más mensajes de IA y WhatsApp",
            ),
        ),
    ],
)
def test_the_ecosystem_puts_every_app_on_every_plan(client, catalogue, language, sentences):
    """Every app comes with every plan and the paid plans add room, not apps: no «Free forever» cell against a
    «Premium apps» one."""
    ecosystem = section(html_of(client, language=language), "ecosystem")

    assert [sentence for sentence in sentences if sentence not in ecosystem] == []
    assert "People 01" not in ecosystem, "no app is quoted as the example of a tier"


# --- JSON-LD of the home ----------------------------------------------------------------------


@pytest.fixture
def cheapest_plan():
    make_plan("seo-dearer-sentinel", price_monthly=Decimal("99.00"), display_order=10)
    return make_plan(
        "seo-cheapest-sentinel", price_monthly=Decimal("7.77"), display_order=-50
    )


def test_every_block_is_valid_json_with_the_schema_context(client):
    blocks = json_ld_blocks(html_of(client))

    assert blocks, "the home page carries no JSON-LD at all"
    for block in blocks:
        assert block["@context"] == "https://schema.org"


def test_there_is_an_organization_with_name_url_and_logo(client):
    organization = of_type(json_ld_blocks(html_of(client)), "Organization")

    assert organization["name"] == "ERPlora"
    assert organization["url"] == "https://testserver/"
    assert organization["logo"].startswith("https://testserver/")


def test_there_is_a_business_software_application_naming_erp_and_pos(client):
    application = of_type(json_ld_blocks(html_of(client)), "SoftwareApplication")

    assert application["applicationCategory"] == "BusinessApplication"
    assert "ERP" in application["description"] and "POS" in application["description"]
    assert "Module marketplace" not in application["featureList"]


def test_the_price_comes_from_the_live_plan_table(no_plans, client, cheapest_plan):
    offers = of_type(json_ld_blocks(html_of(client)), "SoftwareApplication")["offers"]

    assert offers["priceCurrency"] == "EUR"
    assert offers["price"] == "7.77"


def test_the_application_counts_the_listed_apps(client, catalogue):
    application = of_type(json_ld_blocks(html_of(client)), "SoftwareApplication")

    assert "14 of them" in application["description"]


def test_without_plans_there_is_no_offer(no_plans, client):
    assert "offers" not in of_type(
        json_ld_blocks(html_of(client)), "SoftwareApplication"
    )
