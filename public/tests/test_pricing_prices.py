"""The prices of ``/pricing/`` and ``/pricing/<slug>/``: net, with the ex-VAT note; the annual saving worked out
from the two prices; and the price painted being the price the checkout charges.

* The ex-VAT note is ``public/partials/_vat_note.html`` and links ``public:terms``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from billing.money import to_cents
from billing.services import price_checks, stripe_sales
from billing.tests.conftest import plans, stripe_double, stripe_keys  # noqa: F401
from billing.tests.test_services import stripe_price
from hubs.models import Plan
from public.tests.pricing_pages import html_of, make_plan, painted_prices

pytestmark = [pytest.mark.django_db]


# --- The ex-VAT note --------------------------------------------------------------------------

NET = "29.99"
#: The 21 % gross of 29.99: exactly what a selling screen never shows.
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
    assert "El IVA que te corresponde se calcula en el pago a partir de tu dirección de facturación" in html


# --- The annual saving is worked out from the two prices, never typed ------------------------------
# A typed «2 months free» would stay put when the annual price is edited. The months free are 12 minus the months the
# annual price pays for, rounded down so the page never promises more than the checkout gives.


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


# --- The price painted is the price charged ---------------------------------------------------------
# One field, one amount: what /pricing/ and the detail page paint is the net ``Plan`` price, the checkout
# charges that same amount (``billing.services.stripe_sales.plan_sale``) and the Stripe price the plan sells with
# must charge it to the cent, or the admin refuses it. Stripe is the double of billing's
# tests: no call leaves the machine.


def test_every_card_paints_the_price_the_checkout_charges(client, plans):
    painted = painted_prices(html_of(client))
    paid = [plan for plan in Plan.objects.public() if not plan.upgrade_only and plan.price_monthly > 0]

    assert paid, "no paid plan on sale to compare"
    for plan in paid:
        charged = stripe_sales.plan_sale(None, plan.slug, "month")
        assert painted[plan.name_en] == charged.net, plan.slug
        assert charged.price_id == plan.stripe_price_id


def test_the_year_painted_is_the_year_charged(client, plans):
    html = " ".join(html_of(client).split())

    for plan in Plan.objects.public().filter(upgrade_only=False, price_annual__gt=0):
        charged = stripe_sales.plan_sale(None, plan.slug, "year")
        assert f"≈ €{charged.net.normalize():f}/year" in html or f"≈ €{charged.net:.2f}/year" in html, plan.slug


def test_the_detail_page_paints_the_price_the_checkout_charges(client, plans):
    starter = Plan.objects.get(slug="starter")

    html = html_of(client, f"/pricing/{starter.slug}/")

    assert f"{stripe_sales.plan_sale(None, 'starter', 'month').net:.2f} &euro;" in html


def test_a_stripe_price_that_charges_the_painted_amount_is_accepted(client, plans, stripe_double):
    starter = Plan.objects.get(slug="starter")
    cents = to_cents(painted_prices(html_of(client))[starter.name_en])
    stripe_double.answer("prices.retrieve", stripe_price(starter.stripe_price_id, unit_amount=cents, product=""))

    problems = price_checks.plan_price_problems(
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

    problems = price_checks.plan_price_problems(
        prices={"stripe_price_id": starter.stripe_price_id, "stripe_price_id_annual": ""},
        amounts={"price_monthly": starter.price_monthly, "price_annual": starter.price_annual},
        product="",
    )

    assert list(problems) == ["stripe_price_id"]
