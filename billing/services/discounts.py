"""The discount of a promo code on a subscription: what it may be sold with, its coupon in Stripe, and what stays with
the subscription when it changes."""

import logging

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from live.errors import Conflict, OperationError

from billing import discount_terms
from billing.models import Discount
from billing.stripe_coupons import discount_end, ensure_coupon
from hubs.models import Plan

logger = logging.getLogger("billing.services")


def require_sale(discount: Discount, sale) -> None:
    """A code's discount on the plan a checkout sells: with a billing it goes with, on a plan it covers (409, before
    Stripe is asked)."""
    if sale.interval not in discount_terms.intervals(discount):
        raise Conflict(
            _("This code’s discount lasts a number of months: choose monthly billing to use it."),
            code="billing.discount_monthly_only",
        )
    if not discount_terms.covers(set(discount.plans.values_list("pk", flat=True)), sale.plan.pk):
        raise Conflict(_("This code does not apply to the plan chosen."), code="billing.discount_plan_not_covered")


def coupon_for(discount: Discount, sale) -> str:
    """The Stripe coupon of ``discount``, limited to the products of its plans (every paid plan's when it names none),
    so it never takes anything off a module. The plan sold needs its Stripe product: without it, 503."""
    if not sale.plan.stripe_product_id:
        logger.error(
            "[BILLING] Plan %s has no Stripe product: its checkout with a discount cannot open",
            sale.plan.slug,
            extra={"event": "billing.plan_without_stripe_product", "plan": sale.plan.slug},
        )
        raise OperationError(
            _("Payments are not available right now. Nothing was charged; try again later."),
            code="billing.payments_unavailable",
            status=503,
        )
    named = discount.plans.all() if discount.plans.exists() else Plan.objects.exclude(stripe_price_id="")
    products = sorted({plan.stripe_product_id for plan in named if plan.stripe_product_id})
    return ensure_coupon(discount, products)


def phase_discounts(live: dict) -> list[dict]:
    """The discounts of a live subscription for a phase of its schedule: the same ones, reused, so a discount for
    months keeps its end (a phase without them would drop them)."""
    return [
        {"discount": discount["id"] if isinstance(discount, dict) else discount}
        for discount in live.get("discounts") or []
    ]


def held_discounts(phase: dict) -> list[dict]:
    """The discounts a phase of a schedule carries, as they are sent back when its phases are re-stated."""
    return [
        {"discount": held["discount"]} if held.get("discount") else {"coupon": held["coupon"]}
        for held in phase.get("discounts") or []
        if held.get("discount") or held.get("coupon")
    ]


def require_annual_allowed(live: dict, subscription, sale) -> None:
    """Yearly billing waits for a discount for months to end: Stripe would take the whole year off."""
    if sale.interval != "year" or subscription.billing_interval == "year":
        return
    until = discount_end(live)
    if until is not None and until > timezone.now():
        raise Conflict(
            _("This business has a discount until %(date)s: it can move to yearly billing after that date.")
            % {"date": date_format(timezone.localtime(until), "DATE_FORMAT")},
            code="billing.discount_blocks_annual",
        )
