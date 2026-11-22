"""The plans of the home ``/`` (public/landing.py): the ones on sale, their cards, the ex-VAT note and the comparison
section.

* The plans come from ``hubs.plan.list``: the cards end with the plan's real trial and carry the ex-VAT note, never a
  «with 21 % Spanish VAT» line.
* The plan cards are ``public/components/pricing_card.html``.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.tests.factories import make_app
from public.tests.landing_pages import html_of, make_plan, page, section

pytestmark = [pytest.mark.django_db]

CARD_START = re.compile(r'<div class="ep-pricing-card(?: ep-pricing-card--featured)?">')
CARD_ITEM = re.compile(
    r'<li><span class="ep-pricing-card__check" aria-hidden="true">✓</span><span>(.*?)</span></li>',
    re.S,
)


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


# --- The plans --------------------------------------------------------------------------------


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


# --- The plan cards: their trial and the apps they turn on ------------------------------------


def test_the_home_card_ends_with_the_trial_the_plan_grants(no_plans, client):
    make_plan("starter", trial_days=21)

    assert card_items(html_of(client), "Starter") == [
        "Unlimited users",
        "All the apps turned on at once",
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
        "Todas las apps activadas a la vez",
        "21 días de prueba gratis",
    ]


def test_a_plan_without_trial_shows_no_trial_line_on_the_home(no_plans, client):
    make_plan("free", trial_days=0, price_monthly=Decimal("0"))

    assert card_items(html_of(client), "Free") == ["Unlimited users", "All the apps turned on at once"]


def test_the_home_card_says_the_apps_the_plan_turns_on_at_once_after_what_it_includes(no_plans, client):
    """The same card as /pricing/ (public.pricing.plan_card): the cap the Hub applies, from the row."""
    make_plan("starter", features_en=["All apps included", "Unlimited users"], max_apps=40)

    assert card_items(html_of(client), "Starter") == [
        "All apps included",
        "Up to 40 apps turned on at once",
        "Unlimited users",
    ]


def test_painting_the_trial_never_writes_it_into_the_plan(no_plans, client):
    starter = make_plan("starter", trial_days=21)

    for language in ("en", "es"):
        html_of(client, language=language)

    starter.refresh_from_db()
    assert starter.features_en == ["Unlimited users"]
    assert starter.features_es == ["Usuarios ilimitados"]


def test_the_contact_section_states_the_real_trial_never_a_typed_one(no_plans, client):
    """The trial comes from the plan, never typed by hand (such as «a 15-day free trial»)."""
    make_plan("starter", trial_days=30)

    contact = section(html_of(client), "contacto")

    assert "30-day free trial" in contact
    assert "15-day" not in contact


# --- The ex-VAT note --------------------------------------------------------------------------


def test_the_home_shows_the_net_price_with_the_ex_vat_note_and_no_vat_figure(client):
    make_plan("net-display", price_monthly=Decimal("29.99"))

    plans = section(html_of(client), "planes")

    assert "29.99" in plans
    assert "36.29" not in plans and "36,29" not in plans
    assert "+ VAT" not in plans and "Spanish VAT" not in plans
    assert "All prices exclude VAT" in plans
    assert f'href="{reverse("public:terms")}"' in plans


# --- The comparison section -------------------------------------------------------------------


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
    """Every plan includes all the apps: the cell counts them, never «3 free + 1 premium»."""
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
    """The same promise as the head of /pricing/, never «all the free apps, and the paid plans include the premium
    apps too»."""
    plans = section(html_of(client, language=language), "planes")

    assert f'<p class="ep-section-sub">{sentence}</p>' in plans
