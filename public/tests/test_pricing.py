"""``/pricing/`` and ``/pricing/<slug>/``: the plans on sale (public/pricing.py, spec §8.1).

Port of ERPlora/saas ``apps/public/pricing/tests/`` (origin/develop c5ca8ca, 38 tests):
``test_index.py`` (6), ``test_faq_structured_data.py`` (6), ``test_internal_plans_are_never_public.py``
(the pricing half; the home's case lives in test_landing.py), ``test_plan_comparison_table.py`` (6),
``test_pricing_card_trial.py`` (5) and ``test_pricing_trial_period.py`` (10); the ``_vat_note`` half
of ``tests/unit/billing/test_net_price_display.py`` (7) and the pricing contracts of
``apps/public/landing/tests/test_ui_stack_contract.py``. What changed, and why:

* ``public`` imports no model (plan §3.m): the pages read ``hubs.plan.list``. The tests still create
  the rows with the ORM of ``hubs`` (``name_en``, ``features_en``…, the columns of saas-next's
  ``Plan``) and read the page or its context, whose plans are dicts now, matched by ``slug``;
* the cards are the ``ep-pricing-card`` partial (``<ok-pricing-card>`` is gone, PLAN §16.11), so the
  helper that read a card's ✓ lines reads that partial's markup;
* the trial range comes from the trial of each plan on sale (``trial_period_days`` of the
  operation's rows), the same reading as ``Plan.objects.signup_trial_days()``;
* the comparison column «Modules included» is «Apps included» (decision 19: the catalogue is «Apps»
  in en and es), and a premium app is included in the paid plans (decision 17): no «premium
  add-ons», no fee per activated app, no «marketplace» in the competitor table;
* the storage answer names the host, AWS in its Ireland region (Ioan, 2026-10-14), never Hetzner;
* ``Plan.objects.public()`` is pinned by ``hubs/tests/test_plan_list.py``; here, what the pages
  show of it;
* the ex-VAT note is ``public/partials/_vat_note.html`` and links ``public:terms``; the panel's
  selling screens (``/dashboard/…``) and the checkout cases belong to the panel (block 4).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation

from hubs.models import Plan
from public import pricing
from public.tests.test_legal import template_messages

pytestmark = [pytest.mark.django_db]

ROOT = Path(settings.BASE_DIR)
PRICING_TEMPLATES = ROOT / "public" / "templates" / "public" / "pricing"
VAT_NOTE = ROOT / "public" / "templates" / "public" / "partials" / "_vat_note.html"
CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
INDEX = "/pricing/"


def make_plan(slug: str, *, trial_days: int = 0, features=None, **fields) -> Plan:
    defaults = {
        "name_en": slug.replace("-", " ").title(),
        "description_en": f"{slug} plan",
        "price_monthly": Decimal("29.99"),
        "trial_period_days": trial_days,
        "features_en": ["Unlimited users"] if features is None else features,
        "is_active": True,
    }
    return Plan.objects.create(slug=slug, **{**defaults, **fields})


@pytest.fixture
def seeded():
    call_command("sync_hub_plans", stdout=StringIO())


def get(client, path: str = INDEX, language: str | None = None):
    if language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response


def html_of(client, path: str = INDEX, language: str | None = None) -> str:
    return get(client, path, language).content.decode()


CARD_START = re.compile(r'<div class="ep-pricing-card(?: ep-pricing-card--featured)?">')
CARD_ITEM = re.compile(
    r'<li><span class="ep-pricing-card__check" aria-hidden="true">✓</span><span>(.*?)</span></li>',
    re.S,
)


def card_items(html: str, plan_name: str) -> list[str]:
    """The ✓ lines of one plan card, so the note under the cards cannot make a test pass."""
    cards = [
        chunk
        for chunk in CARD_START.split(html)[1:]
        if f'<div class="ep-pricing-card__name">{plan_name}</div>' in chunk
    ]
    assert cards, f"no pricing card for {plan_name}"
    card = cards[0].split("</ul>", 1)[0]
    return [" ".join(item.split()) for item in CARD_ITEM.findall(card)]


def json_ld_blocks(html: str) -> list[dict]:
    marker = '<script type="application/ld+json">'
    blocks, cursor = [], 0
    while (start := html.find(marker, cursor)) != -1:
        start += len(marker)
        end = html.index("</script>", start)
        blocks.append(json.loads(html[start:end]))
        cursor = end
    return blocks


def faq_page_of(html: str) -> dict:
    block = next(
        (block for block in json_ld_blocks(html) if block.get("@type") == "FAQPage"),
        None,
    )
    assert block, "no FAQPage JSON-LD on /pricing/"
    return block


def visible_markup(html: str) -> str:
    """The page with every ``<script>`` removed: what a reader actually sees."""
    return re.sub(
        r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )


# --- Routes -----------------------------------------------------------------------------------


def test_the_routes():
    assert reverse("public:pricing") == "/pricing/"
    assert reverse("public:pricing_detail", args=["starter"]) == "/pricing/starter/"


def test_the_pages_only_answer_safe_methods(client, seeded):
    assert client.post(INDEX).status_code == 405
    assert client.post("/pricing/starter/").status_code == 405


# --- test_index.py ----------------------------------------------------------------------------


def test_pricing_renders_active_plan_data_from_the_database(client):
    make_plan(
        "db-public-sentinel",
        name_en="DB Public Sentinel",
        description_en="Public description loaded from the database",
        price_monthly=Decimal("31.23"),
        features=["Database feature sentinel"],
        display_order=-20,
    )
    make_plan(
        "db-upgrade-sentinel",
        name_en="DB Upgrade Sentinel",
        description_en="Upgrade description loaded from the database",
        price_monthly=Decimal("62.46"),
        features=["Upgrade feature sentinel", "────────────────────"],
        display_order=-10,
        upgrade_only=True,
    )
    make_plan(
        "db-inactive-sentinel",
        name_en="DB Inactive Sentinel",
        price_monthly=Decimal("99.99"),
        is_active=False,
    )

    response = get(client)

    assert [plan["slug"] for plan in response.context["plans_main"]] == [
        "db-public-sentinel"
    ]
    (upgrade,) = response.context["plans_pro"]
    assert upgrade["slug"] == "db-upgrade-sentinel"
    assert upgrade["display_features"] == ["Upgrade feature sentinel"]
    html = response.content.decode()
    for text in (
        "DB Public Sentinel",
        "€31.23",
        "Public description loaded from the database",
        "Database feature sentinel",
        "DB Upgrade Sentinel",
        "€62.46",
        "Upgrade description loaded from the database",
        "Upgrade feature sentinel",
    ):
        assert text in html, text
    assert "────────────────────" not in html
    assert "DB Inactive Sentinel" not in html


# saas#1760: the public page must not rank plans by the box they run on.
PUBLIC_SPEC_PATTERNS = [
    (r"\bv?CPU\b", "CPU spec"),
    (r"\bRAM\b", "RAM spec"),
    (r"\bDB connections\b", "DB connection quota"),
    (r"\bDB storage\b", "DB storage quota"),
    (r"\bcompute resources\b", "compute multiplier"),
]
# Case-sensitive on purpose: case-insensitively «gap-3 mb-2» reads as «3 MB».
SIZE_PATTERN = r"\b\d+\s*(MB|GB|TB)\b"


def test_pricing_page_never_renders_infrastructure_specs(client, seeded):
    html = html_of(client)

    for pattern, label in PUBLIC_SPEC_PATTERNS:
        match = re.search(pattern, html, re.I)
        assert match is None, (
            f"{label} rendered on /pricing/: {html[max(0, match.start() - 90) : match.end() + 90]!r}"
        )
    size = re.search(SIZE_PATTERN, html)
    assert size is None, (
        f"raw size rendered on /pricing/: {html[max(0, size.start() - 90) : size.end() + 90]!r}"
    )


def test_the_size_pattern_tells_megabytes_from_utility_margins():
    """Positive control: the guard above must discriminate, not just stay quiet."""
    assert re.search(SIZE_PATTERN, "512 MB RAM")
    assert re.search(SIZE_PATTERN, "8 GB database storage (2x Standard)")
    assert not re.search(SIZE_PATTERN, '<div class="flex items-baseline gap-3 mb-2">')


def test_pricing_page_states_the_billing_unit_is_the_hub(client, seeded):
    """A customer with two shops must not think the second one costs double."""
    assert "per hub" in html_of(client).lower()


def test_billing_unit_survives_translation_to_spanish(client, seeded):
    """The template strings, not the seed's «Precio por hub»: the cards (main and upgrade-only)
    both carry the period, so the count tells them apart."""
    html = html_of(client, language="es")

    assert html.count("/ mes por hub") >= 2
    assert "Mensual, por hub" in html
    assert "+ IVA" not in html
    for pattern, label in PUBLIC_SPEC_PATTERNS:
        assert re.search(pattern, html, re.I) is None, label


def test_pricing_page_publishes_no_uptime_sla(client, seeded):
    """The terms (99.5 %, reasonable efforts) are the only availability statement."""
    html = html_of(client)

    match = re.search(r"\d{2}[.,]\d+\s*%\s*(uptime|SLA|disponibilidad)", html, re.I)
    assert match is None, match and match.group(0)


# --- test_faq_structured_data.py --------------------------------------------------------------


def test_there_is_a_faq_page_block(client):
    assert faq_page_of(html_of(client))["@context"] == "https://schema.org"


def test_every_faq_entry_is_a_question_with_an_answer(client):
    for entry in faq_page_of(html_of(client))["mainEntity"]:
        assert entry["@type"] == "Question"
        assert entry["name"].strip()
        assert entry["acceptedAnswer"]["@type"] == "Answer"
        assert entry["acceptedAnswer"]["text"].strip()


def test_the_faq_has_one_entry_per_real_question(client):
    assert len(faq_page_of(html_of(client))["mainEntity"]) == len(pricing.faq_items())


def test_every_marked_up_question_is_visible_on_the_page(client):
    """The rule Google enforces: markup describes what the user can see."""
    html = html_of(client)
    body = visible_markup(html)
    # Control: the JSON-LD really is gone, so a question cannot match its own markup.
    assert "FAQPage" not in body

    for entry in faq_page_of(html)["mainEntity"]:
        assert entry["name"] in body, f"{entry['name']!r} is marked up but not rendered"


def test_the_questions_render_in_spanish(client):
    assert "¿Puedo cambiar de plan en cualquier momento?" in html_of(
        client, language="es"
    )


def test_the_faq_json_ld_is_translated_too(client):
    questions = [
        entry["name"]
        for entry in faq_page_of(html_of(client, language="es"))["mainEntity"]
    ]

    assert "¿Puedo cambiar de plan en cualquier momento?" in questions


def test_the_faq_is_an_ionic_accordion_opened_on_its_first_question(client):
    html = html_of(client)
    faq = html[html.index('<section id="faq"') :]

    assert f'<ion-accordion-group value="{pricing.faq_items()[0]["key"]}">' in faq
    assert faq.count("<ion-accordion ") == len(pricing.faq_items())


# --- test_internal_plans_are_never_public.py (the pricing half) --------------------------------


@pytest.fixture
def catalog(seeded):
    """The seeded catalog plus an internal plan that sorts FIRST, and a retired one."""
    make_plan(
        "internal-sentinel",
        name_en="Internal Sentinel Plan",
        price_monthly=Decimal("0.50"),
        display_order=-100,
        internal_only=True,
    )
    make_plan(
        "retired-sentinel",
        name_en="Retired Sentinel",
        price_monthly=Decimal("5"),
        is_active=False,
    )
    assert Plan.objects.filter(
        slug="payment-test", is_active=True, internal_only=True
    ).exists()


def test_pricing_page_does_not_list_internal_or_retired_plans(client, catalog):
    response = get(client)

    listed = {
        plan["slug"]
        for plan in response.context["plans_main"] + response.context["plans_pro"]
    }
    assert "starter" in listed, "control: the public plans are still listed"
    assert not {"payment-test", "internal-sentinel", "retired-sentinel"} & listed
    html = response.content.decode()
    assert "Payment Test (internal)" not in html
    assert "Internal Sentinel Plan" not in html


@pytest.mark.parametrize(
    "slug", ["payment-test", "internal-sentinel", "retired-sentinel", "nonexistent"]
)
def test_a_plan_a_visitor_cannot_buy_has_no_detail_page(client, catalog, slug):
    assert client.get(reverse("public:pricing_detail", args=[slug])).status_code == 404


def test_public_plan_detail_does_not_offer_internal_plans_as_alternatives(
    client, catalog
):
    response = get(client, reverse("public:pricing_detail", args=["starter"]))

    others = {plan["slug"] for plan in response.context["other_plans"]}
    assert "standard" in others, "control: the other public plans are still offered"
    assert "starter" not in others
    assert not {"payment-test", "internal-sentinel"} & others
    html = response.content.decode()
    assert "Payment Test (internal)" not in html
    assert "Internal Sentinel Plan" not in html


# --- test_plan_comparison_table.py ------------------------------------------------------------

TABLE_RE = re.compile(r'<table[^>]*id="plan-compare".*?</table>', re.S)


def plan_table(html: str) -> str:
    match = TABLE_RE.search(html)
    assert match, (
        "the plan comparison table lost its `plan-compare` id: this guard is blind"
    )
    return match.group(0)


def test_table_shows_the_devices_and_users_each_plan_buys(client, seeded):
    table = plan_table(html_of(client))

    assert "1 device" in table
    assert "3 users" in table
    assert "Unlimited devices" in table
    assert "Unlimited users" in table


def test_table_shows_what_each_plan_includes_and_its_support(client, seeded):
    table = plan_table(html_of(client))

    for level in ("Free", "Basic", "Pro", "Enterprise"):
        assert level in table, level
    for support in ("Community forum", "Email", "Priority email", "Agreed in contract"):
        assert support in table, support


def test_table_does_not_compare_plans_on_the_database_engine(client, seeded):
    assert "PostgreSQL" not in plan_table(html_of(client))


def test_the_engine_guard_reads_the_table_and_not_the_whole_page(client, seeded):
    """Positive control: the cards outside the table DO carry the database line."""
    html = html_of(client)

    assert "Managed database" in html
    assert "Managed database" not in plan_table(html)


def test_support_column_states_channel_and_priority_but_never_a_clock(client, seeded):
    table = plan_table(html_of(client))

    assert "24/7" not in table
    assert "business hours" not in table.lower()


def test_the_columns_survive_translation_to_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert "Dispositivos y usuarios" in table
    assert "Apps incluidas" in table
    assert "1 dispositivo" in table
    assert "3 usuarios" in table
    assert "Dispositivos ilimitados" in table
    assert "Foro de la comunidad" in table
    assert "Correo electrónico prioritario" in table


# --- test_pricing_card_trial.py ---------------------------------------------------------------


def test_the_card_shows_the_trial_the_plan_grants(client):
    make_plan("starter", trial_days=21)

    items = card_items(html_of(client), "Starter")

    assert items == ["Unlimited users", "21-day free trial"]


def test_the_card_follows_the_plan_when_its_trial_changes(client):
    starter = make_plan("starter", trial_days=15)
    starter.trial_period_days = 30
    starter.save()

    assert re.findall(r"\d+", card_items(html_of(client), "Starter")[-1]) == ["30"]


def test_a_plan_without_trial_shows_no_trial_line(client):
    make_plan("free", trial_days=0)

    assert card_items(html_of(client), "Free") == ["Unlimited users"]


def test_the_card_trial_is_translated(client):
    make_plan("starter", trial_days=15, name_es="Starter")

    assert card_items(html_of(client, language="es"), "Starter")[-1] == (
        "15 días de prueba gratis"
    )


def test_upgrade_only_plans_never_promise_a_trial(client):
    # An upgrade checkout grants no trial (#809), whatever the row says.
    make_plan("starter", trial_days=15)
    make_plan("pro", trial_days=15, upgrade_only=True)

    (rendered_pro,) = get(client).context["plans_pro"]

    assert rendered_pro["slug"] == "pro"
    assert not any("trial" in line for line in rendered_pro["display_features"])


# --- test_pricing_trial_period.py -------------------------------------------------------------


def trial_note(html: str) -> str:
    match = re.search(r'<p id="pricing-trial-note"[^>]*>(.*?)</p>', html, re.S)
    assert match, "the pricing page lost its trial note under the plans"
    return " ".join(match.group(1).split())


def trial_answer(response) -> str:
    (item,) = [item for item in response.context["faq_items"] if item["key"] == "trial"]
    return str(item["answer"])


def note_and_answer(client, language: str | None = None) -> tuple[str, str]:
    response = get(client, language=language)
    return trial_note(response.content.decode()), trial_answer(response)


def test_the_page_states_the_trial_length_the_checkout_grants(client):
    make_plan("free", trial_days=0)
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=15)

    for text in note_and_answer(client):
        # The free plan's 0 is «no trial», not the short end of a range.
        assert re.findall(r"\d+", text) == ["15"], text


def test_the_page_follows_the_plan_when_its_trial_changes(client):
    make_plan("starter", trial_days=30)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["30"], text


def test_plans_a_visitor_cannot_buy_do_not_count(client):
    make_plan("starter", trial_days=15)
    make_plan("internal", trial_days=90, internal_only=True)
    make_plan("retired", trial_days=180, is_active=False)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15"], text


def test_a_plan_reached_only_by_upgrading_does_not_count(client):
    make_plan("starter", trial_days=15)
    make_plan("pro", trial_days=30, upgrade_only=True)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15"], text


def test_plans_with_different_trials_are_stated_as_a_range(client):
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=30)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15", "30"], text


def test_no_trial_on_sale_means_no_trial_promised(client):
    make_plan("free", trial_days=0)
    make_plan("starter", trial_days=0)

    for text in note_and_answer(client):
        assert "trial" not in text.lower(), text
        assert not re.findall(r"\d+", text), text


def test_the_trial_is_promised_on_hub_creation_and_not_on_an_upgrade(client):
    make_plan("starter", trial_days=15)

    note, answer = note_and_answer(client)

    assert "when you create a Hub" in note
    assert "when creating a Hub" in answer
    assert "does not start a new trial" in answer


def test_a_spanish_visitor_reads_the_trial_in_spanish(client):
    make_plan("starter", trial_days=15)

    note, answer = note_and_answer(client, language="es")

    assert re.search(r"\b15 días\b", note), note
    assert "al crear un Hub" in note
    assert re.search(r"\b15 días\b", answer), answer
    assert "al crear un Hub" in answer
    assert "no inicia un nuevo periodo de prueba" in answer


def test_a_one_day_trial_reads_in_the_singular(client):
    make_plan("starter", trial_days=1)

    note, answer = note_and_answer(client, language="es")

    assert re.search(r"\b1 día\b", note)
    assert re.search(r"\b1 día\b", answer)


def test_faq_items_called_on_its_own_reads_the_plans_too():
    # A public entry point without the caller's reading: never a hand-typed length.
    make_plan("starter", trial_days=30)

    (item,) = [item for item in pricing.faq_items() if item["key"] == "trial"]

    assert re.findall(r"\d+", str(item["answer"])) == ["30"], item["answer"]


# --- Decision 17 and the host -----------------------------------------------------------------


def test_premium_apps_are_included_in_the_paid_plans_never_an_add_on(client, seeded):
    """Decision 17: no premium app is sold on its own (ADR-0474) and there is no marketplace."""
    lowered = visible_markup(html_of(client)).lower()

    # «add-on» stays where it describes a competitor («paid add-on, read-only»): what goes is ours.
    for gone in (
        "premium add-on",
        "premium ones when you need them",
        "add on top",
        "marketplace",
        "per activated module",
        "per-module pricing",
    ):
        assert gone not in lowered, gone
    assert "premium apps" in lowered
    (pricing_item,) = [item for item in pricing.faq_items() if item["key"] == "pricing"]
    assert "included in the paid plans" in str(pricing_item["answer"])


def test_the_storage_answer_names_aws_in_ireland_and_never_hetzner(client):
    """Ioan, 2026-10-14: the servers are on AWS, Ireland region (eu-west-1), for all of Europe;
    never the Spain region (eu-south-2, Aragón) the answer named before."""
    (storage,) = [item for item in pricing.faq_items() if item["key"] == "storage"]
    answer = str(storage["answer"])

    assert "Amazon Web Services" in answer
    assert "Ireland region (eu-west-1)" in answer
    assert "Spain" not in answer
    for language in ("en", "es"):
        html = html_of(client, language=language)
        assert "Hetzner" not in html
        assert "Falkenstein" not in html
        assert "eu-south-2" not in html
        assert "Aragón" not in html
    spanish = html_of(client, language="es")
    assert "región de Irlanda (eu-west-1)" in spanish
    assert "región de España" not in spanish


# --- The empty state --------------------------------------------------------------------------


def test_without_plans_on_sale_the_page_says_so_and_paints_no_table(client):
    html = html_of(client)

    assert "There are no plans on sale right now." in html
    assert 'id="plan-compare"' not in html
    assert "ep-pricing-card" not in html
    # The FAQ still answers, from the same list as its markup.
    assert faq_page_of(html)


# --- The detail page --------------------------------------------------------------------------


def test_the_detail_shows_the_plan_its_price_its_features_and_its_trial(client, seeded):
    response = get(client, "/pricing/starter/")
    html = response.content.decode()

    assert response.context["plan"]["slug"] == "starter"
    assert "<h1" in html and "Starter" in html
    assert "/ month per hub" in html
    assert "15 days free trial" in html
    # The trial is the pill, not one more feature line (the card's line belongs to the cards).
    assert "15-day free trial" not in html
    assert "Managed database, with continuous backups" in html


def test_the_detail_offers_the_other_plans_with_their_links(client, seeded):
    html = html_of(client, "/pricing/starter/")

    assert f'href="{reverse("public:pricing_detail", args=["standard"])}"' in html


def test_the_detail_sends_a_visitor_to_sign_up_and_a_customer_to_the_launcher(
    client, seeded, django_user_model
):
    from accounts.handoff import LAUNCHER

    assert f'href="{reverse("account_login")}"' in html_of(client, "/pricing/starter/")

    client.force_login(django_user_model.objects.create_user(email="ana@example.com"))
    assert f'href="{LAUNCHER}"' in html_of(client, "/pricing/starter/")


def test_the_detail_in_spanish(client, seeded):
    html = html_of(client, "/pricing/starter/", language="es")

    assert "Qué incluye" in html
    assert "/ mes por hub" in html


# --- The ex-VAT note (tests/unit/billing/test_net_price_display.py, saas#1835) ----------------

NET = "29.99"
#: The 21 % gross of 29.99: exactly what a selling screen no longer shows.
GROSS = "36.29"


def has_amount(html: str, amount: str) -> bool:
    return amount in html or amount.replace(".", ",") in html


@pytest.fixture
def net_plan():
    return make_plan(
        "net-display",
        name_en="Net Display",
        price_monthly=Decimal(NET),
        price_annual=Decimal("299.90"),
        display_order=-50,
        features=["One thing"],
    )


SELLING_SURFACES = ["/pricing/", "/pricing/net-display/"]


@pytest.mark.parametrize("path", SELLING_SURFACES)
def test_a_selling_screen_shows_the_net_price(client, net_plan, path):
    assert has_amount(html_of(client, path), NET)


@pytest.mark.parametrize("path", SELLING_SURFACES)
def test_a_selling_screen_shows_no_vat_figure(client, net_plan, path):
    html = html_of(client, path)

    assert not has_amount(html, GROSS)
    assert "+ VAT" not in html and "+ IVA" not in html


@pytest.mark.parametrize("path", SELLING_SURFACES)
def test_a_selling_screen_carries_the_ex_vat_note_with_its_terms_link(
    client, net_plan, path
):
    html = html_of(client, path)

    assert "All prices exclude VAT" in html
    assert f'href="{reverse("public:terms")}"' in html


def test_the_ex_vat_note_is_translated(client, net_plan):
    html = html_of(client, language="es")

    assert "Todos los precios sin IVA" in html
    assert "NIF/CIF/NIE o NIF-IVA" in html


# --- The shared patterns (test_ui_stack_contract.py, pricing half) ----------------------------


def source(name: str) -> str:
    return (PRICING_TEMPLATES / name).read_text(encoding="utf-8")


def test_pricing_tables_use_the_shared_surface_without_nested_frames():
    page = source("index.html")

    assert page.count('class="ep-table-surface"') == 3
    assert page.count('class="ep-container ep-section-content"') >= 3
    assert (
        "overflow-x-auto bg-surface border border-surface-3/60 rounded-xl" not in page
    )
    assert 'class="cat ep-table-group"' in page


def test_pricing_faq_uses_the_shared_container():
    faq = (
        source("index.html")
        .split("<!-- FAQ -->", 1)[1]
        .split("<!-- Closing CTA -->", 1)[0]
    )

    assert '<section id="faq" class="ep-section--compact ep-section--divider">' in faq
    assert '<div class="ep-container ep-section-content">' in faq


def test_pricing_uses_the_shared_alternating_section_surface():
    page = source("index.html")

    assert page.count("ep-section--soft") == 2
    assert (
        'class="ep-section--compact ep-section--soft ep-section--center ep-section--divider" id="upgrade-plans"'
        in page
    )
    assert (
        '<section id="comparativa" class="ep-section--compact ep-section--soft ep-section--divider">'
        in page
    )


def test_pricing_upgrade_plans_use_shared_cards_and_an_auto_fitting_grid():
    upgrade = (
        source("index.html")
        .split("<!-- UPGRADE-ONLY PLANS", 1)[1]
        .split("<!-- FEATURE COMPARISON TABLE", 1)[0]
    )

    assert 'class="ep-grid-cards"' in upgrade
    assert '<ion-card class="ion-no-margin">' in upgrade
    assert "{% for plan in plans_pro %}" in upgrade
    assert "plan.display_features|slice" in upgrade


def test_pricing_is_a_primary_page_with_the_compact_hero_and_the_shared_rhythm():
    page = source("index.html")
    hero = next(
        line
        for line in page.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "hero_compact=True" in hero
    assert not re.search(r"\bpy-(?:14|16|20)\b", page)


def test_the_pricing_look_lives_in_a_stylesheet_not_in_the_page():
    """The old page carried a <style> block; its rules are public/static/public/pricing.css."""
    for name in ("index.html", "detail.html", "_plan_compare_cells.html"):
        assert "<style" not in source(name), name
    css = (ROOT / "public" / "static" / "public" / "pricing.css").read_text(
        encoding="utf-8"
    )
    assert ".compare-table" in css
    assert "{% static 'public/pricing.css' %}" in source("index.html")


@pytest.mark.parametrize(
    "template",
    [*sorted(PRICING_TEMPLATES.glob("*.html")), VAT_NOTE],
    ids=lambda path: path.name,
)
def test_every_message_of_a_pricing_template_has_its_spanish_entry(template):
    import gettext

    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(template)

    assert messages, f"{template.name} has no translatable message"
    assert [m for m in messages if not catalog.get(m)] == []


def test_the_python_messages_have_their_spanish_entry():
    """The FAQ, the trial note and the period labels live in public/pricing.py."""
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=30)
    with translation.override("es"):
        texts = [
            *(str(item["question"]) for item in pricing.faq_items()),
            *(str(item["answer"]) for item in pricing.faq_items()),
            pricing.trial_note((15, 30)),
            pricing.trial_note((15, 15)),
            pricing.trial_note((None, None)),
        ]
    with translation.override("en"):
        english = [
            *(str(item["question"]) for item in pricing.faq_items()),
            *(str(item["answer"]) for item in pricing.faq_items()),
            pricing.trial_note((15, 30)),
            pricing.trial_note((15, 15)),
            pricing.trial_note((None, None)),
        ]

    assert [es for es, en in zip(texts, english) if es == en] == []
