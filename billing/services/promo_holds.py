"""A promo code's use, held by the checkout that offers it.

The coupon of a code's discount goes into the Checkout Session as it opens, so the use is taken then: within the
code's cap (in the ``UPDATE``'s ``WHERE``, which also holds the code's row until the COMMIT, so two checkouts never
take the same last use) and once per business and per payer, checked behind that lock. The paid checkout makes its
hold a use; one that closes unpaid gives it back, and a hold whose session can no longer be paid (``held_until``)
is given back by the next hold of its code or by ``sweep_unpaid``, so none is held for ever.
"""

import logging
from datetime import timedelta

from django.db.models import F, Q
from django.db.models.functions import Greatest
from django.utils import timezone
from django.utils.translation import gettext as _
from live.errors import Conflict
from live.operations import atomic

from billing.models import CheckoutAttempt, PromoCode, PromoRedemption, normalise_promo_code
from billing.services import discounts
from billing.stripe_coupons import discount_end, live_discounts
from hubs.models import Hub

logger = logging.getLogger("billing.services")

#: Stripe keeps a Checkout Session open 24 hours: after that it can no longer be paid.
HOLD_FOR = CheckoutAttempt.REUSE_FOR + timedelta(hours=2)


def not_available() -> Conflict:
    return Conflict(
        _("This code is not valid or has already been used: remove it to pay without it."),
        code="billing.promo_not_available",
    )


def hold(promo: PromoCode, attempt: CheckoutAttempt, *, customer: str, coupon: discounts.Coupon | None) -> None:
    """Take one use of ``promo`` for the checkout ``attempt`` of its business, paid by ``customer`` (409 when the
    code has no use left, or the business or its payer used or holds it). A business that opens another checkout
    while its own hold stands keeps that hold, now for the new checkout."""
    now = timezone.now()
    held = {
        "attempt": attempt,
        "stripe_customer_id": customer,
        "held_until": now + HOLD_FOR,
        "stripe_coupon_id": coupon.id if coupon is not None else "",
        "stripe_products": coupon.products if coupon is not None else [],
    }
    with atomic():
        _give_back(PromoRedemption.objects.filter(promo=promo, held_until__lte=now))
        mine = PromoRedemption.objects.filter(promo=promo, hub_id=attempt.hub_id, held_until__isnull=False)
        # The code's row stays locked until the COMMIT: by the UPDATE that takes a use, or here when the business
        # keeps the one it holds, so the checks below see every other hold.
        if mine.exists():
            PromoCode.objects.select_for_update().filter(pk=promo.pk).first()
        elif not _take_one(promo, now):
            raise not_available()
        used_by = Q(hub=attempt.hub_id) | Q(stripe_customer_id=customer) if customer else Q(hub=attempt.hub_id)
        if PromoRedemption.objects.filter(promo=promo).filter(used_by).exclude(pk__in=mine.values("pk")).exists():
            raise not_available()
        if not mine.update(**held):
            PromoRedemption.objects.create(promo=promo, hub_id=attempt.hub_id, **held)


def _take_one(promo: PromoCode, now) -> bool:
    """One more use of ``promo``, within its cap: the cap is in the ``WHERE``."""
    return bool(
        PromoCode.objects.filter(pk=promo.pk)
        .filter(Q(max_redemptions__isnull=True) | Q(redemption_count__lt=F("max_redemptions")))
        .update(redemption_count=F("redemption_count") + 1, updated_at=now)
    )


def use(code: str, *, hub: Hub, customer: str, session: str, live: dict) -> None:
    """The paid checkout of ``hub`` makes its hold of ``code`` a use, with the subscription it paid and when its
    discount ends. A hold given back before the payment arrived is still a use: Stripe gave the discount."""
    promo = PromoCode.objects.select_related("discount").filter(code=normalise_promo_code(code)).first()
    if promo is None:
        return
    paid = {
        "held_until": None,
        "stripe_session_id": session,
        "stripe_subscription_id": live.get("id") or "",
        "discount_ends_at": discount_end(live),
    }
    held = PromoRedemption.objects.filter(promo=promo, hub=hub).first()
    if held is None:
        logger.warning("[BILLING] Hub %s paid with code %s after its hold was given back: counted now", hub.id, code)
        ours = live_discounts(live)
        PromoRedemption.objects.create(
            promo=promo,
            hub=hub,
            stripe_customer_id=customer,
            stripe_coupon_id=ours[0]["source"]["coupon"] if ours else "",
            stripe_products=discounts.products_of(promo.discount) if promo.discount is not None else [],
            **paid,
        )
        PromoCode.objects.filter(pk=promo.pk).update(redemption_count=F("redemption_count") + 1)
    elif held.held_until is not None:
        PromoRedemption.objects.filter(pk=held.pk).update(stripe_customer_id=customer or held.stripe_customer_id,
                                                          **paid)


def release(*, attempt: CheckoutAttempt | None = None, session: str = "") -> int:
    """Give back the hold of a checkout that closed unpaid: its ``attempt``, or the one of its Stripe ``session``."""
    if attempt is None and not session:
        return 0
    held = PromoRedemption.objects.filter(held_until__isnull=False)
    held = held.filter(attempt=attempt) if attempt is not None else held.filter(attempt__stripe_session_id=session)
    return _give_back(held)


def release_stale() -> int:
    """Give back every hold whose session can no longer be paid (``sweep_unpaid``)."""
    return _give_back(PromoRedemption.objects.filter(held_until__lte=timezone.now()))


def _give_back(held) -> int:
    given = 0
    for pk, promo_id in held.values_list("pk", "promo_id"):
        # Whoever deletes the hold gives its use back, once.
        deleted, _rows = PromoRedemption.objects.filter(pk=pk, held_until__isnull=False).delete()
        if deleted:
            PromoCode.objects.filter(pk=promo_id).update(
                redemption_count=Greatest(F("redemption_count") - 1, 0), updated_at=timezone.now()
            )
            given += 1
    return given
