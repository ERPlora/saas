"""ERPlora's own business has no plan, so nothing is bought, changed, charged or cancelled for it, and no sweep asks
Stripe about it: each door of billing is refused with ``hubs.platform_business`` and Stripe hears nothing."""

import pytest
from django.test import Client
from live.errors import Conflict, NotFound, PermissionDenied

from billing.models import CheckoutAttempt, Invoice
from billing.queries import invoices as invoice_queries
from billing.queries.paying_customers import paying_customers
from billing.queries import subscriptions as subscription_queries
from billing.schemas.checkout import CheckoutConfirmIn, CheckoutStartIn
from billing.schemas.common import HubIn
from billing.schemas.invoices import InvoiceListIn
from billing.schemas.payment_methods import PaymentMethodIn
from billing.schemas.stripe_pages import PortalOpenIn
from billing.schemas.subscription_changes import ModuleIn, PlanChangeIn
from billing.schemas.subscriptions import SubscriptionListIn
from billing.services import (
    checkouts,
    hand_overs,
    module_cancellations,
    plan_changes,
    staff_test_clocks,
    stripe_pages,
    subscription_drift,
    unpaid_sweep,
)
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import checkout_session, event, listing, signed, subscription
from hubs.models import Hub, HubMember, Subscription
from hubs.tests.conftest import add_member, create_platform_business, platform_hub_in

pytestmark = pytest.mark.django_db

DOORS = {
    "start a checkout of a plan": (checkouts.checkout_start, lambda hub: CheckoutStartIn(hub_id=hub.id, plan="starter")),
    "start a checkout of a module": (
        checkouts.checkout_start,
        lambda hub: CheckoutStartIn(hub_id=hub.id, module="inventory"),
    ),
    "confirm a module": (
        plan_changes.checkout_confirm,
        lambda hub: CheckoutConfirmIn(hub_id=hub.id, module="inventory", proration_date=1),
    ),
    "change its plan": (
        plan_changes.plan_change,
        lambda hub: PlanChangeIn(hub_id=hub.id, plan="starter", proration_date=1),
    ),
    "cancel its plan": (plan_changes.plan_cancel, lambda hub: HubIn(hub_id=hub.id)),
    "see what cancelling would do": (subscription_queries.plan_cancel_preview, lambda hub: HubIn(hub_id=hub.id)),
    "keep its plan": (plan_changes.plan_keep, lambda hub: HubIn(hub_id=hub.id)),
    "take its plan over": (hand_overs.plan_take_over, lambda hub: HubIn(hub_id=hub.id)),
    "cancel a module": (module_cancellations.module_cancel, lambda hub: ModuleIn(hub_id=hub.id, module="inventory")),
    "keep a module": (module_cancellations.module_keep, lambda hub: ModuleIn(hub_id=hub.id, module="inventory")),
    "open the payer's portal": (stripe_pages.portal_open, lambda hub: PortalOpenIn(hub_id=hub.id)),
}


@pytest.fixture
def founder(make_user):
    return make_user("founder@example.com", language="es")


@pytest.fixture
def platform_business(hub_double, founder, plans):  # noqa: F811
    return create_platform_business(platform_hub_in(hub_double), founder)


def deliver(payload):
    body, header = signed(payload)
    return Client(enforce_csrf_checks=True).post(
        "/webhooks/stripe/",
        body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
        HTTP_HOST="localhost:8001",
    )


class TestTheDoors:
    @pytest.mark.parametrize("door", DOORS)
    def test_its_owner_is_refused_and_stripe_hears_nothing(self, platform_business, founder, stripe_double, door):
        operation, data = DOORS[door]

        with pytest.raises(Conflict) as caught:
            operation(ctx_for(founder), data(platform_business))

        assert caught.value.code == "hubs.platform_business"
        assert stripe_double.calls == []
        assert not CheckoutAttempt.objects.exists()
        assert not Subscription.objects.filter(hub=platform_business).exists()

    @pytest.mark.parametrize("door", DOORS)
    def test_the_refusal_comes_after_the_role(self, platform_business, make_user, stripe_double, door):
        admin, stranger = make_user("ana@example.com"), make_user("stranger@example.com")
        add_member(platform_business, admin, HubMember.Role.ADMIN)
        operation, data = DOORS[door]

        with pytest.raises(PermissionDenied):
            operation(ctx_for(admin), data(platform_business))
        with pytest.raises(NotFound):
            operation(ctx_for(stranger), data(platform_business))


class TestWhatStripeSends:
    """An event that names it (nobody made such a payment): it names no business of ours, nothing is written and
    Stripe does not send it again."""

    def events_of(self, hub):
        named = {"hub_id": str(hub.id), "kind": "plan"}
        live = subscription(metadata=named, items=[])
        return [
            event("checkout.session.completed", checkout_session(metadata=named)),
            event("customer.subscription.created", live),
            event("customer.subscription.updated", live),
        ]

    def test_nothing_is_written_and_it_is_answered(self, platform_business, stripe_double, issuer_identity):
        before = Hub.objects.filter(pk=platform_business.pk).values().get()

        for payload in self.events_of(platform_business):
            assert deliver(payload).status_code == 200, payload["type"]

        assert Hub.objects.filter(pk=platform_business.pk).values().get() == before
        assert not Subscription.objects.filter(hub=platform_business).exists()
        assert not Invoice.objects.exists()


class TestTheSweeps:
    def test_none_touches_it_nor_asks_stripe(self, platform_business, stripe_double):
        before = Hub.objects.filter(pk=platform_business.pk).values().get()

        counts = unpaid_sweep.sweep_unpaid()
        drift = subscription_drift.sync_subscriptions()

        assert not any(counts.values())
        assert not any(drift.values())
        assert stripe_double.calls == []
        assert Hub.objects.filter(pk=platform_business.pk).values().get() == before

    def test_the_sweep_still_works_on_a_business_that_owes(self, platform_business, shop, stripe_double):
        pay(shop, status="past_due", unpaid_reason="payment_failed")
        stripe_double.answer("invoices.list", listing([]))

        assert unpaid_sweep.sweep_unpaid()["checked"] == 1


class TestWhatItsOwnerReads:
    def test_no_subscription_no_card_and_no_invoice(self, platform_business, founder, stripe_double):
        ctx = ctx_for(founder)

        assert subscription_queries.subscription_list(ctx, SubscriptionListIn()).rows == []
        assert subscription_queries.payment_method_get(ctx, PaymentMethodIn()).methods == []
        assert invoice_queries.invoice_list(ctx, InvoiceListIn()).rows == []
        assert stripe_double.calls == []

    def test_the_income_of_erplora_does_not_count_it(self, platform_business):
        assert not paying_customers().exists()


class TestItsTestClock:
    @pytest.mark.parametrize("action", ["attach_test_clock", "advance_test_clock_of"])
    def test_it_takes_none(self, platform_business, stripe_double, action):
        with pytest.raises(staff_test_clocks.TestClockRefused):
            getattr(staff_test_clocks, action)(platform_business.id)

        assert stripe_double.calls == []
