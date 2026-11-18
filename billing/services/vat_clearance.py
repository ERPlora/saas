"""The VIES verdict of a VAT number: asked, logged and cleared for the payment gateway.

Every VIES query is a NEW ``VatCheck`` row: the log is the proof and is never rewritten. A current proof
(``grants_reverse_charge``) is reused for 30 days; anything else —invalid, unavailable, expired— is asked
again on the next need, so an ``unavailable`` never sticks. Only a query really sent to VIES spends
the budget: the person's (``VAT_CHECK_RATE``) when a person asks, and everybody's
(``VAT_CHECK_GLOBAL_RATE``) always.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from django_ratelimit.core import is_ratelimited

from billing import queries, vat, vies
from billing.models import VatCheck

logger = logging.getLogger("billing.services")

#: The person's VIES budget, for every door a person spends a query from (the panel's check and the
#: admin's «Check now in VIES»), keyed by the account, never by address.
VAT_CHECK_GROUP = "billing.vat-check"
#: Everybody's budget: every query is under ERPlora's one requester number.
VAT_CHECK_GLOBAL_GROUP = "billing.vat-check-global"


class VatCheckNotRecorded(Exception):
    """VIES answered but the answer could not be logged: it proves nothing, so it is not used."""


class VatCheckThrottled(Exception):
    """The budget is spent (the person's or everybody's): nothing was asked."""


CLEARANCE_ABSENT = "absent"
#: The issuer's own country: it can never be reverse charge, so it travels without asking.
CLEARANCE_NATIONAL = "national"
#: Checked in VIES, current and WITH PROOF (consultation number or manual override).
CLEARANCE_VERIFIED = "verified"
CLEARANCE_INVALID = "invalid"
#: The Commission did not answer, or answered without proof.
CLEARANCE_UNAVAILABLE = "unavailable"
#: An HMRC number (``GB``/``XI``): VIES cannot answer and no rate depends on it.
CLEARANCE_OUTSIDE_VIES = "outside_vies"


@dataclass(frozen=True)
class TaxIdClearance:
    """Whether a VAT number may travel to the payment gateway, and why.

    Stripe applies reverse charge by the FORMAT of the number, without waiting for VIES: handing it an
    unchecked number gives away 21 % of the sale. Only three verdicts let the number out: proved in VIES,
    national (never reverse charge) and British (outside VIES, and the rate travels explicit). Whether the
    SALE is reverse charged also depends on the payer's country and the ROI (``vat.reverse_charge_applies``).
    """

    status: str
    vat_number: str = ""
    check: VatCheck | None = None
    #: VIES was asked now (a new row of the log), not answered from a current proof on file.
    asked: bool = False

    @property
    def may_travel_to_stripe(self) -> bool:
        return self.status in (
            CLEARANCE_NATIONAL,
            CLEARANCE_VERIFIED,
            CLEARANCE_OUTSIDE_VIES,
        )

    @property
    def verified(self) -> bool:
        """VIES proved the number (current, with its consultation number or a manual override)."""
        return self.status == CLEARANCE_VERIFIED


def _issuer_country() -> str:
    return (
        (queries.fiscal_policy().issuer_country or vat.DEFAULT_ISSUER_COUNTRY)
        .strip()
        .upper()
    )


def _budget_spent(spender) -> bool:
    """Spend one query of ``spender``'s budget (when a person asks) and of everybody's; ``True`` when
    either is spent. Called only right before a query is really sent."""
    if spender is not None and is_ratelimited(
        None,
        group=VAT_CHECK_GROUP,
        key=lambda group, request: f"user:{spender.pk}",
        rate=settings.VAT_CHECK_RATE,
        increment=True,
    ):
        logger.warning(
            "[VIES] Account %s spent its VIES budget for this minute", spender.pk
        )
        return True
    if is_ratelimited(
        None,
        group=VAT_CHECK_GLOBAL_GROUP,
        key=lambda group, request: "everybody",
        rate=settings.VAT_CHECK_GLOBAL_RATE,
        increment=True,
    ):
        logger.error(
            "[VIES] The global VIES budget is spent for this minute: nothing more is asked until it refills"
        )
        return True
    return False


def record_vat_check(vat_number: str, **fields) -> VatCheck:
    """Log one query. Each query is a row: the log is the proof. A row that cannot be written raises
    ``VatCheckNotRecorded`` (in a savepoint, so the caller's transaction stays usable)."""
    check = VatCheck(
        vat_number=vies.normalise(vat_number), requested_at=timezone.now(), **fields
    )
    try:
        with transaction.atomic():
            check.save()
    except DatabaseError as error:
        logger.exception(
            "[VIES] The query about %s could not be logged, so it proves nothing",
            check.vat_number,
        )
        raise VatCheckNotRecorded(check.vat_number) from error
    return check


def check_vat_number(vat_number: str, *, spender=None) -> VatCheck:
    """Ask VIES NOW as the identified requester and log the answer. Never an anonymous query: it brings
    no consultation number, so it proves nothing. ``spender`` is the account that asked
    (its budget is spent too); ``VatCheckThrottled`` when a budget is spent, before asking."""
    value = vies.normalise(vat_number)
    if not vies.split_vat_number(value)[0]:
        logger.warning(
            "[VIES] '%s' has no VAT number's shape; it is not asked about", value
        )
        return record_vat_check(value, status=VatCheck.INVALID)
    requester = queries.vies_requester()
    if requester is None:
        logger.error(
            "[VIES] Without the issuer's own VAT number (CompanyConfig) %s is not asked about: an anonymous "
            "query brings no consultation number. Fill ERPlora's identity in the admin",
            value,
        )
        return record_vat_check(value, status=VatCheck.UNAVAILABLE)
    if _budget_spent(spender):
        raise VatCheckThrottled(value)
    answer = vies.ask(value, requester=requester)
    return record_vat_check(
        value,
        status=answer.status,
        consultation_number=answer.consultation_number,
        returned_name=answer.name,
        returned_address=answer.address,
    )


def verify_customer_vat(
    vat_number: str, *, customer_country: str = "", spender=None
) -> VatCheck | None:
    """The verdict of a VAT number, asking VIES when needed; ``None`` when there is nothing to ask (no
    number, a national one or HMRC's). THE door: the qualification looks at nothing else."""
    issuer = _issuer_country()
    value = vies.with_country_prefix(
        vat_number, customer_country, issuer_country=issuer
    )
    if not value:
        return None
    if vies.is_domestic_vat_number(
        value, issuer_country=issuer, customer_country=customer_country
    ):
        return None
    if (
        vies.is_uk_vat_number(value)
        or (customer_country or "").strip().upper() in vies.UK_PREFIXES
    ):
        return None
    current = queries.latest_vat_check(value)
    if current is not None and current.grants_reverse_charge:
        return current
    return check_vat_number(value, spender=spender)


def _clearance(
    vat_number: str, *, customer_country: str = "", spender=None
) -> TaxIdClearance:
    """The clearance of a number; raises ``VatCheckNotRecorded`` or ``VatCheckThrottled``."""
    value = vies.with_country_prefix(
        vat_number, customer_country, issuer_country=_issuer_country()
    )
    if not value:
        return TaxIdClearance(CLEARANCE_ABSENT)
    if (
        vies.is_uk_vat_number(value)
        or (customer_country or "").strip().upper() in vies.UK_PREFIXES
    ):
        return TaxIdClearance(CLEARANCE_OUTSIDE_VIES, value)
    before = queries.latest_vat_check(value)
    check = verify_customer_vat(
        value, customer_country=customer_country, spender=spender
    )
    if check is None:
        return TaxIdClearance(CLEARANCE_NATIONAL, value)
    asked = before is None or check.pk != before.pk
    if check.grants_reverse_charge:
        return TaxIdClearance(CLEARANCE_VERIFIED, value, check, asked)
    status = (
        CLEARANCE_INVALID if check.status == VatCheck.INVALID else CLEARANCE_UNAVAILABLE
    )
    return TaxIdClearance(status, value, check, asked)


def clear_tax_id_for_stripe(
    vat_number: str, *, customer_country: str = ""
) -> TaxIdClearance:
    """May this VAT number travel to the gateway? Asked BEFORE charging; never raises nor blocks the sale:
    an answer that could not be logged, or a spent global budget, is ``unavailable`` (the VAT is
    charged), and said so."""
    try:
        return _clearance(vat_number, customer_country=customer_country)
    except (VatCheckNotRecorded, VatCheckThrottled) as reason:
        logger.error(
            "[VIES] No verdict for %s before the sale (%s): it is charged with VAT",
            vies.normalise(vat_number),
            type(reason).__name__,
        )
        return TaxIdClearance(CLEARANCE_UNAVAILABLE, vies.normalise(vat_number))


def record_manual_override(vat_number: str, *, by: str, reason: str) -> VatCheck:
    """Mark a VAT number valid BY HAND, with author and reason: the company incorporated last
    week that is not in VIES yet. The only way to invoice at 0 % without the Commission's answer, so
    somebody must answer for it."""
    author, why = (by or "").strip(), (reason or "").strip()
    if not author or not why:
        raise ValueError("A manual VAT override needs both an author and a reason")
    value = vies.normalise(vat_number)
    logger.warning("[VIES] Manual override of %s by %s: %s", value, author, why)
    return record_vat_check(
        value,
        status=VatCheck.VERIFIED,
        override_by=author,
        override_reason=why,
        override_at=timezone.now(),
    )
