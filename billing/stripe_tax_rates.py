"""What Stripe must charge for a quote OUR engine resolved, in Stripe's vocabulary (saas#1968).

Ported from ERPlora/saas ``apps/dashboard/fiscal/services/stripe_tax_rates.py`` (origin/develop) without the
calls to Stripe, which live in the gateway (``billing.stripe_service``). The rate of every sale is decided by ``billing.TaxRule``; Stripe only
charges it, and on a net price it needs it as a ``TaxRate`` object (the only thing ``default_tax_rates``
accepts). This is the opposite of ``automatic_tax``, where Stripe's own registrations pick the rate and get
it wrong silently (a German consumer paid 0 € of VAT, saas#1478).

Here: ``tax_rate_specs_for`` says WHICH ``TaxRate`` a quote needs, and ``matches`` whether an existing one
is it. The Stripe side is ``billing.stripe_service.tax_rate_ids`` (lot L2-B): the id cached under
``spec.cache_key`` (24 h: a rate never changes its value, only someone archiving it in the dashboard can), else
the first active ``TaxRate`` of the account that ``matches``, else a new one (``display_name``,
``description``, ``percentage``, ``inclusive=False``, ``country``, ``tax_type``). A failed listing is NOT
swallowed (creating blind fills the account with duplicate 21 %): the sale is refused while Stripe does not
answer (503 ``billing.stripe_unavailable``).
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from billing.vat import VatBreakdown


@dataclass(frozen=True)
class TaxRateSpec:
    """A Stripe ``TaxRate`` as our engine wants it: always on top of the net price (``inclusive=False``)."""

    country: str
    region: str
    percentage: Decimal
    inclusive: bool = False
    tax_type: str = "vat"

    @property
    def display_name(self) -> str:
        """Seen by the buyer in the checkout and on Stripe's receipt. One ``TaxRate`` is shared by every
        buyer, so it cannot follow a language: the tax's name in the country that charges it."""
        return "IVA" if self.country.upper() == "ES" else "VAT"

    @property
    def description(self) -> str:
        where = f"{self.country}/{self.region}" if self.region else self.country
        return f"ERPlora — {where} {self.percentage}%"

    @property
    def cache_key(self) -> str:
        return f"billing:stripe-tax-rate:{self.country}:{self.region}:{self.percentage:.4f}"


def tax_rate_specs_for(quote: VatBreakdown) -> list[TaxRateSpec]:
    """The ``TaxRate`` that make Stripe charge the tax of ``quote``.

    An empty list = nothing is added, as good an answer as a rate: the Canary Islands, Ceuta and Melilla
    are outside the scope of VAT, and the reverse charge is declared by the customer.
    """
    rate = Decimal(quote.rate or 0)
    if not quote.is_subject or rate <= 0:
        return []
    return [
        TaxRateSpec(
            country=quote.tax_country.upper(),
            region=quote.tax_region.upper(),
            percentage=rate,
        )
    ]


def matches(existing, spec: TaxRateSpec) -> bool:
    """Is this Stripe ``TaxRate`` exactly ``spec``, and on top of the net price?

    ``inclusive`` matters as much as the percentage: an inclusive 21 % on a net price charges the net and
    gives the quota away.
    """
    if getattr(existing, "inclusive", None) is not False:
        return False
    if str(getattr(existing, "country", "") or "").upper() != spec.country.upper():
        return False
    try:
        percentage = Decimal(str(getattr(existing, "percentage", "")))
    except InvalidOperation:
        # An unreadable percentage is not ours.
        return False
    return percentage == spec.percentage
