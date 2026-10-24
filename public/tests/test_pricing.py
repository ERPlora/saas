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
from pathlib import Path

import pytest
from django.conf import settings
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
def seeded(db):
    """The catalogue the migrations leave (``hubs/0013``)."""


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


UPGRADE_SECTION = '<section id="more-capacity"'


def upgrade_section(html: str) -> str:
    """The «More capacity» section: the upgrade-only plans (Ioan, 2026-10-24, PLAN-SAAS §9)."""
    assert UPGRADE_SECTION in html, "no «More capacity» section on /pricing/"
    return html.split(UPGRADE_SECTION, 1)[1].split("</section>", 1)[0]


def visible_markup(html: str) -> str:
    """The page with every ``<script>`` and hidden form field removed: what a reader actually sees (the
    footer's language forms carry Django's ``csrfmiddlewaretoken``, which no reader sees)."""
    html = re.sub(r'<input type="hidden"[^>]*>', "", html, flags=re.IGNORECASE)
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


def test_pricing_renders_active_plan_data_from_the_database(no_plans, client):
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
    assert [plan["slug"] for plan in response.context["plans_upgrade"]] == ["db-upgrade-sentinel"]
    assert "plans_pro" not in response.context
    html = response.content.decode()
    for text in (
        "DB Public Sentinel",
        "€31.23",
        "Public description loaded from the database",
        "Database feature sentinel",
    ):
        assert text in html, text
    # An upgrade-only row is shown under «More capacity» (Ioan, 2026-10-24), never with the cards a visitor signs up
    # on, and without the old visual separators.
    upgrades = upgrade_section(html)
    for text in ("DB Upgrade Sentinel", "€62.46", "Upgrade description loaded from the database", "Upgrade feature sentinel"):
        assert text in upgrades, text
    assert "DB Upgrade Sentinel" not in html.split(UPGRADE_SECTION, 1)[0]
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

    listed = {plan["slug"] for plan in response.context["plans_main"]}
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
    """The plans on sale, then the upgrade-only ones (Ioan, 2026-10-24); the dedicated row is gone (PLAN-SAAS §9,
    2026-10-24b)."""
    table = plan_table(html_of(client))
    signable, upgrades = table.split('<td colspan="9">More capacity</td>', 1)

    for level in ("Free", "Basic"):
        assert level in signable, level
    for support in ("Community forum", "Email", "Priority email"):
        assert support in signable, support
    for gone in ("Pro", "Enterprise", "Agreed in contract"):
        assert gone not in signable, gone
    for shown in ("<strong>Pro</strong>", "<strong>Enterprise</strong>", "Priority email", "Agreed in contract"):
        assert shown in upgrades, shown
    assert "Dedicated, agreed with you" not in table


def test_table_shows_the_resources_each_plan_buys_in_plain_words(client, seeded):
    """Ioan, 2026-10-15: the «resources» that grow from plan to plan are the database's input/output capacity.
    Free for one device, Starter the full tier, Standard twice it — a buyer reads the ladder as database
    throughput, never an engine, a connection count nor a timeout."""
    table = plan_table(html_of(client))

    assert "Database throughput" in table
    for label in ("Basic, for one device", "Full, for several devices", "Double"):
        assert label in table, label
    assert "Your own, sized with you" not in table
    assert not re.search(r"\b(connections?|timeout|aurora)\b", table, re.I)


def test_the_table_reads_the_resources_in_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert "Capacidad de la base de datos" in table
    for label in ("Básica, para un dispositivo", "Completa, para varios dispositivos", "El doble"):
        assert label in table, label
    assert "Propia, a tu medida" not in table


def test_the_limits_answer_says_each_plan_up_doubles_the_resources(client):
    (item,) = [item for item in pricing.faq_items() if item["key"] == "limits"]

    assert "doubles" in str(item["answer"])


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


# --- The monthly messages of each plan: assistant and WhatsApp (PLAN-SAAS §3.6, 2026-10-15) -------------


def test_each_card_says_the_assistant_and_whatsapp_messages_a_month(client, seeded):
    """In plain words, after the plan's features (and before a trial line, if staff give one): what the plan
    includes, never tokens nor how we count them."""
    html = html_of(client)

    assert card_items(html, "Free")[-2:] == ["AI assistant: 30 messages a month", "WhatsApp: 30 messages a month"]
    starter = card_items(html, "Starter")
    assert starter[-2:] == ["AI assistant: 300 messages a month", "WhatsApp: 150 messages a month"]
    assert not any("trial" in item for item in starter), starter
    assert "AI assistant: 600 messages a month" in card_items(html, "Standard")
    assert "WhatsApp: 300 messages a month" in card_items(html, "Standard")
    assert "token" not in visible_markup(html).lower()


def test_a_plan_without_messages_says_nothing_of_them(no_plans, client):
    """0 is «none»: the card paints no line rather than «0 messages»."""
    make_plan("starter", trial_days=15, assistant_messages_per_month=0, whatsapp_messages_per_month=40)

    assert card_items(html_of(client), "Starter") == ["Unlimited users", "WhatsApp: 40 messages a month", "15-day free trial"]


def test_one_message_reads_in_the_singular(no_plans, client):
    make_plan("starter", assistant_messages_per_month=1)

    assert "AI assistant: 1 message a month" in card_items(html_of(client), "Starter")


def test_the_cards_read_the_messages_in_spanish(client, seeded):
    items = card_items(html_of(client, language="es"), "Starter")

    assert "Asistente de IA: 300 mensajes al mes" in items
    assert "WhatsApp: 150 mensajes al mes" in items


def test_the_table_compares_the_messages_of_each_plan(client, seeded):
    table = plan_table(html_of(client))

    assert "<th>AI assistant</th>" in table and "<th>WhatsApp</th>" in table
    for messages in ("30 messages a month", "300 messages a month", "600 messages a month", "150 messages a month"):
        assert messages in table, messages
    # No row agrees its quota by contact any more (PLAN-SAAS §9, 2026-10-24b).
    assert "Agreed with you" not in table


def test_a_plan_without_messages_reads_not_included_in_the_table(no_plans, client):
    make_plan("starter", assistant_messages_per_month=0, whatsapp_messages_per_month=0)

    assert plan_table(html_of(client)).count("Not included") == 2


def test_the_table_reads_the_messages_in_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert "<th>Asistente de IA</th>" in table
    assert "300 mensajes al mes" in table
    assert "Acordado contigo" not in table


def test_every_row_of_the_table_spans_its_columns(client, seeded):
    """A new column must reach the group rows too, or the table breaks on a wide screen."""
    table = plan_table(html_of(client))
    columns = len(re.findall(r"<th\b", table.split("</thead>", 1)[0]))

    assert set(re.findall(r'colspan="(\d+)"', table)) == {str(columns)}


# --- test_pricing_card_trial.py ---------------------------------------------------------------


def test_the_card_shows_the_trial_the_plan_grants(no_plans, client):
    make_plan("starter", trial_days=21)

    items = card_items(html_of(client), "Starter")

    assert items == ["Unlimited users", "21-day free trial"]


def test_the_card_follows_the_plan_when_its_trial_changes(no_plans, client):
    starter = make_plan("starter", trial_days=15)
    starter.trial_period_days = 30
    starter.save()

    assert re.findall(r"\d+", card_items(html_of(client), "Starter")[-1]) == ["30"]


def test_a_plan_without_trial_shows_no_trial_line(no_plans, client):
    make_plan("free", trial_days=0)

    assert card_items(html_of(client), "Free") == ["Unlimited users"]


def test_the_card_trial_is_translated(no_plans, client):
    make_plan("starter", trial_days=15, name_es="Starter")

    assert card_items(html_of(client, language="es"), "Starter")[-1] == (
        "15 días de prueba gratis"
    )


def test_an_upgrade_only_plan_is_shown_but_has_no_sign_up_nor_detail_page(no_plans, client):
    """Ioan, 2026-10-24 (PLAN-SAAS §9, corrects 2026-10-15): /pricing/ shows an ``upgrade_only`` row under «More
    capacity», so a visitor knows it exists, but it is still no plan to sign up on: not among the cards a visitor
    signs up on, no detail page and not in «Other plans». The mechanism does not move: the Store offers it to a
    business that already pays and the checkout from Free refuses it (``billing.plan_upgrade_only``)."""
    make_plan("starter", trial_days=15)
    make_plan("pro", trial_days=15, upgrade_only=True)

    response = get(client)
    html = response.content.decode()

    assert [plan["slug"] for plan in response.context["plans_main"]] == ["starter"]
    assert [plan["slug"] for plan in response.context["plans_upgrade"]] == ["pro"]
    assert '<div class="ep-pricing-card__name">Pro</div>' in upgrade_section(html)
    assert '<div class="ep-pricing-card__name">Pro</div>' not in html.split(UPGRADE_SECTION, 1)[0]
    assert client.get("/pricing/pro/").status_code == 404
    others = get(client, "/pricing/starter/").context["other_plans"]
    assert [plan["slug"] for plan in others] == []


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


def test_the_page_states_the_trial_length_the_checkout_grants(no_plans, client):
    make_plan("free", trial_days=0)
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=15)

    for text in note_and_answer(client):
        # The free plan's 0 is «no trial», not the short end of a range.
        assert re.findall(r"\d+", text) == ["15"], text


def test_the_page_follows_the_plan_when_its_trial_changes(no_plans, client):
    make_plan("starter", trial_days=30)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["30"], text


def test_plans_a_visitor_cannot_buy_do_not_count(no_plans, client):
    make_plan("starter", trial_days=15)
    make_plan("internal", trial_days=90, internal_only=True)
    make_plan("retired", trial_days=180, is_active=False)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15"], text


def test_a_plan_reached_only_by_upgrading_does_not_count(no_plans, client):
    make_plan("starter", trial_days=15)
    make_plan("pro", trial_days=30, upgrade_only=True)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15"], text


def test_plans_with_different_trials_are_stated_as_a_range(no_plans, client):
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=30)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15", "30"], text


def test_no_trial_on_sale_means_no_trial_promised(no_plans, client):
    make_plan("free", trial_days=0)
    make_plan("starter", trial_days=0)

    for text in note_and_answer(client):
        assert "trial" not in text.lower(), text
        assert not re.findall(r"\d+", text), text


def test_the_trial_is_promised_on_hub_creation_and_not_on_an_upgrade(no_plans, client):
    make_plan("starter", trial_days=15)

    note, answer = note_and_answer(client)

    assert "when you create a Hub" in note
    assert "when creating a Hub" in answer
    assert "does not start a new trial" in answer


def test_a_spanish_visitor_reads_the_trial_in_spanish(no_plans, client):
    make_plan("starter", trial_days=15)

    note, answer = note_and_answer(client, language="es")

    assert re.search(r"\b15 días\b", note), note
    assert "al crear un Hub" in note
    assert re.search(r"\b15 días\b", answer), answer
    assert "al crear un Hub" in answer
    assert "no inicia un nuevo periodo de prueba" in answer


def test_a_one_day_trial_reads_in_the_singular(no_plans, client):
    make_plan("starter", trial_days=1)

    note, answer = note_and_answer(client, language="es")

    assert re.search(r"\b1 día\b", note)
    assert re.search(r"\b1 día\b", answer)


def test_faq_items_called_on_its_own_reads_the_plans_too(no_plans):
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


def test_without_plans_on_sale_the_page_says_so_and_paints_no_table(no_plans, client):
    html = html_of(client)

    assert "There are no plans on sale right now." in html
    assert 'id="plan-compare"' not in html
    assert "ep-pricing-card" not in html
    # The FAQ still answers, from the same list as its markup.
    assert faq_page_of(html)


# --- Nothing above the plans: no dedicated infrastructure (Ioan, 2026-10-24, PLAN-SAAS §9) ---------

CONTACT = "/contact/"
PRICE_400 = re.compile(r"(?<![\d.,])400(?![\d.,])")


def visible_text(html: str) -> str:
    """What a reader reads: :func:`visible_markup` without its tags (``data-reveal-delay="400"`` is no price)."""
    return re.sub(r"<[^>]+>", " ", visible_markup(html))


def test_the_page_offers_no_dedicated_infrastructure(client, seeded):
    """Ronda 2026-10-24b: the «Dedicated infrastructure, from €400 a month» band is no product (no runbook, no
    Terraform) and the plans no longer sell infrastructure; above Standard the page shows only the upgrade-only plans
    (Pro, Enterprise and Max, Ioan 2026-10-24), never an offer by contact."""
    html = html_of(client)
    body = visible_markup(html)

    # The positive control first: an empty page would pass every `not in` below.
    assert [plan["slug"] for plan in get(client).context["plans_main"]] == ["free", "starter", "standard"]
    assert 'id="dedicated"' not in html
    assert "dedicated" not in body.lower()
    assert not PRICE_400.search(visible_text(html))
    for gone in ("Need more?", "By contact", "Upgrade-only", "Professional tier", "upgrade from inside the dashboard"):
        assert gone not in body, gone


def test_the_page_offers_no_dedicated_infrastructure_in_spanish(client, seeded):
    html = html_of(client, language="es")
    body = visible_markup(html)

    assert "Todo lo incluido en cada plan" in body
    assert "dedicad" not in body.lower()
    assert "Por contacto" not in body
    assert not PRICE_400.search(visible_text(html))


def test_pricing_has_no_dedicated_price_left(client, seeded):
    assert not hasattr(pricing, "DEDICATED_FROM")
    assert not hasattr(pricing, "dedicated_price_label")
    assert "dedicated_from" not in get(client).context


def test_the_comparison_table_ends_with_the_upgrade_only_plans_and_no_offer_by_contact(client, seeded):
    table = plan_table(html_of(client))
    rows = [row for row in table.split("<tr")[1:] if "ep-table-group" not in row and "<th>" not in row]

    assert [re.search(r"<strong>(.*?)</strong>", row).group(1) for row in rows] == [
        "Free", "Starter", "Standard", "Pro", "Enterprise", "Max",
    ]  # fmt: skip
    assert f'href="{CONTACT}"' not in table
    assert "Upgrade-only" not in table and "Professional" not in table


def test_the_table_signs_up_on_the_plans_on_sale_and_says_when_the_others_open(client, seeded):
    table = plan_table(html_of(client))
    groups = re.findall(r'<tr class="cat ep-table-group"><td colspan="\d+">(.*?)</td></tr>', table)
    signable, upgrades = table.split('<td colspan="9">More capacity</td>', 1)

    assert groups == ["Plans · sign up directly", "More capacity"]
    assert signable.count('href="/launch"') == 3
    assert 'href="/launch"' not in upgrades
    assert upgrades.count("Available once you are on Starter") == 3
    for amount in ("€109.99", "€209.99", "€419.99"):
        assert amount in upgrades, amount


def test_the_table_reads_the_upgrade_only_plans_in_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert '<td colspan="9">Más capacidad</td>' in table
    assert table.count("Disponible al pasar a Starter") == 3


def test_the_table_intro_sends_nobody_to_a_custom_setup(client, seeded):
    body = " ".join(visible_markup(html_of(client)).split())

    assert "one hub covers all your devices and users" in body
    assert "Need more than that?" not in body


def test_the_page_includes_no_location_in_any_plan(client, seeded):
    """Multi-location comes from Pro and is charged per location (PLAN §32, ronda 2026-10-24b): neither the table's
    intro nor a card on sale (hubs/0021) says a hub covers every location."""
    for language, words in (("en", r"\blocations?\b"), ("es", r"\blocales\b")):
        body = " ".join(visible_text(html_of(client, language=language)).split())
        assert "Pro" in body, "control: the page is the plans page"
        assert not re.search(words, body, re.IGNORECASE), (language, re.search(words, body, re.IGNORECASE))


def test_the_page_sells_what_the_customer_gets_not_how_we_run_it(client, seeded):
    """Plain words for a buyer: no engine, cluster or instance names anywhere on the page."""
    body = visible_markup(html_of(client)).lower()

    assert "amazon web services" in body
    for internal in ("postgres", "aurora", "ecs", "fargate", "kubernetes", "docker", "pgbouncer", "replica set"):
        assert internal not in body, internal


def test_the_faq_has_no_dedicated_entry(client, seeded):
    items = pricing.faq_items()
    html = html_of(client)

    assert items and "trial" in [item["key"] for item in items]
    assert "dedicated" not in [item["key"] for item in items]
    for item in items:
        assert "dedicated" not in f"{item['question']} {item['answer']}".lower(), item["key"]
    assert "dedicated" not in json.dumps(faq_page_of(html)).lower()


# --- More capacity: the upgrade-only plans on the page (Ioan, 2026-10-24, PLAN-SAAS §9) --------------------------
# Corrects 2026-10-15 («/pricing/ no longer lists them»): Odoo, Holded and Square show the whole ladder on their
# pricing page. The mechanism does not move: the rows stay ``upgrade_only``, the Store offers them to a business that
# already pays and the checkout from Free refuses them (``billing.plan_upgrade_only``, billing/tests/test_checkout.py).

UPGRADE_ONLY = ("pro", "enterprise", "max")


def upgrade_rows():
    """The upgrade-only plans a visitor may be shown, as the database orders them."""
    return list(Plan.objects.public().filter(upgrade_only=True).order_by("display_order", "price_monthly"))


def test_the_upgrade_only_plans_are_seeded_on_sale_above_standard(seeded):
    """Control: the catalogue this block reads (hubs/0013), Pro, Enterprise and Max active, at 109.99, 209.99 and
    419.99."""
    assert [(plan.slug, plan.price_monthly) for plan in upgrade_rows()] == [
        ("pro", Decimal("109.99")), ("enterprise", Decimal("209.99")), ("max", Decimal("419.99")),
    ]  # fmt: skip


def test_more_capacity_shows_each_upgrade_only_plan_from_its_row(client, seeded):
    response = get(client)
    section = upgrade_section(response.content.decode())

    assert [card["slug"] for card in response.context["plans_upgrade"]] == list(UPGRADE_ONLY)
    assert '<h2 class="font-display font-semibold text-3xl tracking-tighter">More capacity</h2>' in section
    assert painted_prices(section) == {plan.name_en: plan.price_monthly for plan in upgrade_rows()}
    text = " ".join(section.split())
    for plan in upgrade_rows():
        features = without_separators(plan.features_en)
        assert plan.description_en in text, plan.slug
        assert card_items(section, plan.name_en)[: len(features)] == features, plan.slug
        assert f"≈ €{plan.price_annual:.2f}/year · 2 months free" in text, plan.slug
        assert "/ month per hub" in text


def without_separators(features: list[str]) -> list[str]:
    """A row's features as ``hubs.plan.list`` gives them: the old seed's «───» lines (Max's) are dropped."""
    return [feature for feature in features if feature.strip().strip("─").strip()]


def card_foot(card: str) -> str:
    """What a card paints under its features: the sign-up button of a plan on sale, the label of an upgrade-only one."""
    return card.split('<div class="ep-pricing-card__cta">', 1)[1].split("</div>", 1)[0]


def test_more_capacity_keeps_the_order_staff_give_the_rows(client, seeded):
    Plan.objects.filter(slug="max").update(display_order=45)

    names = re.findall(r'<div class="ep-pricing-card__name">(.*?)</div>', upgrade_section(html_of(client)))

    assert names == ["Max", "Pro", "Enterprise"]


def test_each_upgrade_only_card_says_when_it_opens_instead_of_a_sign_up_button(client, seeded):
    section = upgrade_section(html_of(client))
    cards = CARD_START.split(section)[1:]

    assert len(cards) == 3
    for card in cards:
        foot = card_foot(card)
        assert "Available once you are on Starter" in foot
        assert "<ion-button" not in card.split('<div class="ep-pricing-card__cta">', 1)[0] + foot
        assert "Get started" not in foot


def test_more_capacity_has_one_call_to_action_to_start_free(client, seeded):
    section = upgrade_section(html_of(client))
    buttons = re.findall(r"<ion-button\b[^>]*>(.*?)</ion-button>", section, re.S)

    assert len(buttons) == 1
    assert "Start free and upgrade whenever you want" in buttons[0]
    assert re.search(r'<ion-button\b[^>]*href="/launch"', section)


def test_more_capacity_reads_in_spanish(client, seeded):
    section = " ".join(upgrade_section(html_of(client, language="es")).split())

    assert "Más capacidad" in section
    assert section.count("Disponible al pasar a Starter") == 3
    assert "Empieza gratis y mejora cuando quieras" in section
    for plan in upgrade_rows():
        assert plan.description_es in section, plan.slug
        for feature in without_separators(plan.features_es):
            assert feature in section, (plan.slug, feature)
    for amount in ("€109,99", "€209,99", "€419,99", "≈ 1099,90 €/año · 2 meses gratis"):
        assert amount in section, amount
    assert "Available once you are on Starter" not in section


def test_an_inactive_or_internal_upgrade_only_plan_is_not_shown(client, seeded):
    Plan.objects.filter(slug="enterprise").update(is_active=False)
    Plan.objects.filter(slug="max").update(internal_only=True)

    response = get(client)

    assert [card["slug"] for card in response.context["plans_upgrade"]] == ["pro"]
    section = upgrade_section(response.content.decode())
    assert "Enterprise" not in section and "Max" not in section


def test_without_upgrade_only_plans_there_is_no_more_capacity_section(client, seeded):
    Plan.objects.filter(upgrade_only=True).update(is_active=False)

    html = html_of(client)

    assert UPGRADE_SECTION not in html
    assert "More capacity</h2>" not in html
    assert '<td colspan="9">More capacity</td>' not in html
    assert "Available once you are on Starter" not in html


def test_the_plans_to_sign_up_on_stay_as_they_were(client, seeded):
    """Free, Starter and Standard keep their cards, with their sign-up button, before «More capacity»."""
    response = get(client)
    html = response.content.decode()
    signable = html.split(UPGRADE_SECTION, 1)[0]

    assert [card["slug"] for card in response.context["plans_main"]] == ["free", "starter", "standard"]
    assert re.findall(r'<div class="ep-pricing-card__name">(.*?)</div>', signable) == ["Free", "Starter", "Standard"]
    assert len(CARD_START.split(signable)[1:]) == 3
    for card in CARD_START.split(signable)[1:]:
        assert '<ion-button href="/launch"' in card_foot(card)
        assert "Available once you are on Starter" not in card
    assert painted_prices(signable) == {"Free": Decimal("0"), "Starter": Decimal("29.99"), "Standard": Decimal("54.99")}


def test_more_capacity_promises_no_trial_nor_a_saving_of_its_own_in_the_hero(no_plans, client):
    """An upgrade grants no trial (#809) and the hero's saving is the plans on sale's: an upgrade-only row with a trial
    and another saving changes neither."""
    make_plan("starter", price_annual=Decimal("299.90"))
    make_plan("pro", upgrade_only=True, trial_days=30, price_monthly=Decimal("100"), price_annual=Decimal("900"))

    response = get(client)

    assert response.context["months_free"] == 2
    assert "30-day" not in upgrade_section(response.content.decode())
    assert response.context["trial_note"] == "Free plan with no card required. Cancel anytime."


# --- The detail page --------------------------------------------------------------------------


def test_the_catalogue_promises_no_trial_and_points_to_the_free_plan(client, seeded):
    """Ioan, 2026-10-15: no plan carries a trial; the Free plan is the way in, and the page says so."""
    html = html_of(client)

    assert "free trial" not in visible_markup(html).lower()
    (item,) = [item for item in pricing.faq_items() if item["key"] == "trial"]
    assert "the Free plan is free forever" in str(item["answer"])


def test_the_detail_shows_the_plan_its_price_its_features_and_its_trial(client, seeded):
    # The dormant trial, on: no plan carries one since 2026-10-15, but staff may give one in the admin.
    Plan.objects.filter(slug="starter").update(trial_period_days=15)
    response = get(client, "/pricing/starter/")
    html = response.content.decode()

    assert response.context["plan"]["slug"] == "starter"
    assert "<h1" in html and "Starter" in html
    assert "/ month per hub" in html
    assert "15 days free trial" in html
    # The trial is the pill, not one more feature line (the card's line belongs to the cards).
    assert "15-day free trial" not in html
    assert "Managed database, replicated across several European data centres" in html


def test_the_detail_offers_the_other_plans_with_their_links(client, seeded):
    html = html_of(client, "/pricing/starter/")

    assert f'href="{reverse("public:pricing_detail", args=["standard"])}"' in html


def test_every_plan_of_the_index_starts_at_the_sign_in(client, seeded):
    """The cards, the comparison table and the closing band: the SPA's sign-in, which also signs up."""
    html = html_of(client)

    assert 'href="/launch"' in html
    assert "/accounts/login/" not in html


def test_the_detail_sends_a_visitor_to_sign_up_and_a_customer_to_the_launcher(
    client, seeded, django_user_model
):
    from accounts.handoff import LAUNCHER

    html = html_of(client, "/pricing/starter/")
    assert 'href="/launch"' in html
    assert "/accounts/login/" not in html

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

    assert re.search(r'<section id="faq" class="ep-section--compact[^"]*ep-section--divider">', faq)
    assert '<div class="ep-container ep-section-content">' in faq


SECTION_TAG = re.compile(r'<section\b(?:\s+id="([^"]+)")?\s+class="([^"]*)"')


def page_sections(html: str) -> list[tuple[str, bool]]:
    """The sections of the page's content, in page order: ``(id or "", on the soft surface)``."""
    content = html.split("<!-- PLAN CARDS -->", 1)[1]
    return [(section_id, "ep-section--soft" in classes.split()) for section_id, classes in SECTION_TAG.findall(content)]


def assert_the_surfaces_alternate(sections: list[tuple[str, bool]]) -> None:
    """Plain under the hero, then soft and plain in turn: never two of the same surface side by side."""
    assert [soft for _, soft in sections] == [index % 2 == 1 for index in range(len(sections))], sections


def test_pricing_uses_the_shared_alternating_section_surface(client, seeded):
    """Cards, «More capacity» (soft), the table, the competitors (soft) and the FAQ."""
    sections = page_sections(html_of(client))

    assert [section_id for section_id, _ in sections] == ["", "more-capacity", "", "comparativa", "faq"]
    assert_the_surfaces_alternate(sections)


def test_the_surfaces_still_alternate_without_upgrade_only_plans(client, seeded):
    Plan.objects.filter(upgrade_only=True).update(is_active=False)

    sections = page_sections(html_of(client))

    assert [section_id for section_id, _ in sections] == ["", "", "comparativa", "faq"]
    assert_the_surfaces_alternate(sections)


def test_the_surfaces_still_alternate_without_plans_on_sale(no_plans, client):
    make_plan("pro", upgrade_only=True)

    sections = page_sections(html_of(client))

    assert [section_id for section_id, _ in sections] == ["", "comparativa", "faq"]
    assert_the_surfaces_alternate(sections)


@pytest.mark.parametrize(
    ("shown", "soft"),
    [
        (["plans", "upgrades", "compare", "competitors", "faq"], {"upgrades", "competitors"}),
        (["plans", "compare", "competitors", "faq"], {"compare", "faq"}),
        (["plans", "competitors", "faq"], {"competitors"}),
    ],
)
def test_every_other_section_shown_is_soft(shown, soft):
    surfaces = pricing.section_surfaces(shown)

    assert {name for name, is_soft in surfaces.items() if is_soft} == soft
    assert set(surfaces) == set(shown)


def test_the_template_has_no_offer_by_contact_above_the_plans():
    """Neither the 2026-10-15 «Upgrade-only plans» band nor the dedicated band that replaced it (2026-10-24b): above
    the plans on sale only the upgrade-only rows themselves, under «More capacity» (2026-10-24)."""
    page = source("index.html")

    assert "<!-- PLAN CARDS -->" in page
    assert "plans_pro" not in page
    assert "Upgrade-only" not in page
    assert "dedicated" not in page.lower()
    assert "{% url 'public:contact' %}" not in page


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


def test_the_python_messages_have_their_spanish_entry(no_plans):
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


# --- PUBLIC-F02: the annual saving is worked out from the two prices, never typed ------------------
# The old card said «2 months free» next to any annual price (SAAS_PUBLIC-F56): edit the annual price
# and the sentence stayed. The months free are 12 minus the months the annual price pays for,
# rounded down so the page never promises more than the checkout gives.


@pytest.mark.parametrize(
    ("annual", "line"),
    [
        ("300", "≈ €300/year · 2 months free"),
        ("330", "≈ €330/year · 1 month free"),
        ("345", "≈ €345/year"),
        ("360", "≈ €360/year"),
    ],
)
def test_the_annual_saving_is_worked_out_from_the_prices(no_plans, client, annual, line):
    make_plan("starter", price_monthly=Decimal("30"), price_annual=Decimal(annual))

    html = " ".join(html_of(client).split())

    assert line in html
    if "free" not in line:
        assert "month free" not in html and "months free" not in html


def test_the_annual_saving_reads_in_spanish(no_plans, client):
    make_plan("starter", price_monthly=Decimal("30"), price_annual=Decimal("300"), name_es="Starter")

    assert "≈ 300 €/año · 2 meses gratis" in " ".join(html_of(client, language="es").split())


def test_the_hero_promises_the_saving_the_paid_plans_give(no_plans, client):
    make_plan("free", price_monthly=Decimal("0"), price_annual=Decimal("0"))
    make_plan("starter", price_monthly=Decimal("30"), price_annual=Decimal("330"))

    html = " ".join(html_of(client).split())

    assert "Pay for the year and get 1 month free." in html
    assert "2 months free" not in html


def test_without_an_annual_saving_the_hero_promises_none(no_plans, client):
    make_plan("free", price_monthly=Decimal("0"), price_annual=Decimal("0"))
    make_plan("starter", price_monthly=Decimal("30"), price_annual=Decimal("0"))

    html = html_of(client)

    assert "Pay for the year" not in html
    assert "month free" not in html and "months free" not in html


# --- PUBLIC-F04: the price painted is the price charged ---------------------------------------------
# One field, one amount: what /pricing/ and the detail page paint is the net ``Plan`` price, the checkout
# charges that same amount (``billing.services.plan_sale``) and the Stripe price the plan sells with
# must charge it to the cent, or the admin refuses it (BILLING-F28). Stripe is the double of billing's
# tests: no call leaves the machine.

from billing import services as billing_services  # noqa: E402
from billing.money import to_cents  # noqa: E402
from billing.tests.conftest import plans, stripe_double, stripe_keys  # noqa: E402,F401
from billing.tests.test_services import stripe_price  # noqa: E402
from hubs.tests.conftest import make_user  # noqa: E402,F401

PAINTED_AMOUNT = re.compile(r'<span class="ep-pricing-card__amount">€([\d.,]+)</span>')


def painted_prices(html: str) -> dict[str, Decimal]:
    """Each card's name and the amount it paints."""
    names = re.findall(r'<div class="ep-pricing-card__name">(.*?)</div>', html)
    amounts = PAINTED_AMOUNT.findall(html)
    assert len(names) == len(amounts)
    return {name: Decimal(amount.replace(",", "")) for name, amount in zip(names, amounts)}


def test_every_card_paints_the_price_the_checkout_charges(client, plans, make_user):
    buyer = make_user("painted@example.com")
    painted = painted_prices(html_of(client))
    paid = [plan for plan in Plan.objects.public() if not plan.upgrade_only and plan.price_monthly > 0]

    assert paid, "no paid plan on sale to compare"
    for plan in paid:
        charged = billing_services.plan_sale(buyer, plan.slug, "month")
        assert painted[plan.name_en] == charged.net, plan.slug
        assert charged.price_id == plan.stripe_price_id


def test_the_year_painted_is_the_year_charged(client, plans, make_user):
    buyer = make_user("yearly@example.com")
    html = " ".join(html_of(client).split())

    for plan in Plan.objects.public().filter(upgrade_only=False, price_annual__gt=0):
        charged = billing_services.plan_sale(buyer, plan.slug, "year")
        assert f"≈ €{charged.net.normalize():f}/year" in html or f"≈ €{charged.net:.2f}/year" in html, plan.slug


def test_the_detail_page_paints_the_price_the_checkout_charges(client, plans, make_user):
    buyer = make_user("detail@example.com")
    starter = Plan.objects.get(slug="starter")

    html = html_of(client, f"/pricing/{starter.slug}/")

    assert f"{billing_services.plan_sale(buyer, 'starter', 'month').net:.2f} &euro;" in html


def test_a_stripe_price_that_charges_the_painted_amount_is_accepted(client, plans, stripe_double):
    starter = Plan.objects.get(slug="starter")
    cents = to_cents(painted_prices(html_of(client))[starter.name_en])
    stripe_double.answer("prices.retrieve", stripe_price(starter.stripe_price_id, unit_amount=cents, product=""))

    problems = billing_services.plan_price_problems(
        prices={"stripe_price_id": starter.stripe_price_id, "stripe_price_id_annual": ""},
        amounts={"price_monthly": starter.price_monthly, "price_annual": starter.price_annual},
        product="",
    )

    assert problems == {}


def test_a_stripe_price_a_cent_off_the_painted_amount_is_refused(client, plans, stripe_double):
    """The plan cannot sell at one price and paint another: the admin refuses the Stripe price."""
    starter = Plan.objects.get(slug="starter")
    cents = to_cents(painted_prices(html_of(client))[starter.name_en]) + 1
    stripe_double.answer("prices.retrieve", stripe_price(starter.stripe_price_id, unit_amount=cents, product=""))

    problems = billing_services.plan_price_problems(
        prices={"stripe_price_id": starter.stripe_price_id, "stripe_price_id_annual": ""},
        amounts={"price_monthly": starter.price_monthly, "price_annual": starter.price_annual},
        product="",
    )

    assert list(problems) == ["stripe_price_id"]
