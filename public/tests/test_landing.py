"""The home ``/``, the contact page ``/contact/`` and its form ``/contact/submit/`` (public/landing.py).

Port of ERPlora/saas (origin/develop c5ca8ca): ``apps/public/landing/tests/test_views.py`` (the home,
the contact and the static pages; its ``set_language`` cases are test_language.py and its
``/download/`` cases test_appdist.py), ``test_home_plan_trial.py`` (5), ``test_comparison_section.py``
(3), ``test_ai_data_residency.py`` (3), the home cases of ``test_structured_data.py`` (8), the home
case of ``apps/public/pricing/tests/test_internal_plans_are_never_public.py``, the home and contact
cases of ``tests/unit/test_public_pages.py`` (the company, product, resources, help and legal ones
live with their pages), the landing half of ``tests/unit/billing/test_net_price_display.py`` and
the home/contact contracts of ``apps/public/landing/tests/test_ui_stack_contract.py``.
What changed, and why:

* ``/`` is the landing (plan §3.c): it no longer redirects to the launcher. The project-wide URL name
  ``home`` still reverses to ``/`` (allauth's templates and the error pages use it);
* the demo is back (round 2026-10-17, PLAN-SAAS §3.5): «Try the demo» in the hero and the closing band,
  as in the old landing, leads to ``/demo/`` (public/demo.py); the hero has three doors, sign-up, the
  demo and downloads;
* the modules are apps (decision 19): the six featured cards and the twelve chips are the first
  ``listed`` apps by section and name (``apps.app.list``, spec §8.1; ``is_featured`` and downloads do
  not exist any more), counted as one catalogue; without any listed app the apps blocks are
  omitted (spec §5.3). The chips link to the store filtered by section (``/apps/?category=``);
* the ecosystem section is our own catalogue, there is no marketplace and no third party, and every
  plan includes all the apps (ronda 2026-10-24b, PLAN §32; before, decision 17 split them into free
  and premium): the home sells no tier of apps, the paid plans add devices, capacity and quotas;
* the plans come from ``hubs.plan.list`` (plan §3.m): the cards end with the plan's real trial and
  carry the ex-VAT note instead of the «with 21 % Spanish VAT» line (WORKFLOW F55; the landing was
  frozen in ``pm/LOCKED.md``, the xfail that waited for it is a plain test now);
* the plan cards are ``public/components/pricing_card.html`` and the contact page uses the ``ep-*``
  classes (PLAN §16.11);
* the contact mail is rendered from ``public/templates/public/email/`` and sent branded, as text and as HTML
  (``base.emails``, ACCOUNTS-F46), to ``SUPPORT_EMAIL`` (plan §3.o); the limit per address reads the address the load balancer saw
  (the last hop of ``X-Forwarded-For``), never the balancer's own;
* no page names Hetzner as the host any more (Ioan, 2026-10-13: AWS; Ireland region, 2026-10-14).
"""

from __future__ import annotations

import gettext
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import resolve, reverse
from django.utils import translation

from apps.tests.factories import CUBE_SVG, make_app
from hubs.models import Plan
from public import context_processors, landing
from public.tests.test_cookies import VALKEY_DOWN
from public.tests.test_legal import template_messages

pytestmark = [pytest.mark.django_db]

ROOT = Path(settings.BASE_DIR)
LANDING_TEMPLATES = ROOT / "public" / "templates" / "public" / "landing"
EMAIL_TEMPLATES = ROOT / "public" / "templates" / "public" / "email"
CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
HOME = "/"
CONTACT = "/contact/"
SUBMIT = "/contact/submit/"

CARD_START = re.compile(r'<div class="ep-pricing-card(?: ep-pricing-card--featured)?">')
CARD_ITEM = re.compile(
    r'<li><span class="ep-pricing-card__check" aria-hidden="true">✓</span><span>(.*?)</span></li>',
    re.S,
)


def make_plan(slug: str, *, trial_days: int = 0, **fields) -> Plan:
    defaults = {
        "name_en": slug.replace("-", " ").title(),
        "description_en": f"{slug} plan",
        "price_monthly": Decimal("29.99"),
        "trial_period_days": trial_days,
        "features_en": ["Unlimited users"],
        "features_es": ["Usuarios ilimitados"],
        "is_active": True,
    }
    return Plan.objects.create(slug=slug, **{**defaults, **fields})


def page(client, path: str = HOME, language: str | None = None):
    if language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response


def html_of(client, path: str = HOME, language: str | None = None) -> str:
    return page(client, path, language).content.decode()


def section(html: str, section_id: str) -> str:
    start = html.index(f'id="{section_id}"')
    return html[start : html.index("</section>", start)]


def card_items(html: str, plan_name: str) -> list[str]:
    """The ✓ lines of one plan card of the home, so no other block can make a test pass."""
    cards = [
        chunk
        for chunk in CARD_START.split(html)[1:]
        if f'<div class="ep-pricing-card__name">{plan_name}</div>' in chunk
    ]
    assert cards, f"no plan card for {plan_name} on the home"
    return [
        " ".join(item.split())
        for item in CARD_ITEM.findall(cards[0].split("</ul>", 1)[0])
    ]


def json_ld_blocks(html: str) -> list[dict]:
    marker = '<script type="application/ld+json">'
    blocks, cursor = [], 0
    while (start := html.find(marker, cursor)) != -1:
        start += len(marker)
        end = html.index("</script>", start)
        blocks.append(json.loads(html[start:end]))
        cursor = end
    return blocks


def of_type(blocks: list[dict], wanted: str) -> dict | None:
    return next((block for block in blocks if block.get("@type") == wanted), None)


# --- Routes -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("public:home", "/"),
        ("public:contact", "/contact/"),
        ("public:contact_submit", "/contact/submit/"),
    ],
)
def test_the_routes(name, path):
    assert reverse(name) == path
    assert resolve(path).view_name == name


def test_the_project_wide_home_name_is_the_landing():
    """allauth's templates and the error pages reverse ``home``: it is ``/``, served by the landing."""
    assert reverse("home") == "/"
    assert resolve("/").view_name == "public:home"


def test_the_root_is_the_landing_not_the_launcher(client):
    response = client.get(HOME)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert "ERPlora" in response.content.decode()


@pytest.mark.parametrize("path", [HOME, CONTACT])
def test_the_pages_only_answer_safe_methods(client, path):
    assert client.post(path).status_code == 405


# --- The hero, the navbar and the closing band: their doors, the demo's included (round 2026-10-17) --


def test_the_hero_keeps_the_sign_up_and_the_downloads(client):
    """Asserted on the HERO alone: downloads also live in the footer."""
    hero = html_of(client).split("</section>")[0]

    assert 'href="/launch"' in hero
    assert reverse("public:downloads") in hero


def test_the_home_offers_the_demo_in_the_hero_and_the_closing_band(client):
    """As the old landing: the hero's third door and the closing band's second, both to ``/demo/``."""
    html = html_of(client)
    hero = html.split("</section>")[0]
    closing = html.split("Start today")[-1]

    for part in (hero, closing):
        assert f'href="{reverse("public:demo")}"' in part
        assert "Try the demo" in part


def test_the_closing_band_offers_to_start_free(client):
    closing = html_of(client).split("Start today")[-1]

    assert 'href="/launch"' in closing


def test_a_plan_card_of_the_home_starts_at_the_sign_in(no_plans, client):
    """The SPA's sign-in, which also signs up: no door of the home leads to allauth's old pages."""
    make_plan("starter")

    html = html_of(client)

    assert 'href="/launch"' in section(html, "planes")
    assert "/accounts/login/" not in html


def test_a_paid_plan_card_of_the_home_says_get_started_not_start_free(no_plans, client):
    """PUBLIC-F11: every business starts on Free and is upgraded later, so a paid card does not promise a
    free start of ITS price (SAAS_PUBLIC-F78): it says «Get started», as on /pricing/; the free one keeps
    «Start free». Both lead to the sign-in, which also signs up."""
    make_plan("free", price_monthly=Decimal("0"))
    make_plan("starter")

    plans = section(html_of(client), "planes")
    free, starter = plans.split('class="ep-pricing-card__name">')[1:3]

    assert "Start free" in free and "Get started" not in free
    assert "Get started" in starter and "Start free" not in starter
    assert free.count('href="/launch"') == starter.count('href="/launch"') == 1


# --- The apps blocks (antes _modules.html, _build_to_fit.html) --------------------------------


@pytest.fixture
def catalogue():
    """Fourteen listed apps over three sections, two flagged ``premium`` (reserved, unused today:
    PLAN §32), and one that is not listed."""
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
    """Every plan includes all the apps (PLAN §32): the home counts them, never free apart from premium."""
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
    """Spec §5.3: a page that reads apps omits its apps block, never «0 apps»."""
    make_app("hidden", listed=False)
    html = html_of(client)

    assert 'id="modulos"' not in html
    assert "?category=" not in html
    assert "0 apps" not in html


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
    """Ronda 2026-10-24b (PLAN §32): the two cells were «Free forever» and «Premium apps», with real
    premium names; now every app comes with every plan and the paid plans add room, not apps."""
    ecosystem = section(html_of(client, language=language), "ecosystem")

    assert [sentence for sentence in sentences if sentence not in ecosystem] == []
    assert "People 01" not in ecosystem, "no app is quoted as the example of a tier"


# --- The plans (test_views.py, test_internal_plans_are_never_public.py) -----------------------


def test_the_home_shows_the_plans_a_visitor_can_sign_up_for(no_plans, client):
    make_plan(
        "starter", name_en="Starter", price_monthly=Decimal("9.00"), display_order=1
    )
    make_plan("pro", name_en="Pro", upgrade_only=True)

    response = page(client)

    assert [plan["slug"] for plan in response.context["plans"]] == ["starter"]
    assert "€9" in section(response.content.decode(), "planes")


def test_the_home_does_not_list_internal_plans(client):
    """On the catalogue the migrations leave (``hubs/0013``)."""
    make_plan(
        "internal-sentinel",
        name_en="Internal Sentinel Plan",
        price_monthly=Decimal("0.50"),
        display_order=-100,
        internal_only=True,
    )

    response = page(client)

    listed = {plan["slug"] for plan in response.context["plans"]}
    assert "starter" in listed, "control: the home still lists the public plans"
    assert not {"payment-test", "internal-sentinel"} & listed
    assert not response.context["cheapest_plan"]["internal_only"]
    html = response.content.decode()
    assert "Payment Test (internal)" not in html
    assert "Internal Sentinel Plan" not in html


def test_without_plans_on_sale_the_plans_section_is_omitted(no_plans, client):
    html = html_of(client)

    assert 'id="planes"' not in html
    assert "vs. ERPlora from" not in html


# --- test_home_plan_trial.py ------------------------------------------------------------------


def test_the_home_card_ends_with_the_trial_the_plan_grants(no_plans, client):
    make_plan("starter", trial_days=21)

    assert card_items(html_of(client), "Starter") == [
        "Unlimited users",
        "21-day free trial",
    ]


def test_the_home_card_follows_the_plan_when_its_trial_changes(no_plans, client):
    starter = make_plan("starter", trial_days=15)
    starter.trial_period_days = 30
    starter.save()

    assert card_items(html_of(client), "Starter")[-1] == "30-day free trial"


def test_the_home_card_trial_is_translated(no_plans, client):
    make_plan("starter", trial_days=21, name_es="Starter")

    assert card_items(html_of(client, language="es"), "Starter") == [
        "Usuarios ilimitados",
        "21 días de prueba gratis",
    ]


def test_a_plan_without_trial_shows_no_trial_line_on_the_home(no_plans, client):
    make_plan("free", trial_days=0, price_monthly=Decimal("0"))

    assert card_items(html_of(client), "Free") == ["Unlimited users"]


def test_painting_the_trial_never_writes_it_into_the_plan(no_plans, client):
    starter = make_plan("starter", trial_days=21)

    for language in ("en", "es"):
        html_of(client, language=language)

    starter.refresh_from_db()
    assert starter.features_en == ["Unlimited users"]
    assert starter.features_es == ["Usuarios ilimitados"]


def test_the_contact_section_states_the_real_trial_never_a_typed_one(no_plans, client):
    """The old section said «a 15-day free trial» by hand (the saas#2414 class of bug)."""
    make_plan("starter", trial_days=30)

    contact = section(html_of(client), "contacto")

    assert "30-day free trial" in contact
    assert "15-day" not in contact


# --- The ex-VAT note (test_net_price_display.py, the landing half; WORKFLOW F55) --------------


def test_the_home_shows_the_net_price_with_the_ex_vat_note_and_no_vat_figure(client):
    make_plan("net-display", price_monthly=Decimal("29.99"))

    plans = section(html_of(client), "planes")

    assert "29.99" in plans
    assert "36.29" not in plans and "36,29" not in plans
    assert "+ VAT" not in plans and "Spanish VAT" not in plans
    assert "All prices exclude VAT" in plans
    assert f'href="{reverse("public:terms")}"' in plans


# --- test_comparison_section.py ---------------------------------------------------------------


@pytest.fixture
def four_apps_one_flagged_premium():
    for app_id in ("pos", "inventory", "customers"):
        make_app(app_id)
    make_app("assistant", premium=True)


@pytest.mark.parametrize(
    ("language", "cell"),
    [("en", "4 on every plan"), ("es", "4 en todos los planes")],
)
def test_the_comparison_cell_counts_every_app_on_every_plan(
    client, four_apps_one_flagged_premium, language, cell
):
    """Every plan includes all the apps (PLAN §32): the cell said «3 free + 1 premium»."""
    comparison = section(html_of(client, language=language), "comparativa")

    assert f'<td data-title="ERPlora" class="text-primary font-semibold">{cell}</td>' in comparison
    assert " free +" not in comparison and " gratis +" not in comparison


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            "Every plan includes all the apps, the Free one too; paid plans add unlimited devices, "
            "more capacity and higher AI and WhatsApp quotas.",
        ),
        (
            "es",
            "Todos los planes incluyen todas las apps, también Gratis; los de pago añaden dispositivos "
            "ilimitados, más capacidad y más mensajes de IA y WhatsApp.",
        ),
    ],
)
def test_the_comparison_note_says_what_the_paid_plans_add(client, language, sentence):
    """It said «paid tiers add capacity, multi-device and the premium apps»."""
    comparison = section(html_of(client, language=language), "comparativa")

    assert sentence in comparison


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            "Every plan includes all the apps. Paid plans add unlimited devices, more capacity and "
            "higher AI and WhatsApp quotas.",
        ),
        (
            "es",
            "Todos los planes incluyen todas las apps. Los de pago añaden dispositivos ilimitados, "
            "más capacidad y más mensajes de IA y WhatsApp.",
        ),
    ],
)
def test_the_plans_section_says_every_plan_includes_all_the_apps(client, language, sentence):
    """The same promise as the head of /pricing/ (saas#119); it said «all the free apps, and the
    paid plans include the premium apps too»."""
    plans = section(html_of(client, language=language), "planes")

    assert f'<p class="ep-section-sub">{sentence}</p>' in plans


# --- test_ai_data_residency.py ----------------------------------------------------------------


def test_the_landing_states_the_ai_runs_on_european_servers(client):
    html = html_of(client, language="es").lower()

    assert "servidores europeos" in html or "servidores en europa" in html


def test_the_landing_says_the_assistant_data_stays_in_the_eu(client):
    html = html_of(client, language="es").lower()

    assert "unión europea" in html or "no sale" in html


def test_the_landing_links_the_residency_claim_to_the_privacy_policy(client):
    assert reverse("public:privacy") in html_of(client, language="es")


def test_no_page_of_this_lot_names_hetzner_as_the_host(client):
    """Ioan, 2026-10-13: the servers are on AWS (Ireland region); the AI stays in Frankfurt."""
    for path in (HOME, CONTACT):
        for language in ("en", "es"):
            html = html_of(client, path, language)
            assert "Hetzner" not in html, (path, language)
            assert "Falkenstein" not in html, (path, language)


# --- JSON-LD of the home (test_structured_data.py) --------------------------------------------


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


# --- The contact page -------------------------------------------------------------------------


def test_the_contact_page_has_the_form_posting_to_the_submit_route(client):
    html = html_of(client, CONTACT)

    assert '<form id="contact-form"' in html
    assert f'action="{reverse("public:contact_submit")}"' in html
    assert 'name="csrfmiddlewaretoken"' in html
    assert '<input type="hidden" name="next" value="/contact/">' in html
    for field in ("first_name", "last_name", "email", "phone", "message"):
        assert f'name="{field}"' in html, field
    assert 'id="contacto"' in html


def test_the_contact_page_gives_the_other_ways_to_reach_us(client):
    """PUBLIC-G41: the support address of the footer (no more «info@»), and the support chat."""
    html = html_of(client, CONTACT)

    assert f"mailto:{settings.SUPPORT_EMAIL}" in html
    assert 'href="https://wa.me/34643759040"' in html


def test_the_contact_page_in_spanish(client):
    html = html_of(client, CONTACT, language="es")

    assert "Ponte en contacto" in html or "Contacto" in html
    assert "Nombre" in html


def hero(html: str) -> str:
    start = html.index('class="hero-bg')
    return html[start : html.index("</section>", start)]


@pytest.mark.parametrize(
    ("language", "availability", "reply"),
    [
        ("en", "High availability", "in business hours"),
        ("es", "Alta disponibilidad", "en horas laborables"),
    ],
)
def test_the_hero_promises_what_we_do_not_an_sla_or_round_the_clock_support(
    client, language, availability, reply
):
    """L8: no «Uptime 99.95%» (there is no SLA) and no «Support 24/7»: the form's 4 business hours."""
    stats = hero(html_of(client, language=language))

    assert availability in stats
    assert ">AWS<" in stats
    assert ">4 h<" in stats
    assert reply in stats


@pytest.mark.parametrize(
    ("language", "cell"), [("en", "High availability on AWS"), ("es", "Alta disponibilidad en AWS")]
)
def test_the_platform_bento_says_high_availability_on_aws(client, language, cell):
    assert f'<h3 class="ep-bento-item__title">{cell}</h3>' in html_of(client, language=language)


@pytest.mark.parametrize(
    ("language", "heading", "reply"),
    [
        ("en", "Response time", "Within 4 business hours"),
        ("es", "Tiempo de respuesta", "En un plazo de 4 horas laborables"),
    ],
)
def test_the_contact_page_promises_the_reply_time_of_the_form(client, language, heading, reply):
    """L8: «Available 24/7/365» was not true; the form already promised 4 business hours."""
    html = html_of(client, CONTACT, language=language)
    other_ways = html[html.index('<h2 class="font-display') :]

    assert heading in other_ways
    assert reply in other_ways


def test_the_home_carries_the_contact_form_too(client):
    contact = section(html_of(client), "contacto")

    assert '<form id="contact-form"' in contact
    assert '<input type="hidden" name="next" value="/">' in contact


# --- The contact form: /contact/submit/ (test_views.py, test_public_pages.py) -----------------

VALID = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+34 600 000 000",
    "message": "Hello, I would like more information about ERPlora.",
}


def submit(client, **overrides):
    return client.post(SUBMIT, {**VALID, **overrides})


def messages_of(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@pytest.fixture(autouse=True)
def fresh_limits():
    """The limit per address lives in the cache: each test starts with a clean bucket."""
    cache.clear()
    yield
    cache.clear()


def test_the_submit_route_is_post_only(client):
    assert client.get(SUBMIT).status_code == 405


def test_a_valid_message_is_mailed_to_support_and_answers_with_a_redirect(
    client, settings
):
    settings.SUPPORT_EMAIL = "support@erplora.test"

    response = submit(client, next="/contact/")

    assert response.status_code == 302
    assert response["Location"] == "/contact/#contacto"
    (sent,) = mail.outbox
    assert sent.to == ["support@erplora.test"]
    assert sent.from_email == settings.DEFAULT_FROM_EMAIL
    assert sent.subject == "Contact Form: John Doe"
    for line in (
        "Name: John Doe",
        "Email: john.doe@example.com",
        "Phone: +34 600 000 000",
        "Hello, I would like more information about ERPlora.",
    ):
        assert line in sent.body, line
    assert any("Thanks" in message for message in messages_of(response))


def test_without_a_phone_the_mail_says_so(client):
    submit(client, phone="")

    assert "Phone: Not provided" in mail.outbox[0].body


def test_the_mail_body_is_plain_text_never_escaped_html(client):
    submit(client, message="Tom & Jerry <b>bold</b>")

    assert "Tom & Jerry <b>bold</b>" in mail.outbox[0].body


def test_a_name_cannot_inject_a_header_into_the_subject(client):
    response = submit(client, first_name="John\nBcc: victim@example.com")

    assert response.status_code == 302
    (sent,) = mail.outbox
    assert "\n" not in sent.subject
    assert sent.bcc == []


@pytest.mark.parametrize("missing", ["first_name", "last_name", "email", "message"])
def test_every_field_but_the_phone_is_required(client, missing):
    response = submit(client, **{missing: "  "})

    assert response.status_code == 302
    assert mail.outbox == []
    assert any(
        "All fields are required" in message for message in messages_of(response)
    )


def test_an_empty_post_redirects_with_the_error(client):
    response = client.post(SUBMIT, {})

    assert response.status_code == 302
    assert response["Location"] == "/#contacto"
    assert mail.outbox == []


def test_an_invalid_email_is_refused(client):
    response = submit(client, email="not-an-address")

    assert response.status_code == 302
    assert mail.outbox == []
    assert any("valid email" in message for message in messages_of(response))


def test_an_external_next_is_refused(client):
    response = submit(client, next="https://example.com/phishing")

    assert response.status_code == 302
    assert response["Location"] == "/#contacto"


def test_without_next_it_goes_back_to_the_referer(client):
    response = client.post(SUBMIT, VALID, HTTP_REFERER="http://testserver/pricing/")

    assert response["Location"] == "http://testserver/pricing/#contacto"


def test_an_anchor_already_in_next_is_not_doubled(client):
    response = submit(client, next="/pricing/#faq")

    assert response["Location"] == "/pricing/#faq"


def test_a_mail_failure_is_told_to_the_visitor_and_logged(client, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OSError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)

    response = submit(client)

    assert response.status_code == 302
    assert any("something went wrong" in message for message in messages_of(response))
    assert "Contact form message could not be sent" in caplog.text


def test_the_messages_are_translated(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    response = submit(client, message="")

    assert messages_of(response) and all(
        "All fields are required" not in message for message in messages_of(response)
    )


@override_settings(RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="2/h")
def test_the_form_is_limited_per_address(client):
    """reCAPTCHA is gone (ADR-0154): the form is protected by a limit per address."""
    for _ in range(2):
        assert submit(client).status_code == 302
    assert len(mail.outbox) == 2

    throttled = submit(client)

    assert throttled.status_code == 302
    assert len(mail.outbox) == 2, "a throttled message must not be mailed"
    assert any("Too many messages" in message for message in messages_of(throttled))


@override_settings(
    RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="1/h", TRUSTED_PROXY_HOPS=1
)
def test_the_limit_is_per_visitor_not_per_load_balancer(client):
    """Behind the ALB every request comes from the balancer: the visitor is the last hop of
    ``X-Forwarded-For`` (the address the balancer saw; ``public.client_ip``). Keyed on the
    balancer, the whole internet would share one bucket; on the first hop, a forged header would
    be a fresh one per message."""
    first = client.post(SUBMIT, VALID, HTTP_X_FORWARDED_FOR="203.0.113.7")
    second = client.post(SUBMIT, VALID, HTTP_X_FORWARDED_FOR="198.51.100.9")
    forged = client.post(
        SUBMIT, VALID, HTTP_X_FORWARDED_FOR="192.0.2.50, 203.0.113.7"
    )

    assert (first.status_code, second.status_code) == (302, 302)
    assert len(mail.outbox) == 2
    assert any("Too many messages" in message for message in messages_of(forged))


@override_settings(
    RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="1/h", CACHES=VALKEY_DOWN
)
def test_with_valkey_down_the_form_still_sends(client):
    """The limit cannot count without the cache: it lets the message through (fail open) instead
    of refusing every visitor. Never a 500."""
    responses = [submit(client), submit(client)]

    assert [response.status_code for response in responses] == [302, 302]
    assert len(mail.outbox) == 2


def test_the_visitor_address_is_remote_addr(rf):
    """``public.client_ip`` already put the visitor in ``REMOTE_ADDR``: the header is its job."""
    forwarded = rf.post(
        SUBMIT, HTTP_X_FORWARDED_FOR="203.0.113.7", REMOTE_ADDR="192.0.2.1"
    )
    plain = rf.post(SUBMIT, REMOTE_ADDR="192.0.2.1")

    assert landing.visitor_address(None, forwarded) == "192.0.2.1"
    assert landing.visitor_address(None, plain) == "192.0.2.1"


@pytest.mark.parametrize("address", ["", "not-an-ip"])
def test_without_a_real_address_the_visitor_shares_the_unknown_bucket(rf, address):
    """The limiter masks the key with ``ipaddress``: junk there would be a 500 on a public door."""
    request = rf.post(SUBMIT, REMOTE_ADDR=address)

    assert landing.visitor_address(None, request) == landing.UNKNOWN_ADDRESS


# --- Smoke of the pages of this lot (tests/unit/test_public_pages.py) -------------------------


@pytest.mark.parametrize("path", [HOME, CONTACT])
def test_the_page_carries_the_brand_the_navbar_and_the_footer(client, path):
    html = html_of(client, path)

    assert "ERPlora" in html
    assert '<nav class="ep-navbar"' in html
    assert '<footer class="ep-footer"' in html


def test_the_navbar_links_features_apps_pricing_and_contact_in_that_order(client):
    html = html_of(client)
    links = html[html.index('<div class="ep-navbar__links">') :]
    links = links[: links.index("</div>")]

    assert re.findall(r'href="([^"]+)"', links) == [
        reverse("public:features"),
        reverse("public:store"),
        reverse("public:pricing"),
        reverse("public:contact"),
    ]


def test_the_footer_has_its_social_links_and_the_legal_ones(client):
    html = html_of(client)
    footer = html[html.index('<footer class="ep-footer"') :]

    assert "linkedin.com" in footer
    assert "Privacy" in footer and "Terms" in footer
    assert f'href="{reverse("public:pricing")}"' in footer
    assert f'href="{reverse("public:contact")}"' in footer
    assert f'href="{reverse("public:collaborate")}"' in footer


@pytest.mark.parametrize(
    "path",
    [
        "/contact/does-not-exist/",
        "/pricing/does-not-exist/deeper/",
        "/api/nonexistent/",
    ],
)
def test_a_page_that_does_not_exist_is_a_404(client, path):
    """Under the public web's segments and the API. Any other unknown path is the SPA's (its
    router paints the not-found page): config/tests/test_urls.py pins that the shell answers."""
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/features/",
        "/security/",
        "/updates/",
        "/about/",
        "/careers/",
        "/blog/",
        "/press/",
        "/help/",
        "/support/",
        "/legal/privacy/",
        "/legal/terms/",
        "/pricing/",
        "/collaborate/",
        "/contact/",
        "/",
    ],
)
def test_every_public_page_answers(client, path):
    """The static pages of the old ``TestStaticPages`` (skipped there for importing views that had
    moved), rewritten as it asked: the live URL answers 200."""
    assert client.get(path).status_code == 200


# --- The shared patterns (test_ui_stack_contract.py, home and contact) ------------------------


def landing_source(*parts: str) -> str:
    return LANDING_TEMPLATES.joinpath(*parts).read_text(encoding="utf-8")


def test_the_contact_form_uses_ionic_validation_without_native_browser_feedback():
    form = landing_source("_contact_form.html")

    assert '<form id="contact-form"' in form
    assert "novalidate" in form
    assert "el.setAttribute('aria-invalid', invalid ? 'true' : 'false')" in form
    assert "el.removeAttribute('aria-invalid')" in form
    assert (
        "if (isEmail) el.setAttribute('error-text', val ? EMAIL_ERROR : REQUIRED_ERROR)"
        in form
    )
    assert '<script nonce="{{ csp_nonce }}">' in form
    # mode="md": an outline field does not paint in ios mode (working-rules §2).
    assert form.count('fill="outline"') == form.count('mode="md"') == 5


def test_the_contact_page_uses_the_shared_patterns():
    contact = landing_source("contact.html")
    hero = next(
        line
        for line in contact.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "hero_compact=True" in hero
    assert '<h2 class="font-display font-semibold text-2xl mb-6">' in contact
    assert '<h3 class="font-semibold mb-4">' in contact
    assert '<section id="contacto" class="ep-section">' in contact
    assert "style=" not in contact


def test_the_home_sections_use_the_shared_section_rhythm():
    offenders = [
        path.name
        for path in sorted((LANDING_TEMPLATES / "home").glob("*.html"))
        if re.search(r"\bpy-(?:14|16|20)\b", path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_the_home_is_the_eleven_sections_of_the_old_landing_in_order():
    home = landing_source("home.html")

    assert re.findall(r'include "public/landing/home/(_[a-z_]+)\.html"', home) == [
        "_hero",
        "_cost_vs_stack",
        "_platform_bento",
        "_apps",
        "_app",
        "_ecosystem",
        "_plans",
        "_comparison",
        "_build_to_fit",
        "_cta",
        "_contact",
    ]


# --- Every message has its Spanish entry ------------------------------------------------------


def landing_templates() -> list[Path]:
    return sorted(LANDING_TEMPLATES.rglob("*.html"))


@pytest.mark.parametrize("template", landing_templates(), ids=lambda path: path.name)
def test_every_message_of_a_landing_template_has_its_spanish_entry(template):
    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(template)

    assert [m for m in messages if not catalog.get(m)] == []


def test_the_python_messages_have_their_spanish_entry(client):
    """The form's answers and the contact section's trial line live in public/landing.py."""
    texts = {}
    for language in ("en", "es"):
        with translation.override(language):
            texts[language] = [
                str(text)
                for text in (
                    *landing.FORM_MESSAGES.values(),
                    landing.sent_message(),
                    landing.contact_trial_note((15, 15)),
                    landing.contact_trial_note((15, 30)),
                )
            ]

    assert [en for en, es in zip(texts["en"], texts["es"]) if en == es] == []


def test_the_mail_templates_are_plain_text_and_internal():
    """Support reads them: English, no i18n, no HTML escaping."""
    subject = (EMAIL_TEMPLATES / "contact_subject.txt").read_text(encoding="utf-8")
    body = (EMAIL_TEMPLATES / "contact_body.txt").read_text(encoding="utf-8")

    assert "{% autoescape off %}" in subject and "{% autoescape off %}" in body
    assert "trans" not in subject + body


def test_the_feature_card_paints_an_inline_icon_svg():
    """public/components/feature_card.html takes the app's cleaned ``icon_svg`` as product_card does."""
    from django.template.loader import render_to_string
    from django.utils.safestring import mark_safe

    html = render_to_string(
        "public/components/feature_card.html",
        {"icon_svg": mark_safe(CUBE_SVG), "heading": "Inventory", "body": "Stock"},
    )

    assert '<span class="ep-feature-card__icon"><svg' in html


# --- The sitemap and llms.txt (origin's StaticPagesSitemap and llms_txt) ----------------------


@pytest.mark.parametrize(
    ("name", "priority"),
    [("public:home", 1.0), ("public:pricing", 0.9), ("public:contact", 0.6)],
)
def test_the_pages_of_this_lot_are_in_the_sitemap_with_the_old_priorities(name, priority):
    from public.sitemaps import StaticPagesSitemap

    assert (name, priority) in StaticPagesSitemap.pages


def test_llms_txt_starts_with_the_home_and_the_pricing(client):
    body = client.get("/llms.txt").content.decode()
    start = body[body.index("## Start here") :]

    lines = [line for line in start.splitlines() if line.startswith("- [")]
    assert lines[0] == (
        "- [What ERPlora is](https://testserver/): the product in one page — apps, pricing and "
        "the counter app."
    )
    assert lines[1] == (
        "- [Pricing](https://testserver/pricing/): plans, what each includes, and the answers to "
        "the usual billing questions."
    )


def test_llms_txt_offers_the_terms_and_the_contact_page_as_optional_reading(client):
    body = client.get("/llms.txt").content.decode()
    optional = body[body.index("## Optional") :]

    assert "- [Terms](https://testserver/legal/terms/)" in optional
    assert "- [Contact](https://testserver/contact/)" in optional


def test_the_home_points_to_the_app_page(client):
    """test_installable_app_page.py asked the home; test_appdist.py asked the footer until L7."""
    app_section = section(html_of(client), "app")

    assert f'href="{reverse("public:app")}"' in app_section
    assert "/bridge/" not in app_section


# --- PUBLIC-G39: the message reaches support with the visitor to answer, and nothing typed is lost ---


def form_of(html: str) -> str:
    start = html.index('<form id="contact-form"')
    return html[start : html.index("</form>", start)]


def test_the_mail_to_support_replies_to_the_visitor(client):
    """Support answers with «Reply»: the mail comes from our sender but replies to the visitor."""
    submit(client)

    (sent,) = mail.outbox
    assert sent.reply_to == ["john.doe@example.com"]
    assert sent.from_email == settings.DEFAULT_FROM_EMAIL


@pytest.mark.parametrize(
    "overrides", [{"last_name": ""}, {"email": "not-an-address"}], ids=["required", "email"]
)
def test_a_refused_message_comes_back_with_what_was_typed(client, overrides):
    response = submit(client, next=CONTACT, **overrides)

    form = form_of(client.get(response["Location"].split("#")[0]).content.decode())
    assert 'value="John"' in form
    assert 'value="+34 600 000 000"' in form
    assert "Hello, I would like more information about ERPlora." in form
    assert f'value="{overrides.get("email", VALID["email"])}"' in form


def test_a_mail_failure_keeps_what_was_typed_on_the_home_too(client, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)

    response = submit(client, next=HOME)

    assert 'value="John"' in form_of(html_of(client, response["Location"].split("#")[0]))


def test_what_was_typed_is_shown_once_and_never_after_a_sent_message(client):
    submit(client, next=CONTACT, last_name="")
    client.get(CONTACT)

    assert 'value="John"' not in form_of(html_of(client, CONTACT))
    submit(client, next=CONTACT)
    assert 'value="John"' not in form_of(html_of(client, CONTACT))


def test_what_was_typed_is_escaped_when_it_comes_back(client):
    submit(client, next=CONTACT, last_name="", first_name='"><script>x()</script>')

    form = form_of(html_of(client, CONTACT))
    assert "<script>x()" not in form
    assert "&quot;&gt;&lt;script&gt;" in form


# --- PUBLIC-G40: arriving from another page keeps what the visitor came for ----------------------------


def test_the_collaborate_button_opens_the_form_on_its_topic(client):
    html = html_of(client, "/collaborate/")

    assert f'href="{CONTACT}?subject=collaborate"' in html


def test_a_known_topic_rides_with_the_form_and_names_the_mail(client):
    form = form_of(html_of(client, f"{CONTACT}?subject=collaborate"))

    assert '<input type="hidden" name="subject" value="collaborate">' in form
    submit(client, subject="collaborate")
    assert mail.outbox[0].subject == "Contact Form [Collaborator program]: John Doe"


def test_the_security_button_opens_the_form_on_its_topic(client):
    html = html_of(client, "/security/")

    assert f'href="{CONTACT}?subject=security"' in html
    submit(client, subject="security")
    assert mail.outbox[0].subject == "Contact Form [Security]: John Doe"


@pytest.mark.parametrize("subject", ["Collaborator Program", "<b>x</b>", "x" * 300, ""])
def test_an_unknown_topic_is_ignored(client, subject):
    form = form_of(html_of(client, f"{CONTACT}?subject={subject}"))

    assert 'name="subject"' not in form
    submit(client, subject=subject)
    assert mail.outbox[0].subject == "Contact Form: John Doe"


# --- PUBLIC-G41: one support address, one chat and one reply time, from one place ------------------------


def test_the_contact_page_email_is_the_support_address(client, settings):
    settings.SUPPORT_EMAIL = "help@erplora.test"

    for html in (html_of(client, CONTACT), section(html_of(client), "contacto")):
        assert "mailto:help@erplora.test" in html
        assert "info@erplora.com" not in html


def test_the_reply_time_is_written_once(client, monkeypatch):
    monkeypatch.setattr(context_processors, "SUPPORT_REPLY_HOURS", 6)

    contact = html_of(client, CONTACT)
    home = html_of(client)
    response = submit(client)

    assert "Within 6 business hours" in contact
    assert "We typically respond within 6 business hours." in form_of(contact)
    assert ">6 h<" in hero(home)
    assert any("within 6 business hours" in message for message in messages_of(response))
    assert "4 business hours" not in contact + home


def test_the_reply_time_in_spanish(client):
    html = html_of(client, CONTACT, language="es")

    assert "En un plazo de 4 horas laborables" in html
    assert "Normalmente respondemos en un plazo de 4 horas laborables." in html


def test_the_chat_is_written_once(client, monkeypatch):
    monkeypatch.setattr(context_processors, "SUPPORT_WHATSAPP_URL", "https://wa.me/34600000000")

    for html in (html_of(client, CONTACT), section(html_of(client), "contacto")):
        assert 'href="https://wa.me/34600000000"' in html
        assert "34643759040" not in html


# --- reCAPTCHA on the contact form (Ioan, 2026-10-22: every public form; live.recaptcha) ------------------------
# ADR-0154 had retired it for the limit per address alone; both stand now: the limit first (a throttled message never
# costs an assessment), then the fields, then Google's verdict on `recaptcha_token` (made for `contact` by
# frontend/recaptcha.ts), right before the mail. Google is played by `FakeGoogleRecaptcha` (conftest.py).

UNVERIFIED = "We could not check that you are a person. Try again."


def test_a_message_without_a_token_is_not_mailed_and_says_why(client, recaptcha):
    response = submit(client, next=CONTACT)

    assert response.status_code == 302
    assert mail.outbox == []
    assert UNVERIFIED in messages_of(response)
    assert recaptcha.asked == []


@pytest.mark.parametrize("token", ["bot:contact", "human:demo_request", "forged"], ids=["bot", "other-form", "forged"])
def test_a_bad_token_is_not_mailed(client, recaptcha, token):
    response = submit(client, recaptcha_token=token)

    assert mail.outbox == []
    assert UNVERIFIED in messages_of(response)


def test_a_persons_message_is_mailed(client, recaptcha):
    response = submit(client, recaptcha_token="human:contact")

    assert len(mail.outbox) == 1
    assert recaptcha.asked == [("human:contact", "contact")]
    assert any("Thanks" in message for message in messages_of(response))


def test_google_down_keeps_the_message_unsent_and_what_was_typed(client, recaptcha):
    recaptcha.down = True

    response = submit(client, next=CONTACT, recaptcha_token="human:contact")

    assert mail.outbox == []
    assert 'value="John"' in form_of(client.get(response["Location"].split("#")[0]).content.decode())


def test_an_incomplete_message_never_asks_google(client, recaptcha):
    submit(client, last_name="", recaptcha_token="human:contact")

    assert recaptcha.asked == []


@override_settings(RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="1/h")
def test_a_throttled_message_never_asks_google(client, recaptcha):
    submit(client, recaptcha_token="human:contact")

    submit(client, recaptcha_token="human:contact")

    assert recaptcha.asked == [("human:contact", "contact")]


def test_the_unverified_message_speaks_spanish(client, recaptcha):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    response = submit(client)

    assert "No hemos podido comprobar que eres una persona. Vuelve a intentarlo." in messages_of(response)


@pytest.mark.parametrize("path", [HOME, CONTACT])
def test_the_form_with_recaptcha_asks_google_for_its_token_and_says_so(client, recaptcha, path):
    html = html_of(client, path)

    form = form_of(html)
    assert 'data-recaptcha-action="contact"' in html
    assert 'data-recaptcha-site-key="test-site-key"' in html
    assert 'name="recaptcha_token"' in form
    assert "This site is protected by reCAPTCHA and the Google" in html
    assert 'href="https://policies.google.com/privacy"' in html
    assert 'href="https://policies.google.com/terms"' in html


def test_the_form_without_recaptcha_loads_nothing_of_google(client):
    html = html_of(client, CONTACT)

    assert "data-recaptcha" not in html
    assert "protected by reCAPTCHA" not in html


def test_the_notice_speaks_spanish(client, recaptcha):
    html = html_of(client, CONTACT, language="es")

    assert "Este sitio está protegido por reCAPTCHA" in html
    assert "Política de Privacidad" in html
    assert "Condiciones del Servicio" in html


def test_the_context_gives_the_templates_the_site_key(rf, recaptcha, settings):
    assert context_processors.public_site(rf.get("/"))["RECAPTCHA_SITE_KEY"] == "test-site-key"
    settings.LIVE = {**settings.LIVE, "recaptcha": {"enabled": False, "site_key": "test-site-key"}}
    assert context_processors.public_site(rf.get("/"))["RECAPTCHA_SITE_KEY"] == ""
