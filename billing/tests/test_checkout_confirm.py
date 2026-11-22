"""A business that already pays: the prorated preview, a module added and charged at once or not at all, and the
retries and limits of that charge (``billing.checkout.start`` and ``billing.checkout.confirm``).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.tests.checkout_calls import NOW_TS, confirm, payer, paying, refused, start
from billing.tests.conftest import pay
from billing.tests.stripe_double import card_error, connection_error, item, preview, subscription
from hubs.models import Hub, Subscription, SubscriptionItem

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


# --- A business that pays already previews and confirms ----------------------------------------------


class TestTheProratedPreview:
    def test_a_module_is_previewed_on_the_subscription_it_joins(
        self, shop, owner, inventory, stripe_double
    ):
        paid = paying(shop, stripe_double)
        stripe_double.answer(
            "invoices.create_preview", preview(amount_due=1210, tax=210)
        )

        answer = start(owner, paid, module="inventory")

        assert answer["flow"] == "confirm"
        assert (answer["client_secret"], answer["session_id"]) == (None, None)
        sent = stripe_double.last("invoices.create_preview").params
        assert sent["customer"] == "cus_1"
        assert sent["subscription"] == "sub_1"
        details = sent["subscription_details"]
        assert details["items"] == [
            {
                "price": "price_inventory_month",
                "quantity": 1,
                "tax_rates": [stripe_double.tax_rates[0]["id"]],
            }
        ]
        assert details["proration_behavior"] == "always_invoice"
        assert answer["preview"] == {
            "amount_due_cents": 1210,
            "tax_cents": 210,
            "currency": "eur",
            "proration_date": details["proration_date"],
            "charge_starts_at": None,
        }
        assert stripe_double.calls_to("checkout.sessions.create") == []

    def test_a_module_of_an_annual_subscription_is_its_annual_price(
        self, shop, owner, inventory, stripe_double
    ):
        # 299.90 + 100 a year is 483.88 € with VAT: the renewal's invoice must name the buyer.
        payer(shop, tax_id="12345678Z")
        pay(shop, interval="year")
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                items=[item("si_plan", "price_starter_year", interval="year")]
            ),
        )
        stripe_double.answer("invoices.create_preview", preview())

        start(owner, shop, module="inventory")

        assert stripe_double.last("invoices.create_preview").params[
            "subscription_details"
        ]["items"][0]["price"] == ("price_inventory_year")

    def test_a_new_plan_is_previewed_on_the_plan_item(self, shop, owner, stripe_double):
        paid = paying(shop, stripe_double)
        stripe_double.answer(
            "invoices.create_preview", preview(amount_due=3000, tax=520)
        )

        answer = start(owner, paid, plan="standard")

        items = stripe_double.last("invoices.create_preview").params[
            "subscription_details"
        ]["items"]
        assert items == [
            {
                "id": "si_plan",
                "price": "price_standard_month",
                "tax_rates": [stripe_double.tax_rates[0]["id"]],
            }
        ]
        assert answer["preview"]["amount_due_cents"] == 3000


class TestConfirmingAModule:
    def test_the_item_is_added_and_charged_at_once_or_not_at_all(
        self, shop, owner, inventory, stripe_double
    ):
        paid = paying(shop, stripe_double)
        stripe_double.answer(
            "subscription_items.create", item("si_inventory", "price_inventory_month")
        )
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                items=[
                    item("si_plan", "price_starter_month"),
                    item("si_inventory", "price_inventory_month"),
                ]
            ),
        )

        answer = confirm(owner, paid, module="inventory", proration_date=NOW_TS)

        sent = stripe_double.last("subscription_items.create")
        assert sent.params == {
            "subscription": "sub_1",
            "price": "price_inventory_month",
            "quantity": 1,
            "tax_rates": [stripe_double.tax_rates[0]["id"]],
            "proration_behavior": "always_invoice",
            "proration_date": NOW_TS,
            "payment_behavior": "error_if_incomplete",
            "metadata": {"hub_id": str(shop.id), "module": "inventory"},
        }
        assert sent.options["idempotency_key"].startswith(
            f"module-{shop.id}-inventory-"
        )
        assert (
            SubscriptionItem.objects.get(
                subscription__hub=shop, module_slug="inventory"
            ).stripe_item_id
            == "si_inventory"
        )
        assert [module["slug"] for module in answer["modules"]] == ["inventory"]
        assert Hub.objects.get(pk=shop.pk).state_version > paid.state_version

    @pytest.mark.parametrize("offset", [120, -2 * 3600])
    def test_a_preview_from_another_moment_is_previewed_again(self, shop, owner, inventory, stripe_double, offset):
        """The proration date chooses what is charged: one in the future charges less."""
        paid = paying(shop, stripe_double)
        moment = int(timezone.now().timestamp()) + offset

        refused("billing.preview_expired", lambda: confirm(owner, paid, module="inventory", proration_date=moment))

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_once_charged_a_slow_read_back_is_not_a_failure(self, shop, owner, inventory, stripe_double):
        """The module was added and paid: «nothing was charged» would be a lie; the webhook applies it."""
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", item("si_inventory", "price_inventory_month"))
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[item("si_plan", "price_starter_month")]),
            connection_error(),
        )

        answer = confirm(owner, paid, module="inventory", proration_date=int(timezone.now().timestamp()))

        assert answer["hub_id"] == shop.id

    def test_a_declined_card_adds_nothing(self, shop, owner, inventory, stripe_double):
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", card_error())

        error = refused(
            "billing.card_declined",
            lambda: confirm(
                owner, paid, module="inventory", proration_date=NOW_TS
            ),
        )

        assert error.status == 409
        assert not SubscriptionItem.objects.filter(
            subscription__hub=shop, module_slug="inventory"
        ).exists()

    def test_a_free_business_goes_through_the_checkout(self, shop, owner, inventory):
        refused(
            "billing.checkout_required",
            lambda: confirm(owner, shop, module="inventory", proration_date=NOW_TS),
        )

    def test_a_module_it_has_is_not_added_twice(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"])

        refused(
            "billing.module_owned",
            lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS),
        )

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_a_renewal_over_the_limit_needs_the_tax_id_before_adding(
        self, shop, owner, inventory, stripe_double
    ):
        # Standard yearly (549.90) is already over 400 € with VAT: adding to it needs the payer named.
        from hubs.models import Plan

        paid = paying(shop, stripe_double)
        Subscription.objects.filter(hub=paid).update(
            billing_interval="year", plan=Plan.objects.get(slug="standard")
        )

        refused(
            "billing.tax_id_required",
            lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS),
        )

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_the_net_price_is_what_the_location_guard_sees(
        self, shop, owner, inventory, stripe_double
    ):
        paid = paying(shop, stripe_double)
        payer(paid, billing_postal_code="")

        refused(
            "billing.billing_location_required",
            lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS),
        )

        assert Decimal(inventory.price_monthly_cents) / 100 == Decimal("10")


# --- Retries, limits and trials ----------------------------------------------------------------------


class TestRetriesAndLimits:
    def test_a_retry_after_the_card_changed_is_charged_again(self, shop, owner, inventory, stripe_double):
        """Stripe keeps the answer of an idempotency key, the decline included: each confirmation is its own."""
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", card_error(), item("si_inventory", "price_inventory_month"))

        refused("billing.card_declined", lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS))
        answer = confirm(owner, paid, module="inventory", proration_date=NOW_TS)

        keys = [call.options["idempotency_key"] for call in stripe_double.calls_to("subscription_items.create")]
        assert keys[0] != keys[1]
        assert answer["hub_id"] == shop.id

    def test_a_charge_stripe_did_not_confirm_never_says_nothing_was_charged(self, shop, owner, inventory, stripe_double):
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", connection_error())

        error = refused(
            "billing.stripe_unavailable", lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS)
        )

        assert error.status == 503
        assert "Nothing was charged" not in error.message

    def test_a_subscription_holds_twenty_items_at_most(self, shop, owner, inventory, stripe_double):
        paid = pay(shop)
        lines = [item("si_plan", "price_starter_month")] + [item(f"si_{n}", f"price_other_{n}") for n in range(19)]
        stripe_double.answer("subscriptions.retrieve", subscription(items=lines))

        refused("billing.too_many_items", lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS))

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_a_module_added_during_a_paid_trial_says_when_it_starts_charging(self, shop, owner, inventory,
                                                                          stripe_double):
        trial_end = int((timezone.now() + timedelta(days=9)).timestamp())
        paid = pay(shop, status="trialing")
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(status="trialing", trial=(NOW_TS, trial_end), items=[item("si_plan", "price_starter_month")]),
        )
        stripe_double.answer("invoices.create_preview", preview(amount_due=0, tax=0))

        answer = start(owner, paid, module="inventory")

        assert answer["preview"]["amount_due_cents"] == 0
        assert answer["preview"]["charge_starts_at"] == trial_end
