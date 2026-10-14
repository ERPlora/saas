"""Writes of billing: the VIES verdict of a VAT number (asked, logged, cleared), the tax a sale carries,
and the operation ``billing.vat_check.run``.

Ported from ERPlora/saas ``apps/dashboard/fiscal/vies.py`` (the doors: ``verify_customer_vat``,
``check_vat_number``, ``record_manual_override``, ``clear_tax_id_for_stripe``, the per-person budget) and
``fiscal/services/sale_tax_rates.py`` (origin/develop). Only this module and ``queries.py`` touch the ORM;
the HTTP client is ``billing.vies``.

Every VIES query is a NEW ``VatCheck`` row: the log is the proof and is never rewritten. A current proof
(``grants_reverse_charge``) is reused for 30 days; anything else —invalid, unavailable, expired— is asked
again on the next need. That is the revalidation the old SaaS queued (there is no queue here: no
``django.tasks``, round 11), so an ``unavailable`` never sticks. Only a query really sent to VIES spends
the budget: the person's (``VAT_CHECK_RATE``) when a person asks, and everybody's
(``VAT_CHECK_GLOBAL_RATE``) always.

Nothing here blocks a sale for VIES: without a proven verdict the customer pays the VAT, which is the
recoverable outcome. What refuses a sale (409) is not knowing where the payer is
(``billing.billing_location_required``), a consumer in the UK (``billing.uk_business_required``) or a
territory without a rule (``billing.tax_engine_missing``).
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django_ratelimit.core import is_ratelimited
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError, Unauthorized
from live.operations import operation
from live.outbox import record_event

from billing import events, queries, vat, vies
from billing.models import VatCheck
from billing.money import to_cents
from billing.schemas import VatCheckIn, VatCheckOut
from billing.stripe_tax_rates import TaxRateSpec, tax_rate_specs_for

logger = logging.getLogger("billing.services")

#: The person's VIES budget, for every door a person spends a query from (the panel's check and the
#: admin's «Check now in VIES»), keyed by the account, never by address.
VAT_CHECK_GROUP = "billing.vat-check"
#: Everybody's budget: every query is under ERPlora's one requester number.
VAT_CHECK_GLOBAL_GROUP = "billing.vat-check-global"
#: How long a person's check may hold its single-flight lock (connect + read timeouts and a margin).
IN_FLIGHT_SECONDS = 15

#: A Spanish NIF, NIE or CIF: nine characters, a letter or digit at each end (the form; the AEAT validates).
_SPANISH_TAX_ID = re.compile(r"^(ES)?[A-Z0-9][0-9]{7}[A-Z0-9]$")
#: What follows the prefix of a VAT number: VIES decides whether it exists (a Romanian CUI may be 2 digits).
_VAT_NUMBER_BODY = re.compile(r"^[A-Z0-9]{2,12}$")


class VatCheckNotRecorded(Exception):
    """VIES answered but the answer could not be logged: it proves nothing, so it is not used."""


class VatCheckThrottled(Exception):
    """The budget is spent (the person's or everybody's): nothing was asked."""


class MalformedVatNumber(ValueError):
    """The text cannot be a VAT number: no country to read it in, an unknown prefix or the wrong shape."""


# --- The clearance of a VAT number --------------------------------------------------------------------

CLEARANCE_ABSENT = "absent"
#: The issuer's own country: it can never be reverse charge, so it travels without asking (contract §10.6).
CLEARANCE_NATIONAL = "national"
#: Checked in VIES, current and WITH PROOF (consultation number or manual override).
CLEARANCE_VERIFIED = "verified"
CLEARANCE_INVALID = "invalid"
#: The Commission did not answer, or answered without proof. Not «not yet» (§7).
CLEARANCE_UNAVAILABLE = "unavailable"
#: An HMRC number (``GB``/``XI``): VIES cannot answer and no rate depends on it (saas#2205).
CLEARANCE_OUTSIDE_VIES = "outside_vies"


@dataclass(frozen=True)
class TaxIdClearance:
    """Whether a VAT number may travel to the payment gateway, and why (contract §9, saas#1621).

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
    no consultation number, so it proves nothing (contract §3). ``spender`` is the account that asked
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
    check = verify_customer_vat(value, customer_country=customer_country, spender=spender)
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
    """Mark a VAT number valid BY HAND, with author and reason (contract §7): the company incorporated last
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


def in_flight_key(user) -> str:
    """The cache key of a person's check in flight (one at a time: a double click does not hold two
    database connections waiting on VIES)."""
    return f"billing:vat-check:in-flight:{user.pk}"


# --- The VAT number of a payer --------------------------------------------------------------------------


def vat_number_for(country: str, vat_id: str) -> str:
    """``vat_id`` as ERPlora invoices it and asks VIES about: without separators, upper case, with the
    prefix VIES knows when typed bare in another country (a national number stays as typed). ``""`` when
    nothing was typed; ``MalformedVatNumber`` when it cannot be a VAT number (VIES decides the rest)."""
    issuer = _issuer_country()
    value = vies.with_country_prefix(vat_id, country, issuer_country=issuer)
    if not value:
        return ""
    prefix, body = vies.split_vat_number(value)
    national = prefix in {issuer, vies.vies_prefix(issuer)} or (
        not prefix and (country or "").strip().upper() == issuer
    )
    if national:
        if issuer == "ES" and not _SPANISH_TAX_ID.match(value):
            raise MalformedVatNumber(value)
        return value
    if (
        prefix not in vies.VIES_PREFIXES | vies.UK_PREFIXES
        or not _VAT_NUMBER_BODY.match(body)
    ):
        raise MalformedVatNumber(value)
    return value


@dataclass(frozen=True)
class VatValidation:
    """A payer's VAT number as the billing profile stores it, and what it means for its sales."""

    vat_number: str
    status: str
    #: Its sales go without VAT: VIES proof AND the engine's rule (``vat.reverse_charge_applies``).
    reverse_charge: bool = False
    name: str = ""
    address: str = ""
    consultation_number: str = ""
    checked_at: datetime | None = None


def validate_vat_for_profile(country: str, vat_id: str) -> VatValidation:
    """What ``hubs.billing_profile.update`` calls in lot L2-B (instead of its form-only ``validate_tax_id``):
    the number written as ERPlora invoices it plus its VIES verdict. A malformed one raises
    ``MalformedVatNumber`` (the caller turns it into its field's 422); a number VIES does not confirm is
    kept as identification and simply does not buy reverse charge."""
    number = vat_number_for(country, vat_id)
    if not number:
        return VatValidation("", CLEARANCE_ABSENT)
    clearance = clear_tax_id_for_stripe(number, customer_country=country)
    check = clearance.check
    return VatValidation(
        vat_number=number,
        status=clearance.status,
        reverse_charge=vat.reverse_charge_applies(
            customer_country=country, verified=clearance.verified
        ),
        name=check.returned_name if check else "",
        address=check.returned_address if check else "",
        consultation_number=check.consultation_number if check else "",
        checked_at=check.requested_at if check else None,
    )


# --- The tax of a sale ------------------------------------------------------------------------------

#: What is sold: each with its whole sentence, so the buyer's language gets a sentence, not a glued noun.
Sold = Literal["sale", "plan", "module"]
_CANNOT_BE_PRICED = {
    "sale": gettext_lazy(
        "We cannot work out the tax for this billing address, so this sale cannot be made. Contact support."
    ),
    "plan": gettext_lazy(
        "We cannot work out the tax for this billing address, so this plan cannot be sold to it. Contact support."
    ),
    "module": gettext_lazy(
        "We cannot work out the tax for this billing address, so this module cannot be sold to it. Contact support."
    ),
}


def reverse_charge_cleared(tax_id: str, country: str) -> bool:
    """Whether VIES proved this VAT id: asked here, never trusted from the profile, because a number that
    only looks right buys a sale tax free (saas#1479)."""
    if not tax_id:
        return False
    return clear_tax_id_for_stripe(tax_id, customer_country=country).verified


def require_billing_location(
    hub, *, price: Decimal | None = None, what: Sold = "sale"
) -> None:
    """Refuse to sell before knowing WHERE the payer is: the 409 ``billing.billing_location_required``.

    The postal code is the only thing that tells the Canary Islands, Ceuta and Melilla (outside VAT) from
    the mainland (saas#1972), and only a real one («3500» is Benidorm without its 0, not Las Palmas).
    Charging first leaves two wrong outcomes. A free sale is never refused.
    """
    if price is not None and not to_cents(price):
        return None
    if queries.payer_of(hub).has_location:
        return None
    logger.error(
        "[FISCAL] Refusing a %s: the payer's country and postal code are not on file, or the postal code is "
        "not one of its country, so the sale cannot be priced before charging (hub=%s)",
        what,
        getattr(hub, "id", None),
    )
    raise Conflict(
        _(
            "We need the billing country and postal code before the payment, because they decide the tax on this sale."
        ),
        code="billing.billing_location_required",
    )


def sale_quote(
    hub, *, category_key: str, price: Decimal | None, what: Sold = "sale"
) -> vat.VatBreakdown:
    """The tax of selling ``price`` (net) of ``category_key`` to the payer of ``hub``; ``None`` = there IS
    something to charge, but the amount is not this question's business (the rate never depends on it).

    Refused (409) without a valid billing location, to a consumer in the UK (the terms sell to UK
    businesses only: a UK consumer owes UK VAT that only a supplier registered with HMRC may charge,
    saas#2205), and when no rule resolves the territory (the rate would be a guess and the price is net:
    refusing is loud and reversible; a sale charged wrong is neither).
    """
    require_billing_location(hub, price=price, what=what)
    payer = queries.payer_of(hub)
    if payer.country == "GB" and not payer.tax_id:
        logger.info(
            "[FISCAL] Refusing a %s: the payer is a consumer in the UK (hub=%s)",
            what,
            getattr(hub, "id", None),
        )
        raise Conflict(
            _(
                "We only sell to businesses in the United Kingdom: add the UK VAT number of the payer."
            ),
            code="billing.uk_business_required",
        )
    quote = vat.quote_vat(
        price if price is not None else Decimal("0"),
        customer_country=payer.country,
        customer_postal_code=payer.postal_code,
        customer_tax_id=payer.tax_id,
        customer_tax_id_type=payer.tax_id_type,
        customer_tax_id_verified=reverse_charge_cleared(payer.tax_id, payer.country),
        category_key=category_key,
    )
    if quote is None:
        logger.error(
            "[FISCAL] Refusing a %s: no tax rule resolves for %s %s, so the rate would be a guess and the price "
            "is net (hub=%s)",
            what,
            payer.country or "?",
            payer.postal_code or "?",
            getattr(hub, "id", None),
        )
        raise Conflict(str(_CANNOT_BE_PRICED[what]), code="billing.tax_engine_missing")
    return quote


def sale_tax_rates(
    hub, *, category_key: str, price: Decimal | None = None, what: Sold = "sale"
) -> list[TaxRateSpec]:
    """The rates Stripe must charge on top of this sale's net price (lot L2-B mirrors them into ``TaxRate``
    ids), for every door that sells: the plan and the module price the same buyer the same way (saas#1992).

    An EMPTY list is an answer, not a failure: the Canaries are outside VAT and the reverse charge is the
    customer's. ``price`` €0.00 is never refused (21 % of nothing is nothing, and the Free plan is the way
    in, ADR-0154); ``None`` = an amount that is not this function's business: the rate never depends on it.
    """
    if price is not None and not to_cents(price):
        return []
    quote = sale_quote(
        hub,
        category_key=category_key,
        price=price,
        what=what,
    )
    return tax_rate_specs_for(quote)


# --- Operations ---------------------------------------------------------------------------------------


@operation(
    "billing.vat_check.run",
    kind="command",
    permission="billing.vat_check",
    input=VatCheckIn,
    output=VatCheckOut,
)
def vat_check_run(ctx: OperationContext, data: VatCheckIn) -> dict:
    """Check a VAT number in VIES before paying (the create-business and billing-profile forms): the verdict
    and what the sale will do (``reverse_charge``, by the engine's own rule). A current proof is reused;
    anything else is asked now and logged as a new row. VIES down is an answer (``unavailable``), never a
    5xx; a malformed number is refused before spending a query; a spent budget is a 429, as a check of the
    same person already in flight; an answer that could not be logged is a 503."""
    account = ctx.actor
    if getattr(account, "pk", None) is None:
        raise Unauthorized(_("Sign in to check a VAT number."))
    try:
        number = vat_number_for(data.country, data.vat_number)
    except MalformedVatNumber:
        raise InvalidPayload(
            _("Invalid payload"),
            fields={
                "vat_number": _(
                    "Write the VAT number with its two-letter country prefix, e.g. DE123456789."
                )
            },
        ) from None
    if not number:
        raise InvalidPayload(
            _("Invalid payload"), fields={"vat_number": _("Enter a VAT number.")}
        )
    if not cache.add(in_flight_key(account), 1, timeout=IN_FLIGHT_SECONDS):
        raise OperationError(
            _("A check of yours is already running: wait for its answer."),
            code="billing.vat_check_in_progress",
            status=429,
        )
    try:
        clearance = _clearance(number, customer_country=data.country, spender=account)
    except VatCheckThrottled:
        raise OperationError(
            _(
                "Too many VAT checks in the last minute: nothing was asked. Try again in a moment."
            ),
            code="billing.vat_check_throttled",
            status=429,
        ) from None
    except VatCheckNotRecorded:
        raise OperationError(
            _(
                "VIES answered but the answer could not be saved, so it proves nothing. Try again."
            ),
            code="billing.vat_check_not_recorded",
            status=503,
        ) from None
    finally:
        cache.delete(in_flight_key(account))
    check = clearance.check
    if clearance.asked:
        record_event(
            ctx,
            events.VAT_CHECK_COMPLETED,
            {"vat_number": check.vat_number, "status": check.status},
        )
    return {
        "vat_number": clearance.vat_number,
        "status": clearance.status,
        "valid": {CLEARANCE_VERIFIED: True, CLEARANCE_INVALID: False}.get(
            clearance.status
        ),
        "name": check.returned_name if check else "",
        "address": check.returned_address if check else "",
        "consultation_number": check.consultation_number if check else "",
        "checked_at": check.requested_at if check else None,
        "is_current": check.is_current if check else False,
        "reverse_charge": vat.reverse_charge_applies(
            customer_country=data.country, verified=clearance.verified
        ),
        "manual_override": check.is_manual_override if check else False,
    }
