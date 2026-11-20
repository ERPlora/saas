"""The pages of the plans on sale, ``/pricing/`` and ``/pricing/<slug>/``: their routes, what the index lists and
never says, the internal plans no visitor sees, the empty state and the detail page.

* ``Plan.objects.public()`` is pinned by ``hubs/tests/test_plan_list.py``; here, what the pages show of it.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from hubs.models import Plan
from public import pricing
from public.tests.conftest import without_tokens
from public.tests.pricing_pages import (
    INDEX,
    UPGRADE_SECTION,
    faq_page_of,
    get,
    html_of,
    make_plan,
    upgrade_section,
    visible_markup,
)

pytestmark = [pytest.mark.django_db]


# --- Routes -----------------------------------------------------------------------------------


def test_the_routes():
    assert reverse("public:pricing") == "/pricing/"
    assert reverse("public:pricing_detail", args=["starter"]) == "/pricing/starter/"


def test_the_pages_only_answer_safe_methods(client, seeded):
    assert client.post(INDEX).status_code == 405
    assert client.post("/pricing/starter/").status_code == 405


# --- The index page ---------------------------------------------------------------------------


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
    # An upgrade-only row is shown under «More capacity», never with the cards a visitor signs up
    # on, and without the old visual separators.
    upgrades = upgrade_section(html)
    for text in ("DB Upgrade Sentinel", "€62.46", "Upgrade description loaded from the database", "Upgrade feature sentinel"):
        assert text in upgrades, text
    assert "DB Upgrade Sentinel" not in html.split(UPGRADE_SECTION, 1)[0]
    assert "────────────────────" not in html
    assert "DB Inactive Sentinel" not in html


# The public page must not rank plans by the box they run on.
PUBLIC_SPEC_PATTERNS = [
    (r"\bv?CPU\b", "CPU spec"),
    (r"\bRAM\b", "RAM spec"),
    (r"\bDB connections\b", "DB connection quota"),
    (r"\bDB storage\b", "DB storage quota"),
    (r"\bcompute resources\b", "compute multiplier"),
]
# Case-sensitive on purpose: case-insensitively «gap-3 mb-2» reads as «3 MB».
SIZE_PATTERN = r"\b\d+\s*(MB|GB|TB)\b"


def test_pricing_page_never_renders_infrastructure_specs(client, seeded, tokens_spelling):
    tokens_spelling("CPU", "vCPU", "RAM", "5MB")
    html = without_tokens(html_of(client))

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


def test_billing_unit_survives_translation_to_spanish(client, seeded, tokens_spelling):
    """The template strings, not the seed's «Precio por hub»: the cards (main and upgrade-only)
    both carry the period, so the count tells them apart."""
    tokens_spelling("CPU", "vCPU", "RAM")
    html = without_tokens(html_of(client, language="es"))

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


# --- Internal plans are never public -----------------------------------------------------------


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


# --- The empty state --------------------------------------------------------------------------


def test_without_plans_on_sale_the_page_says_so_and_paints_no_table(no_plans, client):
    html = html_of(client)

    assert "There are no plans on sale right now." in html
    assert 'id="plan-compare"' not in html
    assert "ep-pricing-card" not in html
    # The FAQ still answers, from the same list as its markup.
    assert faq_page_of(html)


# --- The detail page --------------------------------------------------------------------------


def test_the_catalogue_promises_no_trial_and_points_to_the_free_plan(client, seeded):
    """No plan carries a trial; the Free plan is the way in, and the page says so."""
    html = html_of(client)

    assert "free trial" not in visible_markup(html).lower()
    (item,) = [item for item in pricing.faq_items() if item["key"] == "trial"]
    assert "the Free plan is free forever" in str(item["answer"])


def test_the_detail_shows_the_plan_its_price_its_features_and_its_trial(client, seeded):
    # The dormant trial, on: no plan carries one, but staff may give one in the admin.
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
