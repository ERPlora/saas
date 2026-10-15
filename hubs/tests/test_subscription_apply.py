"""``hubs.subscription.apply``: what Stripe says of a business's plan, written where hubs keeps it (lot L2-B).

billing reads the LIVE Stripe subscription (webhook, checkout, sweep) and hubs writes it: an app writes
in another only through its operations (plan 2026-10-13 §3). Only the platform runs it, as the hub's
other system operations (``hubs.business.mark_ready``). A field left out is left as it is, so billing can
link a Stripe customer without restating the plan.

What the Hub must learn (PLAN-SAAS §2.2: the effective plan, the commercial status and ``modules[]``)
bumps ``state_version`` and is pushed after the COMMIT; the rest (period, Stripe ids, why it is unpaid)
only records the event, so the owner's list and page re-run. The standing moves the business:
``good`` brings a business with a payment pending or suspended back, ``grace`` shows «payment pending»
(«Open» still works, round 17 §2.10), ``suspended`` stops it; a deleted business never moves. Why it is
unpaid travels to the Businesses row (mockups README §6.18: «Pay» stays disabled while the card was
declined), and the invoice to pay only to the owner.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.context import Scope, system_context
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from hubs import events, queries, services
from hubs.models import Hub, HubMember, Subscription, SubscriptionItem
from hubs.schemas import BusinessListIn, ModuleRightIn, SubscriptionApplyIn
from hubs.tests.conftest import add_member, ctx_for

pytestmark = pytest.mark.django_db

PERIOD_START = timezone.now().replace(microsecond=0) - timedelta(days=3)
PERIOD_END = PERIOD_START + timedelta(days=30)


def apply(hub, **fields):
    return services.subscription_apply(
        services.system_ctx_for(hub.id), SubscriptionApplyIn(hub_id=hub.id, **fields)
    )


def paid_starter(**extra):
    return {
        "plan": "starter",
        "billing_interval": "month",
        "status": "active",
        "stripe_customer_id": "cus_1",
        "stripe_subscription_id": "sub_1",
        "current_period_start": PERIOD_START,
        "current_period_end": PERIOD_END,
        "cancel_at_period_end": False,
        "trial_start": None,
        "trial_end": None,
        **extra,
    }


def fresh(hub):
    return Hub.objects.get(pk=hub.pk)


def subscription_of(hub):
    return Subscription.objects.select_related("plan", "trial_plan").get(hub=hub)


def ready(hub, status=Hub.Status.ACTIVE):
    Hub.objects.filter(pk=hub.pk).update(
        status=status, ready_at=timezone.now(), pending_hub_call=""
    )
    return fresh(hub)


# --- Who runs it -------------------------------------------------------------------------------------


def test_only_the_platform_applies_what_stripe_says(business, owner):
    with pytest.raises(PermissionDenied) as refused:
        services.subscription_apply(
            ctx_for(owner), SubscriptionApplyIn(hub_id=business.id, plan="starter")
        )

    assert refused.value.code == "internal_command"


def test_an_unknown_business_is_not_found(plans):
    import uuid

    with pytest.raises(NotFound):
        services.subscription_apply(
            system_context(Scope("user", "system")),
            SubscriptionApplyIn(hub_id=uuid.uuid7(), plan="starter"),
        )


def test_an_unknown_plan_is_an_invalid_field(business):
    with pytest.raises(InvalidPayload) as refused:
        apply(business, plan="platinum")

    assert set(refused.value.fields) == {"plan"}


# --- The plan ----------------------------------------------------------------------------------------


def test_a_paid_plan_is_written_with_its_stripe_ids_and_period(business):
    apply(business, **paid_starter())

    subscription = subscription_of(business)
    assert (
        subscription.plan.slug,
        subscription.billing_interval,
        subscription.status,
    ) == ("starter", "month", "active")
    assert (subscription.stripe_customer_id, subscription.stripe_subscription_id) == (
        "cus_1",
        "sub_1",
    )
    assert (subscription.current_period_start, subscription.current_period_end) == (
        PERIOD_START,
        PERIOD_END,
    )


@pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
def test_paying_ends_the_free_trial_of_the_sign_up(business):
    """Free is born with Starter's trial (ADR-0474); a paid plan carries its own trial in Stripe, so the
    trial plan of the sign-up no longer decides the rights (it would hide a paid Standard behind Starter)."""
    assert subscription_of(business).trial_plan is not None

    apply(business, **paid_starter(plan="standard"))

    subscription = subscription_of(business)
    assert subscription.trial_plan is None
    assert subscription.effective_plan(timezone.now()).slug == "standard"


def test_a_module_bought_on_free_keeps_the_sign_up_trial(business):
    """A subscription of modules alone leaves the business on Free: its Starter trial goes on."""
    trial = subscription_of(business).trial_plan

    apply(business, **paid_starter(plan="free"), modules=[ModuleRightIn(module_slug="inventory")])

    assert subscription_of(business).trial_plan == trial


def test_a_stripe_trial_is_kept_as_stripe_says(business):
    trial_end = PERIOD_START + timedelta(days=15)

    apply(
        business,
        **paid_starter(
            status="trialing", trial_start=PERIOD_START, trial_end=trial_end
        ),
    )

    subscription = subscription_of(business)
    assert (subscription.status, subscription.trial_start, subscription.trial_end) == (
        "trialing",
        PERIOD_START,
        trial_end,
    )


def test_the_new_plan_reaches_the_hub_after_the_commit(
    business, hub_double, django_capture_on_commit_callbacks
):
    business = ready(business)
    version = business.state_version

    with django_capture_on_commit_callbacks(execute=True):
        result = apply(business, **paid_starter(plan="standard"))

    assert result.changed is True
    assert result.state_version == version + 1
    snapshot = hub_double.calls_to("PUT", "/state")[-1].body
    assert (snapshot["version"], snapshot["plan"]["slug"]) == (version + 1, "standard")


def test_the_change_is_told_on_the_owners_channel(business, owner):
    apply(business, **paid_starter())

    told = OutboxEvent.objects.filter(name=events.SUBSCRIPTION_CHANGED).last()
    assert (told.scope_kind, told.scope_key, told.payload) == (
        "user",
        str(owner.pk),
        {"id": str(business.id)},
    )


def test_what_the_hub_does_not_see_does_not_bump_its_version(business):
    apply(business, **paid_starter())
    version = fresh(business).state_version

    result = apply(
        business,
        current_period_end=PERIOD_END + timedelta(days=30),
        cancel_at_period_end=True,
    )

    assert result.changed is True
    assert fresh(business).state_version == version


def test_the_same_facts_again_change_nothing(business):
    apply(business, **paid_starter())
    events_before = OutboxEvent.objects.count()
    version = fresh(business).state_version

    result = apply(business, **paid_starter())

    assert result.changed is False
    assert fresh(business).state_version == version
    assert OutboxEvent.objects.count() == events_before


def test_a_field_left_out_is_left_as_it_is(business):
    apply(business, **paid_starter())

    apply(business, status="past_due")

    subscription = subscription_of(business)
    assert (
        subscription.plan.slug,
        subscription.stripe_subscription_id,
        subscription.status,
    ) == ("starter", "sub_1", "past_due")


# --- The customer ------------------------------------------------------------------------------------


def test_the_first_customer_is_remembered_on_the_payer(business):
    result = apply(business, stripe_customer_id="cus_new")

    business.billing_profile.refresh_from_db()
    assert business.billing_profile.stripe_customer_id == "cus_new"
    assert subscription_of(business).stripe_customer_id == "cus_new"
    assert result.state_version == fresh(business).state_version


def test_a_payer_keeps_the_customer_it_already_has(business):
    business.billing_profile.stripe_customer_id = "cus_first"
    business.billing_profile.save()

    apply(business, stripe_customer_id="cus_other")

    business.billing_profile.refresh_from_db()
    assert business.billing_profile.stripe_customer_id == "cus_first"


# --- The modules -------------------------------------------------------------------------------------


def test_the_bought_modules_are_the_ones_stripe_bills(
    business, hub_double, django_capture_on_commit_callbacks
):
    from apps.models import Module

    # Starter includes the basic tier (hubs.services.sync_plan_modules, test_plan_modules.py).
    Module.objects.create(slug="loyalty", tier=Module.Tier.BASIC)
    business = ready(business)
    subscription = subscription_of(business)
    SubscriptionItem.objects.create(
        subscription=subscription, module_slug="loyalty", source="plan"
    )
    SubscriptionItem.objects.create(
        subscription=subscription,
        module_slug="stock",
        source="purchase",
        stripe_item_id="si_old",
    )

    with django_capture_on_commit_callbacks(execute=True):
        apply(
            business,
            **paid_starter(),
            modules=[ModuleRightIn(module_slug="inventory", stripe_item_id="si_inv")],
        )

    items = {
        item.module_slug: (item.source, item.stripe_item_id)
        for item in subscription.items.all()
    }
    # The one Stripe no longer bills is gone; the one the plan includes is not Stripe's to touch.
    assert items == {"inventory": ("purchase", "si_inv"), "loyalty": ("plan", "")}
    snapshot = hub_double.calls_to("PUT", "/state")[-1].body
    assert [module["id"] for module in snapshot["modules"]] == ["inventory", "loyalty"]


def test_a_cancelled_module_lasts_until_its_end_and_then_leaves_the_snapshot(business):
    until = timezone.now() + timedelta(days=5)
    apply(
        business,
        **paid_starter(),
        modules=[ModuleRightIn(module_slug="inventory", valid_until=until)],
    )

    assert queries.hub_snapshot(business.id)["modules"] == [
        {"id": "inventory", "source": "purchase", "valid_until": until.isoformat()}
    ]

    apply(
        business,
        modules=[
            ModuleRightIn(
                module_slug="inventory",
                valid_until=timezone.now() - timedelta(seconds=1),
            )
        ],
    )

    assert queries.hub_snapshot(business.id)["modules"] == []


def test_the_end_of_a_subscription_takes_the_business_back_to_free(business):
    apply(
        business,
        **paid_starter(),
        modules=[ModuleRightIn(module_slug="inventory", stripe_item_id="si_inv")],
    )
    ended = timezone.now()

    apply(
        business,
        plan="free",
        status="active",
        stripe_subscription_id="",
        current_period_start=None,
        current_period_end=None,
        cancel_at_period_end=False,
        modules=[ModuleRightIn(module_slug="inventory", valid_until=ended)],
    )

    subscription = subscription_of(business)
    assert (subscription.plan.slug, subscription.stripe_subscription_id) == ("free", "")
    assert queries.hub_snapshot(business.id)["plan"]["slug"] == "free"
    assert queries.hub_snapshot(business.id)["modules"] == []


# --- The standing ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "before, standing, after",
    [
        (Hub.Status.ACTIVE, "grace", Hub.Status.PAST_DUE),
        (Hub.Status.ACTIVE, "suspended", Hub.Status.SUSPENDED),
        (Hub.Status.PAST_DUE, "suspended", Hub.Status.SUSPENDED),
        (Hub.Status.PAST_DUE, "good", Hub.Status.ACTIVE),
        (Hub.Status.SUSPENDED, "good", Hub.Status.ACTIVE),
        # A late «payment pending» never takes a suspended business back.
        (Hub.Status.SUSPENDED, "grace", Hub.Status.SUSPENDED),
        (Hub.Status.ACTIVE, "good", Hub.Status.ACTIVE),
    ],
)
def test_the_standing_moves_the_business(business, before, standing, after):
    business = ready(business, before)
    if before != Hub.Status.ACTIVE:
        Subscription.objects.filter(hub=business).update(unpaid_reason="payment_failed")

    apply(business, standing=standing)

    assert fresh(business).status == after


def test_a_payment_wakes_only_a_suspension_for_not_paying(business):
    """Suspended for another reason (nothing unpaid on file), a paid subscription leaves it as it is."""
    business = ready(business, Hub.Status.SUSPENDED)

    apply(business, standing="good")

    assert fresh(business).status == Hub.Status.SUSPENDED


def test_a_business_not_ready_yet_comes_back_preparing(business):
    Hub.objects.filter(pk=business.pk).update(
        status=Hub.Status.SUSPENDED, ready_at=None
    )
    Subscription.objects.filter(hub=business).update(unpaid_reason="payment_failed")

    apply(business, standing="good")

    assert fresh(business).status == Hub.Status.PREPARING


@pytest.mark.parametrize("deleted", [Hub.Status.DELETING, Hub.Status.DELETED])
def test_a_deleted_business_never_moves_but_its_subscription_is_recorded(
    business, deleted
):
    Hub.objects.filter(pk=business.pk).update(status=deleted)

    apply(business, standing="good", plan="free", stripe_subscription_id="")

    assert fresh(business).status == deleted
    assert subscription_of(business).plan.slug == "free"


def test_the_hub_learns_the_suspension(
    business, hub_double, django_capture_on_commit_callbacks
):
    business = ready(business)

    with django_capture_on_commit_callbacks(execute=True):
        apply(business, standing="suspended")

    assert hub_double.calls_to("PUT", "/state")[-1].body["status"] == "suspended"


# --- Why it is unpaid --------------------------------------------------------------------------------


def unpaid(business, reason="card_declined"):
    since = timezone.now().replace(microsecond=0) - timedelta(days=2)
    apply(
        business,
        standing="grace",
        unpaid_reason=reason,
        unpaid_since=since,
        unpaid_invoice_url="https://invoice.stripe.com/i/test_1",
    )
    return since


def row_of(user, business):
    rows = queries.business_list(ctx_for(user), BusinessListIn()).model_dump()["rows"]
    return next(row for row in rows if row["id"] == business.id)


def test_the_row_says_why_the_business_is_unpaid(business, owner):
    business = ready(business)
    since = unpaid(business)

    row = row_of(owner, business)

    assert (row["status"], row["unpaid_reason"], row["unpaid_since"]) == (
        "past_due",
        "card_declined",
        since,
    )
    assert row["pay_url"] == "https://invoice.stripe.com/i/test_1"


def test_only_the_owner_gets_the_invoice_to_pay(business, owner, make_user):
    business = ready(business)
    unpaid(business)
    admin = make_user("admin@example.com")
    add_member(business, admin, HubMember.Role.ADMIN, invited_by=owner)

    row = row_of(admin, business)

    assert (row["unpaid_reason"], row["pay_url"]) == ("card_declined", None)


def test_paying_clears_the_reason(business, owner):
    business = ready(business)
    unpaid(business)

    apply(
        business,
        standing="good",
        unpaid_reason=None,
        unpaid_since=None,
        unpaid_invoice_url=None,
    )

    row = row_of(owner, business)
    assert (
        row["status"],
        row["unpaid_reason"],
        row["unpaid_since"],
        row["pay_url"],
    ) == ("active", None, None, None)


def test_a_business_in_good_standing_has_no_reason(business, owner):
    row = row_of(owner, business)

    assert (row["unpaid_reason"], row["unpaid_since"], row["pay_url"]) == (
        None,
        None,
        None,
    )


def test_the_page_of_the_business_says_it_too(business, owner):
    business = ready(business)
    since = unpaid(business, "card_changed")

    detail = queries.business_get(
        ctx_for(owner), queries.ByIdIn(id=business.id)
    ).model_dump()

    assert (detail["unpaid_reason"], detail["unpaid_since"], detail["pay_url"]) == (
        "card_changed",
        since,
        "https://invoice.stripe.com/i/test_1",
    )


def test_the_invoice_to_pay_goes_to_the_payer_not_to_the_role(business, owner, make_user):
    """Review of L2-B: after a transfer the new owner is not the payer; the invoice (and its page, with the
    payer's card) stays with whoever pays."""
    business = ready(business)
    unpaid(business)
    new_owner = make_user("new-owner@example.com")
    HubMember.objects.filter(hub=business, user=owner).update(role=HubMember.Role.ADMIN)
    now = timezone.now()
    HubMember.objects.create(hub=business, user=new_owner, role=HubMember.Role.OWNER, joined_at=now, accepted_at=now)

    assert row_of(new_owner, business)["pay_url"] is None
    assert row_of(owner, business)["pay_url"] == "https://invoice.stripe.com/i/test_1"


def test_deleting_a_paying_business_asks_for_its_stripe_subscription_to_end(business, owner):
    """Review of L2-B: the ask is durable (billing's sweep ends it), so recovering the business before the
    sweep does not leave it charging while the panel says Free."""
    from hubs.schemas import BusinessDeleteIn, ByIdIn

    apply(business, **paid_starter())
    services.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name))
    asked = subscription_of(business).cancel_requested_at

    services.business_restore(ctx_for(owner), ByIdIn(id=business.id))

    assert asked is not None
    assert subscription_of(business).cancel_requested_at == asked


def test_the_end_of_the_stripe_subscription_clears_the_ask(business, owner):
    from hubs.schemas import BusinessDeleteIn

    apply(business, **paid_starter())
    services.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name))

    apply(business, stripe_subscription_id="", cancel_requested_at=None)

    assert subscription_of(business).cancel_requested_at is None


def test_deleting_a_free_business_asks_nothing_of_stripe(business, owner):
    from hubs.schemas import BusinessDeleteIn

    services.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name))

    assert subscription_of(business).cancel_requested_at is None
