"""``/about/``, ``/blog/``, ``/careers/``, ``/press/`` and the old ``/company/`` (public/company.py).

Port of ``apps/public/company`` (origin/develop c5ca8ca). Its only suite,
``company/tests/test_developers_page.py`` (3), is about ``/developers/``, which disappears (spec
§8.3): one case here fixes that it answers 404. The rest come from ``tests/unit/test_public_pages.py``
(200, brand, navbar, footer, GET only, URL names) and from the old ``company/urls.py`` (``/company/``
answers 301 to ``/about/``, issue #547). ``/collaborate/`` reads ``Plan`` and the taxonomy and came
with L7: its cases are at the end of this file.

What changed: ``/about/`` no longer says that a module marketplace lets developers extend ERPlora:
there are no third-party modules (PLAN-SAAS §6, spec §8.3), every app is ours.
"""

from decimal import Decimal

import pytest
from django.conf import settings
from django.urls import reverse

from public.tests.test_stack_copy import copy_of, names_the_stack

pytestmark = pytest.mark.django_db

PAGES = ("/about/", "/blog/", "/careers/", "/press/")
COMING_SOON = ("/blog/", "/careers/", "/press/")


def page(client, path: str, language: str = "en") -> str:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response.content.decode()


@pytest.mark.parametrize("path", PAGES)
def test_the_page_answers_with_the_brand_the_navbar_and_the_footer(client, path):
    html = page(client, path)

    assert "ERPlora" in html
    assert '<nav class="ep-navbar"' in html
    assert f'href="{reverse("public:features")}"' in html
    assert '<footer class="ep-footer"' in html


@pytest.mark.parametrize("path", PAGES)
def test_the_page_only_answers_safe_methods(client, path):
    assert client.post(path).status_code == 405


def test_the_url_names():
    assert reverse("public:about") == "/about/"
    assert reverse("public:blog") == "/blog/"
    assert reverse("public:careers") == "/careers/"
    assert reverse("public:press") == "/press/"


def test_the_old_company_address_moves_permanently_to_about(client):
    """No longer linked, but external and cached links still point there (issue #547)."""
    response = client.get("/company/")

    assert response.status_code == 301
    assert response["Location"] == reverse("public:about")


def test_the_developers_page_is_gone(client):
    """The third-party module toolkit is gone with the marketplace (spec §8.3): a 404, not the SPA."""
    response = client.get("/developers/")

    assert response.status_code == 404
    assert '<div id="app"></div>' not in response.content.decode()


# --- /about/ ---------------------------------------------------------------------------------


def test_about_keeps_its_three_cards(client):
    html = page(client, "/about/")

    assert "About ERPlora." in html
    assert html.count('class="ep-feature-card"') == 3
    for heading in ("Our Mission", "Our Technology", "Our Apps"):
        assert heading in html
    assert "<title>About Us · ERPlora</title>" in html


def test_about_speaks_of_our_apps_not_of_a_third_party_marketplace(client):
    html = page(client, "/about/")

    assert "marketplace" not in html.lower()
    assert "lets developers extend" not in html
    assert "Every app is built by the ERPlora team" in html


@pytest.mark.parametrize(
    ("language", "sentences"),
    [
        (
            "en",
            (
                "Your data lives in its own database, isolated from every other business,",
                "point-in-time recovery for 14 days and high availability in Europe",
            ),
        ),
        (
            "es",
            (
                "Tus datos viven en su propia base de datos, aislada de la de cualquier otro negocio,",
                "recuperación a cualquier momento de los últimos 14 días y alta disponibilidad en "
                "Europa",
            ),
        ),
    ],
)
def test_about_says_what_the_platform_gives_not_what_it_is_built_with(
    client, language, sentences
):
    """Ioan, 2026-10-14: «Our Technology» no longer reads «Built with Django 6.1 and modern web
    components. A cloud-native architecture on AWS…», but what that gives the business."""
    html = page(client, "/about/", language)

    for sentence in sentences:
        assert sentence in html, sentence
    assert names_the_stack(copy_of(html)) == []


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            "Every app is built by the ERPlora team and shares one database, one interface and one "
            "login. Every plan includes all of them — you turn on what fits your business.",
        ),
        (
            "es",
            "Todas las apps las desarrolla el equipo de ERPlora y comparten una base de datos, una "
            "interfaz y un inicio de sesión. Todos los planes las incluyen todas: tú activas lo que "
            "encaja con tu negocio.",
        ),
    ],
)
def test_our_apps_card_puts_every_app_on_every_plan(client, language, sentence):
    """Ronda 2026-10-24b (PLAN §32): the card said «Free apps or premium features — you choose»."""
    assert sentence in page(client, "/about/", language)


def test_about_in_spanish(client):
    html = page(client, "/about/", "es")

    assert "Acerca de ERPlora." in html
    assert "Todas las apps las desarrolla el equipo de ERPlora" in html
    assert "marketplace" not in html.lower()


# --- The «coming soon» pages (F79) ------------------------------------------------------------


@pytest.mark.parametrize("path", COMING_SOON)
def test_a_coming_soon_page_is_not_indexed(client, path):
    assert '<meta name="robots" content="noindex, follow">' in page(client, path)


@pytest.mark.parametrize(
    ("path", "title", "copy"),
    [
        ("/blog/", "Blog", "are coming soon."),
        ("/careers/", "Careers", "will be published here."),
        ("/press/", "Press", "are coming soon."),
    ],
)
def test_a_coming_soon_page_says_what_is_coming(client, path, title, copy):
    html = page(client, path)

    assert f"<title>{title} · ERPlora</title>" in html
    assert copy in html


def test_the_coming_soon_pages_in_spanish(client):
    assert "Muy pronto: historias de producto" in page(client, "/blog/", "es")
    assert "Empleos" in page(client, "/careers/", "es")
    assert "Prensa" in page(client, "/press/", "es")


def test_about_is_indexed(client):
    assert "noindex" not in page(client, "/about/")


# --- Navigation, sitemap and llms.txt ---------------------------------------------------------


def test_the_footer_links_about(client):
    html = page(client, "/features/")
    footer = html[html.index('<footer class="ep-footer"') :]

    assert f'href="{reverse("public:about")}">About Us</a>' in footer


def test_the_sitemap_lists_about_and_not_the_coming_soon_pages():
    from public.sitemaps import StaticPagesSitemap

    names = [name for name, _ in StaticPagesSitemap.pages]
    assert ("public:about", 0.6) in StaticPagesSitemap.pages
    for name in ("public:blog", "public:careers", "public:press"):
        assert name not in names


def test_llms_txt_says_who_builds_erplora(client):
    body = client.get("/llms.txt").content.decode()

    assert "- [About](https://testserver/about/): who builds ERPlora." in body


# --- /collaborate/ (L7) ----------------------------------------------------------------------
#
# The old view had no test of its own. What it promised, and what changed: the counts of active
# sectors and business types come from ``hubs.sector.list`` / ``hubs.business_type.list`` (plan
# §3.m); the plan of «free for a year» is the cheapest PAID plan a visitor can sign up for, read from
# ``hubs.plan.list`` — the old view read ``Plan.objects.filter(slug="starter")``, which WORKFLOW F63
# marks as wrong (a plan off sale or internal would still be shown). ``cheapest_slug`` is the Free
# plan, whose «valued at €0/year» says nothing, hence the cheapest paid one. The third-party
# marketplace is gone (spec §8.3): no «Module marketplace», no paid modules with an 85 % share.

COLLABORATE = "/collaborate/"


def make_plan(slug: str, price: str, **fields):
    from decimal import Decimal

    from hubs.models import Plan

    return Plan.objects.create(
        slug=slug,
        name_en=slug.title(),
        price_monthly=Decimal(price),
        **{"is_active": True, **fields},
    )


@pytest.fixture
def taxonomy():
    from hubs.models import BusinessType, Sector

    beauty = Sector.objects.create(code="beauty", name_en="Beauty", is_active=True)
    food = Sector.objects.create(code="food", name_en="Food", is_active=True)
    Sector.objects.create(code="old", name_en="Old", is_active=False)
    for code, sector in (("hair_salon", beauty), ("nail_salon", beauty), ("bar", food)):
        BusinessType.objects.create(
            code=code, name_en=code.title(), sector=sector, is_active=True
        )
    BusinessType.objects.create(
        code="gone", name_en="Gone", sector=food, is_active=False
    )


def test_the_collaborate_route():
    assert reverse("public:collaborate") == COLLABORATE


def test_collaborate_answers_with_the_brand_the_navbar_and_the_footer(client):
    html = page(client, COLLABORATE)

    assert "Collaborator Program" in html
    assert '<nav class="ep-navbar"' in html
    assert '<footer class="ep-footer"' in html
    assert client.post(COLLABORATE).status_code == 405


def test_collaborate_counts_the_active_sectors_and_business_types(client, taxonomy):
    html = page(client, COLLABORATE)

    assert "2 sectors, 3 business types" in html
    assert "We cover 2 sectors and 3 business types." in html


def test_without_a_taxonomy_collaborate_names_no_count(client):
    html = page(client, COLLABORATE)

    assert "0 sectors" not in html
    assert "Don't see yours? We want to hear from you too." in html


def test_the_free_year_is_valued_at_the_cheapest_paid_plan_on_sale(no_plans, client):
    make_plan("free", "0")
    make_plan("starter", "19.99", display_order=1)
    make_plan("standard", "39.99", display_order=2)
    make_plan("internal-cheap", "1", internal_only=True)
    make_plan("retired-cheap", "2", is_active=False)
    make_plan("pro", "9", upgrade_only=True)

    html = page(client, COLLABORATE)

    assert (
        "Get a full ERPlora Hub on the Starter plan — free for 12 months (valued at €239.88/year)."
        in html
    )
    assert (
        "The full Starter plan with all core features, no credit card required." in html
    )


def test_the_free_year_is_valued_at_what_a_year_of_the_plan_costs(no_plans, client):
    """PUBLIC-F10: a year of the plan is sold at its annual price, not at twelve monthly ones
    (SAAS_PUBLIC-F58 counted ``price_monthly × 12`` next to an annual price of less)."""
    make_plan("free", "0")
    make_plan("starter", "29.99", price_annual=Decimal("299.90"))

    html = page(client, COLLABORATE)

    assert "free for 12 months (valued at €299.90/year)." in html
    assert "359.88" not in html


def test_without_a_paid_plan_on_sale_no_value_is_invented(no_plans, client):
    make_plan("free", "0")

    html = page(client, COLLABORATE)

    assert "valued at" not in html
    assert "Get a full ERPlora Hub free for 12 months." in html


def test_collaborate_speaks_of_our_apps_not_of_a_marketplace(client):
    for language in ("en", "es"):
        html = page(client, COLLABORATE, language).lower()
        assert "marketplace" not in html, language
        assert "85%" not in html and "85 %" not in html, language
    assert "Our own app catalogue" in page(client, COLLABORATE)
    assert "Catálogo de apps propias" in page(client, COLLABORATE, "es")


def test_collaborate_names_no_old_host_and_no_past_launch_date(client):
    """Ioan, 2026-10-13: the servers are on AWS. «Expected launch: September 2026» had passed."""
    for language in ("en", "es"):
        html = page(client, COLLABORATE, language)
        assert "Hetzner" not in html and "Falkenstein" not in html
        assert "September 2026" not in html and "septiembre de 2026" not in html


def test_collaborate_sends_to_the_contact_page_with_its_subject(client, settings):
    """The form keeps the topic it is opened on (PUBLIC-G40): before, «Collaborator+Program» was ignored."""
    settings.SUPPORT_EMAIL = "support@erplora.test"
    html = page(client, COLLABORATE)

    assert f'href="{reverse("public:contact")}?subject=collaborate"' in html
    assert 'href="mailto:support@erplora.test?subject=Collaborator%20Program"' in html


def test_collaborate_in_spanish(client, taxonomy):
    html = page(client, COLLABORATE, "es")

    assert "Programa de Colaboradores" in html
    assert "2 sectores, 3 tipos de negocio" in html


def test_the_sitemap_lists_collaborate():
    from public.sitemaps import StaticPagesSitemap

    assert ("public:collaborate", 0.5) in StaticPagesSitemap.pages


def test_every_message_of_collaborate_has_its_spanish_entry():
    import gettext
    from pathlib import Path

    from public.tests.test_legal import template_messages

    root = Path(settings.BASE_DIR) / "public"
    with (root / "locale" / "es" / "LC_MESSAGES" / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    for name in (
        "collaborate.html",
        "_collaborate_hero_actions.html",
        "_collaborate_cta_actions.html",
    ):
        template = root / "templates" / "public" / "company" / name
        assert [m for m in template_messages(template) if not catalog.get(m)] == [], (
            name
        )
