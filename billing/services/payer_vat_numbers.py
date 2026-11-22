"""The VAT number of a payer: written as ERPlora invoices it, kept on the billing profile with its VIES verdict,
and checked from the panel by the operation ``billing.vat_check.run``."""

import re
from dataclasses import dataclass
from datetime import datetime

from django.core.cache import cache
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import OperationError, Unauthorized
from live.operations import AI, operation
from live.outbox import record_event

from base.refusals import fields_refused
from billing import events, vat, vies
from billing.schemas.tax import VatCheckIn, VatCheckOut
from billing.services.vat_clearance import (
    CLEARANCE_ABSENT,
    CLEARANCE_INVALID,
    CLEARANCE_VERIFIED,
    VatCheckNotRecorded,
    VatCheckThrottled,
    _clearance,
    _issuer_country,
    clear_tax_id_for_stripe,
)

#: How long a person's check may hold its single-flight lock (connect + read timeouts and a margin).
IN_FLIGHT_SECONDS = 15

#: A Spanish NIF, NIE or CIF: nine characters, a letter or digit at each end (the form; the AEAT validates).
_SPANISH_TAX_ID = re.compile(r"^(ES)?[A-Z0-9][0-9]{7}[A-Z0-9]$")
#: What follows the prefix of a VAT number: VIES decides whether it exists (a Romanian CUI may be 2 digits).
_VAT_NUMBER_BODY = re.compile(r"^[A-Z0-9]{2,12}$")


class MalformedVatNumber(ValueError):
    """The text cannot be a VAT number: no country to read it in, an unknown prefix or the wrong shape."""


def in_flight_key(user) -> str:
    """The cache key of a person's check in flight (one at a time: a double click does not hold two
    database connections waiting on VIES)."""
    return f"billing:vat-check:in-flight:{user.pk}"


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
    """What ``hubs.billing_profile.update`` calls (instead of its form-only ``validate_tax_id``): the number
    written as ERPlora invoices it plus its VIES verdict. A malformed one raises ``MalformedVatNumber`` (the
    caller turns it into its field's 422); a number VIES does not confirm is kept as identification and simply
    does not buy reverse charge."""
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


@operation(
    "billing.vat_check.run",
    kind="command",
    permission="billing.vat_check",
    input=VatCheckIn,
    output=VatCheckOut,
    ai=AI(
        description="Checks a VAT number in the EU's VIES: whether it is valid and sales to it are reverse charge.",
        asks={
            "en": (
                "is VAT number PT123456789 valid?",
                "check this EU VAT ID in VIES",
                "is my company's VAT number good for reverse charge?",
            ),
            "es": (
                "¿es válido el NIF-IVA ESB12345678?",
                "comprueba este número de IVA en el VIES",
                "¿mi CIF intracomunitario sirve para la inversión del sujeto pasivo?",
            ),
        },
    ),
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
        raise fields_refused(
            {
                "vat_number": _(
                    "Write the VAT number with its two-letter country prefix, e.g. DE123456789."
                )
            }
        ) from None
    if not number:
        raise fields_refused({"vat_number": _("Enter a VAT number.")})
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
