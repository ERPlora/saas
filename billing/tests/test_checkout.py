"""Buying a plan or a module for a business: ``billing.checkout.start`` and ``billing.checkout.confirm``.

ONE Stripe subscription per business, whose items are the plan and the
modules, at net prices plus OUR tax rates. A business without a Stripe subscription (Free) pays in an
Embedded Checkout (``client_secret`` for the modal); one that has it previews the prorated charge, and
the confirmation adds the item, charged at once (``always_invoice``) or not at all
(``error_if_incomplete``). The rules:

- WHERE the payer is, before charging: the postal code tells the Canary Islands (outside VAT)
  from the mainland; without it, 409 ``billing.billing_location_required`` and Stripe is never called.
- The rate is ours (``billing.TaxRule``): ``automatic_tax`` is never sent; Stripe gets a
  ``TaxRate`` per item; a territory without a rule is refused (``billing.tax_engine_missing``).
- Over 400 € with VAT the invoice must name the buyer (RD 1619/2012, art. 4): 409 ``billing.tax_id_required``.
- Stripe never collects the VAT number (it reverse charges by its FORMAT): only one VIES proved
  (or a national one) reaches the customer.
- A promo code replaces the trial; a free business in its Starter trial keeps the days it has
  left when it buys (no second free ride, and none taken away either).
- No real money while the year's OSS total is unknown: a LIVE key refuses with 409
  ``billing.oss_total_unknown``. A business with an unpaid invoice buys nothing.
- Only the Embedded Checkout opens (no hosted redirect), one business is one subscription, and Free never
  reaches Stripe.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from billing.models import CheckoutAttempt
from billing.services import checkouts, stripe_customers
from billing.tests.checkout_calls import payer, session_params, start
from billing.tests.vies_double import (
    FAKE_VAT,
    NOT_REGISTERED,
    REAL_VAT,
    VALID,
    no_network,
    vies_is_down,
    vies_says,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


# --- A free business pays in an Embedded Checkout ----------------------------------------------------


class TestTheEmbeddedCheckout:
    def test_it_opens_for_the_plan(self, shop, owner, stripe_double):
        answer = start(owner, shop, plan="starter")

        params = session_params(stripe_double)
        assert answer["flow"] == "checkout"
        assert answer["client_secret"].startswith("cs_test_") and answer[
            "session_id"
        ].startswith("cs_test_")
        assert answer["publishable_key"] == "pk_test_double"
        assert answer["preview"] is None
        assert params["ui_mode"] == "embedded_page"
        assert params["mode"] == "subscription"
        assert params["redirect_on_completion"] == "if_required"
        assert params["return_url"].endswith(f"/dashboard/businesses/{shop.id}/summary?checkout={{CHECKOUT_SESSION_ID}}")
        assert params["line_items"] == [
            {
                "price": "price_starter_month",
                "quantity": 1,
                "tax_rates": [stripe_double.tax_rates[0]["id"]],
            }
        ]

    def test_stripe_tax_and_fixed_payment_methods_are_never_sent(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="starter")

        params = session_params(stripe_double)
        assert "automatic_tax" not in params
        assert "payment_method_types" not in params
        assert "default_tax_rates" not in params.get("subscription_data", {})

    def test_the_address_is_collected_and_the_vat_number_is_not(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="starter")

        params = session_params(stripe_double)
        assert params["billing_address_collection"] == "required"
        assert params["tax_id_collection"] == {"enabled": False}

    def test_the_session_says_what_it_pays_for(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter", interval="year")

        params = session_params(stripe_double)
        assert params["metadata"] == {
            "kind": "hub_plan",
            "hub_id": str(shop.id),
            "plan": "starter",
            "billing_interval": "year",
            "attempt": str(CheckoutAttempt.objects.get().id),
        }
        assert params["subscription_data"]["metadata"] == {"hub_id": str(shop.id)}
        assert params["line_items"][0]["price"] == "price_starter_year"

    def test_a_module_is_bought_alone_on_a_free_business(
        self, shop, owner, inventory, stripe_double
    ):
        start(owner, shop, module="inventory")

        params = session_params(stripe_double)
        assert params["metadata"]["kind"] == "module_purchase"
        assert params["metadata"]["module"] == "inventory"
        assert params["line_items"][0]["price"] == "price_inventory_month"
        # A module has no trial.
        assert "trial_end" not in params["subscription_data"]

    def test_it_is_tagged_for_the_dashboard(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")

        assert (
            session_params(stripe_double)["integration_identifier"]
            == checkouts.INTEGRATION_IDENTIFIER
        )

    def test_the_same_selection_reuses_its_open_session(
        self, shop, owner, stripe_double
    ):
        first = start(owner, shop, plan="starter")
        again = start(owner, shop, plan="starter")

        assert again["client_secret"] == first["client_secret"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 1

    def test_another_selection_gets_its_own_session(self, shop, owner, stripe_double):
        first = start(owner, shop, plan="starter")
        other = start(owner, shop, plan="starter", interval="year")

        assert other["session_id"] != first["session_id"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 2

    def test_a_new_selection_expires_the_other_open_session(self, shop, owner, stripe_double):
        """Two open sessions could both be paid: two subscriptions for one business."""
        first = start(owner, shop, plan="starter")
        stripe_double.answer("checkout.sessions.expire", {"id": first["session_id"], "status": "expired"})

        start(owner, shop, plan="standard")

        assert stripe_double.last("checkout.sessions.expire").args == (first["session_id"],)
        assert CheckoutAttempt.objects.get(stripe_session_id=first["session_id"]).status == "expired"

    def test_a_session_stripe_cannot_expire_any_more_does_not_stop_the_new_one(self, shop, owner, stripe_double):
        from billing.tests.stripe_double import invalid_request

        first = start(owner, shop, plan="starter")
        stripe_double.answer("checkout.sessions.expire", invalid_request("checkout_session_not_open", "Not open"))

        assert start(owner, shop, plan="standard")["flow"] == "checkout"
        assert CheckoutAttempt.objects.get(stripe_session_id=first["session_id"]).status == "open"

    def test_a_payer_whose_tax_changed_gets_a_new_session(self, shop, owner, stripe_double):
        first = start(owner, shop, plan="starter")
        payer(shop, billing_postal_code="35001", billing_city="Las Palmas", tax_id="ESB27593136")
        stripe_double.answer("checkout.sessions.expire", {"id": first["session_id"], "status": "expired"})

        again = start(owner, shop, plan="starter")

        assert again["session_id"] != first["session_id"]
        assert session_params(stripe_double)["line_items"][0]["tax_rates"] == []

    def test_a_session_that_expired_is_not_reused(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")
        CheckoutAttempt.objects.update(created_at=timezone.now() - timedelta(hours=24))

        start(owner, shop, plan="starter")

        assert len(stripe_double.calls_to("checkout.sessions.create")) == 2

    def test_the_session_is_created_once_whatever_the_retries(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="starter")

        attempt = CheckoutAttempt.objects.get()
        assert stripe_double.last("checkout.sessions.create").options == {
            "idempotency_key": f"checkout-{attempt.id}"
        }
        assert (attempt.status, attempt.kind, attempt.plan_slug) == (
            "open",
            "plan",
            "starter",
        )


# --- The customer ------------------------------------------------------------------------------------


class TestTheCustomer:
    def test_the_payer_becomes_a_stripe_customer_once(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")

        created = stripe_double.last("customers.create")
        assert created.params["name"] == "Panadería López SL"
        assert created.params["email"] == "owner@example.com"
        assert created.params["address"] == {
            "line1": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28001",
            "country": "ES",
        }
        assert created.params["preferred_locales"] == ["es"]
        assert created.options["idempotency_key"].startswith(f"customer-{shop.billing_profile.id}-")
        shop.billing_profile.refresh_from_db()
        assert shop.billing_profile.stripe_customer_id == "cus_new"
        params = session_params(stripe_double)
        assert params["customer"] == "cus_new"
        assert params["customer_update"] == {"name": "auto", "address": "auto"}

    def test_a_known_customer_is_brought_up_to_date_not_created_again(
        self, shop, owner, stripe_double
    ):
        payer(shop, stripe_customer_id="cus_known")

        start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.create") == []
        assert stripe_double.last("customers.update").args == ("cus_known",)
        assert session_params(stripe_double)["customer"] == "cus_known"

    def test_a_test_clock_travels_to_the_new_customer(self, shop, stripe_double):
        stripe_customers.ensure_customer(shop, test_clock="clock_123")

        assert (
            stripe_double.last("customers.create").params["test_clock"] == "clock_123"
        )

    def test_without_a_clock_the_customer_does_not_mention_one(
        self, shop, stripe_double
    ):
        stripe_customers.ensure_customer(shop)

        assert "test_clock" not in stripe_double.last("customers.create").params


@pytest.mark.usefixtures("every_country_sold")
class TestOnlyAProvedVatNumberReachesStripe:
    def test_a_number_vies_rejects_never_reaches_stripe(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=FAKE_VAT)

        with vies_says(**NOT_REGISTERED):
            answer = start(owner, shop, plan="starter")

        assert answer["flow"] == "checkout"
        assert stripe_double.calls_to("customers.tax_ids.create") == []

    def test_a_proved_number_reaches_the_customer(self, shop, owner, stripe_double):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

        with vies_says(**VALID):
            start(owner, shop, plan="starter")

        assert stripe_double.last("customers.tax_ids.create").params == {
            "type": "eu_vat",
            "value": REAL_VAT,
        }

    def test_vies_down_charges_the_vat_and_attaches_nothing(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

        with vies_is_down():
            start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.tax_ids.create") == []
        assert stripe_double.last("tax_rates.create").params["percentage"] == 21.0

    def test_a_national_number_reaches_stripe_without_asking_vies(
        self, shop, owner, stripe_double
    ):
        payer(shop, tax_id="ESB27593136")

        with no_network() as network:
            start(owner, shop, plan="starter")

        network.assert_not_called()
        assert stripe_double.last("customers.tax_ids.create").params == {
            "type": "eu_vat",
            "value": "ESB27593136",
        }

    def test_a_number_already_on_the_customer_is_not_added_twice(
        self, shop, owner, stripe_double
    ):
        payer(shop, tax_id="ESB27593136", stripe_customer_id="cus_known")
        stripe_double.customer_tax_ids["cus_known"] = [
            {"id": "txi_1", "type": "eu_vat", "value": "ESB27593136"}
        ]

        start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.tax_ids.create") == []
