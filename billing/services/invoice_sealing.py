"""What an invoice and a rectifying invoice share when they are recorded from Stripe: a Stripe line read as a line
of ERPlora's invoice, its amounts sealed by the qualification of the sale, the check that the lines add up to
what Stripe charged, and the answer of a record."""

import logging
from datetime import datetime
from decimal import Decimal

from billing import queries, vat, vat_breakdown
from billing.models import Invoice, InvoiceLine
from billing.money import from_cents, to_cents
from billing.services import stripe_sync

logger = logging.getLogger("billing.services")


def _moment_or_none(value) -> datetime | None:
    return stripe_sync._moment(int(value)) if value else None


def _price_of(line: dict) -> str:
    """The Stripe price a line bills: under ``pricing.price_details`` since the 2025 API, ``price`` before."""
    price = ((line.get("pricing") or {}).get("price_details") or {}).get("price") or line.get("price") or ""
    return price.get("id", "") if isinstance(price, dict) else price


def _is_proration(line: dict) -> bool:
    details = (line.get("parent") or {}).get("subscription_item_details") or {}
    return bool(details.get("proration") or line.get("proration"))


def _line_tax_cents(line: dict) -> int:
    """The tax Stripe charged on a line (``taxes`` since the 2025 API, ``tax_amounts`` before)."""
    taxes = line.get("taxes")
    if taxes is None:
        taxes = line.get("tax_amounts") or []
    return sum(int(tax.get("amount") or 0) for tax in taxes)


def _item_of(price_id: str) -> tuple[str, str, str]:
    """What a line sells: ``(kind, slug, tax category)``."""
    if (found := queries.plan_for_price(price_id)) is not None:
        return InvoiceLine.ItemKind.PLAN, found[0].slug, vat.SAAS_SUBSCRIPTION_CATEGORY
    if (found := queries.module_for_price(price_id)) is not None:
        return InvoiceLine.ItemKind.MODULE, found[0].slug, vat.SOFTWARE_LICENSE_CATEGORY
    return InvoiceLine.ItemKind.OTHER, "", vat.SAAS_SUBSCRIPTION_CATEGORY


def _nominal_rate(breakdown: vat_breakdown.VatBreakdown, category: str) -> Decimal:
    """The rate of the rule in force for what is sold where the sale is taxed (the declared rate: Stripe's
    effective one moves a hundredth with the rounding)."""
    rate = vat.vat_rate_for(country=breakdown.tax_country, region=breakdown.tax_region, category_key=category)
    return rate if rate is not None else breakdown.rate


def _sealed_amounts(amount: int, tax: int, *, treatment: str, rate: Decimal, reconciled: bool) -> tuple[Decimal, int, int]:
    """``(rate, net, tax)`` of a line in cents, by the qualification of the sale: without a rate (reverse
    charge, not subject) all of it is base; reconciled (Stripe charged no tax on a subject sale) the VAT comes
    out of the amount charged; otherwise Stripe's amounts rule."""
    if treatment not in vat_breakdown.TREATMENTS_WITH_RATE:
        return Decimal("0.00"), amount + tax, 0
    if reconciled:
        base, _quota = vat_breakdown.split_gross(from_cents(amount + tax), rate)
        net = to_cents(base)
        return rate, net, amount + tax - net
    return rate, amount, tax


def _record_out(invoice: Invoice | None, outcome: str) -> dict:
    return {
        "id": invoice.id if invoice else None,
        "number": invoice.number if invoice else "",
        "payment_status": invoice.payment_status if invoice else "",
        "outcome": outcome,
    }


class InvoiceDoesNotAddUp(Exception):
    """The lines of a Stripe document do not add up to what it charged or credited: nothing is invoiced (a 500
    for Stripe's retry and support's ERROR), never a different amount."""


def _require_adds_up(source, lines_total: int, stripe_total: int, hub_id) -> None:
    if lines_total != stripe_total:
        logger.error(
            "[INVOICE] The lines of Stripe's %s add up to %s, Stripe charged %s: nothing is invoiced",
            source, lines_total, stripe_total,
            extra={"event": "fiscal.invoice.lines_do_not_add_up", "hub_id": str(hub_id)},
        )
        raise InvoiceDoesNotAddUp(source)
