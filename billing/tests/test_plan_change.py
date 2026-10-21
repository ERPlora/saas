"""Changing, cancelling and keeping the plan of a paying business: ``billing.plan.{change,cancel,keep}``.

Ported from ERPlora/saas ``hubs/main/tests/test_plan_change.py`` (14), ``test_plan_change_needs_tax_id_over_the_simplified_limit.py``
(6), the cancel and resume cases of ``hubs/subscriptions/tests/test_subscription_viewset_permissions.py``
and ``hubs/main/tests/test_stripe_service.py``, and ``TestResumeDoesNotGiveThePlanBackWithoutPaying`` of
``test_unpaid_hub_is_suspended.py`` (origin/develop). In the new design the plan is ONE item of the
business's subscription, beside its modules:

- the change swaps the price of the plan item (and, on a change of billing, every module's price: Stripe
  bills one interval per subscription), charged at once or not at all (``always_invoice`` +
  ``error_if_incomplete``), at the proration the preview showed;
- Free is not a plan to change to: cancelling ends the plan with its period (PLAN-SAAS §3.3) and the
  business goes back to Free then; a cancelled plan is kept before it changes;
- keeping an unpaid plan is refused without calling Stripe (it would hand the plan back without paying);
- only the owner (round 17 §2.7): an employee does not learn more than a 404/403.

Dropped with reason: the Django view, its template, messages and HTMX redirects; the container resize
after a change (no container per business, PLAN §14).
"""

import pytest
from django.utils import timezone
from live.errors import NotFound, OperationError, PermissionDenied

from billing import services
from billing.schemas import HubIn, PlanChangeIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import card_error, item, subscription
from hubs.models import Hub, HubMember, Subscription, SubscriptionItem
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db

PRORATION = int(timezone.now().timestamp())


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def change(user, hub, plan="standard", interval="month"):
    return services.plan_change(
        ctx_for(user),
        PlanChangeIn(
            hub_id=hub.id, plan=plan, interval=interval, proration_date=PRORATION
        ),
    ).model_dump()


def cancel(user, hub):
    return services.plan_cancel(ctx_for(user), HubIn(hub_id=hub.id)).model_dump()


def keep(user, hub):
    return services.plan_keep(ctx_for(user), HubIn(hub_id=hub.id)).model_dump()


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()
    return error.value


def local(hub):
    return Subscription.objects.select_related("plan").get(hub=hub)


def on_starter(shop, stripe_double, *modules, **live):
    paid = pay(shop, modules=modules)
    lines = [item("si_plan", "price_starter_month")] + [
        item(f"si_{slug}", f"price_{slug}_month") for slug in modules
    ]
    stripe_double.answer("subscriptions.retrieve", subscription(items=lines, **live))
    return paid


class TestChangingThePlan:
    def test_the_plan_item_gets_the_new_price_charged_now_or_not_at_all(
        self, shop, owner, stripe_double
    ):
        paid = on_starter(shop, stripe_double)
        stripe_double.answer(
            "subscriptions.update",
            subscription(items=[item("si_plan", "price_standard_month")]),
        )

        answer = change(owner, paid)

        sent = stripe_double.last("subscriptions.update")
        assert sent.args == ("sub_1",)
        assert sent.params == {
            "items": [
                {
                    "id": "si_plan",
                    "price": "price_standard_month",
                    "tax_rates": [stripe_double.tax_rates[0]["id"]],
                }
            ],
            "proration_behavior": "always_invoice",
            "proration_date": PRORATION,
            "payment_behavior": "error_if_incomplete",
        }
        assert sent.options["idempotency_key"].startswith(f"plan-{shop.id}-standard-month-")
        assert answer["plan"] == "standard"
        assert local(shop).plan.slug == "standard"

    def test_the_hub_learns_the_new_plan(
        self, shop, owner, stripe_double, hub_double, django_capture_on_commit_callbacks
    ):
        paid = on_starter(shop, stripe_double)
        Hub.objects.filter(pk=paid.pk).update(
            status=Hub.Status.ACTIVE, ready_at=paid.created_at, pending_hub_call=""
        )
        stripe_double.answer(
            "subscriptions.update",
            subscription(items=[item("si_plan", "price_standard_month")]),
        )

        with django_capture_on_commit_callbacks(execute=True):
            change(owner, paid)

        assert (
            hub_double.calls_to("PUT", "/state")[-1].body["plan"]["slug"] == "standard"
        )

    def test_a_change_of_billing_moves_every_module_to_its_new_price(
        self, shop, owner, inventory, stripe_double
    ):
        # 299.90 + 100 a year is 483.88 € with VAT: the invoice names the buyer.
        shop.billing_profile.tax_id = "12345678Z"
        shop.billing_profile.save()
        paid = on_starter(shop, stripe_double, "inventory")
        stripe_double.answer(
            "subscriptions.update",
            subscription(
                items=[
                    item("si_plan", "price_starter_year", interval="year"),
                    item("si_inventory", "price_inventory_year", interval="year"),
                ]
            ),
        )

        answer = change(owner, paid, plan="starter", interval="year")

        items = stripe_double.last("subscriptions.update").params["items"]
        assert [(line["id"], line["price"]) for line in items] == [
            ("si_plan", "price_starter_year"),
            ("si_inventory", "price_inventory_year"),
        ]
        assert answer["billing_interval"] == "year"
        assert [module["slug"] for module in answer["modules"]] == ["inventory"]

    def test_a_preview_from_another_moment_is_previewed_again(self, shop, owner, stripe_double):
        paid = on_starter(shop, stripe_double)

        with pytest.raises(OperationError) as error:
            services.plan_change(
                ctx_for(owner),
                PlanChangeIn(hub_id=paid.id, plan="standard", proration_date=PRORATION + 3600),
            )

        assert error.value.code == "billing.preview_expired"
        assert stripe_double.calls_to("subscriptions.update") == []

    def test_a_declined_card_changes_nothing(self, shop, owner, stripe_double):
        paid = on_starter(shop, stripe_double)
        stripe_double.answer("subscriptions.update", card_error())

        refused("billing.card_declined", lambda: change(owner, paid))

        assert local(shop).plan.slug == "starter"

    def test_the_same_plan_and_billing_is_no_change(self, shop, owner, stripe_double):
        paid = on_starter(shop, stripe_double)

        refused("billing.same_plan", lambda: change(owner, paid, plan="starter"))

        assert stripe_double.calls_to("subscriptions.update") == []

    def test_a_cancelled_plan_is_kept_before_it_changes(
        self, shop, owner, stripe_double
    ):
        paid = on_starter(shop, stripe_double)
        Subscription.objects.filter(hub=paid).update(cancel_at_period_end=True)

        refused("billing.cancellation_pending", lambda: change(owner, paid))

    def test_free_is_reached_by_cancelling(self, shop, owner, stripe_double):
        paid = on_starter(shop, stripe_double)

        refused("billing.plan_is_free", lambda: change(owner, paid, plan="free"))

        assert local(shop).stripe_subscription_id == "sub_1"

    def test_a_free_business_buys_with_the_checkout(self, shop, owner):
        refused("billing.checkout_required", lambda: change(owner, shop))

    def test_an_annual_plan_over_400_euros_needs_the_tax_id(
        self, shop, owner, stripe_double
    ):
        paid = on_starter(shop, stripe_double)

        refused(
            "billing.tax_id_required",
            lambda: change(owner, paid, plan="standard", interval="year"),
        )

        assert stripe_double.calls_to("subscriptions.update") == []
        assert local(shop).plan.slug == "starter"

    def test_with_the_tax_id_on_file_the_annual_change_goes_through(
        self, shop, owner, stripe_double
    ):
        paid = on_starter(shop, stripe_double)
        paid.billing_profile.tax_id = "12345678Z"
        paid.billing_profile.save()
        stripe_double.answer(
            "subscriptions.update",
            subscription(
                items=[item("si_plan", "price_standard_year", interval="year")]
            ),
        )

        change(owner, paid, plan="standard", interval="year")

        assert local(shop).plan.slug == "standard"

    def test_a_monthly_plan_over_the_limit_needs_it_too(
        self, shop, owner, stripe_double
    ):
        paid = on_starter(shop, stripe_double)

        refused("billing.tax_id_required", lambda: change(owner, paid, plan="max"))

    def test_an_unpaid_business_changes_nothing(self, shop, owner, stripe_double):
        paid = pay(shop, status="past_due")

        refused("billing.invoice_unpaid", lambda: change(owner, paid))

        assert stripe_double.calls == []


class TestCancellingAndKeeping:
    def test_cancelling_ends_the_plan_with_its_period(self, shop, owner, stripe_double):
        paid = on_starter(shop, stripe_double)
        stripe_double.answer(
            "subscriptions.update", subscription(cancel_at_period_end=True)
        )

        answer = cancel(owner, paid)

        assert stripe_double.last("subscriptions.update").params == {
            "cancel_at_period_end": True
        }
        assert answer["cancel_at_period_end"] is True
        assert (local(shop).cancel_at_period_end, local(shop).plan.slug) == (
            True,
            "starter",
        )

    def test_cancelling_again_changes_nothing(self, shop, owner, stripe_double):
        paid = pay(shop, cancel_at_period_end=True)

        assert cancel(owner, paid)["cancel_at_period_end"] is True
        assert stripe_double.calls == []

    def test_a_free_business_has_nothing_to_cancel(self, shop, owner):
        refused("billing.nothing_to_cancel", lambda: cancel(owner, shop))

    def test_an_unpaid_plan_may_still_be_cancelled(self, shop, owner, stripe_double):
        paid = pay(shop, status="past_due")
        stripe_double.answer(
            "subscriptions.update",
            subscription(status="past_due", cancel_at_period_end=True),
        )

        assert cancel(owner, paid)["cancel_at_period_end"] is True

    def test_keeping_undoes_the_cancellation(self, shop, owner, stripe_double):
        paid = pay(shop, cancel_at_period_end=True)
        stripe_double.answer(
            "subscriptions.update", subscription(cancel_at_period_end=False)
        )

        answer = keep(owner, paid)

        assert stripe_double.last("subscriptions.update").params == {
            "cancel_at_period_end": False
        }
        assert answer["cancel_at_period_end"] is False

    def test_keeping_leaves_the_status_stripe_gives(self, shop, owner, stripe_double):
        paid = pay(shop, status="trialing", cancel_at_period_end=True)
        stripe_double.answer(
            "subscriptions.update",
            subscription(status="trialing", cancel_at_period_end=False),
        )

        assert keep(owner, paid)["status"] == "trialing"

    @pytest.mark.parametrize("status", ["past_due", "unpaid"])
    def test_an_unpaid_plan_is_not_kept_without_paying(
        self, shop, owner, stripe_double, status
    ):
        paid = pay(shop, status=status, cancel_at_period_end=True)

        refused("billing.invoice_unpaid", lambda: keep(owner, paid))

        assert stripe_double.calls == []
        assert local(shop).cancel_at_period_end is True

    def test_keeping_a_plan_that_is_not_cancelled_changes_nothing(
        self, shop, owner, stripe_double
    ):
        paid = pay(shop)

        assert keep(owner, paid)["cancel_at_period_end"] is False
        assert stripe_double.calls == []


class TestOnlyTheOwner:
    @pytest.mark.parametrize("role", [HubMember.Role.ADMIN, HubMember.Role.EMPLOYEE])
    def test_nobody_else_touches_the_plan(
        self, shop, owner, make_user, stripe_double, role
    ):
        paid = pay(shop)
        other = make_user("other@example.com")
        add_member(paid, other, role, invited_by=owner)

        for call in (
            lambda: change(other, paid),
            lambda: cancel(other, paid),
            lambda: keep(other, paid),
        ):
            with pytest.raises(PermissionDenied):
                call()

        assert stripe_double.calls == []

    def test_a_stranger_does_not_learn_the_business_exists(self, shop, make_user):
        paid = pay(shop)

        with pytest.raises(NotFound):
            cancel(make_user("stranger@example.com"), paid)

    def test_only_this_business_is_touched(self, shop, owner, stripe_double, plans):
        from hubs.tests.conftest import create_business

        paid = on_starter(shop, stripe_double)  # paying: its owner may create another free business
        other = pay(create_business(owner, name="Otro Bar"), sub_id="sub_other")
        stripe_double.answer(
            "subscriptions.update", subscription(cancel_at_period_end=True)
        )

        cancel(owner, paid)

        assert local(other).cancel_at_period_end is False
        assert [
            call.args for call in stripe_double.calls_to("subscriptions.update")
        ] == [("sub_1",)]
        assert not SubscriptionItem.objects.filter(subscription__hub=other).exists()


def test_a_new_owner_does_not_change_the_plan_on_the_previous_owners_card(shop, owner, make_user, stripe_double):
    from billing.tests.test_checkout import transferred

    paid = pay(shop)
    new_owner = transferred(paid, owner, make_user)

    for call in (lambda: change(new_owner, paid), lambda: cancel(new_owner, paid)):
        with pytest.raises(OperationError) as error:
            call()
        assert error.value.code == "billing.payer_required"

    assert stripe_double.calls == []


def test_a_retry_of_a_declined_change_is_its_own_request(shop, owner, stripe_double):
    paid = on_starter(shop, stripe_double)
    stripe_double.answer("subscriptions.update", card_error(), subscription(items=[item("si_plan", "price_standard_month")]))

    with pytest.raises(OperationError):
        change(owner, paid)
    change(owner, paid)

    keys = [call.options["idempotency_key"] for call in stripe_double.calls_to("subscriptions.update")]
    assert keys[0] != keys[1]
    assert local(shop).plan.slug == "standard"


def test_a_change_of_billing_puts_our_tax_on_every_item(shop, owner, inventory, stripe_double):
    shop.billing_profile.tax_id = "12345678Z"
    shop.billing_profile.save()
    paid = on_starter(shop, stripe_double, "inventory")
    stripe_double.answer("subscriptions.update", subscription(items=[
        item("si_plan", "price_starter_year", interval="year"),
        item("si_inventory", "price_inventory_year", interval="year"),
    ]))

    change(owner, paid, plan="starter", interval="year")

    items = stripe_double.last("subscriptions.update").params["items"]
    rate = stripe_double.tax_rates[0]["id"]
    assert [line["tax_rates"] for line in items] == [[rate], [rate]]


def test_a_payer_not_subject_to_vat_loses_the_old_rate_on_the_change(shop, owner, inventory, stripe_double):
    """BILLING-F11: a payer now in Las Palmas whose items still hold the Spanish 21 % changes plan. An empty
    list of rates is dropped by the SDK and Stripe keeps the old rate on the item: the update has to say
    «none» with an empty string, on the plan and on every module it moves."""
    shop.billing_profile.billing_postal_code = "35001"
    shop.billing_profile.save()
    paid = pay(shop, modules=("inventory",))
    stripe_double.answer("subscriptions.retrieve", subscription(items=[
        item("si_plan", "price_starter_month", tax_rates=["txr_es_21"]),
        item("si_inventory", "price_inventory_month", tax_rates=["txr_es_21"]),
    ]))
    stripe_double.answer("subscriptions.update", subscription(items=[
        item("si_plan", "price_starter_year", interval="year"),
        item("si_inventory", "price_inventory_year", interval="year"),
    ]))

    change(owner, paid, plan="starter", interval="year")

    items = stripe_double.last("subscriptions.update").params["items"]
    assert [(line["id"], line["tax_rates"]) for line in items] == [("si_plan", ""), ("si_inventory", "")]
