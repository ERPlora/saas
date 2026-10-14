"""A cheaper plan, or annual → monthly, starts with the next period (review of L3-C; decision of the lot).

Charging a downgrade now credits the unused part of the dearer plan: a Stripe invoice with a NEGATIVE total,
which a Spanish invoice cannot be (it would need a rectifying one for every downgrade). Like cancelling to
Free (PLAN-SAAS §3.3), a downgrade waits for the end of the paid period: Stripe holds it as a subscription
schedule whose current phase ends with the period and whose next one bills the new items without proration.
The business keeps what it paid for until then; the panel says «Starter from …». An upgrade stays immediate.

- the preview of a downgrade charges nothing now and says when the new price starts;
- keeping the plan undoes a pending downgrade (the schedule is released); cancelling releases it first (Free
  wins); a module bought or cancelled meanwhile waits until the downgrade is undone (the next phase would
  drop it); an upgrade releases it and is charged now;
- once Stripe applies it, the pending change is forgotten.
"""

import pytest
from django.test import Client
from django.utils import timezone
from live.errors import OperationError

from billing import services
from billing.models import PlanChangeSchedule
from billing.schemas import CheckoutConfirmIn, CheckoutStartIn, HubIn, ModuleIn, PlanChangeIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import MONTH_END, event, item, schedule, signed, subscription
from hubs.models import Subscription

pytestmark = pytest.mark.django_db

PRORATION = int(timezone.now().timestamp())


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscription_schedules.create", schedule())
    stripe_double.answer("subscription_schedules.update", schedule())
    stripe_double.answer("subscription_schedules.release", schedule(status="released"))
    return stripe_double


def on(shop, stripe_double, plan="standard", interval="month", modules=(), **live):
    paid = pay(shop, plan=plan, interval=interval, modules=modules)
    lines = [item("si_plan", f"price_{plan}_{interval}", interval=interval)] + [
        item(f"si_{slug}", f"price_{slug}_{interval}", interval=interval) for slug in modules
    ]
    stripe_double.answer("subscriptions.retrieve", subscription(items=lines, **live))
    return paid


def change(user, hub, plan="starter", interval="month"):
    return services.plan_change(
        ctx_for(user), PlanChangeIn(hub_id=hub.id, plan=plan, interval=interval, proration_date=PRORATION)
    ).model_dump(mode="json")


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()


class TestADowngradeWaits:
    def test_a_cheaper_plan_starts_with_the_next_period(self, shop, owner, stripe_double):
        paid = on(shop, stripe_double)

        answer = change(owner, paid)

        assert stripe_double.calls_to("subscriptions.update") == []
        assert stripe_double.last("subscription_schedules.create").params == {"from_subscription": "sub_1"}
        sent = stripe_double.last("subscription_schedules.update")
        assert sent.args == ("sub_sched_1",)
        current, following = sent.params["phases"]
        assert sent.params["end_behavior"] == "release"
        assert (current["end_date"], current["proration_behavior"]) == (MONTH_END, "none")
        assert [line["price"] for line in current["items"]] == ["price_standard_month"]
        assert [line["price"] for line in following["items"]] == ["price_starter_month"]
        assert following["items"][0]["tax_rates"] == [stripe_double.tax_rates[0]["id"]]
        assert (following["proration_behavior"], following["duration"]) == (
            "none", {"interval": "month", "interval_count": 1},
        )
        # It keeps what it paid for until then.
        assert Subscription.objects.get(hub=paid).plan.slug == "standard"
        assert answer["plan"] == "standard"
        assert answer["scheduled_change"]["plan"] == "starter"
        assert answer["scheduled_change"]["starts_at"].startswith(
            timezone.datetime.fromtimestamp(MONTH_END, tz=timezone.UTC).date().isoformat()
        )

    def test_annual_to_monthly_waits_too_and_moves_every_module(self, shop, owner, inventory, stripe_double):
        paid = on(shop, stripe_double, plan="starter", interval="year", modules=["inventory"])

        change(owner, paid, plan="starter", interval="month")

        following = stripe_double.last("subscription_schedules.update").params["phases"][1]
        assert [line["price"] for line in following["items"]] == ["price_starter_month", "price_inventory_month"]
        assert following["duration"] == {"interval": "month", "interval_count": 1}
        assert stripe_double.calls_to("subscriptions.update") == []

    def test_its_preview_charges_nothing_now(self, shop, owner, stripe_double):
        paid = on(shop, stripe_double)

        answer = services.checkout_start(
            ctx_for(owner), CheckoutStartIn(hub_id=paid.id, plan="starter", interval="month")
        ).model_dump()

        assert answer["flow"] == "confirm"
        assert (answer["preview"]["amount_due_cents"], answer["preview"]["charge_starts_at"]) == (0, MONTH_END)
        assert stripe_double.calls_to("invoices.create_preview") == []

    def test_an_upgrade_is_still_charged_now(self, shop, owner, stripe_double):
        paid = on(shop, stripe_double, plan="starter")
        stripe_double.answer("subscriptions.update", subscription(items=[item("si_plan", "price_standard_month")]))

        change(owner, paid, plan="standard")

        assert stripe_double.last("subscriptions.update").params["proration_behavior"] == "always_invoice"
        assert stripe_double.calls_to("subscription_schedules.create") == []


class TestWhilePending:
    def pending(self, shop, owner, stripe_double, **live):
        paid = on(shop, stripe_double, **live)
        change(owner, paid)
        stripe_double.answer(
            "subscriptions.retrieve",
            {**subscription(items=[item("si_plan", "price_standard_month")]), "schedule": "sub_sched_1"},
        )
        return paid

    def test_keeping_the_plan_undoes_it(self, shop, owner, stripe_double):
        paid = self.pending(shop, owner, stripe_double)

        answer = services.plan_keep(ctx_for(owner), HubIn(hub_id=paid.id)).model_dump()

        assert stripe_double.last("subscription_schedules.release").args == ("sub_sched_1",)
        assert answer["scheduled_change"] is None
        assert not PlanChangeSchedule.objects.exists()

    def test_cancelling_releases_it_first_and_free_wins(self, shop, owner, stripe_double):
        paid = self.pending(shop, owner, stripe_double)
        stripe_double.answer("subscriptions.update", subscription(cancel_at_period_end=True))

        services.plan_cancel(ctx_for(owner), HubIn(hub_id=paid.id))

        paths = stripe_double.paths()
        assert paths.index("subscription_schedules.release") < paths.index("subscriptions.update")
        assert not PlanChangeSchedule.objects.exists()

    def test_a_module_waits_until_it_is_undone(self, shop, owner, inventory, stripe_double):
        paid = self.pending(shop, owner, stripe_double)

        refused(
            "billing.plan_change_pending",
            lambda: services.checkout_confirm(
                ctx_for(owner), CheckoutConfirmIn(hub_id=paid.id, module="inventory", proration_date=PRORATION)
            ),
        )

    def test_cancelling_a_module_waits_too(self, shop, owner, inventory, stripe_double):
        paid = self.pending(shop, owner, stripe_double, modules=["inventory"])

        refused(
            "billing.plan_change_pending",
            lambda: services.module_cancel(ctx_for(owner), ModuleIn(hub_id=paid.id, module="inventory")),
        )

    def test_an_upgrade_releases_it_and_is_charged_now(self, shop, owner, stripe_double):
        paid = self.pending(shop, owner, stripe_double)
        stripe_double.answer("subscriptions.update", subscription(items=[item("si_plan", "price_pro_month")]))

        change(owner, paid, plan="pro")

        paths = stripe_double.paths()
        assert paths.index("subscription_schedules.release") < paths.index("subscriptions.update")
        assert not PlanChangeSchedule.objects.exists()

    def test_another_downgrade_replaces_it(self, shop, owner, stripe_double):
        paid = on(shop, stripe_double, plan="pro")
        change(owner, paid, plan="standard")
        stripe_double.answer(
            "subscriptions.retrieve",
            {**subscription(items=[item("si_plan", "price_pro_month")]), "schedule": "sub_sched_1"},
        )

        change(owner, paid, plan="starter")

        assert stripe_double.last("subscription_schedules.release").args == ("sub_sched_1",)
        assert PlanChangeSchedule.objects.get().plan_slug == "starter"

    def test_once_stripe_applies_it_it_is_forgotten(self, shop, owner, stripe_double):
        paid = self.pending(shop, owner, stripe_double)
        applied = {**subscription(items=[item("si_plan", "price_starter_month")]), "schedule": "sub_sched_1"}
        stripe_double.answer("subscriptions.retrieve", applied)
        body, header = signed(event("customer.subscription.updated", applied))

        Client().post("/webhooks/stripe/", body, content_type="application/json", HTTP_STRIPE_SIGNATURE=header,
                      HTTP_HOST="localhost:8001")

        assert Subscription.objects.get(hub=paid).plan.slug == "starter"
        assert not PlanChangeSchedule.objects.exists()

    def test_the_subscriptions_tab_says_it(self, shop, owner, stripe_double):
        from billing import queries
        from billing.schemas import SubscriptionListIn

        self.pending(shop, owner, stripe_double)

        [row] = queries.subscription_list(ctx_for(owner), SubscriptionListIn()).model_dump(mode="json")["rows"]

        assert (row["scheduled_change"]["plan"], row["scheduled_change"]["interval"]) == ("starter", "month")
