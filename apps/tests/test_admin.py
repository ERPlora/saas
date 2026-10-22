"""APPS-F04: the Stripe prices pasted on a module in the admin are checked in Stripe before the module sells with them.

The same checks as a plan's (BILLING-F28, ``billing.services.module_price_problems``), through the real admin form
and Stripe's double at the boundary (``billing.stripe_service.client``): no network. Not configured (development)
saves with a warning; Stripe not answering saves nothing and asks to try again.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.models import Module
from apps.tests.factories import make_app
from billing.tests.stripe_double import StripeDouble, connection_error

pytestmark = pytest.mark.django_db

HOST = "localhost"
ADD = "/admin/apps/module/add/"


@pytest.fixture
def staff_client(client):
    client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))
    return client


@pytest.fixture
def stripe(settings, monkeypatch):
    from billing import stripe_service

    settings.STRIPE_SECRET_KEY = "rk_test_double"
    double = StripeDouble()
    monkeypatch.setattr(stripe_service, "client", lambda: double)
    return double


@pytest.fixture
def whatsapp():
    return make_app("whatsapp_inbox", premium=True)


def stripe_price(price_id="price_month", **fields):
    return {
        "id": price_id,
        "object": "price",
        "active": True,
        "currency": "eur",
        "unit_amount": 999,
        "tax_behavior": "exclusive",
        "product": "prod_whatsapp",
        "recurring": {"interval": "month", "interval_count": 1},
        **fields,
    }


def module_form(**changes) -> dict[str, str]:
    return {
        "slug": "whatsapp_inbox",
        "tier": "basic",
        "price_monthly_cents": "999",
        "price_annual_cents": "0",
        "stripe_product_id": "prod_whatsapp",
        "stripe_price_id_monthly": "price_month",
        "stripe_price_id_annual": "",
        "is_active": "on",
        **changes,
    }


def test_a_price_that_charges_the_modules_amount_is_saved(staff_client, stripe, whatsapp):
    stripe.answer("prices.retrieve", stripe_price())

    response = staff_client.post(ADD, module_form(), HTTP_HOST=HOST)

    assert response.status_code == 302
    assert Module.objects.get(slug="whatsapp_inbox").stripe_price_id_monthly == "price_month"
    assert [call.args for call in stripe.calls_to("prices.retrieve")] == [("price_month",)]


@pytest.mark.parametrize(
    ("price", "message"),
    [
        ({"unit_amount": 900}, "Stripe charges 9.00 and the module says 9.99."),
        ({"currency": "usd"}, "This price is not in euros."),
        ({"tax_behavior": "inclusive"}, "This price includes the VAT or does not say"),
    ],
)
def test_a_price_that_would_charge_otherwise_is_refused_under_its_field(staff_client, stripe, whatsapp, price, message):
    stripe.answer("prices.retrieve", stripe_price(**price))

    response = staff_client.post(ADD, module_form(), HTTP_HOST=HOST)

    assert response.status_code == 200
    assert not Module.objects.exists()
    assert list(response.context["adminform"].form.errors) == ["stripe_price_id_monthly"]
    assert message in response.content.decode()


def test_the_refusal_speaks_the_language_of_the_admin(staff_client, stripe, whatsapp):
    stripe.answer("prices.retrieve", stripe_price(unit_amount=900))

    page = staff_client.post(ADD, module_form(), HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Stripe cobra 9.00 y el módulo dice 9.99." in page


def test_stripe_not_answering_saves_nothing_and_asks_to_try_again(staff_client, stripe, whatsapp):
    stripe.answer("prices.retrieve", connection_error())

    response = staff_client.post(ADD, module_form(), HTTP_HOST=HOST)

    assert response.status_code == 200
    assert not Module.objects.exists()
    assert "Stripe did not answer: the prices were not checked. Try again." in response.content.decode()


def test_without_stripe_it_is_saved_and_says_it_was_not_checked(staff_client, settings, whatsapp):
    settings.STRIPE_SECRET_KEY = ""

    response = staff_client.post(ADD, module_form(), HTTP_HOST=HOST, follow=True)

    assert Module.objects.get(slug="whatsapp_inbox").stripe_price_id_monthly == "price_month"
    assert "Stripe is not configured here: the prices were not checked." in response.content.decode()


def test_other_changes_ask_stripe_nothing(staff_client, stripe, whatsapp):
    stripe.answer("prices.retrieve", stripe_price())
    staff_client.post(ADD, module_form(), HTTP_HOST=HOST)
    module = Module.objects.get(slug="whatsapp_inbox")
    asked = len(stripe.calls_to("prices.retrieve"))

    response = staff_client.post(
        f"/admin/apps/module/{module.pk}/change/", module_form(tier="pro"), HTTP_HOST=HOST
    )

    assert response.status_code == 302
    assert Module.objects.get(pk=module.pk).tier == "pro"
    assert len(stripe.calls_to("prices.retrieve")) == asked
