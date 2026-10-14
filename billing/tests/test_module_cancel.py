"""Cancelling and keeping a bought module, and the Customer Portal: ``billing.module.{cancel,keep}``,
``billing.portal.open`` (lot L2-B).

PLAN-SAAS §3.3: a cancelled module leaves the subscription WITHOUT proration and works until the end of
the period it was paid for (``valid_until`` in the snapshot, so the Hub switches it off then). Stripe keeps
at least one item per subscription, so the last thing a subscription bills ends the whole subscription at
the period's end instead. Keeping it before then bills it again from the next renewal, charging nothing
now. New in this design (the old SaaS sold each module as its own subscription; its cancel was the
subscription's ``cancel_at_period_end``, ported in ``test_plan_change.py``).

The portal (Stripe's Customer Portal: cards and Stripe's receipts) was ``BillingPortalAPIView`` of
``public/modules/api_views.py``: only for the payer, and only once there is a Stripe customer.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import NotFound, OperationError, PermissionDenied

from billing import services
from billing.schemas import ModuleIn, PortalOpenIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import MONTH_END, item, subscription
from hubs import queries as hub_queries
from hubs.models import HubMember, SubscriptionItem
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def cancel(user, hub, module="inventory"):
    return services.module_cancel(
        ctx_for(user), ModuleIn(hub_id=hub.id, module=module)
    ).model_dump()


def keep(user, hub, module="inventory"):
    return services.module_keep(
        ctx_for(user), ModuleIn(hub_id=hub.id, module=module)
    ).model_dump()


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()


def bought(hub, slug="inventory"):
    return SubscriptionItem.objects.get(subscription__hub=hub, module_slug=slug)


PLAN = item("si_plan", "price_starter_month")
INVENTORY = item("si_inventory", "price_inventory_month")


class TestCancellingAModule:
    def test_it_leaves_stripe_without_proration_and_works_until_the_period_ends(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"])
        stripe_double.answer(
            "subscriptions.retrieve", subscription(items=[PLAN, INVENTORY])
        )
        stripe_double.answer("subscriptions.update", subscription(items=[PLAN]))

        answer = cancel(owner, paid)

        sent = stripe_double.last("subscriptions.update").params
        assert sent == {
            "items": [{"id": "si_inventory", "deleted": True}],
            "proration_behavior": "none",
        }
        until = bought(shop).valid_until
        assert until is not None and int(until.timestamp()) == MONTH_END
        assert answer["modules"] == [
            {"slug": "inventory", "source": "purchase", "valid_until": until}
        ]
        snapshot = hub_queries.hub_snapshot(shop.id)["modules"]
        assert snapshot == [
            {"id": "inventory", "source": "purchase", "valid_until": until.isoformat()}
        ]

    def test_the_last_thing_billed_ends_the_subscription_with_its_period(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, plan="free", modules=["inventory"])
        stripe_double.answer("subscriptions.retrieve", subscription(items=[INVENTORY]))
        stripe_double.answer(
            "subscriptions.update",
            subscription(items=[INVENTORY], cancel_at_period_end=True),
        )

        cancel(owner, paid)

        assert stripe_double.last("subscriptions.update").params == {
            "cancel_at_period_end": True
        }
        assert int(bought(shop).valid_until.timestamp()) == MONTH_END

    def test_cancelling_again_changes_nothing(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"])
        SubscriptionItem.objects.filter(module_slug="inventory").update(
            valid_until=timezone.now() + timedelta(days=3)
        )

        cancel(owner, paid)

        assert stripe_double.calls == []

    def test_a_module_of_the_plan_is_dropped_by_changing_the_plan(
        self, shop, owner, stripe_double
    ):
        paid = pay(shop)
        SubscriptionItem.objects.create(
            subscription=paid.subscription, module_slug="loyalty", source="plan"
        )

        refused("billing.module_included", lambda: cancel(owner, paid, "loyalty"))

    def test_a_module_the_business_does_not_have(self, shop, owner):
        paid = pay(shop)

        with pytest.raises(NotFound):
            cancel(owner, paid, "nothing")


class TestKeepingAModule:
    def cancelled(self, shop, days=10):
        paid = pay(shop, modules=["inventory"])
        SubscriptionItem.objects.filter(module_slug="inventory").update(
            stripe_item_id="", valid_until=timezone.now() + timedelta(days=days)
        )
        return paid

    def test_it_is_billed_again_from_the_next_renewal_charging_nothing_now(
        self, shop, owner, inventory, stripe_double
    ):
        paid = self.cancelled(shop)
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[PLAN]),
            subscription(items=[PLAN, INVENTORY]),
        )
        stripe_double.answer("subscription_items.create", INVENTORY)

        answer = keep(owner, paid)

        sent = stripe_double.last("subscription_items.create").params
        assert sent["subscription"] == "sub_1"
        assert sent["price"] == "price_inventory_month"
        assert sent["proration_behavior"] == "none"
        assert (bought(shop).valid_until, bought(shop).stripe_item_id) == (
            None,
            "si_inventory",
        )
        assert answer["modules"][0]["valid_until"] is None

    def test_a_module_that_ended_is_bought_again(
        self, shop, owner, inventory, stripe_double
    ):
        paid = self.cancelled(shop, days=-1)

        refused("billing.module_ended", lambda: keep(owner, paid))

        assert stripe_double.calls == []

    def test_the_last_module_undoes_the_end_of_the_subscription(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, plan="free", modules=["inventory"], cancel_at_period_end=True)
        SubscriptionItem.objects.filter(module_slug="inventory").update(
            valid_until=timezone.now() + timedelta(days=5)
        )
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[INVENTORY], cancel_at_period_end=True),
        )
        stripe_double.answer("subscriptions.update", subscription(items=[INVENTORY]))

        keep(owner, paid)

        assert stripe_double.last("subscriptions.update").params == {
            "cancel_at_period_end": False
        }
        assert bought(shop).valid_until is None

    def test_a_cancelled_plan_takes_its_modules_along(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"], cancel_at_period_end=True)
        SubscriptionItem.objects.filter(module_slug="inventory").update(
            valid_until=timezone.now() + timedelta(days=5)
        )
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[PLAN, INVENTORY], cancel_at_period_end=True),
        )

        refused("billing.plan_cancelled", lambda: keep(owner, paid))

        assert stripe_double.calls_to("subscriptions.update") == []

    def test_an_unpaid_business_keeps_nothing(
        self, shop, owner, inventory, stripe_double
    ):
        paid = self.cancelled(shop)
        from hubs.models import Subscription

        Subscription.objects.filter(hub=paid).update(status="past_due")

        refused("billing.invoice_unpaid", lambda: keep(owner, paid))

        assert stripe_double.calls == []


class TestOnlyTheOwner:
    def test_nobody_else_cancels_or_keeps(
        self, shop, owner, make_user, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"])
        admin = make_user("admin@example.com")
        add_member(paid, admin, HubMember.Role.ADMIN, invited_by=owner)

        with pytest.raises(PermissionDenied):
            cancel(admin, paid)
        with pytest.raises(PermissionDenied):
            keep(admin, paid)

        assert stripe_double.calls == []


class TestThePortal:
    def test_it_opens_for_the_payer(self, shop, owner, stripe_double):
        paid = pay(shop)
        paid.billing_profile.refresh_from_db()

        answer = services.portal_open(
            ctx_for(owner), PortalOpenIn(hub_id=paid.id)
        ).model_dump()

        sent = stripe_double.last("billing_portal.sessions.create").params
        assert sent["customer"] == "cus_1"
        assert sent["return_url"].endswith("/billing")
        assert answer["url"].startswith("https://billing.stripe.com/")

    def test_it_opens_with_our_configuration(self, shop, owner, stripe_double, settings):
        """Review of L2-B: an explicit portal configuration (cards and receipts; no plan changes, which must
        carry our tax rates)."""
        settings.STRIPE_PORTAL_CONFIGURATION = "bpc_erplora"
        paid = pay(shop)

        services.portal_open(ctx_for(owner), PortalOpenIn(hub_id=paid.id))

        assert stripe_double.last("billing_portal.sessions.create").params["configuration"] == "bpc_erplora"

    def test_without_its_configuration_it_does_not_open(self, shop, owner, stripe_double, settings):
        settings.STRIPE_PORTAL_CONFIGURATION = ""
        paid = pay(shop)

        with pytest.raises(OperationError) as error:
            services.portal_open(ctx_for(owner), PortalOpenIn(hub_id=paid.id))

        assert (error.value.status, error.value.code) == (503, "billing.portal_unavailable")
        assert stripe_double.calls == []

    def test_there_is_nothing_to_manage_before_the_first_payment(
        self, shop, owner, stripe_double
    ):
        refused(
            "billing.no_customer",
            lambda: services.portal_open(ctx_for(owner), PortalOpenIn(hub_id=shop.id)),
        )

        assert stripe_double.calls == []

    def test_it_is_the_owners(self, shop, owner, make_user, stripe_double):
        paid = pay(shop)
        admin = make_user("admin@example.com")
        add_member(paid, admin, HubMember.Role.ADMIN, invited_by=owner)

        with pytest.raises(PermissionDenied):
            services.portal_open(ctx_for(admin), PortalOpenIn(hub_id=paid.id))

    def test_without_stripe_it_says_so(self, shop, owner, settings):
        paid = pay(shop)
        settings.STRIPE_SECRET_KEY = ""

        with pytest.raises(OperationError) as error:
            services.portal_open(ctx_for(owner), PortalOpenIn(hub_id=paid.id))

        assert (error.value.status, error.value.code) == (
            503,
            "billing.payments_unavailable",
        )


def test_a_new_owner_does_not_open_the_previous_owners_portal(shop, owner, make_user, stripe_double):
    """Review of L2-B: the portal shows the payer's cards and address; a transfer does not hand them over."""
    from billing.tests.test_checkout import transferred

    paid = pay(shop)
    new_owner = transferred(paid, owner, make_user)

    with pytest.raises(OperationError) as error:
        services.portal_open(ctx_for(new_owner), PortalOpenIn(hub_id=paid.id))

    assert error.value.code == "billing.payer_required"
    assert stripe_double.calls == []


def test_keeping_again_after_cancelling_again_is_its_own_request(shop, owner, inventory, stripe_double):
    """cancel → keep → cancel → keep within one period: the second keep is not the first one replayed."""
    paid = pay(shop, modules=["inventory"])
    SubscriptionItem.objects.filter(module_slug="inventory").update(
        stripe_item_id="", valid_until=timezone.now() + timedelta(days=10)
    )
    stripe_double.answer("subscriptions.retrieve", subscription(items=[PLAN]), subscription(items=[PLAN, INVENTORY]))
    stripe_double.answer("subscription_items.create", INVENTORY)
    keep(owner, paid)
    SubscriptionItem.objects.filter(module_slug="inventory").update(
        stripe_item_id="", valid_until=timezone.now() + timedelta(days=10)
    )
    stripe_double.answer("subscriptions.retrieve", subscription(items=[PLAN]), subscription(items=[PLAN, INVENTORY]))

    keep(owner, paid)

    keys = [call.options["idempotency_key"] for call in stripe_double.calls_to("subscription_items.create")]
    assert len(keys) == 2 and keys[0] != keys[1]


def test_a_keep_stripe_does_not_show_back_is_an_error(shop, owner, inventory, stripe_double):
    paid = pay(shop, modules=["inventory"])
    SubscriptionItem.objects.filter(module_slug="inventory").update(
        stripe_item_id="", valid_until=timezone.now() + timedelta(days=10)
    )
    stripe_double.answer("subscriptions.retrieve", subscription(items=[PLAN]))
    stripe_double.answer("subscription_items.create", INVENTORY)

    refused("billing.not_confirmed", lambda: keep(owner, paid))

    assert bought(shop).valid_until is not None
