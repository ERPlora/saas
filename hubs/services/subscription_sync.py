"""What Stripe says of a business's plan, and the rights its plan and modules give it in the Hub."""

import logging
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import InvalidPayload, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from hubs import events
from hubs.models import BillingProfile, Hub, Plan, Subscription, SubscriptionItem
from hubs.queries import access_control, hub_sync, plan_catalog
from hubs.schemas.subscriptions import SubscriptionApplyIn, SubscriptionApplyOut
from hubs.services.hub_push import LIVE_STATUSES, bump_state, push_after_commit

logger = logging.getLogger(__name__)


#: The fields of ``Subscription`` that ``hubs.subscription.apply`` writes as they come (``None`` clears the
#: two texts).
APPLIED_FIELDS = (
    "billing_interval",
    "status",
    "stripe_customer_id",
    "stripe_subscription_id",
    "current_period_start",
    "current_period_end",
    "cancel_at_period_end",
    "trial_start",
    "trial_end",
    "unpaid_reason",
    "unpaid_since",
    "unpaid_invoice_url",
    "cancel_requested_at",
)
CLEARED_TO_EMPTY = ("unpaid_reason", "unpaid_invoice_url", "stripe_customer_id", "stripe_subscription_id")
#: How a standing moves a business (a deleted one never moves; a paid one not ready yet is preparing).
STANDING_MOVES = {
    "good": {Hub.Status.PAST_DUE: Hub.Status.ACTIVE, Hub.Status.SUSPENDED: Hub.Status.ACTIVE},
    "grace": {Hub.Status.ACTIVE: Hub.Status.PAST_DUE},
    "suspended": {
        Hub.Status.PREPARING: Hub.Status.SUSPENDED,
        Hub.Status.ACTIVE: Hub.Status.SUSPENDED,
        Hub.Status.PAST_DUE: Hub.Status.SUSPENDED,
    },
}


@operation(
    "hubs.subscription.apply",
    kind="command",
    permission="hubs.manage",
    input=SubscriptionApplyIn,
    output=SubscriptionApplyOut,
    ai=INTERNAL,  # only the platform runs it
)
def subscription_apply(ctx: OperationContext, data: SubscriptionApplyIn) -> dict:  # noqa: C901, PLR0912, PLR0915
    """Write what the live Stripe subscription says of a business (billing reads it: webhook, checkout,
    the sweep of unpaid plans). Only the platform runs it, in the owner's channel (``system_ctx_for``).

    A field left out is left as it is. What the Hub sees (the effective plan, the commercial status and
    ``modules[]``) bumps ``state_version`` and is pushed after the COMMIT; anything written
    records ``hubs.subscription.changed``. A paid subscription carries its own trial, so it ends the trial
    plan of the sign-up. A deleted business keeps its status whatever the standing.
    """
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform applies what Stripe says."), code="internal_command")
    hub = Hub.objects.select_for_update().filter(pk=data.hub_id).first()
    if hub is None:
        raise access_control.not_found()
    sent = data.model_dump(exclude_unset=True, exclude={"hub_id"})
    seen_before = _what_the_hub_sees(hub.id)
    subscription = Subscription.objects.select_for_update().filter(hub=hub).first()
    # Only a business stopped for not paying comes back with a payment (nothing else suspends one today,
    # but a payment must never undo a suspension it did not cause).
    was_unpaid = bool(subscription and subscription.unpaid_reason)
    changed = False
    plan = None
    if "plan" in sent:
        plan = Plan.objects.filter(slug=sent["plan"]).first()
        if plan is None:
            reason = _("There is no plan with this identifier.")
            raise InvalidPayload(reason, fields={"plan": reason})
    if subscription is None:
        subscription = Subscription(hub=hub, plan=plan or plan_catalog.free_plan())
        changed = True
    changes = {}
    if plan is not None and subscription.plan_id != plan.pk:
        changes["plan"] = plan
    # A customer sent alone is the payer's (``billing.services.stripe_customers.ensure_customer``): a live
    # subscription keeps the one Stripe charges until Stripe says otherwise (the previous payer's card after a
    # hand-over, HUBS-F28).
    payers_only = "stripe_subscription_id" not in sent and bool(subscription.stripe_subscription_id)
    for field in APPLIED_FIELDS:
        if field == "stripe_customer_id" and payers_only:
            continue
        if field in sent:
            value = sent[field]
            if value is None and field in CLEARED_TO_EMPTY:
                value = ""
            if getattr(subscription, field) != value:
                changes[field] = value
    paid_plan = plan is not None and plan.price_monthly > 0
    if sent.get("stripe_subscription_id") and paid_plan and subscription.trial_plan_id is not None:
        # The paid plan carries its own trial in Stripe; modules alone leave the business on Free.
        changes["trial_plan"] = None
    for field, value in changes.items():
        setattr(subscription, field, value)
    if changes or changed:
        subscription.save()
        changed = True
    customer = sent.get("stripe_customer_id")
    profile = hub.billing_profile
    if customer and profile is not None and not profile.stripe_customer_id:
        BillingProfile.objects.filter(pk=profile.pk).update(stripe_customer_id=customer, updated_at=timezone.now())
        changed = True
    elif customer and profile is not None and profile.stripe_customer_id != customer:
        logger.warning(
            "hubs.subscription.customer_differs hub=%s payer=%s subscription=%s",
            hub.id,
            profile.stripe_customer_id,
            customer,
        )
    if "modules" in sent:
        changed |= _apply_modules(subscription, data.modules or [])
    changed |= sync_plan_modules(subscription)
    if "standing" in sent:
        changed |= _apply_standing(hub, sent["standing"], was_unpaid=was_unpaid)
    if _what_the_hub_sees(hub.id) != seen_before:
        bump_state(hub.id)
        push_after_commit(hub.id)
    if changed:
        record_event(ctx, events.SUBSCRIPTION_CHANGED, {"id": str(hub.id)})
    hub.refresh_from_db(fields=["state_version"])
    return {"hub_id": hub.id, "state_version": hub.state_version, "changed": changed}


def _what_the_hub_sees(hub_id: UUID) -> tuple:
    snapshot = hub_sync.hub_snapshot(hub_id)
    return snapshot["status"], snapshot["plan"], snapshot["modules"]


def _apply_modules(subscription: Subscription, rights) -> bool:
    """The bought modules become ``rights``; the ones the plan includes are not Stripe's to touch, unless Stripe
    bills one open-ended: then its row is bought (with the Stripe item that cancelling it needs)."""
    changed = False
    wanted = {right.module_slug: right for right in rights}
    bought = SubscriptionItem.objects.filter(subscription=subscription, source=SubscriptionItem.Source.PURCHASE)
    gone = bought.exclude(module_slug__in=wanted)
    if gone.exists():
        gone.delete()
        changed = True
    have = {item.module_slug: item for item in SubscriptionItem.objects.filter(subscription=subscription)}
    for slug, right in wanted.items():
        item = have.get(slug)
        if item is None:
            SubscriptionItem.objects.create(
                subscription=subscription,
                module_slug=slug,
                source=SubscriptionItem.Source.PURCHASE,
                stripe_item_id=right.stripe_item_id,
                valid_until=right.valid_until,
            )
            changed = True
        elif item.source == SubscriptionItem.Source.PLAN and right.valid_until is None:
            item.source = SubscriptionItem.Source.PURCHASE
            item.stripe_item_id = right.stripe_item_id
            item.valid_until = None
            item.save(update_fields=["source", "stripe_item_id", "valid_until", "updated_at"])
            changed = True
        elif item.source == SubscriptionItem.Source.PURCHASE and (
            item.stripe_item_id != right.stripe_item_id or item.valid_until != right.valid_until
        ):
            item.stripe_item_id = right.stripe_item_id
            item.valid_until = right.valid_until
            item.save(update_fields=["stripe_item_id", "valid_until", "updated_at"])
            changed = True
    return changed


def sync_plan_modules(subscription: Subscription, now=None) -> bool:
    """Make the business's ``source="plan"`` rights the modules its plan includes now; ``True`` if a row changed.

    The plan is the one the business has now (``effective_plan``): what only the sign-up's trial includes lasts
    until ``trial_end``. A module Stripe bills open-ended keeps its bought row (cancelling it needs its Stripe
    item); a bought one already cancelled (``valid_until``) yields its row to the plan, so the right never lapses.
    Called wherever the plan may change: ``hubs.subscription.apply``, the sign-up, the restore, a trial's end.
    """
    now = now or timezone.now()
    wanted = dict.fromkeys(plan_catalog.modules_included_in(subscription.plan))
    effective = subscription.effective_plan(now)
    if effective.pk != subscription.plan_id:
        for slug in plan_catalog.modules_included_in(effective):
            wanted.setdefault(slug, subscription.trial_end)
    items = SubscriptionItem.objects.filter(subscription=subscription)
    rows = {item.module_slug: item for item in items}
    changed = False
    for slug, item in rows.items():
        if item.source == SubscriptionItem.Source.PURCHASE and item.valid_until is None:
            wanted.pop(slug, None)
        elif item.source == SubscriptionItem.Source.PLAN and slug not in wanted:
            item.delete()
            changed = True
    for slug, until in wanted.items():
        item = rows.get(slug)
        if item is None:
            SubscriptionItem.objects.create(
                subscription=subscription, module_slug=slug, source=SubscriptionItem.Source.PLAN, valid_until=until
            )
            changed = True
        elif (item.source, item.valid_until, item.stripe_item_id) != (SubscriptionItem.Source.PLAN, until, ""):
            item.source, item.valid_until, item.stripe_item_id = SubscriptionItem.Source.PLAN, until, ""
            item.save(update_fields=["source", "valid_until", "stripe_item_id", "updated_at"])
            changed = True
    return changed


def owe_plan_rights(plan: Plan, now=None) -> int:
    """The staff changed in the admin what ``plan`` gives (``hub_sync.SNAPSHOT_PLAN_FIELDS``; HUBS-F31): each live
    business on it, as its plan or as the trial's, gets the modules of its level written (``sync_plan_modules``) and,
    when its snapshot changes, owes the Hub a newer one, which the next pass of ``reconcile_hub_states`` (every 15
    minutes) delivers instead of the night's. How many businesses owe it.

    Never pushed here: a plan may have thousands of businesses, and the admin's save is one transaction.
    """
    now = now or timezone.now()
    owed = 0
    subscriptions = Subscription.objects.select_related("plan", "trial_plan").filter(
        Q(plan=plan) | Q(trial_plan=plan), hub__status__in=LIVE_STATUSES
    )
    for subscription in subscriptions.order_by("pk"):
        changed = sync_plan_modules(subscription, now)
        if changed or subscription.effective_plan(now) == plan:
            bump_state(subscription.hub_id)
            owed += 1
    return owed


def owe_module_rights(tier: str, previous_tier: str | None = None, now=None) -> int:
    """A paid module of ``tier`` was added in the admin, or moved there from ``previous_tier`` (HUBS-F34): every live
    business whose plan (or trial) reaches either level gets its plan's modules written again (``sync_plan_modules``)
    and, where they changed, owes the Hub a newer snapshot, which the next pass of ``reconcile_hub_states`` delivers.
    How many businesses owe it. Never pushed here, as ``owe_plan_rights``."""
    now = now or timezone.now()
    reached = [plan_catalog.LEVELS.index(level) for level in (tier, previous_tier) if level in plan_catalog.LEVELS]
    if not reached:
        return 0
    plans = Plan.objects.filter(included_level__in=plan_catalog.LEVELS[min(reached) :])
    owed = 0
    subscriptions = Subscription.objects.select_related("plan", "trial_plan").filter(
        Q(plan__in=plans) | Q(trial_plan__in=plans), hub__status__in=LIVE_STATUSES
    )
    for subscription in subscriptions.order_by("pk"):
        if sync_plan_modules(subscription, now):
            bump_state(subscription.hub_id)
            owed += 1
    return owed


def _apply_standing(hub: Hub, standing: str, *, was_unpaid: bool) -> bool:
    if standing == "good" and not was_unpaid:
        return False
    status = STANDING_MOVES[standing].get(hub.status)
    if status == Hub.Status.ACTIVE and hub.ready_at is None:
        status = Hub.Status.PREPARING
    if status is None or status == hub.status:
        return False
    now = timezone.now()
    # The clock of HUBS-F20: suspending dates it; leaving the suspension (it paid) stops it and forgets its notices.
    clock = (
        {"suspended_at": now, "suspension_warned_at": None, "suspension_final_notice_at": None}
        if status == Hub.Status.SUSPENDED
        else {"suspended_at": None, "suspension_warned_at": None, "suspension_final_notice_at": None}
    )
    Hub.objects.filter(pk=hub.pk).update(status=status, updated_at=now, **clock)
    hub.status = status
    logger.info("hubs.subscription.standing hub=%s standing=%s status=%s", hub.id, standing, status)
    return True
