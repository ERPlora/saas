"""Promo codes at checkout: what a code grants a new subscription (trial days, or free months as a Stripe coupon),
its use once the checkout is paid, and what a business may not change while its free months last."""

from datetime import datetime, timedelta
from typing import NamedTuple

from django.db.models import F, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from live.errors import Conflict

from billing import queries
from billing.models import PromoCode, PromoRedemption, normalise_promo_code
from billing.stripe_coupons import ensure_free_months_coupon, free_months_end
from hubs.models import Hub, Subscription

#: Stripe refuses a Checkout trial that ends in less than 48 hours: a shorter one is not carried.
MIN_TRIAL = timedelta(hours=48)


class CheckoutTerms(NamedTuple):
    """What a promo code adds to a Checkout Session: its code, the session's ``subscription_data`` (a trial) and its
    own parameters (the coupon of free months)."""

    code: str
    subscription_data: dict
    params: dict


def redeem_promo(
    code: str | None, *, hub: Hub | None = None, customer: str = "", session: str = "", free_until: datetime | None = None
) -> bool:
    """Count one redemption of ``code``; ``False`` when unknown, at its cap, or already used by ``hub`` (once
    per business: the use is recorded, ``PromoRedemption``, with when its free months end). The cap is in the
    UPDATE's WHERE, so two checkouts completing at once never pass it (the trial was granted when each session
    opened: two people taking the last seat at once both get it, only one is counted)."""
    normalised = normalise_promo_code(code)
    if not normalised:
        return False
    promo = PromoCode.objects.filter(code=normalised).first()
    if promo is None:
        return False
    if hub is not None:
        _use, created = PromoRedemption.objects.get_or_create(
            promo=promo,
            hub=hub,
            defaults={"stripe_customer_id": customer or "", "stripe_session_id": session or "", "free_until": free_until},
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
    """What the Checkout Session of ``sale`` carries: the coupon of a code's free months on a monthly plan, with the
    card asked for although nothing is due today and never with a trial (the coupon runs on the clock); otherwise
    the trial a plan gets (``trial_end``). Asks Stripe for the coupon."""
    code = promo.code if promo is not None else ""
    if promo is not None and promo.free_months is not None:
        if sale.interval != "month":
            raise Conflict(
                _("This code gives free months of a monthly plan: choose monthly billing to use it."),
                code="billing.promo_monthly_only",
            )
        coupon = ensure_free_months_coupon(promo.free_months)
        return CheckoutTerms(code, {}, {"discounts": [{"coupon": coupon}], "payment_method_collection": "always"})
    end = trial_end(subscription, promo, now) if sale.kind == "plan" else None
    return CheckoutTerms(code, {"trial_end": end} if end is not None else {}, {})


def plan_change_promo(code: str, *, hub: Hub, customer: str) -> PromoCode | None:
    """The code a plan change honours (its trial days). Free months are only for a business that starts paying."""
    promo = queries.redeemable_promo(code, hub=hub, customer=customer)
    if promo is not None and promo.free_months is not None:
        raise Conflict(
            _("This code gives free months to a business that starts paying a plan, not to a change of plan."),
            code="billing.promo_new_subscription_only",
        )
    return promo


def require_no_free_months(live: dict) -> None:
    """While the free months of a live subscription last, its plan, its billing and its modules stay as they are:
    the coupon would make any change free too. Cancelling is still allowed."""
    until = free_months_end(live)
    if until is not None and until > timezone.now():
        raise Conflict(
            _(
                "This business has free months until %(date)s: until then its plan, its billing and its apps stay as "
                "they are. You can still cancel the plan."
            )
            % {"date": date_format(timezone.localtime(until), "DATE_FORMAT")},
            code="billing.free_months_active",
        )
