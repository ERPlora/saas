"""Promo codes at checkout: what a code grants a new subscription (trial days, or a discount as a Stripe coupon), the
code a checkout brings, and its use on a plan change (a checkout holds its use: ``promo_holds``)."""

from datetime import datetime, timedelta
from typing import NamedTuple

from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from live.errors import Conflict

from billing import queries
from billing.models import PromoCode, PromoRedemption, normalise_promo_code
from billing.services import discounts, promo_holds
from hubs.models import Hub, Subscription

#: Stripe refuses a Checkout trial that ends in less than 48 hours: a shorter one is not carried.
MIN_TRIAL = timedelta(hours=48)


class CheckoutTerms(NamedTuple):
    """What a promo code adds to a Checkout Session: its code, the session's ``subscription_data`` (a trial) and its
    own parameters (the coupon of its discount); the code and its coupon, for the hold of its use."""

    code: str
    subscription_data: dict
    params: dict
    promo: PromoCode | None = None
    coupon: discounts.Coupon | None = None


def redeem_promo(code: str | None, *, hub: Hub | None = None, customer: str = "") -> bool:
    """Count one use of ``code`` on a confirmed plan change (its trial days); ``False`` when unknown, at its cap, or
    already used by ``hub`` (once per business: the use is recorded, ``PromoRedemption``). The cap is in the UPDATE's
    WHERE, so two changes confirmed at once never pass it. A checkout holds its use instead (``promo_holds``)."""
    normalised = normalise_promo_code(code)
    if not normalised:
        return False
    promo = PromoCode.objects.filter(code=normalised).first()
    if promo is None:
        return False
    if hub is not None:
        _use, created = PromoRedemption.objects.get_or_create(
            promo=promo, hub=hub, defaults={"stripe_customer_id": customer or ""}
        )
        if not created:
            return False
    counted = (
        PromoCode.objects.filter(pk=promo.pk)
        .filter(Q(max_redemptions__isnull=True) | Q(redemption_count__lt=F("max_redemptions")))
        .update(redemption_count=F("redemption_count") + 1, updated_at=timezone.now())
    )
    return counted > 0


def trial_end(subscription: Subscription | None, promo: PromoCode | None, now: datetime) -> int | None:
    """When a plan bought by a free business starts charging: the days left of its sign-up trial, or the
    promo code's trial days, the later of the two; none under Stripe's 48 h."""
    ends = []
    if subscription is not None and subscription.trial_plan_id and subscription.trial_end:
        ends.append(subscription.trial_end)
    if promo is not None and promo.trial_days:
        ends.append(now + timedelta(days=promo.trial_days))
    end = max(ends, default=None)
    if end is None or end - now < MIN_TRIAL:
        return None
    return int(end.timestamp())


def checkout_terms(sale, subscription: Subscription | None, promo: PromoCode | None, now: datetime) -> CheckoutTerms:
    """What the Checkout Session of ``sale`` carries: the coupon of a code's discount, with the card asked for even
    when nothing is due today and never with a trial (a discount for months runs on the clock); otherwise the trial
    a plan gets (``trial_end``). Asks Stripe for the coupon."""
    code = promo.code if promo is not None else ""
    if promo is not None and promo.discount is not None:
        discounts.require_sale(promo.discount, sale)
        coupon = discounts.coupon_for(promo.discount, sale)
        params = {"discounts": [{"coupon": coupon.id}], "payment_method_collection": "always"}
        return CheckoutTerms(code, {}, params, promo, coupon)
    end = trial_end(subscription, promo, now) if sale.kind == "plan" else None
    return CheckoutTerms(code, {"trial_end": end} if end is not None else {}, {}, promo)


def checkout_promo(code: str, *, hub: Hub, customer: str) -> PromoCode | None:
    """The code a business starting to pay brings, or ``None`` without one. One it can no longer use (used up, used
    by it or its payer since it was checked, turned off) is said, never dropped in silence: the panel already
    promised what it gives."""
    if not normalise_promo_code(code):
        return None
    promo = queries.redeemable_promo(code, hub=hub, customer=customer)
    if promo is None:
        raise promo_holds.not_available()
    return promo


def plan_change_promo(code: str, *, hub: Hub, customer: str) -> PromoCode | None:
    """The code a plan change honours (its trial days). A discount is only for a business that starts paying."""
    promo = queries.redeemable_promo(code, hub=hub, customer=customer)
    if promo is not None and promo.discount is not None:
        raise Conflict(
            _("This code gives a discount to a business that starts paying a plan, not to a change of plan."),
            code="billing.promo_discount_new_subscription_only",
        )
    return promo
