"""A checkout the previous owner left open when the business changed hands (review of saas#89, HUBS-F28).

Found by the review with a probe: the owner opens the Embedded Checkout of a plan, hands the business over, and the
payment still completes afterwards; the webhook applied it, so the business was charged to somebody who no longer
owns it and cannot cancel it. The market's way (Stripe Checkout, Shopify, Square, Odoo; round proposed in
APP-HUBS-3):

- accepting the hand-over expires the business's open Checkout Sessions (Stripe's ``expire``, after the COMMIT):
  nobody can pay them any more. One Stripe cannot expire (paid meanwhile, or Stripe away) never undoes nor blocks
  the hand-over: it is logged as an error and the webhook below decides;
- a ``checkout.session.completed`` of somebody who is no longer the owner is not applied: its subscription ends now,
  what it charged is refunded in full (Stripe's «Cancel + refund»; the refund becomes a rectifying invoice through
  ``charge.refunded``), the attempt says ``refunded`` (its audit trail keeps who and when) and the payer is told by
  mail. Once, whatever the redeliveries; Stripe away raises, so Stripe delivers it again.

Stripe is the double at its boundary (``billing.tests.stripe_double``); the operations of hubs and billing are the
real ones.
"""

import pytest
from django.core import mail

from billing import services
from billing.models import CheckoutAttempt
from billing.schemas import CheckoutStartIn, HubIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import (
    checkout_session,
    connection_error,
    invalid_request,
    invoice_payment,
    item,
    listing,
    subscription,
)
from hubs import services as hub_services
from hubs.models import Hub, HubMember, Subscription
from hubs.schemas import BillingProfileIn, ByIdIn, OwnershipTransferIn
from hubs.tests.conftest import add_member
from hubs.tests.conftest import ctx_for as hub_ctx

pytestmark = pytest.mark.django_db

PAID_CENTS = 3629


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


@pytest.fixture
def heir(make_user):
    return make_user("heir@example.com", first_name="Hugo", language="es")


def hand_over(hub, owner, heir):
    """The owner offers the business to ``heir`` (an admin of it) and ``heir`` accepts, as the panel does."""
    if not HubMember.objects.filter(hub=hub, user=heir).exists():
        add_member(hub, heir, HubMember.Role.ADMIN)
    member = HubMember.objects.get(hub=hub, user=heir)
    offer = hub_services.ownership_transfer(hub_ctx(owner), OwnershipTransferIn(hub_id=hub.id, member_id=member.id))
    return hub_services.ownership_accept(hub_ctx(heir), ByIdIn(id=offer.id))


def opened_by(user, hub):
    """``user`` opens the Embedded Checkout of Starter for ``hub``: its attempt."""
    services.checkout_start(ctx_for(user), CheckoutStartIn(hub_id=hub.id, plan="starter"))
    return CheckoutAttempt.objects.filter(hub=hub, owner=user).latest("created_at")


def completed(attempt, stripe_double, *, new="sub_new"):
    """Stripe's ``checkout.session.completed`` of ``attempt``'s session, paid: the session as Stripe sends it."""
    created = next(
        call for call in stripe_double.calls_to("checkout.sessions.create")
        if call.params["metadata"].get("attempt") == str(attempt.id)
    )
    return checkout_session(attempt.stripe_session_id, metadata=created.params["metadata"], subscription_id=new,
                            customer="cus_new")


def stripe_charged(stripe_double, *, new="sub_new", amount=PAID_CENTS):
    """What the completed checkout left in Stripe: a subscription on the payer's card and its first invoice paid."""
    live = {**subscription(new, customer="cus_new", items=[item("si_plan", "price_starter_month")]),
            "latest_invoice": f"in_{new}"}
    stripe_double.answer("subscriptions.retrieve", live)
    stripe_double.answer("subscriptions.cancel", {**live, "status": "canceled"})
    payments = [{**invoice_payment(f"pi_{new}", invoice_id=f"in_{new}"), "status": "paid", "amount_paid": amount}]
    stripe_double.answer("invoice_payments.list", listing(payments if amount else []))
    stripe_double.answer(
        "refunds.create",
        lambda call: {"id": "re_1", "object": "refund", "status": "succeeded", "amount": amount,
                      "payment_intent": call.params["payment_intent"]},
    )


def local(hub):
    return Subscription.objects.select_related("plan").get(hub=hub)


def status(attempt):
    attempt.refresh_from_db()
    return attempt.status


# --- The payment that still arrives ---------------------------------------------------------------------


class TestAPaymentOfSomebodyWhoNoLongerOwnsIt:
    def test_it_is_not_applied_its_subscription_ends_and_the_payment_is_refunded(
        self, shop, owner, heir, stripe_double, django_capture_on_commit_callbacks
    ):
        """The review's probe: start (owner) → hand-over accepted → the checkout completes."""
        attempt = opened_by(owner, shop)
        hand_over(shop, owner, heir)
        stripe_charged(stripe_double)

        with django_capture_on_commit_callbacks(execute=True):
            outcome = services.checkout_completed(completed(attempt, stripe_double))

        assert outcome == "not_owner"
        assert (local(shop).plan.slug, local(shop).stripe_subscription_id) == ("free", "")
        cancelled = stripe_double.last("subscriptions.cancel")
        assert (cancelled.args, cancelled.params) == (("sub_new",), {})
        refund = stripe_double.last("refunds.create")
        assert (refund.params["payment_intent"], refund.params["reason"]) == ("pi_sub_new", "requested_by_customer")
        assert refund.options["idempotency_key"] == f"refund-{attempt.stripe_session_id}-pi_sub_new"
        assert status(attempt) == CheckoutAttempt.Status.REFUNDED

    def test_the_payer_is_told_in_their_language_what_was_refunded_and_why(
        self, shop, owner, heir, stripe_double, django_capture_on_commit_callbacks
    ):
        attempt = opened_by(owner, shop)
        hand_over(shop, owner, heir)
        stripe_charged(stripe_double)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            services.checkout_completed(completed(attempt, stripe_double))

        (message,) = [message for message in mail.outbox if message.to == [owner.email]]
        assert shop.name in message.subject
        assert "36,29 €" in message.body
        assert "/dashboard/billing/invoices" in message.body
        assert message.alternatives, "branded: text and HTML"

    def test_a_redelivery_ends_and_refunds_nothing_twice(self, shop, owner, heir, stripe_double):
        attempt = opened_by(owner, shop)
        hand_over(shop, owner, heir)
        stripe_charged(stripe_double)
        session = completed(attempt, stripe_double)
        services.checkout_completed(session)

        assert services.checkout_completed(session) == "not_owner"

        assert len(stripe_double.calls_to("subscriptions.cancel")) == 1
        assert len(stripe_double.calls_to("refunds.create")) == 1

    def test_one_stripe_already_ended_is_only_refunded(self, shop, owner, heir, stripe_double):
        attempt = opened_by(owner, shop)
        hand_over(shop, owner, heir)
        stripe_charged(stripe_double)
        stripe_double.answer(
            "subscriptions.retrieve",
            {**subscription("sub_new", status="canceled", customer="cus_new"), "latest_invoice": "in_sub_new"},
        )

        assert services.checkout_completed(completed(attempt, stripe_double)) == "not_owner"

        assert stripe_double.calls_to("subscriptions.cancel") == []
        assert len(stripe_double.calls_to("refunds.create")) == 1

    def test_nothing_charged_today_is_only_ended(self, shop, owner, heir, stripe_double):
        attempt = opened_by(owner, shop)
        hand_over(shop, owner, heir)
        stripe_charged(stripe_double, amount=0)

        assert services.checkout_completed(completed(attempt, stripe_double)) == "not_owner"

        assert len(stripe_double.calls_to("subscriptions.cancel")) == 1
        assert stripe_double.calls_to("refunds.create") == []
        assert status(attempt) == CheckoutAttempt.Status.REFUNDED

    def test_with_stripe_away_nothing_is_applied_and_stripe_delivers_it_again(self, shop, owner, heir, stripe_double):
        attempt = opened_by(owner, shop)
        hand_over(shop, owner, heir)
        stripe_charged(stripe_double)
        stripe_double.answer("refunds.create", connection_error())

        with pytest.raises(Exception):  # noqa: B017, PT011 - the webhook answers 500 and Stripe delivers it again
            services.checkout_completed(completed(attempt, stripe_double))

        assert local(shop).stripe_subscription_id == ""
        assert status(attempt) != CheckoutAttempt.Status.REFUNDED

    def test_the_owner_s_own_payment_is_applied_as_always(self, shop, owner, stripe_double):
        attempt = opened_by(owner, shop)
        stripe_charged(stripe_double)

        assert services.checkout_completed(completed(attempt, stripe_double)) == "completed"

        assert (local(shop).plan.slug, local(shop).stripe_subscription_id) == ("starter", "sub_new")
        assert stripe_double.calls_to("refunds.create") == []
        assert status(attempt) == CheckoutAttempt.Status.COMPLETED


class TestAKeptPlanOfSomebodyWhoHandedItOnAgain:
    def test_the_business_stays_on_its_subscription_and_the_new_one_ends(self, shop, owner, heir, make_user,
                                                                         stripe_double):
        """«Keep it with my card» opened by the heir, who hands the business on before paying (the review's second
        probe): the third owner's business stays on the plan it has, nothing moves to the heir's card."""
        paid = pay(shop)
        stripe_double.answer("subscriptions.update", subscription(cancel_at_period_end=True))
        hand_over(paid, owner, heir)
        stripe_double.answer("subscriptions.retrieve", subscription(cancel_at_period_end=True))
        hub_services.billing_profile_update(
            hub_ctx(heir),
            BillingProfileIn(hub_id=paid.id, billing_name="Hugo SL", billing_country="ES", billing_postal_code="28002"),
        )
        services.plan_take_over(ctx_for(heir), HubIn(hub_id=paid.id))
        attempt = CheckoutAttempt.objects.get(hub=paid, kind=CheckoutAttempt.Kind.TAKEOVER)
        third = make_user("third@example.com")
        hand_over(Hub.objects.get(pk=paid.pk), heir, third)
        stripe_charged(stripe_double, new="sub_2", amount=0)

        assert services.checkout_completed(completed(attempt, stripe_double, new="sub_2")) == "not_owner"

        assert local(paid).stripe_subscription_id == "sub_1"
        assert [call.args for call in stripe_double.calls_to("subscriptions.cancel")] == [("sub_2",)]


# --- The hand-over expires what was left open --------------------------------------------------------------


class TestTheHandOverExpiresTheOpenCheckouts:
    def test_accepting_expires_the_previous_owner_s_open_checkout(
        self, shop, owner, heir, stripe_double, django_capture_on_commit_callbacks
    ):
        attempt = opened_by(owner, shop)

        with django_capture_on_commit_callbacks(execute=True):
            hand_over(shop, owner, heir)

        assert [call.args for call in stripe_double.calls_to("checkout.sessions.expire")] == [
            (attempt.stripe_session_id,)
        ]
        assert status(attempt) == CheckoutAttempt.Status.EXPIRED

    def test_it_is_asked_only_after_the_commit(self, shop, owner, heir, stripe_double,
                                               django_capture_on_commit_callbacks):
        opened_by(owner, shop)

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            hand_over(shop, owner, heir)

        assert stripe_double.calls_to("checkout.sessions.expire") == []
        assert callbacks

    def test_stripe_away_neither_undoes_nor_blocks_the_hand_over_and_says_so(
        self, shop, owner, heir, stripe_double, django_capture_on_commit_callbacks, caplog
    ):
        attempt = opened_by(owner, shop)
        stripe_double.answer("checkout.sessions.expire", connection_error())

        with caplog.at_level("ERROR", logger="billing.services"):
            with django_capture_on_commit_callbacks(execute=True):
                hand_over(shop, owner, heir)

        assert HubMember.objects.get(hub=shop, user=heir).role == HubMember.Role.OWNER
        assert status(attempt) == CheckoutAttempt.Status.OPEN
        assert [record.event for record in caplog.records if hasattr(record, "event")] == [
            "billing.checkout_not_expired"
        ]

    def test_one_stripe_cannot_expire_does_not_stop_the_next_one(self, shop, owner, stripe_double):
        """It runs after the COMMIT and never raises: each open session is asked, whatever the one before did."""
        first = opened_by(owner, shop)
        CheckoutAttempt.objects.filter(pk=first.pk).update(created_at=first.created_at.replace(year=2025))
        second = CheckoutAttempt.objects.create(
            hub=shop, owner=owner, kind=CheckoutAttempt.Kind.MODULE, module_slug="inventory", selection="module",
            stripe_session_id="cs_test_module",
        )
        stripe_double.answer(
            "checkout.sessions.expire", connection_error(), {"id": "cs_test_module", "status": "expired"}
        )

        services.expire_open_checkouts(shop.id)

        assert (status(second), status(first)) == (CheckoutAttempt.Status.OPEN, CheckoutAttempt.Status.EXPIRED)

    def test_one_paid_meanwhile_is_left_to_the_webhook(
        self, shop, owner, heir, stripe_double, django_capture_on_commit_callbacks
    ):
        attempt = opened_by(owner, shop)
        stripe_double.answer(
            "checkout.sessions.expire",
            invalid_request(code="checkout_session_not_open", message="This Checkout Session is not open."),
        )

        with django_capture_on_commit_callbacks(execute=True):
            hand_over(shop, owner, heir)

        assert status(attempt) == CheckoutAttempt.Status.OPEN
        stripe_charged(stripe_double)
        assert services.checkout_completed(completed(attempt, stripe_double)) == "not_owner"


class TestARedeliveryOfAPaymentAppliedBeforeTheHandOver:
    def test_it_changes_nothing_and_the_business_keeps_what_it_paid(
        self, shop, owner, heir, stripe_double, django_capture_on_commit_callbacks
    ):
        """The owner paid and the payment was applied; then the business changed hands and Stripe delivers the
        same ``checkout.session.completed`` again (a lost 200, a resend from the Dashboard): a payment applied
        while its payer owned the business is not ended nor refunded, the business keeps the period it paid."""
        attempt = opened_by(owner, shop)
        stripe_charged(stripe_double)
        session = completed(attempt, stripe_double)
        assert services.checkout_completed(session) == "completed"
        paying = {**subscription("sub_new", customer="cus_new", items=[item("si_plan", "price_starter_month")],
                                 cancel_at_period_end=True), "latest_invoice": "in_sub_new"}
        stripe_double.answer("subscriptions.update", paying)
        with django_capture_on_commit_callbacks(execute=True):
            hand_over(shop, owner, heir)

        assert services.checkout_completed(session) == "completed"

        assert (local(shop).plan.slug, local(shop).stripe_subscription_id) == ("starter", "sub_new")
        assert stripe_double.calls_to("subscriptions.cancel") == []
        assert stripe_double.calls_to("refunds.create") == []
        assert status(attempt) == CheckoutAttempt.Status.COMPLETED
