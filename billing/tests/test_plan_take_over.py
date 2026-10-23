"""A business handed over with a paid plan (HUBS-F28, «mover el pagador»): who pays from the hand-over.

The market's way (Wix, Shopify, Lightspeed, Squarespace, Fresha; round proposed in APP-HUBS-3): the plan is the
business's and goes with it; the payment method does not. So:

- accepting the hand-over stops the renewal on the previous payer's card (Stripe ``cancel_at_period_end``): the
  business keeps its plan until the end of the period already paid, and the previous payer is never charged again;
- the new owner keeps it with their own card («Keep it with my card», ``billing.plan.take_over``): their details,
  then an Embedded Checkout of the same plan and modules whose billing starts on the date the paid period ends
  (``billing_cycle_anchor``, no proration), so nothing is charged today and nobody pays twice;
- once that checkout completes (the webhook), the business moves to the new subscription and the previous one ends
  at once, without a refund (its period is the one the business is using);
- without it, the plan ends on that date and the business goes back to Free, as any cancelled plan.

Stripe is the double at its boundary (``billing.tests.stripe_double``); the operations of hubs and billing are the
real ones.
"""

import pytest
from django.core import mail
from django.utils import timezone, translation
from django.utils.formats import date_format
from live.errors import NotFound, OperationError, PermissionDenied

from billing import queries, services
from billing.models import CheckoutAttempt
from billing.schemas import HubIn, SubscriptionListIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import (
    MONTH_END,
    checkout_session,
    connection_error,
    item,
    subscription,
)
from hubs import services as hub_services
from hubs.models import Hub, HubMember, HubOwnershipTransfer, Subscription
from hubs.schemas import BillingProfileIn, ByIdIn, OwnershipTransferIn
from hubs.tests.conftest import add_member
from hubs.tests.conftest import ctx_for as hub_ctx

pytestmark = pytest.mark.django_db


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


def says_who_pays(heir, hub, name="Hugo SL"):
    hub_services.billing_profile_update(
        hub_ctx(heir),
        BillingProfileIn(hub_id=hub.id, billing_name=name, billing_country="ES", billing_postal_code="28002"),
    )
    return Hub.objects.select_related("billing_profile").get(pk=hub.pk)


def day(moment, language):
    with translation.override(language):
        return date_format(timezone.localtime(moment), "DATE_FORMAT")


def take_over(user, hub):
    return services.plan_take_over(ctx_for(user), HubIn(hub_id=hub.id)).model_dump()


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()
    return error.value


def local(hub):
    return Subscription.objects.get(hub=hub)


def role(hub, user):
    return HubMember.objects.get(hub=hub, user=user).role


def lines(*modules):
    return [item("si_plan", "price_starter_month")] + [item(f"si_{slug}", f"price_{slug}_month") for slug in modules]


def on_starter(shop, stripe_double, *modules):
    """The business on Starter (and ``modules``), charged to its owner's card (``cus_1``)."""
    paid = pay(shop, modules=modules)
    stripe_double.answer("subscriptions.update", subscription(items=lines(*modules), cancel_at_period_end=True))
    return paid


def handed_over(shop, owner, heir, stripe_double, *modules):
    """On Starter, handed over to ``heir``, who said who pays: what «Keep it with my card» starts from."""
    paid = on_starter(shop, stripe_double, *modules)
    hand_over(paid, owner, heir)
    stripe_double.answer("subscriptions.retrieve", subscription(items=lines(*modules), cancel_at_period_end=True))
    return says_who_pays(heir, paid)


def rows(user, hub):
    return queries.subscription_list(ctx_for(user), SubscriptionListIn(hub_id=hub.id)).model_dump()["rows"]


# --- The hand-over ------------------------------------------------------------------------------------


class TestTheHandOverStopsThePreviousPayersRenewal:
    def test_accepting_ends_the_plan_on_the_previous_payers_card_with_its_period(self, shop, owner, heir,
                                                                                  stripe_double):
        paid = on_starter(shop, stripe_double)

        hand_over(paid, owner, heir)

        update = stripe_double.last("subscriptions.update")
        assert (update.args, update.params) == (("sub_1",), {"cancel_at_period_end": True})
        assert local(paid).cancel_at_period_end is True
        assert (role(paid, heir), role(paid, owner)) == (HubMember.Role.OWNER, HubMember.Role.ADMIN)

    def test_a_business_on_free_changes_hands_without_stripe(self, shop, owner, heir, stripe_double):
        hand_over(shop, owner, heir)

        assert stripe_double.calls == []
        assert role(shop, heir) == HubMember.Role.OWNER

    def test_a_plan_the_new_owner_already_pays_keeps_renewing(self, shop, owner, heir, stripe_double):
        paid = pay(shop)
        add_member(paid, heir, HubMember.Role.ADMIN)
        paid.billing_profile.owner = heir
        paid.billing_profile.save()

        hand_over(paid, owner, heir)

        assert stripe_double.calls == []
        assert local(paid).cancel_at_period_end is False

    def test_a_plan_already_ending_is_left_as_it_is(self, shop, owner, heir, stripe_double):
        paid = pay(shop, cancel_at_period_end=True)

        hand_over(paid, owner, heir)

        assert stripe_double.calls_to("subscriptions.update") == []
        assert role(paid, heir) == HubMember.Role.OWNER

    def test_with_stripe_away_the_business_does_not_change_hands(self, shop, owner, heir, stripe_double):
        paid = pay(shop)
        stripe_double.answer("subscriptions.update", connection_error())

        refused("billing.stripe_unavailable", lambda: hand_over(paid, owner, heir))

        assert role(paid, owner) == HubMember.Role.OWNER
        assert HubOwnershipTransfer.objects.get().status == HubOwnershipTransfer.Status.PENDING
        assert local(paid).cancel_at_period_end is False


    def test_the_new_owners_details_do_not_retax_the_plan_on_the_previous_payers_card(self, shop, owner, heir,
                                                                                       stripe_double):
        """The tax of a plan is its payer's: the details the new owner saves are not charged on another's card."""
        paid = handed_over(shop, owner, heir, stripe_double)
        asked = len(stripe_double.calls)

        assert services.retax_subscription(paid) == "skipped"

        assert len(stripe_double.calls) == asked


class TestTheMailsOfTheHandOver:
    """The offer says until when the plan is paid and where the new owner keeps it; the acceptance tells the
    previous payer that their card no longer renews it (``hubs.emails``, after the COMMIT)."""

    def mails(self, captured, shop, owner, heir):
        with captured(execute=True):
            hand_over(shop, owner, heir)
        offer = next(message for message in mail.outbox if message.to == [heir.email])
        accepted = next(message for message in mail.outbox if message.to == [owner.email])
        return offer, accepted

    def test_a_paid_business_says_until_when_it_is_paid(self, shop, owner, heir, stripe_double,
                                                        django_capture_on_commit_callbacks):
        paid = on_starter(shop, stripe_double)
        until = local(paid).current_period_end

        offer, accepted = self.mails(django_capture_on_commit_callbacks, paid, owner, heir)

        assert day(until, heir.language) in offer.body
        assert "/billing/subscriptions" in offer.body
        assert day(local(paid).current_period_end, owner.language) in accepted.body

    def test_a_business_on_free_says_nothing_of_a_plan(self, shop, owner, heir, stripe_double,
                                                       django_capture_on_commit_callbacks):
        offer, accepted = self.mails(django_capture_on_commit_callbacks, shop, owner, heir)

        assert "/billing" not in offer.body
        assert "/billing" not in accepted.body


# --- «Keep it with my card» ---------------------------------------------------------------------------


class TestTheNewOwnerKeepsThePlan:
    def test_it_opens_a_checkout_of_the_same_plan_billed_from_the_end_of_the_paid_period(self, shop, owner, heir,
                                                                                          stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)

        answer = take_over(heir, paid)

        params = stripe_double.last("checkout.sessions.create").params
        assert answer["flow"] == "checkout"
        assert answer["client_secret"].startswith("cs_test_")
        assert params["mode"] == "subscription"
        assert params["customer"] == "cus_new"
        assert stripe_double.last("customers.create").params["name"] == "Hugo SL"
        assert [(line["price"], line["quantity"]) for line in params["line_items"]] == [("price_starter_month", 1)]
        assert all(line["tax_rates"] for line in params["line_items"])
        assert params["subscription_data"]["billing_cycle_anchor"] == MONTH_END
        assert params["subscription_data"]["proration_behavior"] == "none"
        assert params["metadata"]["kind"] == "plan_takeover"
        assert params["metadata"]["replaces"] == "sub_1"
        assert params["metadata"]["hub_id"] == str(paid.id)
        attempt = CheckoutAttempt.objects.get()
        assert (attempt.kind, attempt.owner_id) == (CheckoutAttempt.Kind.TAKEOVER, heir.pk)

    def test_opening_it_leaves_the_plan_on_the_previous_card_until_it_completes(self, shop, owner, heir,
                                                                               stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)

        take_over(heir, paid)

        assert local(paid).stripe_customer_id == "cus_1"
        assert Hub.objects.get(pk=paid.pk).billing_profile.stripe_customer_id == "cus_new"
        (row,) = rows(heir, paid)
        assert row["actions"][0] == "take_over"

    def test_its_modules_go_with_it(self, shop, owner, heir, inventory, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double, "inventory")

        take_over(heir, paid)

        params = stripe_double.last("checkout.sessions.create").params
        assert [line["price"] for line in params["line_items"]] == ["price_starter_month", "price_inventory_month"]

    def test_the_same_request_again_reuses_its_open_checkout(self, shop, owner, heir, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)

        first = take_over(heir, paid)
        again = take_over(heir, paid)

        assert again["client_secret"] == first["client_secret"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 1

    def test_the_new_owner_says_who_pays_first(self, shop, owner, heir, stripe_double):
        paid = on_starter(shop, stripe_double)
        hand_over(paid, owner, heir)
        before = len(stripe_double.calls)

        refused("billing.payer_required", lambda: take_over(heir, paid))

        assert len(stripe_double.calls) == before

    def test_a_business_on_free_has_nothing_to_keep(self, shop, owner, heir, stripe_double):
        hand_over(shop, owner, heir)
        says_who_pays(heir, shop)

        refused("billing.nothing_to_take_over", lambda: take_over(heir, shop))

    def test_a_plan_already_on_the_owners_card_has_nothing_to_keep(self, shop, owner, stripe_double):
        paid = pay(shop)

        refused("billing.nothing_to_take_over", lambda: take_over(owner, paid))

        assert stripe_double.calls == []

    def test_only_the_owner_keeps_it(self, shop, owner, heir, make_user, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        stranger = make_user("stranger@example.com")

        with pytest.raises(PermissionDenied):
            take_over(owner, paid)
        with pytest.raises(NotFound):
            take_over(stranger, paid)

    def test_an_unpaid_business_pays_its_invoice_first(self, shop, owner, heir, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        Subscription.objects.filter(hub=paid).update(status="past_due")

        refused("billing.invoice_unpaid", lambda: take_over(heir, paid))


# --- The checkout completes ---------------------------------------------------------------------------


def completed_takeover(hub, *, new="sub_2"):
    opened = CheckoutAttempt.objects.filter(hub=hub, kind=CheckoutAttempt.Kind.TAKEOVER).first()
    return checkout_session(
        opened.stripe_session_id if opened else "cs_test_takeover",
        metadata={"kind": "plan_takeover", "hub_id": str(hub.id), "replaces": "sub_1"},
        subscription_id=new,
        customer="cus_new",
        payment_status="no_payment_required",
    )


def stripe_holds(stripe_double, *, old_status="active"):
    """Stripe's two subscriptions: the new one on the new owner's card, the previous one still running."""
    held = {
        "sub_2": subscription("sub_2", customer="cus_new", items=lines()),
        "sub_1": subscription("sub_1", status=old_status, items=lines(), cancel_at_period_end=True),
    }
    stripe_double.answer("subscriptions.retrieve", lambda call: held[call.args[0]])
    stripe_double.answer("subscriptions.cancel", lambda call: {**held[call.args[0]], "status": "canceled"})


class TestTheTakeOverCompletes:
    def test_the_business_moves_to_the_new_card_and_the_previous_subscription_ends_without_refund(
        self, shop, owner, heir, stripe_double
    ):
        paid = handed_over(shop, owner, heir, stripe_double)
        take_over(heir, paid)
        stripe_holds(stripe_double)

        assert services.checkout_completed(completed_takeover(paid)) == "completed"

        moved = local(paid)
        assert (moved.stripe_subscription_id, moved.stripe_customer_id) == ("sub_2", "cus_new")
        assert moved.cancel_at_period_end is False
        assert moved.plan.slug == "starter"
        cancel = stripe_double.last("subscriptions.cancel")
        assert (cancel.args, cancel.params) == (("sub_1",), {})
        assert CheckoutAttempt.objects.get().status == CheckoutAttempt.Status.COMPLETED

    def test_a_redelivery_ends_nothing_twice(self, shop, owner, heir, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        stripe_holds(stripe_double)
        services.checkout_completed(completed_takeover(paid))
        stripe_holds(stripe_double, old_status="canceled")
        asked = len(stripe_double.calls)

        assert services.checkout_completed(completed_takeover(paid)) == "completed"

        assert len(stripe_double.calls_to("subscriptions.cancel")) == 1
        assert len(stripe_double.calls) == asked, "a business already moved asks Stripe nothing"
        assert local(paid).stripe_subscription_id == "sub_2"

    def test_a_previous_subscription_stripe_ended_already_is_not_ended_again(self, shop, owner, heir,
                                                                             stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        stripe_holds(stripe_double, old_status="canceled")

        services.checkout_completed(completed_takeover(paid))

        assert stripe_double.calls_to("subscriptions.cancel") == []
        assert local(paid).stripe_subscription_id == "sub_2"

    def test_with_stripe_away_nothing_moves_and_stripe_retries(self, shop, owner, heir, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        stripe_holds(stripe_double)
        stripe_double.answer("subscriptions.cancel", connection_error())

        with pytest.raises(Exception):  # noqa: B017, PT011 - the webhook answers 500 and Stripe delivers it again
            services.checkout_completed(completed_takeover(paid))

        assert local(paid).stripe_subscription_id == "sub_1"

    def test_the_end_of_the_previous_subscription_leaves_the_plan_alone(self, shop, owner, heir, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        stripe_holds(stripe_double)
        services.checkout_completed(completed_takeover(paid))

        assert services.subscription_deleted({"id": "sub_1"}) == "unknown"

        assert local(paid).plan.slug == "starter"


# --- What Billing shows -------------------------------------------------------------------------------


class TestTheRow:
    def test_the_new_owner_is_offered_to_keep_it_until_the_paid_period_ends(self, shop, owner, heir,
                                                                            stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)

        (row,) = rows(heir, paid)

        assert row["actions"] == ["take_over", "view_invoices"]
        assert row["paid_by_another_account"] is True
        assert row["cancelling"] is True
        assert row["can"]["take_over"] is True
        assert row["can"]["change_plan"] is False

    def test_before_saying_who_pays_it_is_offered_too(self, shop, owner, heir, stripe_double):
        paid = on_starter(shop, stripe_double)
        hand_over(paid, owner, heir)

        (row,) = rows(heir, paid)

        assert row["actions"][0] == "take_over"

    def test_the_owner_who_pays_is_not_offered_it(self, shop, owner, stripe_double):
        paid = pay(shop)

        (row,) = rows(owner, paid)

        assert "take_over" not in row["actions"]
        assert row["paid_by_another_account"] is False

    def test_once_kept_the_row_is_the_owners_own(self, shop, owner, heir, stripe_double):
        paid = handed_over(shop, owner, heir, stripe_double)
        stripe_holds(stripe_double)
        services.checkout_completed(completed_takeover(paid))

        (row,) = rows(heir, paid)

        assert row["actions"] == ["change_plan", "cancel_plan", "view_invoices"]
        assert row["paid_by_another_account"] is False
