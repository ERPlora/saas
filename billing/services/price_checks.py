"""The Stripe prices pasted on a plan or a module are its own (the staff, in the admin)."""

from decimal import Decimal

from django.utils.translation import gettext as _

from billing import stripe_service
from billing.money import from_cents, to_cents
from billing.stripe_keys import StripeKeyMode


#: Each Stripe price of a plan: its field, the plan's amount it must charge and how often.
PLAN_PRICE_FIELDS = (("stripe_price_id", "price_monthly", "month"), ("stripe_price_id_annual", "price_annual", "year"))
#: The same for a paid module (``apps.Module``), whose amounts are already euro cents.
MODULE_PRICE_FIELDS = (
    ("stripe_price_id_monthly", "price_monthly_cents", "month"),
    ("stripe_price_id_annual", "price_annual_cents", "year"),
)


class PriceCheckUnavailable(Exception):
    """The prices could not be checked: said, never taken for a yes. One of the two below."""


class PriceCheckSkipped(PriceCheckUnavailable):
    """No usable Stripe key here (development): the admin saves and warns that nothing was checked."""


class PriceCheckFailed(PriceCheckUnavailable):
    """Stripe did not answer: the admin saves nothing and asks to try again."""


def plan_price_problems(*, prices: dict[str, str], amounts: dict[str, Decimal], product: str) -> dict[str, str]:
    """Why each Stripe price pasted on a plan would not sell it as the plan says, by field (empty = they do).

    A price must exist with this key's mode (a test id in production is not found), be active, in euros, charged
    every month or every year as its field says, the plan's amount, NET (``tax_behavior = exclusive``: our VAT goes
    on top, never Stripe's) and, when the plan names its product, of that product. Nothing pasted asks nothing."""
    return _price_problems(
        PLAN_PRICE_FIELDS,
        prices,
        {field: to_cents(amount or Decimal(0)) for field, amount in amounts.items()},
        product,
        lambda stripe, expected: _("Stripe charges %(stripe)s and the plan says %(plan)s.")
        % {"stripe": stripe, "plan": expected},
    )


def module_price_problems(*, prices: dict[str, str], amounts: dict[str, int], product: str) -> dict[str, str]:
    """The same checks as :func:`plan_price_problems`, for the Stripe prices pasted on a paid module, by the
    module's own fields; ``amounts`` are its net prices in euro cents (``price_monthly_cents``, ``price_annual_cents``)."""
    return _price_problems(
        MODULE_PRICE_FIELDS,
        prices,
        {field: int(amount or 0) for field, amount in amounts.items()},
        product,
        lambda stripe, expected: _("Stripe charges %(stripe)s and the module says %(module)s.")
        % {"stripe": stripe, "module": expected},
    )


def _price_problems(fields, prices: dict[str, str], cents: dict[str, int], product: str, other_amount) -> dict[str, str]:  # noqa: C901
    """The checks of a pasted Stripe price; ``other_amount(stripe, expected)`` words an amount that differs."""
    pasted = [(field, prices.get(field) or "", amount, interval) for field, amount, interval in fields]
    pasted = [row for row in pasted if row[1]]
    if not pasted:
        return {}
    if stripe_service.key_mode() is StripeKeyMode.UNKNOWN:
        raise PriceCheckSkipped(_("Stripe is not configured here: the prices were not checked."))
    problems: dict[str, str] = {}
    for field, price_id, amount_field, interval in pasted:
        try:
            price = stripe_service.retrieve_price(price_id)
        except stripe_service.StripeRefused:
            problems[field] = _("Stripe has no price %(id)s with these keys.") % {"id": price_id}
            continue
        except stripe_service.StripeUnavailable as failed:
            raise PriceCheckFailed(_("Stripe did not answer: the prices were not checked. Try again.")) from failed
        expected = cents.get(amount_field) or 0
        recurring = price.get("recurring") or {}
        if not price.get("active"):
            problems[field] = _("This price is archived in Stripe.")
        elif (price.get("currency") or "").lower() != "eur":
            problems[field] = _("This price is not in euros.")
        elif recurring.get("interval") != interval or recurring.get("interval_count", 1) != 1:
            problems[field] = (
                _("This price is not charged every month.") if interval == "month" else _("This price is not charged every year.")
            )
        elif price.get("unit_amount") != expected:
            problems[field] = other_amount(from_cents(price.get("unit_amount") or 0), from_cents(expected))
        elif price.get("tax_behavior") != "exclusive":
            problems[field] = _("This price includes the VAT or does not say: it must be net (tax behaviour «exclusive»).")
        elif product and price.get("product") != product:
            problems[field] = _("This price is of another Stripe product.")
    return problems
