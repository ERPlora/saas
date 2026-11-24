"""How a charged amount splits into base and quota, and the treatments a sale is qualified with."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# The VAT engine logs under one name: its alerts and tests listen to it.
logger = logging.getLogger("billing.vat")

DOMESTIC = "domestic"
OSS = "oss"
REVERSE_CHARGE = "reverse_charge"
NOT_SUBJECT = "not_subject"
#: Subject but exempt (art. 20 LIVA): never returned by ``resolve_vat``; stamped by hand on a line.
EXEMPT = "exempt"

#: The treatments that charge VAT, so carry a rate and a quota. The rest declare the whole amount as base.
TREATMENTS_WITH_RATE = frozenset({DOMESTIC, OSS})

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class VatBreakdown:
    """Base, quota, rate and qualification. ``base + tax`` is always the gross."""

    base: Decimal
    tax: Decimal
    rate: Decimal
    tax_country: str
    treatment: str = DOMESTIC
    tax_region: str = ""
    #: The quota was NOT charged by the gateway: it was taken out of the amount charged as VAT-inclusive
    #: A FACT of the breakdown, so the invoice can say why its base is not the plan's price.
    vat_included_reconciled: bool = False

    @property
    def is_reverse_charge(self) -> bool:
        return self.treatment == REVERSE_CHARGE

    @property
    def is_subject(self) -> bool:
        return self.treatment in TREATMENTS_WITH_RATE


@dataclass(frozen=True)
class _Qualification:
    """How a sale is taxed, decided WITHOUT looking at the amount: one place for ``resolve_vat`` (what was
    charged) and ``quote_vat`` (what will be charged), so the two cannot qualify the same sale apart."""

    treatment: str
    rate: Decimal | None
    tax_country: str
    tax_region: str
    customer_country: str = ""

    def breakdown(
        self, base: Decimal, tax: Decimal, rate: Decimal, *, reconciled: bool = False
    ) -> VatBreakdown:
        """The breakdown of an amount of this sale."""
        return VatBreakdown(
            base=base,
            tax=tax,
            rate=rate,
            tax_country=self.tax_country,
            treatment=self.treatment,
            tax_region=self.tax_region,
            vat_included_reconciled=reconciled,
        )


def _q(value: Decimal) -> Decimal:
    # Explicit HALF_UP: a bare quantize() inherits HALF_EVEN from the context.
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def split_gross(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Base and quota of an amount with the VAT inside; ``base + quota == gross``.

    The quota is derived BY SUBTRACTION, so the sum rebuilds the gross exactly even when rounding the base
    moved a cent: matching what was charged matters more than matching the rate.
    """
    gross = _q(Decimal(gross))
    rate = Decimal(rate or 0)
    if rate <= 0:
        return gross, Decimal("0.00")
    base = _q(gross / (Decimal("1") + rate / Decimal("100")))
    return base, gross - base


def add_vat(net: Decimal, rate: Decimal) -> Decimal:
    """The total to charge, adding ``rate`` to a NET amount: the one arithmetic of «€29.99 + VAT»."""
    net = _q(Decimal(net))
    rate = Decimal(rate or 0)
    if rate <= 0:
        return net
    return _q(net * (Decimal("1") + rate / Decimal("100")))


def _effective_rate(gross: Decimal, tax_cents: int) -> Decimal:
    """The rate an amount and its quota imply (``0.00`` without a base)."""
    tax = _q(Decimal(tax_cents) / Decimal("100"))
    base = gross - tax
    return _q(tax / base * Decimal("100")) if base else Decimal("0.00")


def _report_stripe_charged_no_tax(gross: Decimal, sale: _Qualification) -> None:
    """A subject sale on which Stripe collected nothing: always a structured ERROR (alert on ``event``).

    Two misconfigurations end here —a sale that reached Stripe without our rate and a VAT id
    Stripe reverse charged by its format while VIES had not confirmed it— and both are silent
    on Stripe's side. The sale is reconciled out of our own margin until it is fixed.
    """
    logger.error(
        "[VAT] Stripe charged no tax on a %s sale of %s EUR at %s%% to a %s customer: reconciled as "
        "VAT-inclusive, so the quota comes out of our margin. Check the tax rules, the mirrored TaxRate in "
        "Stripe, FiscalPolicy.intra_eu_reverse_charge and the customer's VIES verdict",
        sale.treatment,
        gross,
        sale.rate,
        sale.customer_country or "?",
        extra={
            "event": "fiscal.vat.stripe_charged_no_tax_on_subject_sale",
            "treatment": sale.treatment,
            "gross": str(gross),
            "expected_rate": str(sale.rate),
            "tax_country": sale.tax_country,
            "customer_country": sale.customer_country,
            "reconciled": True,
        },
    )


def _breakdown(
    gross: Decimal, sale: _Qualification, *, tax_cents: int = 0, tax_included: bool = True
) -> VatBreakdown:
    """Split the amount charged between base and quota by how the sale is qualified."""
    if sale.rate is None:
        # Not subject / reverse charge: all of it is base, there is no quota.
        return sale.breakdown(gross, Decimal("0.00"), Decimal("0.00"))

    reconciled = False
    if not tax_included and not tax_cents and gross:
        # NET price and Stripe charged no tax on a sale OUR qualification says is SUBJECT: reconcile.
        # A Spanish domestic sale at 0 % does not exist; what was charged becomes
        # VAT-inclusive, as the tax office does when VAT was not charged (TJUE C-249/12 and C-250/12,
        # Tulică; art. 78.Cuatro LIVA). The total does not move; the quota comes out of our margin.
        _report_stripe_charged_no_tax(gross, sale)
        reconciled = True

    if tax_cents:
        # Stripe already split it: its amounts rule.
        tax = _q(Decimal(tax_cents) / Decimal("100"))
        return sale.breakdown(gross - tax, tax, _effective_rate(gross, tax_cents))

    base, tax = split_gross(gross, sale.rate)
    return sale.breakdown(base, tax, sale.rate, reconciled=reconciled)
