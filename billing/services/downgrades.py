"""A plan change that gives the business less for its money waits for the end of the paid period, held in Stripe as
a schedule."""

import logging

from django.utils import timezone
from django.utils.translation import gettext as _
from live.errors import Conflict, OperationError

from billing import queries, stripe_service
from billing.models import PlanChangeSchedule
from billing.money import to_cents
from billing.services import discounts, payment_gates, stripe_sales, stripe_sync
from billing.stripe_period import subscription_period
from hubs.models import Hub, Plan, Subscription

logger = logging.getLogger("billing.services")


def is_downgrade(subscription: Subscription, sale: stripe_sales.Sale) -> bool:
    """Whether a plan change gives the business less for its money: annual → monthly, or a cheaper plan on the
    same billing. It waits for the end of the paid period: charged now it would credit the
    unused part of the dearer plan, a Stripe invoice with a negative total."""
    if subscription.billing_interval == Subscription.Interval.YEAR and sale.interval == "month":
        return True
    if sale.interval != subscription.billing_interval:
        return False

    def price(plan: Plan) -> int:
        return to_cents((plan.price_annual if sale.interval == "year" else plan.price_monthly) or 0)

    return price(sale.plan) < price(subscription.plan)


def pending_change(hub: Hub) -> PlanChangeSchedule | None:
    return PlanChangeSchedule.objects.filter(hub=hub).first()


def _require_no_pending_change(hub: Hub) -> None:
    """A module bought or cancelled while a downgrade waits would be dropped by the schedule's next phase."""
    if pending_change(hub) is not None:
        raise Conflict(
            _("The plan changes at the end of this period: keep the current plan first, then change the modules."),
            code="billing.plan_change_pending",
        )


def _release_pending(hub: Hub, live: dict | None = None) -> None:
    """Undo a downgrade that waits (or detach the schedule of one already applied): Stripe releases the
    schedule, the subscription keeps its items. A schedule Stripe no longer holds counts as released."""
    pending = pending_change(hub)
    attached = (live or {}).get("schedule")
    if isinstance(attached, dict):
        attached = attached.get("id")
    for schedule_id in dict.fromkeys(filter(None, [attached, pending.stripe_schedule_id if pending else None])):
        try:
            with payment_gates.stripe_errors():
                stripe_service.release_schedule(schedule_id)
        except OperationError as refused:
            if refused.code != "billing.stripe_refused":
                raise
            logger.warning("[BILLING] Schedule %s of hub %s was released already", schedule_id, hub.id)
    PlanChangeSchedule.objects.filter(hub=hub).delete()


def _phase_items(live: dict, replaced: dict[str, dict]) -> list[dict]:
    """The items of a schedule phase: the live ones, with ``replaced`` (item id → price and tax rates)."""
    items = []
    for line in stripe_sales._live_items(live):
        rates = [rate["id"] if isinstance(rate, dict) else rate for rate in line.get("tax_rates") or []]
        change = replaced.get(line["id"], {})
        items.append(
            {
                "price": change.get("price") or line["price"]["id"],
                "quantity": line.get("quantity") or 1,
                # A phase lists its items whole: no rate is an empty list there (``_rates_param`` is for updates).
                "tax_rates": change.get("tax_rates", rates) or [],
            }
        )
    return items


def _schedule_downgrade(hub: Hub, subscription: Subscription, live: dict, sale: stripe_sales.Sale, items: list[dict]) -> None:
    """Hold the downgrade in Stripe as a schedule: the current phase ends with the paid period, the next one
    bills ``items`` without proration (so no negative invoice), and the schedule then lets the subscription go
    on its own (``release``)."""
    _release_pending(hub, live)
    _start, period_end = subscription_period(live)
    with payment_gates.stripe_errors():
        made = stripe_service.create_schedule(subscription.stripe_subscription_id)
        phase = (made.get("phases") or [{}])[0]
        stripe_service.update_schedule(
            made["id"],
            {
                "end_behavior": "release",
                "phases": [
                    {
                        "items": _phase_items(live, {}),
                        "start_date": phase.get("start_date"),
                        "end_date": period_end,
                        "proration_behavior": "none",
                        "discounts": discounts.phase_discounts(live),
                    },
                    {
                        "items": _phase_items(live, {item["id"]: item for item in items if item.get("id")}),
                        "proration_behavior": "none",
                        "duration": {"interval": sale.interval, "interval_count": 1},
                        "discounts": discounts.phase_discounts(live),
                    },
                ],
            },
        )
    PlanChangeSchedule.objects.update_or_create(
        hub=hub,
        defaults={
            "stripe_schedule_id": made["id"],
            "plan_slug": sale.slug,
            "interval": sale.interval,
            "starts_at": stripe_sync._moment(period_end) or subscription.current_period_end or timezone.now(),
        },
    )


def _forget_applied_change(hub_id, live: dict) -> None:
    """Stripe started the next phase of a downgrade: the pending change is done, and its schedule is detached
    so the subscription takes any later change directly."""
    pending = PlanChangeSchedule.objects.filter(hub_id=hub_id).first()
    if pending is None:
        return
    item = stripe_sales._plan_item(live)
    found = queries.plan_for_price(item["price"]["id"]) if item else None
    if found is None or (found[0].slug, found[1]) != (pending.plan_slug, pending.interval):
        return
    _release_pending(Hub.objects.get(pk=hub_id), live)
