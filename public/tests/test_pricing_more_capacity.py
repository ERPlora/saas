"""Above the plans on sale of ``/pricing/``: no dedicated infrastructure nor an offer by contact, only the
upgrade-only plans, under «More capacity»."""

from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest

from hubs.models import Plan
from public import pricing
from public.tests.pricing_pages import (
    CARD_START,
    COLUMNS,
    PRICE_400,
    UPGRADE_SECTION,
    card_items,
    faq_page_of,
    get,
    html_of,
    make_plan,
    painted_prices,
    plan_table,
    upgrade_section,
    visible_markup,
    visible_text,
)

pytestmark = [pytest.mark.django_db]


# --- Nothing above the plans: no dedicated infrastructure ------------------------------------------

CONTACT = "/contact/"


def test_the_page_offers_no_dedicated_infrastructure(client, seeded):
    """No «Dedicated infrastructure, from €400 a month» band: it is no product and the plans sell no infrastructure.
    Above Standard the page shows only the upgrade-only plans (Pro, Enterprise and Max), never an offer by contact."""
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
    signable, upgrades = table.split(f'<td colspan="{COLUMNS}">More capacity</td>', 1)

    assert groups == ["Plans · sign up directly", "More capacity"]
    assert signable.count('href="/launch"') == 3
    assert 'href="/launch"' not in upgrades
    assert upgrades.count("Available once you are on Starter") == 3
    for amount in ("€109.99", "€209.99", "€419.99"):
        assert amount in upgrades, amount


def test_the_table_reads_the_upgrade_only_plans_in_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert f'<td colspan="{COLUMNS}">Más capacidad</td>' in table
    assert table.count("Disponible al pasar a Starter") == 3


def test_the_table_intro_sends_nobody_to_a_custom_setup(client, seeded):
    body = " ".join(visible_markup(html_of(client)).split())

    assert "one hub covers all your devices and users" in body
    assert "Need more than that?" not in body


def test_the_page_includes_no_location_in_any_plan(client, seeded):
    """Multi-location comes from Pro and is charged per location: neither the table's
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


# --- More capacity: the upgrade-only plans on the page -----------------------------------------------------------
# Odoo, Holded and Square show the whole ladder on their pricing page. The rows stay ``upgrade_only``: the Store offers
# them to a business that already pays and the checkout from Free refuses them (``billing.plan_upgrade_only``,
# billing/tests/test_checkout_who_and_what.py).

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
        # The row's lines, with the apps it turns on at once right after its «Everything in …».
        expected = [features[0], "All the apps turned on at once", *features[1:]]
        assert card_items(section, plan.name_en)[: len(expected)] == expected, plan.slug
        assert f"≈ €{plan.price_annual:.2f}/year · 2 months free" in text, plan.slug
        assert "/ month per hub" in text


def without_separators(features: list[str]) -> list[str]:
    """A row's features as ``hubs.plan.list`` gives them: the seed's «───» separator lines (Max's) are dropped."""
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
        assert 'href="' not in card.split('<div class="ep-pricing-card__cta">', 1)[0] + foot
        assert "Get started" not in foot


def test_more_capacity_has_one_call_to_action_to_start_free(client, seeded):
    section = upgrade_section(html_of(client))
    buttons = re.findall(r'<a class="ep-button[^"]*" href="([^"]*)">(.*?)</a>', section, re.S)

    assert len(buttons) == 1
    assert buttons[0][0] == "/launch"
    assert "Start free and upgrade whenever you want" in buttons[0][1]


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
    assert f'<td colspan="{COLUMNS}">More capacity</td>' not in html
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
        assert re.search(r'<a class="ep-button[^"]*" href="/launch">', card_foot(card))
        assert "Available once you are on Starter" not in card
    assert painted_prices(signable) == {"Free": Decimal("0"), "Starter": Decimal("29.99"), "Standard": Decimal("54.99")}


def test_more_capacity_promises_no_trial_nor_a_saving_of_its_own_in_the_hero(no_plans, client):
    """An upgrade grants no trial and the hero's saving is the plans on sale's: an upgrade-only row with a trial
    and another saving changes neither."""
    make_plan("starter", price_annual=Decimal("299.90"))
    make_plan("pro", upgrade_only=True, trial_days=30, price_monthly=Decimal("100"), price_annual=Decimal("900"))

    response = get(client)

    assert response.context["months_free"] == 2
    assert "30-day" not in upgrade_section(response.content.decode())
    assert response.context["trial_note"] == "Free plan with no card required. Cancel anytime."
