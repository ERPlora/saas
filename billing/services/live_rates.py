"""The tax rates of a live subscription: every item takes the rates the payer's place calls for today, when the payer's
billing details change and once a day."""

import logging
from collections import Counter
from decimal import Decimal

from django.utils import timezone
from live.errors import Conflict

from billing import stripe_service
from billing.services import (
    discounts,
    downgrades,
    hand_overs,
    payment_gates,
    stripe_customers,
    stripe_sales,
    stripe_sync,
)
from hubs.models import Hub, Subscription

logger = logging.getLogger("billing.services")


#: Stripe statuses whose next invoice is still going to be charged.
RETAX_STATUSES = ("active", "trialing", "past_due")
#: The counts of a daily pass; ``refused`` and ``errors`` make the run fail after its pass (``task_failed``).
RETAX_COUNTS = ("retaxed", "unchanged", "skipped", "refused", "errors")


def retax_subscription(hub: Hub) -> str:
    """Hand Stripe the rates the payer's place calls for today on every item of the business's live
    subscription: the checkout fixes a rate per item and Stripe charges it on every renewal, so a payer who
    moves (Madrid → Las Palmas), proves a VAT number, or a year that crosses the OSS threshold would keep the
    old one. The same engine as the sale (``price_sale``); the next invoice takes the new rate,
    the paid period is not touched (no proration).

    ``retaxed`` · ``unchanged`` (Stripe already holds them: nothing sent) · ``skipped`` (no live Stripe
    subscription, or one still charged to another account's card: its tax is that payer's) ·
    ``refused`` (the place is not sold to now: an ERROR, and the old rates stay until the billing details are
    fixed). With a downgrade waiting in a schedule, its phases are retaxed instead (``_retax_schedule``). Stripe
    failing raises (``stripe_errors``)."""
    subscription = Subscription.objects.filter(hub=hub).select_related("plan").first()
    if (
        subscription is None
        or not subscription.stripe_subscription_id
        or subscription.status not in RETAX_STATUSES
    ):
        return "skipped"
    hub = Hub.objects.select_related("billing_profile").get(pk=hub.pk)
    if hand_overs.billed_to_another_account(subscription, hub.billing_profile):
        return "skipped"
    payment_gates.require_stripe()
    pending = downgrades.pending_change(hub)
    if pending is not None:
        return _retax_schedule(hub, subscription, pending.stripe_schedule_id)
    live = stripe_sales._live(subscription)
    changes = []
    for line in stripe_sales._live_items(live):
        sale = stripe_sales._item_sale(subscription, line)
        if sale is None:
            continue
        try:
            due = stripe_sales.price_sale(
                hub, sale, recurring_net=stripe_sales._recurring_net(subscription, sale.interval), renewing=True
            )
        except Conflict as refused:
            return _retax_refused(hub, sale.kind, refused)
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in line.get("tax_rates") or []]
        if sorted(held) != sorted(due):
            changes.append({"id": line["id"], "tax_rates": stripe_sync._rates_param(due)})
    if not changes:
        return "unchanged"
    with payment_gates.stripe_errors():
        stripe_service.update_subscription(
            subscription.stripe_subscription_id,
            {"items": changes, "proration_behavior": "none"},
        )
    logger.info("[BILLING] Hub %s retaxed: %s", hub.id, changes)
    return "retaxed"


def _retax_refused(hub: Hub, kind: str, refused: Conflict) -> str:
    logger.error(
        "[BILLING] %s of hub %s cannot be retaxed (%s): Stripe keeps charging its old rate",
        kind,
        hub.id,
        refused.code,
        extra={"event": "billing.retax_refused", "hub_id": str(hub.id), "code": refused.code},
    )
    return "refused"


def _retax_schedule(hub: Hub, subscription: Subscription, schedule_id: str) -> str:
    """A downgrade waiting in a Stripe schedule: the first invoice of the new plan is billed by its next phase,
    whose items carry the rates fixed when it was scheduled. Every phase still to run is re-stated with
    today's rates (a phase over is left out; the current one keeps its start) and its discounts. Phases are
    re-stated whole, so no rate is an empty list there, and changing the current phase changes the subscription
    at once (checked against Stripe's test API). A price no plan nor module has keeps its rates."""
    with payment_gates.stripe_errors():
        schedule = stripe_service.retrieve_schedule(schedule_id)
    now = int(timezone.now().timestamp())
    phases = []
    changed = False
    for phase in schedule.get("phases") or []:
        if phase.get("end_date") is not None and phase["end_date"] <= now:
            continue
        restated = _restated_items(hub, subscription, phase)
        if restated is None:
            return "refused"
        items, retaxed = restated
        changed = changed or retaxed
        phases.append(_restated_phase(phase, items))
    if not changed:
        return "unchanged"
    with payment_gates.stripe_errors():
        stripe_service.update_schedule(schedule_id, {"end_behavior": "release", "phases": phases})
    logger.info("[BILLING] Hub %s retaxed the phases of schedule %s", hub.id, schedule_id)
    return "retaxed"


def _restated_items(hub: Hub, subscription: Subscription, phase: dict) -> tuple[list[dict], bool] | None:
    """The items of a phase with today's rates, and whether any changed; ``None`` when one cannot be retaxed."""
    sales = []
    for item in phase.get("items") or []:
        price = item["price"] if isinstance(item["price"], str) else item["price"]["id"]
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in item.get("tax_rates") or []]
        sales.append(
            (price, item.get("quantity") or 1, held, stripe_sales._item_sale(subscription, {"price": {"id": price}}))
        )
    # What a renewal of that phase charges, net: the 400 € of the simplified invoice is on the whole of it.
    recurring = sum((sale.net for _price, _quantity, _held, sale in sales if sale is not None), Decimal("0"))
    items = []
    changed = False
    for price, quantity, held, sale in sales:
        due = held
        if sale is not None:
            try:
                due = stripe_sales.price_sale(hub, sale, recurring_net=recurring, renewing=True)
            except Conflict as refused:
                _retax_refused(hub, sale.kind, refused)
                return None
        changed = changed or sorted(held) != sorted(due)
        items.append({"price": price, "quantity": quantity, "tax_rates": due})
    return items, changed


def _restated_phase(phase: dict, items: list[dict]) -> dict:
    restated = {"items": items, "start_date": phase["start_date"], "proration_behavior": "none"}
    if phase.get("end_date") is not None:
        restated["end_date"] = phase["end_date"]
    if phase.get("trial_end"):
        restated["trial_end"] = phase["trial_end"]
    restated["discounts"] = discounts.held_discounts(phase)
    return restated


def retax_payer(profile_id) -> None:
    """After the owner saves the billing details (on commit): the payer's Stripe customer takes them
    and every business this payer pays is retaxed. A failure is logged and never
    stops the other: the next checkout brings the customer up to date (``ensure_customer``), the daily pass
    (``retax_subscriptions``) retaxes again."""
    paid = list(Hub.objects.filter(billing_profile_id=profile_id).order_by("pk"))
    try:
        stripe_customers.push_payer_to_stripe(profile_id)
    except Exception:  # noqa: BLE001 - the save stands; the next checkout updates the customer
        logger.exception(
            "[BILLING] The Stripe customer of payer %s did not take the new billing details",
            profile_id,
            extra={"event": "billing.customer_push_failed", "hub_id": str(paid[0].id) if paid else ""},
        )
    for hub in paid:
        try:
            retax_subscription(hub)
        except Exception:  # noqa: BLE001 - the save stands; the daily pass retaxes it
            logger.exception(
                "[BILLING] Hub %s could not be retaxed after its billing details changed",
                hub.id,
                extra={"event": "billing.retax_failed", "hub_id": str(hub.id)},
            )


def retax_live_subscriptions() -> Counter:
    """One daily pass: every live Stripe subscription takes the rates of today (an address change whose push
    failed, the OSS threshold crossed or a new year back to origin, a rate the table schedules). One business
    never stops the others."""
    counts = Counter({key: 0 for key in RETAX_COUNTS})
    live = (
        Subscription.objects.filter(status__in=RETAX_STATUSES)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in live:
        try:
            counts[retax_subscription(subscription.hub)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[BILLING] %s could not be retaxed",
                subscription.stripe_subscription_id,
                extra={"event": "billing.retax_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts
