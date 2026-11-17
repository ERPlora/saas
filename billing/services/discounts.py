"""The discount of a promo code on a subscription: what it may be sold with, its coupon in Stripe, and what stays with
the subscription when it changes."""

import copy
import logging
from typing import NamedTuple

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from live.errors import Conflict, OperationError

from billing import discount_terms
from billing.models import Discount, PromoRedemption
from billing.stripe_coupons import discount_end, ensure_coupon, live_discounts
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


class Coupon(NamedTuple):
    """The Stripe coupon a checkout carries, and the products it covers: what Stripe will discount."""

    id: str
    products: list[str]


def products_of(discount: Discount) -> list[str]:
    """The Stripe products of the plans ``discount`` names, or of every plan that has one when it names none."""
    named = discount.plans.all() if discount.plans.exists() else Plan.objects.exclude(stripe_product_id="")
    return sorted({plan.stripe_product_id for plan in named if plan.stripe_product_id})


def coupon_for(discount: Discount, sale) -> Coupon:
    """The Stripe coupon of ``discount``, limited to the products of its plans (every plan's when it names none), so
    it never takes anything off a module. The plan sold needs its Stripe product: without it, 503."""
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
    products = products_of(discount)
    return Coupon(ensure_coupon(discount, products), products)


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


def takeover_discounts(subscription_id: str, live: dict) -> list[dict]:
    """What the new owner's checkout carries of the discount a business has (``live``, its running subscription): it
    was given to the business, so what is left of it goes on. A Checkout Session takes a coupon, never a running
    discount, so one forever goes on as it was, one for months as a coupon of the whole months left (none under
    one, so it never runs past its end), and one spent on the first payment does not come back."""
    redemption = (
        PromoRedemption.objects.select_related("promo__discount")
        .filter(stripe_subscription_id=subscription_id, held_until__isnull=True)
        .exclude(promo__discount=None)
        .first()
    )
    if redemption is None or not live_discounts(live):
        return []
    discount = redemption.promo.discount
    products = redemption.stripe_products or products_of(discount)
    if discount.duration == Discount.Duration.FOREVER:
        return [{"coupon": ensure_coupon(discount, products)}]
    until = discount_end(live)
    months = discount_terms.whole_months(timezone.now(), until) if until is not None else 0
    if discount.duration != Discount.Duration.REPEATING or months < 1:
        return []
    left = copy.copy(discount)
    left.duration_in_months = months
    return [{"coupon": ensure_coupon(left, products)}]


def move_redemption(replaced: str, live: dict) -> None:
    """The use of a code moves with the business to the subscription that replaced ``replaced`` (``live``), with
    when what went over ends; nothing went over, it ends now."""
    carried = live_discounts(live)
    PromoRedemption.objects.filter(stripe_subscription_id=replaced, held_until__isnull=True).update(
        stripe_subscription_id=live.get("id") or "",
        discount_ends_at=discount_end(live) if carried else timezone.now(),
    )
