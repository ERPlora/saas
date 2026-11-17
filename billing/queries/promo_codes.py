"""Promo codes: the code a checkout may redeem and the operation ``billing.promo.check``."""

from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext as _
from django_ratelimit.core import is_ratelimited
from live.context import OperationContext
from live.errors import OperationError, Unauthorized
from live.operations import AI, operation

from billing import discount_terms
from billing.models import Discount, PromoCode, PromoRedemption, normalise_promo_code
from billing.schemas.promo_codes import PromoCheckIn, PromoCheckOut


# --- Promo codes --------------------------------------------------------------------------------------

#: The per-person budget of ``billing.promo.check``.
PROMO_CHECK_GROUP = "billing.promo-check"


def redeemable_promo(
    code: str | None, *, hub=None, customer: str = ""
) -> PromoCode | None:
    """The promo code that grants something now, or ``None``: unknown, inactive (or its discount), expired and exhausted are all
    ``None``, because none of them may block a sale (a bad code is simply not applied). With ``hub`` (and its
    payer's Stripe ``customer``), also ``None`` once that business or that payer used it."""
    normalised = normalise_promo_code(code)
    if not normalised:
        return None
    promo = PromoCode.objects.select_related("discount").filter(code=normalised).first()
    if promo is None or not promo.is_redeemable:
        return None
    if hub is not None:
        used_by = (
            Q(hub=hub) | Q(stripe_customer_id=customer) if customer else Q(hub=hub)
        )
        if PromoRedemption.objects.filter(promo=promo).filter(used_by).exists():
            return None
    return promo


@operation(
    "billing.promo.check",
    kind="query",
    permission="billing.view",
    input=PromoCheckIn,
    output=PromoCheckOut,
    ai=AI(
        description="Whether a promo code is valid now and what it grants: trial days or a discount.",
        asks={
            "en": (
                "is the code SUMMER26 valid?",
                "does this promo code still work?",
                "what do I get with code WELCOME?",
            ),
            "es": ("¿sirve el código VERANO26?", "¿este cupón sigue valiendo?", "¿qué me da el código de bienvenida?"),
        },
    ),
)
def promo_check(ctx: OperationContext, params: PromoCheckIn) -> dict:
    """Whether a promo code grants a trial now, before paying (the store). An invalid code is an answer, not
    an error; asking too often is a 429, so codes cannot be guessed by brute force."""
    account = ctx.actor
    if getattr(account, "pk", None) is None:
        raise Unauthorized(_("Sign in to use a promo code."))
    if is_ratelimited(
        None,
        group=PROMO_CHECK_GROUP,
        key=lambda group, request: f"user:{account.pk}",
        rate=settings.PROMO_CHECK_RATE,
        increment=True,
    ):
        raise OperationError(
            _("Too many promo codes tried in the last minute. Try again in a moment."),
            code="billing.promo_check_throttled",
            status=429,
        )
    code = normalise_promo_code(params.code)
    promo = redeemable_promo(code)
    return {
        "code": code,
        "valid": promo is not None,
        "trial_days": (promo.trial_days if promo else None) or 0,
        "discount": discount_out(promo.discount) if promo is not None and promo.discount is not None else None,
    }


def discount_out(discount: Discount) -> dict:
    """``DiscountOut``: its terms and what it applies to, as the panel says them."""
    return {
        "percent_off": discount.percent_off,
        "amount_off_cents": discount.amount_off_cents,
        "currency": discount.currency,
        "duration": discount.duration,
        "duration_in_months": discount.duration_in_months,
        "applies_to": {
            "kind": discount.applies_to,
            "plans": sorted(discount.plans.values_list("slug", flat=True)),
            "intervals": list(discount_terms.intervals(discount)),
        },
    }
