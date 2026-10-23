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

import hashlib
import json
import logging
import re
import uuid
from collections import Counter
from contextlib import contextmanager
from functools import partial
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django_ratelimit.core import is_ratelimited
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, OperationError, Unauthorized
from live.errors import NotFound as NotFoundError
from live.operations import operation
from live.outbox import notify, record_event

from apps.models import Module
from billing import events, queries, stripe_service, stripe_test_clocks, vat, vies
from billing.models import (
    CheckoutAttempt,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    OssNotice,
    PaymentFailure,
    PlanChangeSchedule,
    PromoCode,
    PromoRedemption,
    VatCheck,
    WebhookEvent,
    normalise_promo_code,
)
from billing.money import from_cents, to_cents
from billing.schemas import (
    CheckoutConfirmIn,
    CheckoutRefundRecordIn,
    CheckoutRefundRecordOut,
    CreditNoteRecordIn,
    FiscalAnswerIn,
    FiscalAnswerOut,
    InvoicePayIn,
    InvoicePayOut,
    InvoiceRecordIn,
    InvoiceRecordOut,
    RefundRecordIn,
    CheckoutStartIn,
    CheckoutStartOut,
    HubIn,
    ModuleIn,
    PlanChangeIn,
    PortalOpenIn,
    PortalOpenOut,
    SubscriptionOut,
    VatCheckIn,
    VatCheckOut,
)
from billing.stripe_checkout import (
    EMBEDDED_UI_MODE,
    KIND_METADATA_KEY,
    CheckoutKind,
    checkout_session_kind,
)
from billing.stripe_keys import StripeKeyMode
from billing.stripe_period import subscription_period
from billing.stripe_tax_rates import TaxRateSpec, tax_rate_specs_for
from hubs import emails as hub_emails
from hubs import hub_client
from hubs import queries as hub_queries
from hubs import services as hub_services
from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription, SubscriptionItem
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.schemas import ModuleRightIn, SubscriptionApplyIn

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


# --- Promo codes (lot L2-B) --------------------------------------------------------------------------


def redeem_promo(
    code: str | None, *, hub: Hub | None = None, customer: str = "", session: str = ""
) -> bool:
    """Count one redemption of ``code``; ``False`` when unknown, at its cap, or already used by ``hub`` (once
    per business, review of L2-B: the use is recorded, ``PromoRedemption``). The cap is in the UPDATE's
    WHERE, so two checkouts completing at once never pass it (the trial was granted when each session
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
            defaults={
                "stripe_customer_id": customer or "",
                "stripe_session_id": session or "",
            },
        )
        if not created:
            return False
    counted = (
        PromoCode.objects.filter(pk=promo.pk)
        .filter(
            Q(max_redemptions__isnull=True)
            | Q(redemption_count__lt=F("max_redemptions"))
        )
        .update(redemption_count=F("redemption_count") + 1, updated_at=timezone.now())
    )
    return counted > 0


# --- Stripe: buying, changing and cancelling (lot L2-B; PLAN-SAAS §3.2–§3.4 and §4) -------------------
#
# ONE Stripe subscription per business, whose items are its plan and its bought modules, at NET prices
# plus OUR tax rates (one ``TaxRate`` per item, ``billing.TaxRule``; never ``automatic_tax``). A business
# without one pays in an Embedded Checkout; one that has it previews the proration and confirms. Every
# change is read back from Stripe and written by ``hubs.subscription.apply`` (an app writes in another
# only through its operations), which pushes the snapshot to the Hub after the COMMIT.

#: Stripe's tag of this checkout flow (Dashboard → Checkout), fixed with its 8-letter suffix.
INTEGRATION_IDENTIFIER = "erplora_saas_billing_qmvhtkzd"
#: A simplified invoice is allowed up to 400 € with VAT (RD 1619/2012, art. 4.1); above it the invoice
#: names the buyer, so the sale needs the payer's tax id first.
SIMPLIFIED_INVOICE_LIMIT = Decimal("400.00")
#: Stripe refuses a Checkout trial that ends in less than 48 hours: a shorter one is not carried.
MIN_TRIAL = timedelta(hours=48)
#: How long a business whose renewal failed keeps its whole plan while Stripe retries, counted from the
#: failed invoice (saas#2574; market: WooCommerce 7 days, Square 9, Lightspeed 21; PLAN-SAAS §3.3).
UNPAID_PLAN_GRACE = timedelta(days=7)
PAID_STATUSES = frozenset({"active", "trialing"})
DUNNING_STATUSES = frozenset({"past_due", "unpaid"})
ENDED_STATUSES = frozenset({"canceled", "incomplete_expired"})
#: Stripe failure codes that mean the CARD will not pay again as it is (the bank refused it, or it is no
#: longer valid): «Pay» waits until the card changes (mockups README §6.18).
CARD_REFUSED_CODES = frozenset(
    {
        "card_declined",
        "expired_card",
        "incorrect_cvc",
        "incorrect_number",
        "invalid_cvc",
        "invalid_expiry_month",
        "invalid_expiry_year",
        "invalid_number",
        "card_not_supported",
    }
)


@dataclass(frozen=True)
class Sale:
    """What is sold, at which Stripe price and net amount, and as which tax category."""

    kind: str  # "plan" | "module"
    slug: str
    interval: str
    price_id: str
    net: Decimal
    category_key: str
    plan: Plan | None = None
    module: Module | None = None


def _payments_unavailable() -> OperationError:
    return OperationError(
        _(
            "Payments are not available right now. Nothing was charged; try again later."
        ),
        code="billing.payments_unavailable",
        status=503,
    )


@contextmanager
def stripe_errors(*, charging: bool = False):
    """Stripe's failures as the panel's errors. ``charging``: the call may have charged when Stripe did not
    answer (the request may have gone through), so the panel never hears «nothing was charged» then; a
    refusal, a declined card included, charged nothing."""
    try:
        yield
    except stripe_service.StripeNotConfigured:
        raise _payments_unavailable() from None
    except stripe_service.StripeUnavailable:
        message = (
            _(
                "The payment service did not answer, so the charge is not confirmed. Check Billing before trying again."
            )
            if charging
            else _(
                "The payment service did not answer. Nothing was charged; try again in a moment."
            )
        )
        raise OperationError(
            message, code="billing.stripe_unavailable", status=503
        ) from None
    except stripe_service.StripeRefused as refused:
        if refused.card:
            raise Conflict(
                _(
                    "The bank declined the card. Nothing was charged: change the card and try again."
                ),
                code="billing.card_declined",
            ) from None
        raise OperationError(
            _(
                "The payment service refused the operation. Nothing was charged; contact support."
            ),
            code="billing.stripe_refused",
            status=502,
        ) from None


def require_stripe() -> None:
    """Stripe is configured (a secret or restricted key): 503 ``billing.payments_unavailable`` otherwise,
    before anything is asked of it."""
    if stripe_service.key_mode() is StripeKeyMode.UNKNOWN:
        raise _payments_unavailable()


#: How long a healthy answer of the platform hub opens live charging; a failed one is asked again next time.
PLATFORM_HEALTH_SECONDS = 5 * 60
PLATFORM_HEALTH_KEY = "billing.platform_invoicing.healthy"


def invoicing_available() -> bool:
    """Whether a route sends ERPlora's invoices now (working rules §15): the platform invoicing is switched on
    (``PLATFORM_INVOICING_ENABLED``, off by default) AND the platform hub answers its health route
    (``GET /internal/platform/invoices/health`` → 200 ``{"status": "ok"}``), kept ``PLATFORM_HEALTH_SECONDS``.
    Not «the model exists» (review of L3-C)."""
    if not settings.PLATFORM_INVOICING_ENABLED:
        return False
    if cache.get(PLATFORM_HEALTH_KEY):
        return True
    try:
        answer = hub_client.platform_invoicing_health()
    except (HubUnavailable, HubRefused) as failed:
        logger.error("[BILLING] The platform hub does not issue invoices now: %s", failed)
        return False
    healthy = answer.status == 200 and isinstance(answer.body, dict) and answer.body.get("status") == "ok"
    if healthy:
        cache.set(PLATFORM_HEALTH_KEY, True, PLATFORM_HEALTH_SECONDS)
    return healthy


def require_payments() -> None:
    """Stripe is configured, and a LIVE key moves real money only while a route sends ERPlora's invoice of
    it (``invoicing_available``: working rules §15, «in production nothing is charged without a sending
    route») and this year's OSS total is known.

    The OSS threshold (10,000 € a year of cross-border B2C sales) decides between Spanish and destination
    VAT, and part of the year was sold by the old SaaS (``FiscalPolicy.oss_carried_*``): until that sum is
    on file for this year, a sale could cross the threshold unseen (billing README, «Fuera de L2-A»). A
    test key moves no real money and is never held.
    """
    require_stripe()
    if stripe_service.key_mode() is not StripeKeyMode.LIVE:
        return
    if not invoicing_available():
        logger.error(
            "[BILLING] A live sale was refused: no route sends ERPlora's invoice now (PLATFORM_INVOICING_ENABLED "
            "and the platform hub's health)",
            extra={"event": "billing.invoicing_unavailable"},
        )
        raise Conflict(
            _(
                "Payments open once ERPlora can invoice them. Nothing was charged; try again later."
            ),
            code="billing.invoicing_unavailable",
        )
    year = timezone.localdate().year
    if not queries.oss_total_is_known(queries.fiscal_policy(), year):
        logger.error(
            "[BILLING] A live sale was refused: the OSS total of %s is not on file (FiscalPolicy.oss_carried_*)",
            year,
            extra={"event": "billing.oss_total_unknown", "year": year},
        )
        raise Conflict(
            _(
                "Payments are paused while this year's EU sales total is brought up to date. Nothing was "
                "charged; try again later."
            ),
            code="billing.oss_total_unknown",
        )


def _owned(ctx: OperationContext, hub_id) -> tuple[Hub, Subscription | None]:
    """The business ``hub_id`` if the account OWNS it (what a business pays is its owner's, round 17 §2.7:
    404 without access, 403 for another role), locked, and its subscription; a deleted one buys nothing.

    And the account is its PAYER (review of L2-B): an accepted transfer leaves the previous owner's payer, card
    and Stripe customer on the business, and a new owner must not charge, read or cancel them (409
    ``billing.payer_required``): they say who pays first (``hubs.billing_profile.update`` gives the business
    a payer of theirs). A subscription still billed to the previous payer's customer is kept with the new owner's
    card first («Keep it with my card», ``billing.plan.take_over``, HUBS-F28)."""
    user = hub_queries.account_of(ctx)
    member = hub_queries.access(user, hub_id, HubMember.Role.OWNER, lock=True)
    if not hub_queries.is_writable(member.hub):
        raise hub_services.business_deleted()
    hub = Hub.objects.select_related("billing_profile").get(pk=member.hub_id)
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan")
        .filter(hub=hub)
        .first()
    )
    profile = hub.billing_profile
    if profile is None or profile.owner_id != user.pk:
        raise Conflict(
            _(
                "Say who pays for this business first: its billing details are another account's."
            ),
            code="billing.payer_required",
        )
    billed_to = subscription.stripe_customer_id if _paying(subscription) else ""
    if billed_to and billed_to != profile.stripe_customer_id:
        logger.warning(
            "[BILLING] Hub %s is billed to customer %s, not to its payer's (%s)",
            hub.id,
            billed_to,
            profile.stripe_customer_id or "none",
        )
        raise Conflict(
            _(
                "This business's plan is still paid with its previous owner's card: keep it with yours in Billing first."
            ),
            code="billing.payer_required",
        )
    return hub, subscription


def _paying(subscription: Subscription | None) -> bool:
    return (
        bool(subscription and subscription.stripe_subscription_id)
        and subscription.status not in ENDED_STATUSES
    )


def _require_paid_up(hub: Hub, subscription: Subscription | None) -> None:
    """A business with an unpaid invoice buys nothing more until it pays it (mockups README §6.18)."""
    unpaid = subscription is not None and subscription.status in DUNNING_STATUSES
    if unpaid or hub.status == Hub.Status.SUSPENDED:
        raise Conflict(
            _(
                "This business has an unpaid invoice: pay it before buying or changing anything."
            ),
            code="billing.invoice_unpaid",
        )


def _not_on_sale(what: str) -> Conflict:
    logger.error(
        "[BILLING] %s has no Stripe price for this billing: it cannot be sold", what
    )
    return Conflict(
        _("This cannot be bought right now. Contact support."),
        code="billing.not_on_sale",
    )


def _upgrade_only() -> Conflict:
    """Pro, Enterprise and Max (``upgrade_only``) are an upgrade of a business that already pays (audit 2 S-03);
    the Store does not offer them to a Free one (``billing.store.catalog``'s ``offered_plans``)."""
    return Conflict(
        _(
            "This plan is an upgrade of a paid plan: start with one of the plans sold at sign-up."
        ),
        code="billing.plan_upgrade_only",
    )


def plan_sale(user, slug: str, interval: str) -> Sale:
    plan = queries.plan_on_sale(slug)
    if plan is None or not plan.is_available_to(user):
        raise InvalidPayload(
            _("Invalid payload"),
            fields={"plan": _("There is no plan with this identifier.")},
        )
    if not to_cents(plan.price_monthly or 0):
        raise Conflict(
            _(
                "Free is not bought: to go back to it, cancel the plan and it ends with its period."
            ),
            code="billing.plan_is_free",
        )
    price_id = (
        plan.stripe_price_id_annual if interval == "year" else plan.stripe_price_id
    )
    net = plan.price_annual if interval == "year" else plan.price_monthly
    if not price_id:
        raise _not_on_sale(f"Plan {plan.slug} ({interval})")
    return Sale(
        "plan",
        plan.slug,
        interval,
        price_id,
        Decimal(net or 0),
        vat.SAAS_SUBSCRIPTION_CATEGORY,
        plan=plan,
    )


def module_sale(slug: str, interval: str, *, module: Module | None = None) -> Sale:
    module = module or queries.module_on_sale(slug)
    if module is None:
        raise InvalidPayload(
            _("Invalid payload"),
            fields={"module": _("There is no module with this identifier on sale.")},
        )
    price_id = (
        module.stripe_price_id_annual
        if interval == "year"
        else module.stripe_price_id_monthly
    )
    cents = (
        module.price_annual_cents if interval == "year" else module.price_monthly_cents
    )
    if not price_id:
        raise _not_on_sale(f"Module {module.slug} ({interval})")
    return Sale(
        "module",
        module.slug,
        interval,
        price_id,
        Decimal(cents) / 100,
        vat.SOFTWARE_LICENSE_CATEGORY,
        module=module,
    )


def _owns_module(subscription: Subscription | None, slug: str) -> bool:
    if subscription is None:
        return False
    item = SubscriptionItem.objects.filter(
        subscription=subscription, module_slug=slug
    ).first()
    return item is not None and item.is_live(timezone.now())


def _require_module_not_owned(subscription: Subscription | None, slug: str) -> None:
    if _owns_module(subscription, slug):
        raise Conflict(
            _("This business already has this module."), code="billing.module_owned"
        )


def _recurring_net(
    subscription: Subscription | None,
    interval: str,
    *,
    plan: Plan | None = None,
    adding: Sale | None = None,
) -> Decimal:
    """What a renewal of the business charges, net, once ``adding`` is in: the plan and its bought modules,
    at ``interval``'s prices (the full invoice decides on the whole renewal, not one line of it)."""
    total = Decimal("0")
    plan = (
        plan
        if plan is not None
        else (subscription.plan if _paying(subscription) else None)
    )
    if plan is not None:
        total += Decimal(
            (plan.price_annual if interval == "year" else plan.price_monthly) or 0
        )
    if subscription is not None:
        now = timezone.now()
        for item in SubscriptionItem.objects.filter(
            subscription=subscription, source=SubscriptionItem.Source.PURCHASE
        ):
            if not item.is_live(now) or item.valid_until is not None:
                continue
            module = Module.objects.filter(slug=item.module_slug).first()
            if module is not None:
                total += (
                    Decimal(
                        module.price_annual_cents
                        if interval == "year"
                        else module.price_monthly_cents
                    )
                    / 100
                )
    if adding is not None and adding.kind == "module":
        total += adding.net
    return total


def price_sale(hub: Hub, sale: Sale, *, recurring_net: Decimal) -> list[str]:
    """The Stripe ``TaxRate`` ids that charge OUR tax on ``sale``, after the guards that refuse it: no
    location (409 ``billing.billing_location_required``), a UK consumer, a territory without a rule, and
    a renewal over the simplified-invoice limit without the payer's tax id (409 ``billing.tax_id_required``)."""
    quote = sale_quote(
        hub, category_key=sale.category_key, price=sale.net, what=sale.kind
    )
    rate = Decimal(quote.rate or 0) if quote.is_subject else Decimal("0")
    gross = vat.add_vat(recurring_net, rate) if rate else recurring_net
    profile = hub.billing_profile
    if gross > SIMPLIFIED_INVOICE_LIMIT and not (profile.tax_id or "").strip():
        logger.info(
            "[BILLING] %s of hub %s needs the payer's tax id: %s € with VAT",
            sale.kind,
            hub.id,
            gross,
        )
        raise Conflict(
            _(
                "Above 400 € with VAT the invoice must name the buyer: add the payer's tax ID before paying."
            ),
            code="billing.tax_id_required",
        )
    with stripe_errors():
        return stripe_service.tax_rate_ids(tax_rate_specs_for(quote))


def ensure_customer(hub: Hub, *, test_clock: str | None = None) -> str:
    """The payer of ``hub`` as a Stripe customer: created once (and remembered on the payer through
    ``hubs.subscription.apply``), brought up to date otherwise. Its VAT number travels only when VIES
    proved it, or it is national (Stripe reverse charges by the FORMAT of a number, saas#1479).
    ``test_clock`` attaches a new customer to a Stripe test clock (``billing.stripe_test_clocks``)."""
    profile = hub.billing_profile
    params = _customer_params(hub, profile)
    with stripe_errors():
        if profile.stripe_customer_id:
            customer = stripe_service.update_customer(
                profile.stripe_customer_id, params
            )["id"]
        else:
            # One that a failed checkout created (its id rolled back with it) is found, not created again.
            found = stripe_service.find_customer(str(profile.id))
            if found is not None:
                customer = stripe_service.update_customer(found["id"], params)["id"]
            else:
                if test_clock:
                    params["test_clock"] = test_clock
                # Keyed by the payer AND what is sent: Stripe refuses the same key with other details.
                digest = hashlib.sha256(
                    json.dumps(params, sort_keys=True).encode()
                ).hexdigest()[:16]
                customer = stripe_service.create_customer(
                    params, idempotency_key=f"customer-{profile.id}-{digest}"
                )["id"]
            hub_services.subscription_apply(
                hub_services.system_ctx_for(hub.id),
                SubscriptionApplyIn(hub_id=hub.id, stripe_customer_id=customer),
            )
            profile.stripe_customer_id = customer
        _attach_cleared_tax_id(customer, profile)
    return customer


def _customer_params(hub: Hub, profile) -> dict:
    """What the payer's Stripe customer holds: the billing details, the language of its mails and the payer."""
    owner = profile.owner or _owner_of(hub)
    address = {
        key: value
        for key, value in (
            ("line1", profile.billing_address),
            ("city", profile.billing_city),
            ("postal_code", profile.billing_postal_code),
            ("country", profile.billing_country),
        )
        if value
    }
    return {
        "name": profile.billing_name or hub.name,
        "email": profile.billing_email or getattr(owner, "email", ""),
        "address": address,
        "preferred_locales": [getattr(owner, "language", "") or settings.LANGUAGE_CODE],
        "metadata": {"billing_profile_id": str(profile.id)},
    }


def push_payer_to_stripe(profile_id) -> str:
    """The billing details the owner saved, onto the payer's Stripe customer (BILLING-F01): what Stripe sends
    (the page to authenticate a renewal, its receipts) and the Customer Portal show them, not the old ones.
    ``updated`` · ``skipped`` (Stripe never saw this payer: the first checkout creates the customer with them,
    ``ensure_customer``). Stripe failing raises (``stripe_errors``)."""
    profile = BillingProfile.objects.select_related("owner").get(pk=profile_id)
    hub = Hub.objects.filter(billing_profile=profile).order_by("pk").first()
    if not profile.stripe_customer_id or hub is None:
        return "skipped"
    with stripe_errors():
        stripe_service.update_customer(profile.stripe_customer_id, _customer_params(hub, profile))
        _attach_cleared_tax_id(profile.stripe_customer_id, profile)
    return "updated"


# --- BILLING-F28 and APPS-F04: the Stripe prices pasted on a plan or a module are its own (the staff, in the admin) -

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
    """APPS-F04: the same checks as :func:`plan_price_problems`, for the Stripe prices pasted on a paid module, by the
    module's own fields; ``amounts`` are its net prices in euro cents (``price_monthly_cents``, ``price_annual_cents``)."""
    return _price_problems(
        MODULE_PRICE_FIELDS,
        prices,
        {field: int(amount or 0) for field, amount in amounts.items()},
        product,
        lambda stripe, expected: _("Stripe charges %(stripe)s and the module says %(module)s.")
        % {"stripe": stripe, "module": expected},
    )


def _price_problems(fields, prices: dict[str, str], cents: dict[str, int], product: str, other_amount) -> dict[str, str]:
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


# --- BILLING-F29: a real charge in PRE with a Stripe test clock (the staff, from the admin) ------------

#: How far «Advance the clock» moves it: past a monthly renewal.
TEST_CLOCK_STEP = timedelta(days=31)


class TestClockRefused(Exception):
    """Why a test clock was not attached or advanced, said to the staff as it is."""


def _require_test_mode() -> None:
    if stripe_service.key_mode() is not StripeKeyMode.TEST:
        raise TestClockRefused(_("Test clocks only exist with Stripe's test keys."))


def attach_test_clock(hub_id) -> str:
    """Create a Stripe test clock and the payer of ``hub_id`` as a NEW Stripe customer on it (Stripe attaches a
    clock only when the customer is created); its id. Test keys only."""
    _require_test_mode()
    hub = Hub.objects.select_related("billing_profile").get(pk=hub_id)
    profile = hub.billing_profile
    if profile is None:
        raise TestClockRefused(_("This business has no payer yet: fill in its billing details first."))
    try:
        known = profile.stripe_customer_id or stripe_service.find_customer(str(profile.id))
        if known:
            raise TestClockRefused(_("Its payer is a Stripe customer already: a clock only takes a new one."))
        clock = stripe_test_clocks.create_test_clock(int(timezone.now().timestamp()), name=f"QA {hub.slug}")
        ensure_customer(hub, test_clock=clock)
    except (stripe_service.StripeUnavailable, stripe_service.StripeRefused) as failed:
        raise TestClockRefused(_("Stripe did not take it: %(reason)s") % {"reason": failed}) from failed
    return clock


def advance_test_clock_of(hub_id) -> datetime:
    """Move the test clock of the payer of ``hub_id`` one step (``TEST_CLOCK_STEP``) from its own time; when it
    reaches. It does not wait: Stripe advances it and tells what happens (a renewal, a charge) by its events, as
    in production. Test keys only; a clock still advancing is not pushed again."""
    _require_test_mode()
    hub = Hub.objects.select_related("billing_profile").get(pk=hub_id)
    customer = hub.billing_profile.stripe_customer_id if hub.billing_profile is not None else ""
    if not customer:
        raise TestClockRefused(_("This business has no test clock: attach one first."))
    try:
        clock_id = stripe_service.retrieve_customer(customer).get("test_clock") or ""
        if isinstance(clock_id, dict):
            clock_id = clock_id.get("id", "")
        if not clock_id:
            raise TestClockRefused(_("This business has no test clock: attach one first."))
        clock = stripe_service.retrieve_test_clock(clock_id)
        if clock.get("status") != "ready":
            raise TestClockRefused(_("Its clock is still advancing: try again in a minute."))
        to = int(clock["frozen_time"] + TEST_CLOCK_STEP.total_seconds())
        stripe_service.advance_test_clock(clock_id, {"frozen_time": to})
    except (stripe_service.StripeUnavailable, stripe_service.StripeRefused) as failed:
        raise TestClockRefused(_("Stripe did not take it: %(reason)s") % {"reason": failed}) from failed
    logger.info("[TEST CLOCK] %s of hub %s advancing to %s", clock_id, hub.id, to)
    return datetime.fromtimestamp(to, tz=UTC)


def _owner_of(hub: Hub):
    member = (
        HubMember.objects.select_related("user")
        .filter(hub=hub, role=HubMember.Role.OWNER)
        .first()
    )
    return member.user if member else None


def _attach_cleared_tax_id(customer: str, profile) -> None:
    if not (profile.tax_id or "").strip():
        return
    clearance = clear_tax_id_for_stripe(
        profile.tax_id, customer_country=profile.billing_country
    )
    tax_type = vat.tax_id_type_for(profile.billing_country)
    if not clearance.may_travel_to_stripe or not tax_type:
        return
    if any(
        existing.get("value") == clearance.vat_number
        for existing in stripe_service.customer_tax_ids(customer)
    ):
        return
    stripe_service.add_customer_tax_id(
        customer, tax_type=tax_type, value=clearance.vat_number
    )


def _trial_end(
    subscription: Subscription | None, promo: PromoCode | None, now: datetime
) -> int | None:
    """When a plan bought by a free business starts charging: the days left of its sign-up trial, or the
    promo code's, the later of the two; none under Stripe's 48 h."""
    ends = []
    if (
        subscription is not None
        and subscription.trial_plan_id
        and subscription.trial_end
    ):
        ends.append(subscription.trial_end)
    if promo is not None:
        ends.append(now + timedelta(days=promo.trial_days))
    end = max(ends, default=None)
    if end is None or end - now < MIN_TRIAL:
        return None
    return int(end.timestamp())


@operation(
    "billing.checkout.start",
    kind="command",
    permission="billing.pay",
    input=CheckoutStartIn,
    output=CheckoutStartOut,
)
def checkout_start(ctx: OperationContext, data: CheckoutStartIn) -> dict:
    """The owner buys a plan or a module for a business. Without a Stripe subscription (Free): an Embedded
    Checkout (``flow = checkout`` and its ``client_secret``; the same selection reuses its open session).
    With one: the prorated charge of adding it (``flow = confirm`` and ``preview``), confirmed with
    ``billing.checkout.confirm`` (a module) or ``billing.plan.change`` (a plan). Nothing is charged here."""
    user = hub_queries.account_of(ctx)
    hub, subscription = _owned(ctx, data.hub_id)
    if _paying(subscription):
        interval = data.interval if data.plan else subscription.billing_interval
    else:
        interval = data.interval
    if data.plan and not _paying(subscription):
        asked = queries.plan_on_sale(data.plan)
        if asked is not None and asked.upgrade_only:
            raise _upgrade_only()
    sale = (
        plan_sale(user, data.plan, interval)
        if data.plan
        else module_sale(data.module, interval)
    )
    require_payments()
    _require_paid_up(hub, subscription)
    if sale.kind == "module":
        _require_module_not_owned(subscription, sale.slug)
    if _paying(subscription):
        return _preview(hub, subscription, sale, data.promo_code)
    tax_rates = price_sale(hub, sale, recurring_net=sale.net)
    customer = hub.billing_profile.stripe_customer_id
    promo = (
        queries.redeemable_promo(data.promo_code, hub=hub, customer=customer)
        if sale.kind == "plan"
        else None
    )
    # The tax rates too: a payer whose place or VAT number changed is charged anew, never at the old rate.
    selection = f"{sale.kind}:{sale.slug}:{interval}:{promo.code if promo else ''}:{','.join(tax_rates)}"[
        :255
    ]
    reusable = CheckoutAttempt.objects.filter(
        hub=hub,
        selection=selection,
        status=CheckoutAttempt.Status.OPEN,
        created_at__gt=timezone.now() - CheckoutAttempt.REUSE_FOR,
    ).exclude(client_secret="")
    attempt = reusable.order_by("-created_at").first()
    if attempt is None:
        attempt = _open_checkout(
            ctx, hub, subscription, sale, tax_rates, promo, selection
        )
    return {
        "flow": "checkout",
        "session_id": attempt.stripe_session_id,
        "client_secret": attempt.client_secret,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "preview": None,
    }


def _expire_other_sessions(hub: Hub, selection: str) -> None:
    """One open checkout per business: two open sessions could both be paid, and the business would end up
    with two subscriptions. One Stripe no longer lets expire (paid meanwhile) is left to the webhook."""
    others = CheckoutAttempt.objects.filter(
        hub=hub, status=CheckoutAttempt.Status.OPEN
    ).exclude(selection=selection)
    for attempt in others.exclude(stripe_session_id=None):
        try:
            with stripe_errors():
                stripe_service.expire_checkout_session(attempt.stripe_session_id)
        except Conflict:
            raise
        except OperationError as refused:
            if refused.code != "billing.stripe_refused":
                raise
            logger.info(
                "[BILLING] Checkout %s could not be expired: it is not open any more",
                attempt.stripe_session_id,
            )
            continue
        CheckoutAttempt.objects.filter(pk=attempt.pk).update(
            status=CheckoutAttempt.Status.EXPIRED, updated_at=timezone.now()
        )


def _open_checkout(
    ctx, hub, subscription, sale: Sale, tax_rates, promo, selection
) -> CheckoutAttempt:
    _expire_other_sessions(hub, selection)
    customer = ensure_customer(hub)
    attempt = CheckoutAttempt.objects.create(
        hub=hub,
        owner=hub_queries.account_of(ctx),
        kind=CheckoutAttempt.Kind.PLAN
        if sale.kind == "plan"
        else CheckoutAttempt.Kind.MODULE,
        plan_slug=sale.slug if sale.kind == "plan" else "",
        module_slug=sale.slug if sale.kind == "module" else "",
        billing_interval=sale.interval,
        promo_code=promo.code if promo else "",
        selection=selection,
    )
    kind = (
        CheckoutKind.HUB_PLAN if sale.kind == "plan" else CheckoutKind.MODULE_PURCHASE
    )
    metadata = {
        KIND_METADATA_KEY: kind.value,
        "hub_id": str(hub.id),
        sale.kind: sale.slug,
        "billing_interval": sale.interval,
        "attempt": str(attempt.id),
    }
    if promo is not None:
        metadata["promo_code"] = promo.code
    subscription_data = {
        "description": f"ERPlora — {hub.name}",
        "metadata": {"hub_id": str(hub.id)},
    }
    if sale.kind == "plan":
        trial_end = _trial_end(subscription, promo, timezone.now())
        if trial_end is not None:
            subscription_data["trial_end"] = trial_end
    base = hub_emails.base_url(ctx.request)
    params = {
        "ui_mode": EMBEDDED_UI_MODE,
        "mode": "subscription",
        "customer": customer,
        # With a customer, what the buyer types in the checkout is saved on it (saas#1077).
        "customer_update": {"name": "auto", "address": "auto"},
        "line_items": [{"price": sale.price_id, "quantity": 1, "tax_rates": tax_rates}],
        "metadata": metadata,
        "subscription_data": subscription_data,
        "redirect_on_completion": "if_required",
        "return_url": f"{base}/businesses/{hub.id}/summary?checkout={{CHECKOUT_SESSION_ID}}",
        "locale": "auto",
        # Without an address there is no country, and without it no tax jurisdiction (saas#1051).
        "billing_address_collection": "required",
        # Never: Stripe reverse charges by the FORMAT of a number. Ours is asked in our form and only a
        # proved one reaches the customer (saas#1621, ``ensure_customer``).
        "tax_id_collection": {"enabled": False},
        "integration_identifier": INTEGRATION_IDENTIFIER,
    }
    with stripe_errors():
        session = stripe_service.create_checkout_session(
            params, idempotency_key=f"checkout-{attempt.id}"
        )
    attempt.stripe_session_id = session["id"]
    attempt.client_secret = session.get("client_secret") or ""
    attempt.save(update_fields=["stripe_session_id", "client_secret", "updated_at"])
    record_event(
        ctx,
        events.CHECKOUT_STARTED,
        {"hub_id": str(hub.id), "kind": sale.kind, "attempt": str(attempt.id)},
    )
    return attempt


def _live(subscription: Subscription) -> dict:
    with stripe_errors():
        return stripe_service.retrieve_subscription(subscription.stripe_subscription_id)


def _live_items(live: dict) -> list[dict]:
    return list(((live.get("items") or {}).get("data")) or [])


def _plan_item(live: dict) -> dict | None:
    for item in _live_items(live):
        if queries.plan_for_price(item["price"]["id"]) is not None:
            return item
    return None


#: Stripe's cap of items per subscription (the plan and 19 modules).
MAX_ITEMS = 20


def _require_room(live: dict, adding: int = 1) -> None:
    if len(_live_items(live)) + adding > MAX_ITEMS:
        raise Conflict(
            _(
                "This business has as many modules as one subscription can bill. Contact support."
            ),
            code="billing.too_many_items",
        )


def is_downgrade(subscription: Subscription, sale: Sale) -> bool:
    """Whether a plan change gives the business less for its money: annual → monthly, or a cheaper plan on the
    same billing. It waits for the end of the paid period (review of L3-C): charged now it would credit the
    unused part of the dearer plan, a Stripe invoice with a negative total."""
    if subscription.billing_interval == Subscription.Interval.YEAR and sale.interval == "month":
        return True
    if sale.interval != subscription.billing_interval:
        return False

    def price(plan: Plan) -> int:
        return to_cents((plan.price_annual if sale.interval == "year" else plan.price_monthly) or 0)

    return price(sale.plan) < price(subscription.plan)


def pending_change(hub: Hub) -> PlanChangeSchedule | None:
    return PlanChangeSchedule.objects.filter(hub=hub).first()


def _require_no_pending_change(hub: Hub) -> None:
    """A module bought or cancelled while a downgrade waits would be dropped by the schedule's next phase."""
    if pending_change(hub) is not None:
        raise Conflict(
            _("The plan changes at the end of this period: keep the current plan first, then change the modules."),
            code="billing.plan_change_pending",
        )


def _release_pending(hub: Hub, live: dict | None = None) -> None:
    """Undo a downgrade that waits (or detach the schedule of one already applied): Stripe releases the
    schedule, the subscription keeps its items. A schedule Stripe no longer holds counts as released."""
    pending = pending_change(hub)
    attached = (live or {}).get("schedule")
    if isinstance(attached, dict):
        attached = attached.get("id")
    for schedule_id in dict.fromkeys(filter(None, [attached, pending.stripe_schedule_id if pending else None])):
        try:
            with stripe_errors():
                stripe_service.release_schedule(schedule_id)
        except OperationError as refused:
            if refused.code != "billing.stripe_refused":
                raise
            logger.warning("[BILLING] Schedule %s of hub %s was released already", schedule_id, hub.id)
    PlanChangeSchedule.objects.filter(hub=hub).delete()


def _phase_items(live: dict, replaced: dict[str, dict]) -> list[dict]:
    """The items of a schedule phase: the live ones, with ``replaced`` (item id → price and tax rates)."""
    items = []
    for line in _live_items(live):
        rates = [rate["id"] if isinstance(rate, dict) else rate for rate in line.get("tax_rates") or []]
        change = replaced.get(line["id"], {})
        items.append(
            {
                "price": change.get("price") or line["price"]["id"],
                "quantity": line.get("quantity") or 1,
                # A phase lists its items whole: no rate is an empty list there (``_rates_param`` is for updates).
                "tax_rates": change.get("tax_rates", rates) or [],
            }
        )
    return items


def _schedule_downgrade(hub: Hub, subscription: Subscription, live: dict, sale: Sale, items: list[dict]) -> None:
    """Hold the downgrade in Stripe as a schedule: the current phase ends with the paid period, the next one
    bills ``items`` without proration (so no negative invoice), and the schedule then lets the subscription go
    on its own (``release``)."""
    _release_pending(hub, live)
    _start, period_end = subscription_period(live)
    with stripe_errors():
        made = stripe_service.create_schedule(subscription.stripe_subscription_id)
        phase = (made.get("phases") or [{}])[0]
        stripe_service.update_schedule(
            made["id"],
            {
                "end_behavior": "release",
                "phases": [
                    {
                        "items": _phase_items(live, {}),
                        "start_date": phase.get("start_date"),
                        "end_date": period_end,
                        "proration_behavior": "none",
                    },
                    {
                        "items": _phase_items(live, {item["id"]: item for item in items if item.get("id")}),
                        "proration_behavior": "none",
                        "duration": {"interval": sale.interval, "interval_count": 1},
                    },
                ],
            },
        )
    PlanChangeSchedule.objects.update_or_create(
        hub=hub,
        defaults={
            "stripe_schedule_id": made["id"],
            "plan_slug": sale.slug,
            "interval": sale.interval,
            "starts_at": _moment(period_end) or subscription.current_period_end or timezone.now(),
        },
    )


def _forget_applied_change(hub_id, live: dict) -> None:
    """Stripe started the next phase of a downgrade: the pending change is done, and its schedule is detached
    so the subscription takes any later change directly."""
    pending = PlanChangeSchedule.objects.filter(hub_id=hub_id).first()
    if pending is None:
        return
    item = _plan_item(live)
    found = queries.plan_for_price(item["price"]["id"]) if item else None
    if found is None or (found[0].slug, found[1]) != (pending.plan_slug, pending.interval):
        return
    _release_pending(Hub.objects.get(pk=hub_id), live)


@dataclass(frozen=True)
class PlanChange:
    """What a plan change sends to Stripe: the items, and how it is charged."""

    items: list
    #: ``always_invoice`` (charged now) or ``none`` (a trial: nothing until it ends).
    proration_behavior: str
    #: The sign-up trial left, or a promo code's: the plan starts charging then.
    trial_end: int | None = None
    promo: PromoCode | None = None


def _plan_change(
    hub: Hub, subscription: Subscription, live: dict, sale: Sale, promo_code: str = ""
) -> PlanChange:
    """The items of a plan change: the plan item gets the new price; on a change of billing, every module
    item its price of the new billing (Stripe bills one interval per subscription), each with our tax. A
    subscription of modules alone (a Free business) gets its plan item, keeping the days left of the sign-up
    trial or a promo code's, as the checkout does (review of L2-B)."""
    if (
        sale.plan.pk == subscription.plan_id
        and sale.interval == subscription.billing_interval
    ):
        raise Conflict(
            _("This business is already on this plan."), code="billing.same_plan"
        )
    if subscription.cancel_at_period_end:
        raise Conflict(
            _("The plan is cancelled: keep it first, then change it."),
            code="billing.cancellation_pending",
        )
    recurring = _recurring_net(subscription, sale.interval, plan=sale.plan)
    tax_rates = price_sale(hub, sale, recurring_net=recurring)
    current = _plan_item(live)
    plan_line = {"price": sale.price_id, "tax_rates": tax_rates}
    if current is None:
        _require_room(live)
    items = [
        {"id": current["id"], **plan_line, "tax_rates": _rates_param(tax_rates)}
        if current
        else {**plan_line, "quantity": 1}
    ]
    if sale.interval != subscription.billing_interval:
        for item in _live_items(live):
            found = queries.module_for_price(item["price"]["id"])
            if found is None:
                continue
            module_line = module_sale(found[0].slug, sale.interval, module=found[0])
            items.append(
                {
                    "id": item["id"],
                    "price": module_line.price_id,
                    "tax_rates": _rates_param(
                        price_sale(hub, module_line, recurring_net=recurring)
                    ),
                }
            )
    if current is not None:
        return PlanChange(items, "always_invoice")
    promo = queries.redeemable_promo(
        promo_code, hub=hub, customer=subscription.stripe_customer_id
    )
    trial_end = _trial_end(subscription, promo, timezone.now())
    if trial_end is None:
        return PlanChange(items, "always_invoice")
    return PlanChange(items, "none", trial_end=trial_end, promo=promo)


def _preview(
    hub: Hub, subscription: Subscription, sale: Sale, promo_code: str = ""
) -> dict:
    live = _live(subscription)
    proration_date = int(timezone.now().timestamp())
    details: dict = {
        "proration_behavior": "always_invoice",
        "proration_date": proration_date,
    }
    if sale.kind == "plan":
        change = _plan_change(hub, subscription, live, sale, promo_code)
        if change.trial_end is None and _plan_item(live) is not None and is_downgrade(subscription, sale):
            _start, period_end = subscription_period(live)
            return {
                "flow": "confirm",
                "session_id": None,
                "client_secret": None,
                "publishable_key": None,
                "preview": {
                    "amount_due_cents": 0,
                    "tax_cents": 0,
                    "currency": "eur",
                    "proration_date": proration_date,
                    # The new price starts with the next period (a downgrade waits for it).
                    "charge_starts_at": period_end,
                },
            }
        details["items"] = change.items
        if change.trial_end is not None:
            # A trial charges nothing now: no proration (Stripe refuses a proration date without one).
            details = {
                "items": change.items,
                "proration_behavior": "none",
                "trial_end": change.trial_end,
            }
    else:
        _require_room(live)
        recurring = _recurring_net(subscription, sale.interval, adding=sale)
        details["items"] = [
            {
                "price": sale.price_id,
                "quantity": 1,
                "tax_rates": price_sale(hub, sale, recurring_net=recurring),
            }
        ]
    with stripe_errors():
        preview = stripe_service.preview_invoice(
            {
                "customer": live.get("customer") or subscription.stripe_customer_id,
                "subscription": subscription.stripe_subscription_id,
                "subscription_details": details,
            }
        )
    trial_end = live.get("trial_end")
    trialing = (
        live.get("status") == "trialing" and trial_end and trial_end > proration_date
    )
    return {
        "flow": "confirm",
        "session_id": None,
        "client_secret": None,
        "publishable_key": None,
        "preview": {
            "amount_due_cents": int(preview.get("amount_due") or 0),
            "tax_cents": tax_cents_of(preview),
            "currency": preview.get("currency") or "eur",
            "proration_date": proration_date,
            # A module added during the plan's trial is charged once the trial ends, with the plan.
            "charge_starts_at": details.get("trial_end")
            or (trial_end if trialing else None),
        },
    }


def tax_cents_of(invoice: dict) -> int:
    """The tax an invoice (or a preview) carries, in cents: ``total_taxes`` since the 2025 API, ``tax``
    before."""
    taxes = invoice.get("total_taxes")
    if taxes is not None:
        return sum(int(tax.get("amount") or 0) for tax in taxes)
    return int(invoice.get("tax") or 0)


#: How long a preview's price holds, and how far ahead of now a proration date may be (clock skew).
PREVIEW_VALID_FOR = timedelta(hours=1)
PREVIEW_SKEW = timedelta(seconds=60)


def _require_fresh_preview(proration_date: int) -> None:
    """The proration date the confirmation sends is the preview's, and the preview is recent: a date in the
    future would charge less, an old one another price."""
    now = timezone.now()
    moment = _moment(proration_date)
    if (
        moment is None
        or moment < now - PREVIEW_VALID_FOR
        or moment > now + PREVIEW_SKEW
    ):
        raise Conflict(
            _("The price shown is out of date: review it again."),
            code="billing.preview_expired",
        )


def _checkout_required() -> Conflict:
    return Conflict(
        _("This business does not pay anything yet: buy it with the checkout."),
        code="billing.checkout_required",
    )


@operation(
    "billing.checkout.confirm",
    kind="command",
    permission="billing.pay",
    input=CheckoutConfirmIn,
    output=SubscriptionOut,
)
def checkout_confirm(ctx: OperationContext, data: CheckoutConfirmIn) -> dict:
    """Add a module to the subscription of a business that pays already, at the previewed proration: the
    prorated part is charged NOW (``always_invoice``) or the module is not added (``error_if_incomplete``:
    a declined card is 409 ``billing.card_declined`` and nothing changes). Each confirmation is its own Stripe
    request (a retry after changing the card must not replay the decline); the hub's lock serialises them."""
    hub, subscription = _owned(ctx, data.hub_id)
    _require_no_pending_change(hub)
    if not _paying(subscription):
        raise _checkout_required()
    sale = module_sale(data.module, subscription.billing_interval)
    require_payments()
    _require_fresh_preview(data.proration_date)
    _require_paid_up(hub, subscription)
    _require_module_not_owned(subscription, sale.slug)
    _require_room(_live(subscription))
    tax_rates = price_sale(
        hub,
        sale,
        recurring_net=_recurring_net(subscription, sale.interval, adding=sale),
    )
    with stripe_errors(charging=True):
        stripe_service.create_subscription_item(
            {
                "subscription": subscription.stripe_subscription_id,
                "price": sale.price_id,
                "quantity": 1,
                "tax_rates": tax_rates,
                "proration_behavior": "always_invoice",
                "proration_date": data.proration_date,
                "payment_behavior": "error_if_incomplete",
                "metadata": {"hub_id": str(hub.id), "module": sale.slug},
            },
            idempotency_key=f"module-{hub.id}-{sale.slug}-{uuid.uuid4().hex}",
        )
    # Charged: a read-back that fails is not «nothing was charged»; the webhook applies it then.
    live = _read_live(subscription.stripe_subscription_id)
    if live is not None:
        apply_live(hub.id, live)
    record_event(ctx, events.MODULE_ADDED, {"hub_id": str(hub.id), "module": sale.slug})
    return subscription_out(hub.id)


@operation(
    "billing.plan.change",
    kind="command",
    permission="billing.pay",
    input=PlanChangeIn,
    output=SubscriptionOut,
)
def plan_change(ctx: OperationContext, data: PlanChangeIn) -> dict:
    """Move a paying business to another plan or billing, at the previewed proration (``billing.checkout.start``
    with the plan): charged NOW or not at all. A free business buys with the checkout; going back to Free is
    cancelling; a cancelled plan is kept before it changes. A business paying modules alone gets its plan
    with the trial it has left (or its promo code's), charging nothing until it ends."""
    user = hub_queries.account_of(ctx)
    hub, subscription = _owned(ctx, data.hub_id)
    if not _paying(subscription):
        raise _checkout_required()
    sale = plan_sale(user, data.plan, data.interval)
    require_payments()
    _require_fresh_preview(data.proration_date)
    _require_paid_up(hub, subscription)
    live = _live(subscription)
    change = _plan_change(hub, subscription, live, sale, data.promo_code)
    if change.trial_end is None and _plan_item(live) is not None and is_downgrade(subscription, sale):
        _schedule_downgrade(hub, subscription, live, sale, change.items)
        record_event(
            ctx,
            events.PLAN_CHANGE_SCHEDULED,
            {"hub_id": str(hub.id), "plan": sale.slug, "interval": sale.interval},
        )
        return subscription_out(hub.id)
    _release_pending(hub, live)
    params = {"items": change.items, "payment_behavior": "error_if_incomplete"}
    if change.trial_end is not None:
        params.update(proration_behavior="none", trial_end=change.trial_end)
    else:
        params.update(
            proration_behavior="always_invoice", proration_date=data.proration_date
        )
    with stripe_errors(charging=True):
        updated = stripe_service.update_subscription(
            subscription.stripe_subscription_id,
            params,
            idempotency_key=f"plan-{hub.id}-{sale.slug}-{sale.interval}-{uuid.uuid4().hex}",
        )
    apply_live(hub.id, updated)
    if change.promo is not None:
        redeem_promo(
            change.promo.code, hub=hub, customer=subscription.stripe_customer_id
        )
    record_event(
        ctx,
        events.PLAN_CHANGED,
        {"hub_id": str(hub.id), "plan": sale.slug, "interval": sale.interval},
    )
    return subscription_out(hub.id)


@operation(
    "billing.plan.cancel",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=SubscriptionOut,
)
def plan_cancel(ctx: OperationContext, data: HubIn) -> dict:
    """Cancel the plan at the end of its period (PLAN-SAAS §3.3): it works until then and the business goes
    back to Free, with its data. Cancelling again changes nothing."""
    hub, subscription = _owned(ctx, data.hub_id)
    if not _paying(subscription):
        raise Conflict(
            _("This business is on Free: there is nothing to cancel."),
            code="billing.nothing_to_cancel",
        )
    if not subscription.cancel_at_period_end:
        require_stripe()
        # Free wins over a downgrade that waits (Stripe refuses to cancel a scheduled subscription).
        _release_pending(hub)
        with stripe_errors():
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": True}
            )
        apply_live(hub.id, updated)
        record_event(ctx, events.PLAN_CANCELLED, {"hub_id": str(hub.id)})
    return subscription_out(hub.id)


@operation(
    "billing.plan.keep",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=SubscriptionOut,
)
def plan_keep(ctx: OperationContext, data: HubIn) -> dict:
    """Undo a cancellation before the period ends: the plan renews as before. Not with an unpaid invoice
    (pay it first: keeping would hand the plan back without paying it)."""
    hub, subscription = _owned(ctx, data.hub_id)
    if not _paying(subscription):
        raise Conflict(
            _("This business is on Free: there is nothing to keep."),
            code="billing.nothing_to_cancel",
        )
    if subscription.cancel_at_period_end:
        _require_paid_up(hub, subscription)
        require_stripe()
        with stripe_errors():
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": False}
            )
        apply_live(hub.id, updated)
        record_event(ctx, events.PLAN_KEPT, {"hub_id": str(hub.id)})
    elif pending_change(hub) is not None:
        # A downgrade that waits for the end of the period is undone: the plan renews as it is.
        require_stripe()
        _release_pending(hub)
        record_event(ctx, events.PLAN_KEPT, {"hub_id": str(hub.id)})
    return subscription_out(hub.id)


# --- A business handed over with a paid plan (HUBS-F28) -------------------------------------------------


def end_renewal_after_hand_over(hub: Hub, new_owner) -> datetime | None:
    """The business ``hub`` was just handed over to ``new_owner`` (``hubs.ownership.accept``, in its transaction):
    a plan still charged to the card of another account's payer stops renewing there (Stripe
    ``cancel_at_period_end``). The business keeps it until the end of the period already paid, the previous payer
    is never charged again, and the new owner keeps it with their own card (``billing.plan.take_over``) or it
    goes back to Free on that date. A plan the new owner already pays is left alone, and so is one already ending.
    Stripe not answering refuses the hand-over (503): nothing changes hands.

    The end of that paid period, which the mail of the hand-over tells the previous payer; ``None`` on Free or when
    the new owner already pays it."""
    subscription = Subscription.objects.filter(hub=hub).first()
    if not _paying(subscription) or hub_queries.plans_charged_to(hub.id, new_owner.pk).exists():
        return None
    if subscription.cancel_at_period_end:
        return subscription.current_period_end
    require_stripe()
    # Free wins over a downgrade that waits (Stripe refuses to cancel a scheduled subscription).
    _release_pending(hub)
    with stripe_errors():
        updated = stripe_service.update_subscription(
            subscription.stripe_subscription_id, {"cancel_at_period_end": True}
        )
    apply_live(hub.id, updated)
    logger.info("[BILLING] Hub %s handed over: its plan stops renewing on its previous payer's card", hub.id)
    return Subscription.objects.get(hub=hub).current_period_end


def billed_to_another_account(subscription: Subscription | None, profile) -> bool:
    """Whether the live plan of a business is charged to a Stripe customer that is not its payer's (``profile``):
    the card of the payer before a hand-over (HUBS-F28)."""
    if not _paying(subscription):
        return False
    return profile is None or subscription.stripe_customer_id != profile.stripe_customer_id


def _nothing_to_take_over() -> Conflict:
    return Conflict(
        _("This business's plan is already paid with your card, or it is on Free: there is nothing to keep."),
        code="billing.nothing_to_take_over",
    )


@operation(
    "billing.plan.take_over",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=CheckoutStartOut,
)
def plan_take_over(ctx: OperationContext, data: HubIn) -> dict:
    """«Keep it with my card» (HUBS-F28): the new owner of a handed-over business keeps its plan and modules with
    their own payer. An Embedded Checkout of the same prices whose billing starts on the day the paid period ends
    (``billing_cycle_anchor``, no proration): nothing is charged today and nobody pays twice. Its completion
    (``checkout_completed``) moves the business to the new subscription and ends the previous one.

    Only its owner (404 without access, 403 for another role); their own payer first (409
    ``billing.payer_required``, the form of the dialog); a business on Free or already paid with this owner's
    card has nothing to keep (409 ``billing.nothing_to_take_over``); an unpaid invoice is paid first."""
    user = hub_queries.account_of(ctx)
    member = hub_queries.access(user, data.hub_id, HubMember.Role.OWNER, lock=True)
    if not hub_queries.is_writable(member.hub):
        raise hub_services.business_deleted()
    hub = Hub.objects.select_related("billing_profile").get(pk=member.hub_id)
    subscription = Subscription.objects.select_related("plan").filter(hub=hub).first()
    if not _paying(subscription) or hub_queries.plans_charged_to(hub.id, user.pk).exists():
        raise _nothing_to_take_over()
    profile = hub.billing_profile
    if profile is None or profile.owner_id != user.pk:
        raise Conflict(
            _("Say who pays for this business first: its billing details are another account's."),
            code="billing.payer_required",
        )
    _require_paid_up(hub, subscription)
    require_payments()
    live = _live(subscription)
    if (live.get("status") or "") in ENDED_STATUSES:
        raise _nothing_to_take_over()
    _start, period_end = subscription_period(live)
    line_items = []
    for line in _live_items(live):
        sale = _item_sale(subscription, line)
        if sale is None:
            raise Conflict(
                _("This business pays something we no longer sell: contact support to keep it."),
                code="billing.unknown_price",
            )
        tax_rates = price_sale(hub, sale, recurring_net=_recurring_net(subscription, sale.interval))
        line_items.append({"price": sale.price_id, "quantity": line.get("quantity") or 1, "tax_rates": tax_rates})
    selection = f"takeover:{subscription.stripe_subscription_id}:" + ";".join(
        f"{line['price']}={','.join(line['tax_rates'])}" for line in line_items
    )
    selection = selection[:255]
    attempt = (
        CheckoutAttempt.objects.filter(
            hub=hub,
            selection=selection,
            status=CheckoutAttempt.Status.OPEN,
            created_at__gt=timezone.now() - CheckoutAttempt.REUSE_FOR,
        )
        .exclude(client_secret="")
        .order_by("-created_at")
        .first()
    )
    if attempt is None:
        attempt = _open_takeover(ctx, hub, subscription, line_items, period_end, selection)
    return {
        "flow": "checkout",
        "session_id": attempt.stripe_session_id,
        "client_secret": attempt.client_secret,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "preview": None,
    }


def _open_takeover(ctx, hub: Hub, subscription: Subscription, line_items: list[dict], period_end, selection: str):
    _expire_other_sessions(hub, selection)
    customer = ensure_customer(hub)
    attempt = CheckoutAttempt.objects.create(
        hub=hub,
        owner=hub_queries.account_of(ctx),
        kind=CheckoutAttempt.Kind.TAKEOVER,
        plan_slug=subscription.plan.slug if subscription.plan else "",
        billing_interval=subscription.billing_interval,
        selection=selection,
    )
    base = hub_emails.base_url(ctx.request)
    params = {
        "ui_mode": EMBEDDED_UI_MODE,
        "mode": "subscription",
        "customer": customer,
        "customer_update": {"name": "auto", "address": "auto"},
        "line_items": line_items,
        "metadata": {
            KIND_METADATA_KEY: CheckoutKind.PLAN_TAKEOVER.value,
            "hub_id": str(hub.id),
            "replaces": subscription.stripe_subscription_id,
            "attempt": str(attempt.id),
        },
        "subscription_data": {
            "description": f"ERPlora — {hub.name}",
            "metadata": {"hub_id": str(hub.id)},
            # Billed from the day the paid period ends, nothing before it: the business uses what was paid.
            "billing_cycle_anchor": period_end,
            "proration_behavior": "none",
        },
        "redirect_on_completion": "if_required",
        "return_url": f"{base}/businesses/{hub.id}/summary?checkout={{CHECKOUT_SESSION_ID}}",
        "locale": "auto",
        "billing_address_collection": "required",
        "tax_id_collection": {"enabled": False},
        "integration_identifier": INTEGRATION_IDENTIFIER,
    }
    with stripe_errors():
        session = stripe_service.create_checkout_session(params, idempotency_key=f"checkout-{attempt.id}")
    attempt.stripe_session_id = session["id"]
    attempt.client_secret = session.get("client_secret") or ""
    attempt.save(update_fields=["stripe_session_id", "client_secret", "updated_at"])
    record_event(
        ctx,
        events.CHECKOUT_STARTED,
        {"hub_id": str(hub.id), "kind": "takeover", "attempt": str(attempt.id)},
    )
    return attempt


def _takeover_completed(hub: Hub, session: dict, subscription_id: str, replaced: str) -> str:
    """The new owner kept the plan with their card (HUBS-F28): the business moves to the new subscription and the
    previous one, on the previous payer's card, ends now without a refund (the business is using the period it
    paid; the new one bills from its end). Stripe not answering raises: nothing moves and Stripe delivers it
    again. A redelivery finds the business moved and ends nothing twice."""
    with holding(hub.id):
        local = Subscription.objects.filter(hub=hub).first()
        if local is None or local.stripe_subscription_id != subscription_id:
            apply_live(hub.id, stripe_service.retrieve_subscription(subscription_id))
            if replaced and replaced != subscription_id:
                previous = stripe_service.retrieve_subscription(replaced)
                if (previous.get("status") or "") not in ENDED_STATUSES:
                    stripe_service.cancel_subscription(replaced)
            logger.info("[BILLING] Hub %s kept its plan with its new owner's card: %s ends", hub.id, replaced)
        CheckoutAttempt.objects.filter(stripe_session_id=session.get("id")).exclude(
            status=CheckoutAttempt.Status.COMPLETED
        ).update(status=CheckoutAttempt.Status.COMPLETED, completed_at=timezone.now(), updated_at=timezone.now())
    return "completed"


def _bought_item(subscription: Subscription | None, slug: str) -> SubscriptionItem:
    item = (
        SubscriptionItem.objects.filter(
            subscription=subscription, module_slug=slug
        ).first()
        if subscription is not None
        else None
    )
    if item is None:
        raise NotFoundError(_("This business has no such module."))
    if item.source == SubscriptionItem.Source.PLAN:
        raise Conflict(
            _("This module comes with the plan: change the plan to drop it."),
            code="billing.module_included",
        )
    return item


@operation(
    "billing.module.cancel",
    kind="command",
    permission="billing.pay",
    input=ModuleIn,
    output=SubscriptionOut,
)
def module_cancel(ctx: OperationContext, data: ModuleIn) -> dict:
    """Cancel a bought module: it leaves the subscription without proration and works until the end of the
    period (PLAN-SAAS §3.3: ``valid_until`` in the snapshot). The last thing a subscription bills ends the
    subscription at the end of the period instead (Stripe keeps at least one item)."""
    hub, subscription = _owned(ctx, data.hub_id)
    _require_no_pending_change(hub)
    item = _bought_item(subscription, data.module)
    if item.valid_until is not None:
        return subscription_out(hub.id)
    require_stripe()
    live = _live(subscription)
    others = [line for line in _live_items(live) if line["id"] != item.stripe_item_id]
    with stripe_errors():
        if others:
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id,
                {
                    "items": [{"id": item.stripe_item_id, "deleted": True}],
                    "proration_behavior": "none",
                },
            )
        else:
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": True}
            )
    apply_live(hub.id, updated)
    record_event(
        ctx, events.MODULE_CANCELLED, {"hub_id": str(hub.id), "module": data.module}
    )
    return subscription_out(hub.id)


@operation(
    "billing.module.keep",
    kind="command",
    permission="billing.pay",
    input=ModuleIn,
    output=SubscriptionOut,
)
def module_keep(ctx: OperationContext, data: ModuleIn) -> dict:
    """Undo the cancellation of a module before it ends: it is billed again from the next renewal (nothing
    is charged now: the period was paid). Not with an unpaid invoice, nor once it ended (buy it again),
    nor while the plan itself is cancelled (keep the plan first)."""
    hub, subscription = _owned(ctx, data.hub_id)
    _require_no_pending_change(hub)
    item = _bought_item(subscription, data.module)
    if item.valid_until is None:
        return subscription_out(hub.id)
    if item.valid_until <= timezone.now():
        raise Conflict(
            _("This module has ended: buy it again in the store."),
            code="billing.module_ended",
        )
    if queries.module_on_sale(item.module_slug) is None:
        # saas#2589: it works until its cancellation ends, and is not sold again by undoing it.
        raise Conflict(
            _("This module is no longer sold: it works until its cancellation ends and cannot be kept."),
            code="billing.module_off_sale",
        )
    _require_paid_up(hub, subscription)
    require_stripe()
    live = _live(subscription)
    billed = {line["id"] for line in _live_items(live)}
    with stripe_errors():
        if item.stripe_item_id and item.stripe_item_id in billed:
            if _plan_item(live) is not None:
                raise Conflict(
                    _(
                        "The plan is cancelled, and its modules with it: keep the plan first."
                    ),
                    code="billing.plan_cancelled",
                )
            live = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": False}
            )
        else:
            _require_room(live)
            sale = module_sale(
                item.module_slug,
                subscription.billing_interval,
                module=Module.objects.filter(slug=item.module_slug).first(),
            )
            tax_rates = price_sale(
                hub,
                sale,
                recurring_net=_recurring_net(subscription, sale.interval, adding=sale),
            )
            stripe_service.create_subscription_item(
                {
                    "subscription": subscription.stripe_subscription_id,
                    "price": sale.price_id,
                    "quantity": 1,
                    "tax_rates": tax_rates,
                    "proration_behavior": "none",
                    "metadata": {"hub_id": str(hub.id), "module": sale.slug},
                },
                # Its own request: keeping again after cancelling again must not replay the first keep.
                idempotency_key=f"module-keep-{hub.id}-{sale.slug}-{uuid.uuid4().hex}",
            )
            live = stripe_service.retrieve_subscription(
                subscription.stripe_subscription_id
            )
            if not any(
                (
                    found := queries.module_for_price(
                        (line.get("price") or {}).get("id", "")
                    )
                )
                and found[0].slug == sale.slug
                for line in _live_items(live)
            ):
                logger.error(
                    "[BILLING] Hub %s kept %s but Stripe does not bill it back",
                    hub.id,
                    sale.slug,
                )
                raise OperationError(
                    _(
                        "The payment service did not confirm the change. Nothing was charged; try again."
                    ),
                    code="billing.not_confirmed",
                    status=502,
                )
    apply_live(hub.id, live)
    record_event(
        ctx, events.MODULE_KEPT, {"hub_id": str(hub.id), "module": data.module}
    )
    return subscription_out(hub.id)


@operation(
    "billing.portal.open",
    kind="command",
    permission="billing.pay",
    input=PortalOpenIn,
    output=PortalOpenOut,
)
def portal_open(ctx: OperationContext, data: PortalOpenIn) -> dict:
    """Stripe's Customer Portal for the payer of the business: cards and Stripe's receipts (the panel opens
    it only on the web; the apps sell nothing, round 17 §2.5)."""
    hub, _subscription = _owned(ctx, data.hub_id)
    require_stripe()
    if not settings.STRIPE_PORTAL_CONFIGURATION:
        logger.error(
            "[BILLING] STRIPE_PORTAL_CONFIGURATION is empty: the Customer Portal does not open"
        )
        raise OperationError(
            _("Payment details cannot be managed right now. Try again later."),
            code="billing.portal_unavailable",
            status=503,
        )
    customer = hub.billing_profile.stripe_customer_id if hub.billing_profile else ""
    if not customer:
        raise Conflict(
            _("The payment details appear here after the first payment."),
            code="billing.no_customer",
        )
    with stripe_errors():
        session = stripe_service.create_portal_session(
            customer,
            return_url=f"{hub_emails.base_url(ctx.request)}/billing",
            configuration=settings.STRIPE_PORTAL_CONFIGURATION,
        )
    record_event(ctx, events.PORTAL_OPENED, {"hub_id": str(hub.id)})
    return {"url": session["url"]}


def subscription_out(hub_id) -> dict:
    subscription = Subscription.objects.select_related("plan").get(hub_id=hub_id)
    return {
        "hub_id": hub_id,
        "plan": subscription.plan.slug,
        "billing_interval": subscription.billing_interval,
        "status": subscription.status,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "current_period_end": subscription.current_period_end,
        "trial_end": subscription.trial_end,
        "modules": [
            {
                "slug": item.module_slug,
                "source": item.source,
                "valid_until": item.valid_until,
            }
            for item in subscription.items.order_by("module_slug")
        ],
        "scheduled_change": scheduled_change_of(hub_id),
    }


def scheduled_change_of(hub_id) -> dict | None:
    pending = PlanChangeSchedule.objects.filter(hub_id=hub_id).first()
    if pending is None:
        return None
    return {"plan": pending.plan_slug, "interval": pending.interval, "starts_at": pending.starts_at}


# --- What the live subscription says, applied (webhook, operations, sweep) ---------------------------


def _moment(timestamp: int | None) -> datetime | None:
    return datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else None


def unpaid_state(hub: Hub, live_status: str, now: datetime | None = None) -> dict:
    """The standing and the «why unpaid» of a business whose live subscription is ``live_status``: paid →
    good (its failures resolved); in dunning → grace for 7 days from the oldest unpaid invoice, then
    suspended (Stripe's ``unpaid`` at once); anything else leaves both as they are."""
    now = now or timezone.now()
    open_failures = PaymentFailure.objects.filter(hub=hub, resolved_at__isnull=True)
    if live_status in PAID_STATUSES or live_status in ENDED_STATUSES:
        open_failures.update(resolved_at=now)
        return {
            "standing": "good",
            "unpaid_reason": None,
            "unpaid_since": None,
            "unpaid_invoice_url": None,
        }
    if live_status not in DUNNING_STATUSES:
        return {}
    oldest = open_failures.order_by("invoice_created_at").first()
    latest = open_failures.order_by("-failed_at").first()
    since = oldest.invoice_created_at if oldest else None
    overdue = since is not None and now - since > UNPAID_PLAN_GRACE
    suspended = live_status == "unpaid" or overdue or hub.status == Hub.Status.SUSPENDED
    reason = PaymentFailure.Reason.PAYMENT_FAILED.value
    if latest is not None:
        reason = (
            "card_changed"
            if latest.reason == PaymentFailure.Reason.CARD_DECLINED
            and latest.card_changed_at
            else latest.reason
        )
    return {
        "standing": "suspended" if suspended else "grace",
        "unpaid_reason": reason,
        "unpaid_since": since,
        "unpaid_invoice_url": (latest.hosted_invoice_url or None) if latest else None,
    }


def live_state(hub: Hub, live: dict, now: datetime | None = None) -> dict:
    """``hubs.subscription.apply``'s fields for what the live subscription ``live`` says of ``hub``."""
    now = now or timezone.now()
    status = live.get("status") or ""
    if status in ENDED_STATUSES:
        return ended_state(hub, now)
    start, end = subscription_period(live)
    period_end = _moment(end)
    cancelling = bool(live.get("cancel_at_period_end") or live.get("cancel_at"))
    plan, interval, rights, unknown = None, None, {}, False
    for line in _live_items(live):
        price_id = (line.get("price") or {}).get("id", "")
        if (found := queries.plan_for_price(price_id)) is not None:
            plan, interval = found
        elif (found := queries.module_for_price(price_id)) is not None:
            module, interval = found[0], interval or found[1]
            rights[module.slug] = ModuleRightIn(
                module_slug=module.slug,
                stripe_item_id=line["id"],
                valid_until=period_end if cancelling else None,
            )
        else:
            unknown = True
            logger.error(
                "[BILLING] Stripe bills hub %s a price nobody sells: %s",
                hub.id,
                price_id,
            )
    subscription = Subscription.objects.filter(hub=hub).first()
    for item in SubscriptionItem.objects.filter(
        subscription=subscription, source=SubscriptionItem.Source.PURCHASE
    ):
        if item.module_slug in rights or not item.is_live(now):
            continue
        # Cancelled (it left Stripe without proration) and paid until the end of its period.
        rights[item.module_slug] = ModuleRightIn(
            module_slug=item.module_slug,
            stripe_item_id="",
            valid_until=item.valid_until or period_end or now,
        )
    method = live.get("default_payment_method")
    if isinstance(method, dict):
        method = method.get("id")
    if method:
        # A card put on the subscription (the Customer Portal) after a decline: «Pay» works again.
        mark_card_changed(hub=hub, method=method)
    customer = live.get("customer")
    state = {
        "status": status,
        "stripe_customer_id": customer["id"]
        if isinstance(customer, dict)
        else customer or "",
        "stripe_subscription_id": live["id"],
        "current_period_start": _moment(start),
        "current_period_end": period_end,
        "cancel_at_period_end": cancelling,
        "modules": list(rights.values()),
        **unpaid_state(hub, status, now),
    }
    if plan is not None or not unknown:
        # Only modules: the business is on Free with them. A price nobody sells leaves the plan as it is.
        state["plan"] = plan.slug if plan else _free_slug()
    if interval:
        state["billing_interval"] = interval
    if plan is not None:
        # A module bought alone on Free keeps the sign-up trial; a paid plan carries its own.
        state["trial_start"] = _moment(live.get("trial_start"))
        state["trial_end"] = _moment(live.get("trial_end"))
    return state


def _free_slug() -> str:
    plan = hub_queries.free_plan()
    return plan.slug if plan else "free"


def ended_state(hub: Hub, now: datetime | None = None) -> dict:
    """A subscription that ended: back to Free (PLAN-SAAS §3.3), its bought modules over now, nothing owed."""
    now = now or timezone.now()
    subscription = Subscription.objects.filter(hub=hub).first()
    rights = [
        ModuleRightIn(
            module_slug=item.module_slug,
            stripe_item_id="",
            valid_until=min(item.valid_until or now, now),
        )
        for item in SubscriptionItem.objects.filter(
            subscription=subscription, source=SubscriptionItem.Source.PURCHASE
        )
    ]
    return {
        "plan": _free_slug(),
        "status": Subscription.Status.ACTIVE.value,
        "stripe_subscription_id": "",
        "current_period_start": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "trial_start": None,
        "trial_end": None,
        "modules": rights,
        "cancel_requested_at": None,
        **unpaid_state(hub, "canceled", now),
    }


def apply_live(hub_id, live: dict) -> None:
    """Write what the live subscription says of the business (``hubs.subscription.apply``); a downgrade Stripe
    has just applied is forgotten."""
    hub = Hub.objects.get(pk=hub_id)
    apply_state(hub, live_state(hub, live))
    _forget_applied_change(hub_id, live)


def apply_state(hub: Hub, state: dict) -> bool:
    """Write ``state`` through ``hubs.subscription.apply``; whether anything changed."""
    applied = hub_services.subscription_apply(
        hub_services.system_ctx_for(hub.id), SubscriptionApplyIn(hub_id=hub.id, **state)
    )
    if state.get("standing") in ("grace", "suspended"):
        # Whatever put the business in dunning (a failure, Stripe's ``unpaid``, the sweep), its payer is told
        # once, after the COMMIT (BILLING-F16); a mail that cannot leave is sent by the next ``sweep_unpaid``.
        transaction.on_commit(partial(_notify_quietly, hub.id), robust=True)
    return applied.changed


# --- The webhook: each Stripe event once, the live subscription applied ------------------------------

CLAIMED, DUPLICATE, IN_PROGRESS = "claimed", "duplicate", "in_progress"


def claim_event(event_id: str, event_type: str) -> str:
    """Decide whether this delivery processes the event: ``CLAIMED`` (process it, then ``finish_event``),
    ``DUPLICATE`` (processed already) or ``IN_PROGRESS`` (another delivery holds it; Stripe retries). The
    row is created or locked in one transaction, so of two simultaneous deliveries only one claims it; a
    claim older than ``CLAIM_LEASE`` (a process that died) is taken over."""
    now = timezone.now()
    with transaction.atomic():
        row, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={"event_type": event_type, "processing_since": now, "attempts": 1},
        )
        if created:
            return CLAIMED
        if row.success:
            return DUPLICATE
        if (
            row.processing_since is not None
            and row.processing_since > now - WebhookEvent.CLAIM_LEASE
        ):
            return IN_PROGRESS
        WebhookEvent.objects.filter(pk=row.pk).update(
            processing_since=now, attempts=F("attempts") + 1
        )
        return CLAIMED


def finish_event(
    event_id: str, *, success: bool, outcome: str, error: str = ""
) -> None:
    """Release the claim with how the processing ended; a failure stays claimable for Stripe's retry."""
    WebhookEvent.objects.filter(event_id=event_id).update(
        success=success,
        outcome=outcome[:32],
        error_message=error,
        processing_since=None,
        processed_at=timezone.now(),
    )


#: How long an event's row is kept (BILLING-F37): Stripe resends an event for 3 days at most and keeps it 30, so
#: an older row never guards a delivery again.
WEBHOOK_EVENT_RETENTION = timedelta(days=30)


def purge_webhook_events() -> int:
    """saas-cron, ``manage.py purge_webhook_events``: forget the events received more than
    ``WEBHOOK_EVENT_RETENTION`` ago, processed or not. How many were deleted."""
    deleted, _ = WebhookEvent.objects.filter(received_at__lt=timezone.now() - WEBHOOK_EVENT_RETENTION).delete()
    return deleted


def process_stripe_event(event: dict) -> str:
    """Process one signed Stripe event; its outcome (``completed``, ``processed``, ``ignored``, ``unknown``,
    ``invalid``, ``pending``…). Raises when it must be retried (Stripe did not answer a read the event needs)."""
    obj = (event.get("data") or {}).get("object") or {}
    match event.get("type"):
        case "checkout.session.completed" | "checkout.session.async_payment_succeeded":
            return checkout_completed(obj)
        case "checkout.session.async_payment_failed":
            return checkout_closed(obj, CheckoutAttempt.Status.FAILED)
        case "checkout.session.expired":
            return checkout_closed(obj, CheckoutAttempt.Status.EXPIRED)
        case "invoice.paid" | "invoice.payment_succeeded":
            return invoice_paid(obj)
        case "invoice.payment_failed":
            return invoice_payment_failed(obj)
        case "invoice.voided" | "invoice.marked_uncollectible":
            return invoice_voided(obj)
        case "credit_note.created":
            return credit_note_created(obj)
        case "charge.refunded":
            return charge_refunded(obj)
        case "customer.subscription.created" | "customer.subscription.updated":
            return subscription_updated(obj)
        case "customer.subscription.deleted":
            return subscription_deleted(obj)
        case "customer.updated":
            return customer_updated(obj)
    return "ignored"


def _hub_named(hub_id) -> Hub | None:
    try:
        return Hub.objects.filter(pk=hub_id).first() if hub_id else None
    except ValueError, TypeError, DjangoValidationError:
        return None


def _checkout_paid(session: dict) -> bool:
    """A complete checkout is not always a settled payment: ``paid``, or nothing to pay now (a trial)."""
    status = session.get("payment_status")
    if status == "paid":
        return True
    return (
        status == "no_payment_required"
        and session.get("mode") == "subscription"
        and bool(session.get("subscription"))
    )


def checkout_completed(session: dict) -> str:
    """A business paid in the Embedded Checkout: its subscription, read LIVE, is applied, the attempt is
    completed and its promo code counted, once whatever the redeliveries."""
    metadata = session.get("metadata") or {}
    if checkout_session_kind(metadata) is CheckoutKind.UNKNOWN:
        return "ignored"
    hub = _hub_named(metadata.get("hub_id"))
    if hub is None or not session.get("subscription"):
        logger.error(
            "[STRIPE WEBHOOK] Checkout %s names no business of ours: %s",
            session.get("id"),
            metadata,
        )
        return "invalid"
    if not _checkout_paid(session):
        return "pending"
    subscription_id = session["subscription"]
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id["id"]
    with holding(hub.id):
        attempt = CheckoutAttempt.objects.select_related("owner").filter(stripe_session_id=session.get("id")).first()
        if attempt is not None and attempt.owner_id is not None and attempt.owner_id != hub_queries.owner_id(hub.id):
            return _end_not_owner(hub, attempt, session, subscription_id)
        if checkout_session_kind(metadata) is CheckoutKind.PLAN_TAKEOVER:
            return _takeover_completed(hub, session, subscription_id, metadata.get("replaces") or "")
        local = Subscription.objects.filter(hub=hub).first()
        if (
            local is not None
            and local.stripe_subscription_id
            and local.stripe_subscription_id != subscription_id
            and local.status not in ENDED_STATUSES
        ):
            return _end_duplicate(hub, local, session, subscription_id)
        live = stripe_service.retrieve_subscription(subscription_id)
        apply_live(hub.id, live)
        completed = (
            CheckoutAttempt.objects.filter(stripe_session_id=session.get("id"))
            .exclude(status=CheckoutAttempt.Status.COMPLETED)
            .update(
                status=CheckoutAttempt.Status.COMPLETED,
                completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
        )
        if completed and metadata.get("promo_code"):
            customer = live.get("customer")
            redeem_promo(
                metadata["promo_code"],
                hub=hub,
                customer=customer["id"]
                if isinstance(customer, dict)
                else customer or "",
                session=session.get("id") or "",
            )
    return "completed"


@contextmanager
def holding(hub_id):
    """A transaction holding the business's row: what a webhook reads from Stripe inside it is applied before
    any operation on the business can change it (operations take the same lock)."""
    with transaction.atomic():
        Hub.objects.select_for_update().filter(pk=hub_id).first()
        yield


def _end_duplicate(
    hub: Hub, local: Subscription, session: dict, subscription_id: str
) -> str:
    """A second checkout paid for a business that pays already: the subscription it has stays; the new one
    ends now, its unused time credited to the customer, and support is told (the refund is theirs)."""
    logger.error(
        "[BILLING] Hub %s paid checkout %s while it already pays %s: the new subscription %s is ended now with "
        "its unused time as credit. Refund it if the customer asks",
        hub.id,
        session.get("id"),
        local.stripe_subscription_id,
        subscription_id,
        extra={"event": "billing.duplicate_subscription", "hub_id": str(hub.id)},
    )
    stripe_service.cancel_subscription(subscription_id, credit_unused=True)
    CheckoutAttempt.objects.filter(stripe_session_id=session.get("id")).update(
        status=CheckoutAttempt.Status.COMPLETED,
        completed_at=timezone.now(),
        updated_at=timezone.now(),
    )
    return "duplicate_subscription"


#: The webhook's outcome of a checkout paid by somebody who no longer owns the business.
NOT_OWNER = "not_owner"


def _end_not_owner(hub: Hub, attempt: CheckoutAttempt, session: dict, subscription_id: str) -> str:
    """A checkout paid by somebody who no longer owns the business (handed over while it was open, review of
    saas#89): it is not applied. Its subscription ends now and what it charged is refunded in full (Stripe's
    «Cancel + refund»; ``charge.refunded`` makes the rectifying invoice), the attempt says ``refunded`` (its audit
    trail keeps when) and its payer is told after the COMMIT. Once: a redelivery finds it refunded. Stripe not
    answering raises, so nothing is marked and Stripe delivers it again (the refund is idempotent)."""
    if attempt.status == CheckoutAttempt.Status.REFUNDED:
        return NOT_OWNER
    live = stripe_service.retrieve_subscription(subscription_id)
    if (live.get("status") or "") not in ENDED_STATUSES:
        stripe_service.cancel_subscription(subscription_id)
    invoice = live.get("latest_invoice") or ""
    if isinstance(invoice, dict):
        invoice = invoice.get("id") or ""
    refunded = (
        stripe_service.refund_invoice(
            invoice,
            key=f"refund-{session.get('id')}",
            metadata={"hub_id": str(hub.id), "checkout_session": session.get("id") or "", "reason": NOT_OWNER},
        )
        if invoice
        else 0
    )
    checkout_refund_record(
        system_context(Scope("user", str(attempt.owner_id))),
        CheckoutRefundRecordIn(attempt_id=attempt.id, refunded=refunded),
    )
    logger.error(
        "[BILLING] Hub %s: checkout %s was paid by account %s, which no longer owns it. Subscription %s ended and "
        "%s cents refunded",
        hub.id,
        session.get("id"),
        attempt.owner_id,
        subscription_id,
        refunded,
        extra={"event": "billing.checkout_not_owner", "hub_id": str(hub.id)},
    )
    return NOT_OWNER


@operation(
    "billing.checkout.refund_record",
    kind="command",
    permission="billing.manage",
    input=CheckoutRefundRecordIn,
    output=CheckoutRefundRecordOut,
)
def checkout_refund_record(ctx: OperationContext, data: CheckoutRefundRecordIn) -> dict:
    """A checkout already ended and refunded in Stripe because its payer no longer owned the business (the platform
    only, from the webhook; no route): the attempt says ``refunded`` (its audit trail keeps when), the event goes
    to the payer's channel and the payer is told by mail after the COMMIT."""
    attempt = CheckoutAttempt.objects.select_for_update().get(pk=data.attempt_id)
    attempt.status = CheckoutAttempt.Status.REFUNDED
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["status", "completed_at", "updated_at"])
    record_event(
        ctx,
        events.CHECKOUT_REFUNDED,
        {"hub_id": str(attempt.hub_id), "attempt": str(attempt.id), "refunded": data.refunded},
    )
    transaction.on_commit(partial(_tell_refunded, attempt.owner_id, attempt.hub_id, data.refunded), robust=True)
    return {"attempt_id": attempt.id, "status": attempt.status}


def _tell_refunded(account_id, hub_id, cents: int) -> None:
    """The mail to the payer of a checkout ended because they no longer owned the business (after the COMMIT).
    One that cannot leave is logged (``billing.emails``): the refund and its rectifying invoice in Billing are
    the record."""
    from django.contrib.auth import get_user_model

    from billing import emails

    account = get_user_model().objects.filter(pk=account_id).first()
    hub = Hub.objects.filter(pk=hub_id).first()
    if account is None or hub is None:
        logger.error("[BILLING] Nobody to tell of the refund of hub %s to account %s", hub_id, account_id)
        return
    try:
        emails.send_checkout_refunded(hub, to=account.email, language=account.language, amount=from_cents(cents))
    except emails.MailNotSent:
        return


def expire_open_checkouts(hub_id) -> None:
    """After a hand-over's COMMIT (``hubs.ownership.accept``): the Checkout Sessions the business had open (its
    previous owner's) can no longer be paid (Stripe's ``expire``). One Stripe no longer lets expire (paid meanwhile)
    is left to the webhook, which refunds a payment of somebody who no longer owns it (``_end_not_owner``); Stripe
    away is logged as an error and changes nothing else: the hand-over is done either way."""
    for attempt in CheckoutAttempt.objects.filter(hub_id=hub_id, status=CheckoutAttempt.Status.OPEN).exclude(
        stripe_session_id=None
    ):
        try:
            stripe_service.expire_checkout_session(attempt.stripe_session_id)
        except stripe_service.StripeRefused as refused:
            logger.info(
                "[BILLING] Checkout %s of hub %s is not open any more (%s): the webhook decides",
                attempt.stripe_session_id,
                hub_id,
                refused.code,
            )
            continue
        except (stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured) as failed:
            logger.error(
                "[BILLING] Checkout %s of hub %s stays open after its hand-over: %s. A payment of it is refunded by "
                "the webhook",
                attempt.stripe_session_id,
                hub_id,
                failed,
                extra={"event": "billing.checkout_not_expired", "hub_id": str(hub_id)},
            )
            continue
        attempt.status = CheckoutAttempt.Status.EXPIRED
        attempt.save(update_fields=["status", "updated_at"])


def checkout_closed(session: dict, status: str) -> str:
    """A checkout whose delayed payment failed, or that expired unpaid: its attempt is closed (the next
    start opens a new session); the business does not change."""
    if checkout_session_kind(session.get("metadata")) is CheckoutKind.UNKNOWN:
        return "ignored"
    CheckoutAttempt.objects.filter(
        stripe_session_id=session.get("id"), status=CheckoutAttempt.Status.OPEN
    ).update(status=status, updated_at=timezone.now())
    return status


def invoice_subscription(invoice: dict) -> str:
    """The subscription an invoice bills: under ``parent.subscription_details`` since the 2025 API, at the
    root before (events of an older endpoint)."""
    parent = invoice.get("parent") or {}
    found = (
        (parent.get("subscription_details") or {}).get("subscription")
        or invoice.get("subscription")
        or ""
    )
    return found["id"] if isinstance(found, dict) else found


def _local_subscription(subscription_id: str) -> Subscription | None:
    if not subscription_id:
        return None
    return (
        Subscription.objects.select_related("hub", "plan")
        .filter(stripe_subscription_id=subscription_id)
        .first()
    )


def _read_live(subscription_id: str) -> dict | None:
    """The live subscription, or ``None`` when Stripe does not answer (the caller decides what that means)."""
    try:
        return stripe_service.retrieve_subscription(subscription_id)
    except stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured:
        logger.warning(
            "[STRIPE WEBHOOK] Could not read %s from Stripe: the event is applied as it came",
            subscription_id,
        )
        return None


def _invoice_business(invoice: dict) -> tuple[Hub | None, str]:
    """The business an invoice bills, and its Stripe subscription. Known by the subscription, or — when the
    invoice comes ahead of its ``checkout.session.completed`` (Stripe does not order events) — by the
    ``hub_id`` its subscription's metadata carries, for a business that has no other subscription."""
    subscription_id = invoice_subscription(invoice)
    local = _local_subscription(subscription_id)
    if local is not None:
        return local.hub, subscription_id
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    named = _hub_named((details.get("metadata") or {}).get("hub_id"))
    if (
        subscription_id
        and named is not None
        and not Subscription.objects.filter(hub=named)
        .exclude(stripe_subscription_id="")
        .exists()
    ):
        return named, subscription_id
    return None, subscription_id


def invoice_paid(invoice: dict) -> str:
    """A renewal (or any invoice of the subscription) was paid: its failure is resolved and the LIVE
    subscription applied, which takes a business with a payment pending or suspended back once Stripe says
    it is paid (saas#2529). A late success of an older invoice while the subscription is still in dunning
    changes nothing (saas#2261). Stripe not answering is retried by Stripe (500), never guessed.

    In the same transaction ERPlora's invoice is recorded and numbered (lot L3-C, ``billing.invoice.record``):
    when anything fails, neither the subscription nor the invoice nor its number is written. Its lines and the
    payer's VIES verdict are read before the business is locked (they may ask Stripe and VIES)."""
    hub, subscription_id = _invoice_business(invoice)
    if hub is None:
        return _invoice_paid_elsewhere(invoice, subscription_id)
    invoice = _with_all_lines(invoice)
    charged_at = _moment_or_none((invoice.get("status_transitions") or {}).get("paid_at")) or timezone.now()
    verified, consultation = _payer_clearance(hub, charged_at)
    with holding(hub.id):
        # Stripe not answering raises: its retry reads the truth (a paid invoice may be a proration or an
        # older one, and guessing «active» woke businesses still in dunning).
        live = stripe_service.retrieve_subscription(subscription_id)
        PaymentFailure.objects.filter(
            stripe_invoice_id=invoice.get("id"), resolved_at__isnull=True
        ).update(resolved_at=timezone.now())
        apply_live(hub.id, live)
        invoice_record(
            hub_services.system_ctx_for(hub.id),
            InvoiceRecordIn(
                hub_id=hub.id,
                invoice=invoice,
                status="paid",
                tax_id_verified=verified,
                vat_consultation_number=consultation,
            ),
        )
    return "processed"


class UnplacedPayment(Exception):
    """Stripe collected money on an invoice no business of ERPlora's can be found for: never forgotten, the
    webhook answers 500 (Stripe retries for three days) and the ERROR tells support."""


def _invoice_paid_elsewhere(invoice: dict, subscription_id: str) -> str:
    """A paid invoice that is not of a business's current subscription (review of L3-C): the first invoice of
    a duplicate checkout (cancelled with its unused time as credit, ``_end_duplicate``) is still money of that
    business, invoiced to it without touching its plan. One nobody can place raises."""
    named = _hub_named(((invoice.get("parent") or {}).get("subscription_details") or {}).get("metadata", {}).get("hub_id")
                       or (invoice.get("metadata") or {}).get("hub_id"))
    if named is None:
        if int(invoice.get("total") or 0) == 0:
            return "unknown" if subscription_id else "ignored"
        logger.error(
            "[INVOICE] Stripe invoice %s (subscription %s) was paid and no business of ours is known for it",
            invoice.get("id"), subscription_id or "-", extra={"event": "billing.unplaced_payment"},
        )
        raise UnplacedPayment(invoice.get("id"))
    invoice = _with_all_lines(invoice)
    charged_at = _moment_or_none((invoice.get("status_transitions") or {}).get("paid_at")) or timezone.now()
    verified, consultation = _payer_clearance(named, charged_at)
    with holding(named.id):
        invoice_record(
            hub_services.system_ctx_for(named.id),
            InvoiceRecordIn(
                hub_id=named.id, invoice=invoice, status="paid", tax_id_verified=verified,
                vat_consultation_number=consultation,
            ),
        )
    return "processed"


#: Declines the same card may pass on a retry (the bank said «not now», not «never»): «Pay» stays enabled.
SOFT_DECLINES = frozenset(
    {
        "insufficient_funds",
        "try_again_later",
        "processing_error",
        "approve_with_id",
        "reenter_transaction",
        "issuer_not_available",
        "card_velocity_exceeded",
        "withdrawal_count_limit_exceeded",
        "duplicate_transaction",
    }
)


def _failure_reason(why: dict | None) -> str:
    """Why a renewal failed, as the panel needs it: ``card_declined`` only when the card will not pay as it
    is (a true decline, an expired or mistyped card: «Pay» waits for another card), ``authentication_required``
    (the customer confirms it), ``payment_failed`` otherwise (review of L2-B)."""
    if why is None:
        return PaymentFailure.Reason.PAYMENT_FAILED
    code, decline = why.get("code"), why.get("decline_code")
    if "authentication_required" in (code, decline):
        return PaymentFailure.Reason.AUTHENTICATION_REQUIRED
    if code in CARD_REFUSED_CODES and decline not in SOFT_DECLINES:
        return PaymentFailure.Reason.CARD_DECLINED
    return PaymentFailure.Reason.PAYMENT_FAILED


def invoice_payment_failed(invoice: dict, *, replay: bool = False) -> str:
    """A renewal could not be collected: why (``PaymentFailure``) and the business in dunning. The LIVE
    subscription decides (saas#2261): outside ``past_due``/``unpaid`` what Stripe says now is written and the
    event is ignored; inside, 7 days of grace from the failed invoice, then suspended (``unpaid``: at once).
    Stripe not answering raises: Stripe retries the event, the sweep its next pass (review of L2-B).
    ``replay``: the sweep deciding again, not another failed attempt."""
    hub, subscription_id = _invoice_business(invoice)
    if hub is None:
        return "unknown" if subscription_id else "ignored"
    with holding(hub.id):
        return _record_failure(hub, subscription_id, invoice, replay=replay)


def _record_failure(
    hub: Hub, subscription_id: str, invoice: dict, *, replay: bool
) -> str:
    # Stripe not answering raises (Stripe retries the event; the sweep, its next pass): a failure is never
    # applied «as it came», which suspended businesses on stale events (review of L2-B).
    live = stripe_service.retrieve_subscription(subscription_id)
    live_status = live.get("status")
    if live_status not in DUNNING_STATUSES:
        # Paid (or ended) meanwhile: what Stripe says now is written, whatever this event said.
        logger.info(
            "[STRIPE WEBHOOK] Failure of %s ignored: the subscription is %s now",
            invoice.get("id"),
            live_status,
        )
        apply_live(hub.id, live)
        return "ignored"
    try:
        why = stripe_service.payment_failure_of(invoice["id"])
    except stripe_service.StripeUnavailable, stripe_service.StripeRefused:
        why = None
    now = timezone.now()
    reason = _failure_reason(why)
    issued = _moment(invoice.get("created")) or now
    failure, created = PaymentFailure.objects.select_for_update().get_or_create(
        stripe_invoice_id=invoice["id"],
        defaults={
            "hub": hub,
            "stripe_subscription_id": subscription_id,
            "stripe_customer_id": invoice.get("customer") or live.get("customer") or "",
            "reason": reason,
            "failure_code": (why or {}).get("code", "")[:64],
            "decline_code": (why or {}).get("decline_code", "")[:64],
            "payment_method_id": (why or {}).get("payment_method", ""),
            "hosted_invoice_url": invoice.get("hosted_invoice_url") or "",
            "invoice_created_at": issued,
            "failed_at": now,
        },
    )
    if not created and failure.resolved_at is not None:
        # Paid already: a redelivered failure of it never reopens it.
        pass
    elif not created:
        known = {
            "hosted_invoice_url": invoice.get("hosted_invoice_url")
            or failure.hosted_invoice_url
        }
        if why is not None:
            # What Stripe says now; a lookup that failed never erases what was known.
            changed_card = (
                why.get("payment_method")
                and why["payment_method"] != failure.payment_method_id
            )
            known.update(
                reason=reason,
                failure_code=why.get("code", "")[:64],
                decline_code=why.get("decline_code", "")[:64],
                payment_method_id=why.get("payment_method", "")
                or failure.payment_method_id,
                card_changed_at=None if changed_card else failure.card_changed_at,
            )
        if not replay:
            # Another failed attempt of Stripe's; the sweep only replays to decide, it is not one.
            known.update(failed_at=now, attempts=F("attempts") + 1)
        PaymentFailure.objects.filter(pk=failure.pk).update(**known)
    apply_live(hub.id, live)
    # Listed in Billing as «not collected», with «Pay» (lot L3-C); numbered once it is paid.
    invoice_record(
        hub_services.system_ctx_for(hub.id), InvoiceRecordIn(hub_id=hub.id, invoice=invoice, status="open")
    )
    return "processed"


def subscription_updated(obj: dict) -> str:
    """A subscription changed (plan, items, status, period, cancellation): the LIVE one is applied (saas#2321);
    Stripe not answering → the event as it came. The first event of a new subscription finds its business
    by the ``hub_id`` of its metadata, only if that business has no other subscription."""
    subscription_id = obj.get("id") or ""
    subscription = _local_subscription(subscription_id)
    hub = subscription.hub if subscription is not None else None
    if hub is None:
        named = _hub_named((obj.get("metadata") or {}).get("hub_id"))
        if (
            named is not None
            and not Subscription.objects.filter(hub=named)
            .exclude(stripe_subscription_id="")
            .exists()
        ):
            hub = named
    if hub is None:
        return "unknown"
    with holding(hub.id):
        # Stripe not answering raises: the event's snapshot may be stale, and Stripe retries it.
        live = stripe_service.retrieve_subscription(subscription_id)
        if live.get("status") in ("incomplete", ""):
            return "pending"
        apply_live(hub.id, live)
    return "processed"


def subscription_deleted(obj: dict) -> str:
    """The subscription ended (a cancelled plan at its period's end, Stripe giving up, a deleted business):
    the business goes back to Free (PLAN-SAAS §3.3), its bought modules end, nothing is owed. Nothing new is
    opened in Stripe (no «maintenance» subscription any more)."""
    subscription = _local_subscription(obj.get("id") or "")
    if subscription is None:
        return "unknown"
    with holding(subscription.hub_id):
        apply_state(subscription.hub, ended_state(subscription.hub))
    return "processed"


# --- saas-cron: manage.py sync_subscriptions (BILLING-F38) ----------------------------------------------

#: The counts of a pass; ``missing`` and ``errors`` make the run fail after it (``task_failed``).
SYNC_COUNTS = ("checked", "in_sync", "fixed", "drifted", "pending", "missing", "errors")
#: What the log names when a subscription drifted (``hubs.subscription.apply`` decides what is written).
DRIFT_FIELDS = (
    "plan",
    "billing_interval",
    "status",
    "stripe_subscription_id",
    "current_period_start",
    "current_period_end",
    "cancel_at_period_end",
    "trial_start",
    "trial_end",
)


def _drift(subscription: Subscription, state: dict) -> list[str]:
    """The fields where what Stripe says (``state``) and what erplora.com holds differ, bought modules too."""
    held = {field: getattr(subscription, field) for field in DRIFT_FIELDS if field != "plan"}
    held["plan"] = subscription.plan.slug
    fields = [field for field in DRIFT_FIELDS if field in state and state[field] != held[field]]
    bought = {
        (item.module_slug, item.valid_until)
        for item in subscription.items.filter(source=SubscriptionItem.Source.PURCHASE)
    }
    if {(right.module_slug, right.valid_until) for right in state["modules"]} != bought:
        fields.append("modules")
    return fields


def sync_subscription(subscription: Subscription, *, apply: bool = True) -> str:
    """Read the business's subscription from Stripe and write what it says, as a lost
    ``customer.subscription.updated`` would have (``live_state``, BILLING-F21), under the business's lock.
    ``in_sync`` · ``fixed`` · ``drifted`` (``apply=False``: nothing written) · ``pending`` (its first payment is
    not done) · ``missing`` (Stripe does not know it: left as it is, for the team). Stripe not answering raises
    (``stripe_service.StripeUnavailable``)."""
    hub = subscription.hub
    with holding(hub.id):
        # Read inside the lock, as the webhook does: nothing changes the business between reading and writing.
        try:
            live = stripe_service.retrieve_subscription(subscription.stripe_subscription_id)
        except stripe_service.StripeRefused as refused:
            if refused.code != "resource_missing":
                raise
            logger.error(
                "[BILLING] Stripe does not know subscription %s of hub %s",
                subscription.stripe_subscription_id,
                hub.id,
                extra={"event": "billing.subscription_missing", "hub_id": str(hub.id)},
            )
            return "missing"
        if live.get("status") in ("incomplete", ""):
            return "pending"
        held = Subscription.objects.select_related("plan").get(pk=subscription.pk)
        state = live_state(hub, live)
        fields = _drift(held, state)
        changed = apply_state(hub, state)
        if not apply:
            # Everything the reading wrote (a card noted as changed included) goes back.
            transaction.set_rollback(True)
        elif changed:
            _forget_applied_change(hub.id, live)
    if not changed:
        return "in_sync"
    logger.warning(
        "[BILLING] Subscription %s of hub %s drifted from Stripe: %s",
        subscription.stripe_subscription_id,
        hub.id,
        ", ".join(fields) or "its standing",
        extra={"event": "billing.subscription_drift", "hub_id": str(hub.id), "fields": fields},
    )
    return "fixed" if apply else "drifted"


def sync_subscriptions(*, apply: bool = True) -> Counter:
    """One pass of ``manage.py sync_subscriptions``: every subscription Stripe still bills (with its id), one at a
    time; one business never stops the others."""
    counts = Counter({key: 0 for key in SYNC_COUNTS})
    for subscription in (
        Subscription.objects.exclude(stripe_subscription_id="").select_related("hub").order_by("pk")
    ):
        counts["checked"] += 1
        try:
            counts[sync_subscription(subscription, apply=apply)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; the next one reads it again
            logger.exception(
                "[BILLING] Subscription %s could not be read from Stripe",
                subscription.stripe_subscription_id,
                extra={"event": "billing.sync_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts


def customer_updated(customer: dict) -> str:
    """The payer's default card changed (the Customer Portal): a declined card's failure becomes
    ``card_changed``, and «Pay» works again (mockups README §6.18). The card Billing shows
    (``billing.payment_method.get``) is read again from Stripe."""
    cache.delete(queries.card_cache_key(customer.get("id") or ""))
    method = (customer.get("invoice_settings") or {}).get("default_payment_method")
    if isinstance(method, dict):
        method = method.get("id")
    return (
        "processed"
        if method
        and mark_card_changed(stripe_customer_id=customer.get("id"), method=method)
        else "ignored"
    )


def mark_card_changed(
    *, method: str, stripe_customer_id: str | None = None, hub: Hub | None = None
) -> bool:
    """Note that the card of the unresolved declined failures (of a customer, or of a business) is not
    ``method`` any more; ``True`` when one was noted. Each business is locked before its failures (the one
    lock order of every writer: Hub, then PaymentFailure)."""

    def changeable(business_id):
        return (
            PaymentFailure.objects.filter(
                hub_id=business_id,
                resolved_at__isnull=True,
                reason=PaymentFailure.Reason.CARD_DECLINED,
                card_changed_at__isnull=True,
            )
            .exclude(payment_method_id=method)
            # The card that failed is unknown: no card can be said to be another one.
            .exclude(payment_method_id="")
        )

    if hub is not None:
        # Called with the business already held (``live_state``, inside its lock).
        return changeable(hub.id).update(card_changed_at=timezone.now()) > 0
    hub_ids = set(
        PaymentFailure.objects.filter(
            stripe_customer_id=stripe_customer_id,
            resolved_at__isnull=True,
            reason=PaymentFailure.Reason.CARD_DECLINED,
            card_changed_at__isnull=True,
        ).values_list("hub_id", flat=True)
    )
    noted = False
    for business in Hub.objects.filter(pk__in=hub_ids).order_by("pk"):
        with holding(business.id):
            now = timezone.now()
            if not changeable(business.id).update(card_changed_at=now):
                continue
            noted = True
            local = Subscription.objects.filter(hub=business).first()
            if local is not None and local.status in DUNNING_STATUSES:
                apply_state(business, unpaid_state(business, local.status, now))
    return noted


# --- The rate of a live subscription (BILLING-F02, BILLING-F06) -----------------------------------------

#: Stripe statuses whose next invoice is still going to be charged.
RETAX_STATUSES = ("active", "trialing", "past_due")
#: The counts of a daily pass; ``refused`` and ``errors`` make the run fail after its pass (``task_failed``).
RETAX_COUNTS = ("retaxed", "unchanged", "skipped", "refused", "errors")


def _rates_param(rates: list[str]) -> list[str] | str:
    """``tax_rates`` of an item UPDATE: an empty list is dropped by the SDK (Stripe keeps the old rate), an
    empty string is what removes it."""
    return rates or ""


def _item_sale(subscription: Subscription, line: dict) -> Sale | None:
    """What an item of the live subscription sells (its plan or its module, at its interval), or ``None`` for
    a price no plan nor module has."""
    price_id = (line.get("price") or {}).get("id", "")
    found = queries.plan_for_price(price_id)
    if found is not None:
        plan, interval = found
        return Sale(
            "plan",
            plan.slug,
            interval,
            price_id,
            Decimal((plan.price_annual if interval == "year" else plan.price_monthly) or 0),
            vat.SAAS_SUBSCRIPTION_CATEGORY,
            plan=plan,
        )
    found = queries.module_for_price(price_id)
    if found is not None:
        module, interval = found
        cents = module.price_annual_cents if interval == "year" else module.price_monthly_cents
        return Sale(
            "module",
            module.slug,
            interval,
            price_id,
            Decimal(cents) / 100,
            vat.SOFTWARE_LICENSE_CATEGORY,
            module=module,
        )
    logger.warning(
        "[BILLING] Item %s of %s bills price %s, which no plan nor module has: its rate is left alone",
        line.get("id"),
        subscription.stripe_subscription_id,
        price_id,
    )
    return None


def retax_subscription(hub: Hub) -> str:
    """Hand Stripe the rates the payer's place calls for today on every item of the business's live
    subscription: the checkout fixes a rate per item and Stripe charges it on every renewal, so a payer who
    moves (Madrid → Las Palmas), proves a VAT number, or a year that crosses the OSS threshold would keep the
    old one (saas#2293). The same engine as the sale (``price_sale``); the next invoice takes the new rate,
    the paid period is not touched (no proration).

    ``retaxed`` · ``unchanged`` (Stripe already holds them: nothing sent) · ``skipped`` (no live Stripe
    subscription, or one still charged to another account's card: its tax is that payer's, HUBS-F28) ·
    ``refused`` (the place is not sold to now: an ERROR, and the old rates stay until the billing details are
    fixed). With a downgrade waiting in a schedule, its phases are retaxed instead (``_retax_schedule``). Stripe
    failing raises (``stripe_errors``)."""
    subscription = Subscription.objects.filter(hub=hub).select_related("plan").first()
    if (
        subscription is None
        or not subscription.stripe_subscription_id
        or subscription.status not in RETAX_STATUSES
    ):
        return "skipped"
    hub = Hub.objects.select_related("billing_profile").get(pk=hub.pk)
    if billed_to_another_account(subscription, hub.billing_profile):
        return "skipped"
    require_stripe()
    pending = pending_change(hub)
    if pending is not None:
        return _retax_schedule(hub, subscription, pending.stripe_schedule_id)
    live = _live(subscription)
    changes = []
    for line in _live_items(live):
        sale = _item_sale(subscription, line)
        if sale is None:
            continue
        try:
            due = price_sale(
                hub, sale, recurring_net=_recurring_net(subscription, sale.interval)
            )
        except Conflict as refused:
            return _retax_refused(hub, sale.kind, refused)
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in line.get("tax_rates") or []]
        if sorted(held) != sorted(due):
            changes.append({"id": line["id"], "tax_rates": _rates_param(due)})
    if not changes:
        return "unchanged"
    with stripe_errors():
        stripe_service.update_subscription(
            subscription.stripe_subscription_id,
            {"items": changes, "proration_behavior": "none"},
        )
    logger.info("[BILLING] Hub %s retaxed: %s", hub.id, changes)
    return "retaxed"


def _retax_refused(hub: Hub, kind: str, refused: Conflict) -> str:
    logger.error(
        "[BILLING] %s of hub %s cannot be retaxed (%s): Stripe keeps charging its old rate",
        kind,
        hub.id,
        refused.code,
        extra={"event": "billing.retax_refused", "hub_id": str(hub.id), "code": refused.code},
    )
    return "refused"


def _retax_schedule(hub: Hub, subscription: Subscription, schedule_id: str) -> str:
    """A downgrade waiting in a Stripe schedule: the first invoice of the new plan is billed by its next phase,
    whose items carry the rates fixed when it was scheduled. Every phase still to run is re-stated with
    today's rates (a phase over is left out; the current one keeps its start). Phases are re-stated whole, so
    no rate is an empty list there, and changing the current phase changes the subscription at once (checked
    against Stripe's test API). A price no plan nor module has keeps its rates."""
    with stripe_errors():
        schedule = stripe_service.retrieve_schedule(schedule_id)
    now = int(timezone.now().timestamp())
    phases = []
    changed = False
    for phase in schedule.get("phases") or []:
        end = phase.get("end_date")
        if end is not None and end <= now:
            continue
        sales = []
        for item in phase.get("items") or []:
            price = item["price"] if isinstance(item["price"], str) else item["price"]["id"]
            held = [rate["id"] if isinstance(rate, dict) else rate for rate in item.get("tax_rates") or []]
            sales.append((price, item.get("quantity") or 1, held, _item_sale(subscription, {"price": {"id": price}})))
        # What a renewal of that phase charges, net: the 400 € of the simplified invoice is on the whole of it.
        recurring = sum((sale.net for _price, _quantity, _held, sale in sales if sale is not None), Decimal("0"))
        items = []
        for price, quantity, held, sale in sales:
            if sale is None:
                due = held
            else:
                try:
                    due = price_sale(hub, sale, recurring_net=recurring)
                except Conflict as refused:
                    return _retax_refused(hub, sale.kind, refused)
            changed = changed or sorted(held) != sorted(due)
            items.append({"price": price, "quantity": quantity, "tax_rates": due})
        restated = {"items": items, "start_date": phase["start_date"]}
        if end is not None:
            restated["end_date"] = end
        if phase.get("trial_end"):
            restated["trial_end"] = phase["trial_end"]
        restated["proration_behavior"] = "none"
        phases.append(restated)
    if not changed:
        return "unchanged"
    with stripe_errors():
        stripe_service.update_schedule(schedule_id, {"end_behavior": "release", "phases": phases})
    logger.info("[BILLING] Hub %s retaxed the phases of schedule %s", hub.id, schedule_id)
    return "retaxed"


def retax_payer(profile_id) -> None:
    """After the owner saves the billing details (on commit): the payer's Stripe customer takes them
    (BILLING-F01) and every business this payer pays is retaxed (BILLING-F02). A failure is logged and never
    stops the other: the next checkout brings the customer up to date (``ensure_customer``), the daily pass
    (``retax_subscriptions``) retaxes again."""
    paid = list(Hub.objects.filter(billing_profile_id=profile_id).order_by("pk"))
    try:
        push_payer_to_stripe(profile_id)
    except Exception:  # noqa: BLE001 - the save stands; the next checkout updates the customer
        logger.exception(
            "[BILLING] The Stripe customer of payer %s did not take the new billing details",
            profile_id,
            extra={"event": "billing.customer_push_failed", "hub_id": str(paid[0].id) if paid else ""},
        )
    for hub in paid:
        try:
            retax_subscription(hub)
        except Exception:  # noqa: BLE001 - the save stands; the daily pass retaxes it
            logger.exception(
                "[BILLING] Hub %s could not be retaxed after its billing details changed",
                hub.id,
                extra={"event": "billing.retax_failed", "hub_id": str(hub.id)},
            )


def retax_live_subscriptions() -> Counter:
    """One daily pass: every live Stripe subscription takes the rates of today (an address change whose push
    failed, the OSS threshold crossed or a new year back to origin, a rate the table schedules). One business
    never stops the others."""
    counts = Counter({key: 0 for key in RETAX_COUNTS})
    live = (
        Subscription.objects.filter(status__in=RETAX_STATUSES)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in live:
        try:
            counts[retax_subscription(subscription.hub)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[BILLING] %s could not be retaxed",
                subscription.stripe_subscription_id,
                extra={"event": "billing.retax_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts


# --- saas-cron: manage.py sweep_unpaid ----------------------------------------------------------------

#: The counts a sweep reports; ``errors`` makes the run fail after its whole pass (``task_failed``).
SWEEP_COUNTS = (
    "checked",
    "suspended",
    "cancelled",
    "payers_forgotten",
    "notified",
    "mail_failed",
    "errors",
    # The clock of the suspended businesses (HUBS-F20, ``hubs.services.age_suspended``).
    "warned",
    "final_notice",
    "expired",
    "undated",
)
#: Businesses whose unpaid plan the sweep looks at: still running (a suspended one already is).
SWEPT_STATUSES = [Hub.Status.PREPARING, Hub.Status.ACTIVE, Hub.Status.PAST_DUE]


def sweep_unpaid() -> Counter:
    """One pass of ``sweep_unpaid`` (saas#2594): every business in dunning still running is replayed with its
    OLDEST open invoice through ``invoice_payment_failed`` (the live subscription decides; ``unpaid`` at once,
    else past the grace; one suspension), and the Stripe subscription of every deleted business is
    cancelled now. One business never stops the others; Stripe missing or failing for one is an error."""
    counts = Counter({key: 0 for key in SWEEP_COUNTS})
    configured = stripe_service.key_mode() is not StripeKeyMode.UNKNOWN
    owed = (
        Subscription.objects.filter(
            status__in=DUNNING_STATUSES, hub__status__in=SWEPT_STATUSES
        )
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in owed:
        counts["checked"] += 1
        if not configured:
            logger.error(
                "[UNPAID SWEEP] Stripe is not configured: %s is not swept",
                subscription.stripe_subscription_id,
            )
            counts["errors"] += 1
            continue
        try:
            invoices = stripe_service.open_invoices(subscription.stripe_subscription_id)
            if invoices:
                invoice_payment_failed(
                    min(invoices, key=lambda invoice: invoice.get("created") or 0),
                    replay=True,
                )
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[UNPAID SWEEP] %s could not be swept",
                subscription.stripe_subscription_id,
            )
            counts["errors"] += 1
            continue
        if Hub.objects.filter(
            pk=subscription.hub_id, status=Hub.Status.SUSPENDED
        ).exists():
            counts["suspended"] += 1
    # The businesses suspended too long (HUBS-F20; PLAN-SAAS §1.1): the notices of day 30 and 150 and the deletion
    # on day 180, which the loop below ends in Stripe in this same pass.
    counts.update(hub_services.age_suspended())
    # Asked at deletion (``hubs.business.delete``), whatever the business is now: recovered on Free, too.
    deleted = (
        Subscription.objects.filter(cancel_requested_at__isnull=False)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in deleted:
        if not configured:
            logger.error(
                "[UNPAID SWEEP] Stripe is not configured: deleted hub %s still pays",
                subscription.hub_id,
            )
            counts["errors"] += 1
            continue
        try:
            _end_billing_of_deleted(subscription)
        except Exception:  # noqa: BLE001 - kept for the next run, which fails until it goes through
            logger.exception(
                "[UNPAID SWEEP] The billing of deleted hub %s could not be ended",
                subscription.hub_id,
            )
            counts["errors"] += 1
            continue
        counts["cancelled"] += 1
    # The payers of deleted accounts, once nothing more can be charged to them (ACCOUNTS-F27).
    departed = BillingProfile.objects.filter(forget_after__isnull=False).order_by("pk").values_list("pk", flat=True)
    for profile_id in list(departed):
        try:
            outcome = forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - one payer never stops the pass; it is retried on the next one
            logger.exception("[UNPAID SWEEP] The payer %s of a deleted account could not be forgotten", profile_id)
            counts["errors"] += 1
            continue
        if outcome == PAYER_FORGOTTEN:
            counts["payers_forgotten"] += 1
    # A mail of the unpaid episode that could not leave is sent again here (BILLING-F16).
    untold = (
        PaymentFailure.objects.filter(resolved_at__isnull=True)
        .filter(
            Q(hub__status=Hub.Status.PAST_DUE, notified_at__isnull=True)
            | Q(hub__status=Hub.Status.SUSPENDED, suspension_notified_at__isnull=True)
        )
        .values_list("hub_id", flat=True)
        .distinct()
    )
    for hub_id in sorted(set(untold)):
        try:
            outcome = notify_unpaid(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("[UNPAID SWEEP] The payer of hub %s could not be told", hub_id)
            outcome = MAIL_NOT_SENT
        if outcome == NOTIFIED:
            counts["notified"] += 1
        elif outcome == MAIL_NOT_SENT:
            counts["mail_failed"] += 1
    return counts


NOTIFIED, NOTHING_TO_TELL, MAIL_NOT_SENT = "notified", "nothing", "mail_failed"


def notify_unpaid(hub_id) -> str:
    """Tell the payer of ``hub_id`` what its unpaid episode owes them (BILLING-F16, saas#2593): each unpaid
    invoice once, while the business still works (how much, until when, where to pay); the suspension once,
    which also stands for the invoices not told yet. The business is locked, so two deliveries never send the
    same mail twice. Nobody to tell is done too; a mail that cannot leave stays owed (``MAIL_NOT_SENT``)."""
    from billing import emails

    with holding(hub_id):
        hub = Hub.objects.select_related("billing_profile__owner").get(pk=hub_id)
        owed = list(PaymentFailure.objects.filter(hub=hub, resolved_at__isnull=True).order_by("invoice_created_at"))
        suspended = hub.status == Hub.Status.SUSPENDED
        if suspended:
            to_tell = [] if any(f.suspension_notified_at for f in owed) else owed
        else:
            to_tell = [f for f in owed if f.notified_at is None] if hub.status == Hub.Status.PAST_DUE else []
        if not to_tell:
            return NOTHING_TO_TELL
        to, language = _unpaid_recipient(hub)
        now = timezone.now()
        try:
            if to and suspended:
                emails.send_business_suspended(
                    hub, to=to, language=language, amount=sum((_owed_amount(f) for f in owed), Decimal(0))
                )
            elif to:
                for failure in to_tell:
                    emails.send_payment_failed(
                        hub,
                        to=to,
                        language=language,
                        amount=_owed_amount(failure),
                        declined=failure.reason == PaymentFailure.Reason.CARD_DECLINED,
                        suspends_on=failure.invoice_created_at + UNPAID_PLAN_GRACE,
                    )
                    PaymentFailure.objects.filter(pk=failure.pk).update(notified_at=now)
        except emails.MailNotSent:
            return MAIL_NOT_SENT
        if not to:
            logger.warning("[UNPAID] Hub %s owes an invoice and has nobody to tell", hub.id)
        if suspended:
            PaymentFailure.objects.filter(pk__in=[f.pk for f in owed]).update(
                suspension_notified_at=now, notified_at=Coalesce("notified_at", Value(now))
            )
        return NOTIFIED


def _unpaid_recipient(hub: Hub) -> tuple[str, str]:
    """Who hears of the unpaid invoice: the payer's address for invoices, else the payer's own (the owner's
    when the business has no payer yet), in the payer's language."""
    profile = hub.billing_profile
    account = (profile.owner if profile is not None else None) or _owner_of(hub)
    to = (profile.billing_email if profile is not None else "") or (account.email if account else "")
    return to, getattr(account, "language", "") or hub.language or settings.LANGUAGE_CODE


def _owed_amount(failure: PaymentFailure) -> Decimal:
    """What the unpaid invoice asks for, as Billing lists it («Not collected»)."""
    listed = Invoice.objects.filter(stripe_invoice_id=failure.stripe_invoice_id).first()
    return listed.total if listed is not None else Decimal(0)


def _notify_quietly(hub_id) -> None:
    try:
        notify_unpaid(hub_id)
    except Exception:  # noqa: BLE001 - a mail never undoes the dunning; sweep_unpaid sends it again
        logger.exception("[UNPAID] The payer of hub %s could not be told", hub_id)


def _end_billing_of_deleted(subscription: Subscription) -> None:
    """A deleted business stops paying now (``test_hub_delete_cancels_billing``): a subscription Stripe no
    longer has counts as ended; any other failure keeps it for the next run."""
    try:
        stripe_service.cancel_subscription(subscription.stripe_subscription_id)
    except stripe_service.StripeRefused as refused:
        if refused.code != "resource_missing":
            raise
    logger.info(
        "[UNPAID SWEEP] Ended %s of deleted hub %s",
        subscription.stripe_subscription_id,
        subscription.hub_id,
    )
    with transaction.atomic():
        apply_state(subscription.hub, ended_state(subscription.hub))


# --- The payer of an account that deleted itself (ACCOUNTS-F27) ----------------------------------------
#
# GDPR art. 17: the payer record (``hubs.BillingProfile``) and its Stripe customer go with the account; the
# invoices ERPlora issued keep their own copy of the payer (Commercial Code art. 30, General Tax Law art. 66),
# which is what the law asks to keep (art. 17(3)(b)). Only what can still be charged holds the payer, because
# the invoice issued at that payment must name it: a subscription Stripe still bills, or an invoice not paid
# yet, which waits at most ``PAYER_RETENTION`` and is then voided in Stripe, as Stripe advises for a deletion
# request (docs.stripe.com/privacy/deletion-requests).

#: How long the payer of a deleted account waits for an invoice still unpaid: the 90 days a deleted business
#: is kept (``Hub.RETENTION``). On that day (``forget_after``) what is unpaid is voided and the payer goes.
PAYER_RETENTION = Hub.RETENTION
PAYER_FORGOTTEN = "forgotten"
PAYER_HELD = "held"


def payer_leaving(sender, user_id, **kwargs) -> None:
    """``accounts.signals.account_deleting``: each payer of the account gets its purge date and goes after the
    COMMIT, unless something can still be charged to it (``forget_departed_payer``; ``sweep_unpaid`` finishes).

    A live subscription only holds it here in a business that was deleted, which ``sweep_unpaid`` cancels on its
    next pass. A business still alive never does: whoever still pays for it (``hubs.queries.still_pays``) can
    neither delete its account (409 ``accounts.pays_businesses``) nor be taken out of it (409 ``hubs.member_pays``)."""
    profile_ids = list(BillingProfile.objects.filter(owner_id=user_id).values_list("pk", flat=True))
    if not profile_ids:
        return
    now = timezone.now()
    BillingProfile.objects.filter(pk__in=profile_ids).update(forget_after=now + PAYER_RETENTION, updated_at=now)
    transaction.on_commit(partial(_forget_payers_quietly, profile_ids), robust=True)


def _forget_payers_quietly(profile_ids) -> None:
    for profile_id in profile_ids:
        try:
            forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the deletion; sweep_unpaid retries
            logger.exception("[PAYER] The payer %s of a deleted account could not be forgotten yet", profile_id)


def forget_departed_payer(profile_id, now: datetime | None = None) -> str:
    """Forget the payer of a deleted account (``forget_after`` set) once nothing can be charged to it any more:
    no subscription Stripe still bills for its businesses, and no invoice of it unpaid (from its purge date,
    those are voided in Stripe first). Its Stripe customer is deleted, its businesses stop naming it and the
    record goes. ``PAYER_HELD`` while something holds it; a Stripe failure raises (the sweep counts it)."""
    now = now or timezone.now()
    profile = BillingProfile.objects.filter(pk=profile_id, forget_after__isnull=False).first()
    if profile is None:
        return PAYER_FORGOTTEN
    if Subscription.objects.filter(hub__billing_profile=profile).exclude(stripe_subscription_id="").exists():
        return PAYER_HELD
    unpaid = Invoice.objects.filter(
        Q(billing_profile=profile) | Q(hub__billing_profile=profile), payment_status=Invoice.PaymentStatus.OPEN
    )
    if unpaid.exists():
        if now < profile.forget_after:
            return PAYER_HELD
        for stripe_invoice_id in list(unpaid.values_list("stripe_invoice_id", flat=True)):
            invoice_voided(stripe_service.void_invoice(stripe_invoice_id))
    if profile.stripe_customer_id:
        try:
            stripe_service.delete_customer(profile.stripe_customer_id)
        except stripe_service.StripeRefused as refused:
            if refused.code != "resource_missing":
                raise
    with transaction.atomic():
        Hub.objects.filter(billing_profile=profile).update(billing_profile=None, updated_at=now)
        profile.delete()
    logger.info("[PAYER] The payer %s of a deleted account is forgotten", profile_id)
    return PAYER_FORGOTTEN


# --- ERPlora's invoices: the number (lot L3-C) ---------------------------------------------------------

#: The series of each kind of document: a rectifying invoice has its own (RD 1619/2012, art. 15.5).
INVOICE_SERIES = {Invoice.Kind.INVOICE: "ERP", Invoice.Kind.CREDIT_NOTE: "ERPR"}


def invoice_today() -> date:
    """The issue date of an invoice numbered now (the tests set it)."""
    return timezone.localdate()


def issue_number(kind: str) -> tuple[str, int, str, date]:
    """The next number of ``kind``'s series and its issue date: ``(series, sequence, "ERP-2026-00123", date)``.

    ``fiscal_counter`` (CLAUDE.md, «Fiscal»): the series' row is locked in the transaction that records the
    invoice, and only then the date is read, so a number that waited for another one never carries an earlier
    date (review of L3-C); a new year starts at 1. A second invoice waits for the first one's COMMIT, and a
    ROLLBACK gives the number back: no gap, no duplicate (a Postgres sequence would leave a hole). Refused
    outside a transaction: a number given alone is a hole the day its invoice fails.
    """
    if connection.get_autocommit():
        raise RuntimeError("An invoice number is only given inside the transaction that records its invoice")
    series = INVOICE_SERIES[kind]
    table = InvoiceCounter._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table} (id, series, year, last_number) VALUES (%s, %s, 0, 0) ON CONFLICT (series) DO NOTHING",
            [uuid.uuid7(), series],
        )
        cursor.execute(f"SELECT year, last_number FROM {table} WHERE series = %s FOR UPDATE", [series])
        year, last_number = cursor.fetchone()
        on = invoice_today()
        sequence = last_number + 1 if year == on.year else 1
        cursor.execute(
            f"UPDATE {table} SET year = %s, last_number = %s WHERE series = %s RETURNING last_number",
            [on.year, sequence, series],
        )
        sequence = cursor.fetchone()[0]
    return series, sequence, f"{series}-{on.year}-{sequence:05d}", on


# --- ERPlora's invoices: recorded from Stripe (lot L3-C) -----------------------------------------------
#
# PLAN-SAAS §4: «the Stripe receipt is not the legal invoice». A paid Stripe invoice becomes ERPlora's
# ``Invoice`` in the webhook's transaction (the durability is the row, ADR-0478 §4), numbered here and issued
# by ERPlora's platform hub in hub-next, which chains it in VeriFactu (``post_platform_invoice``, after the
# COMMIT). An unpaid one is listed without a number («Not collected», «Pay»); a credit note is a rectifying
# invoice of its own series.


def _with_all_lines(invoice: dict) -> dict:
    """The Stripe invoice with every line in ``lines.data`` (the event embeds only the first ones)."""
    lines = stripe_service.invoice_lines(invoice)
    return {**invoice, "lines": {"object": "list", "data": lines, "has_more": False}}


class VatProofUnavailable(Exception):
    """VIES could not answer and no verdict on file says how the payer's VAT number stood when it was charged:
    the invoice waits (the webhook answers 500 and Stripe retries) rather than guess."""


def _payer_clearance(hub: Hub, charged_at: datetime) -> tuple[bool, str]:
    """Whether the payer's VAT number grants the reverse charge on a sale charged at ``charged_at``, and the
    VIES consultation number that proves it. Asked before the business is locked (VIES may take seconds).

    Judged as of the charge (review of L3-C): the last verdict VIES gave until then decides, even one older
    than the 30 days a SALE trusts (the proof travels with the invoice; a later outage of VIES cannot turn a
    verified intra-EU B2B sale into a Spanish one). With no verdict before the charge, VIES is asked now; if it
    cannot answer, ``VatProofUnavailable``: never Spanish VAT because VIES was down. Only a number of ANOTHER
    member state is ever judged: a national or a non-EU one cannot be reverse charged."""
    profile = hub.billing_profile
    if profile is None or not profile.tax_id:
        return False, ""
    country = (profile.billing_country or "").strip().upper()
    issuer = _issuer_country()
    value = vies.with_country_prefix(profile.tax_id, country, issuer_country=issuer)
    if (
        not value
        or country == issuer
        or country not in vat.EU_VAT_RATES
        or vies.is_uk_vat_number(value)
        or vies.is_domestic_vat_number(value, issuer_country=issuer, customer_country=country)
    ):
        return False, ""
    verdict = queries.vat_verdict_as_of(value, charged_at)
    if verdict is not None:
        if verdict.status == VatCheck.VERIFIED:
            return True, verdict.consultation_number
        return False, ""
    clearance = clear_tax_id_for_stripe(value, customer_country=country)
    if clearance.verified:
        return True, (clearance.check.consultation_number if clearance.check is not None else "")
    if clearance.status == CLEARANCE_INVALID:
        return False, ""
    logger.error(
        "[INVOICE] VIES cannot answer about %s and nothing on file proves it: the invoice of hub %s waits",
        value, hub.id, extra={"event": "billing.invoice_waits_for_vies"},
    )
    raise VatProofUnavailable(value)


def _moment_or_none(value) -> datetime | None:
    return _moment(int(value)) if value else None


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


def _nominal_rate(breakdown: vat.VatBreakdown, category: str) -> Decimal:
    """The rate of the rule in force for what is sold where the sale is taxed (the declared rate: Stripe's
    effective one moves a hundredth with the rounding)."""
    rate = vat.vat_rate_for(country=breakdown.tax_country, region=breakdown.tax_region, category_key=category)
    return rate if rate is not None else breakdown.rate


def _sealed_amounts(amount: int, tax: int, *, treatment: str, rate: Decimal, reconciled: bool) -> tuple[Decimal, int, int]:
    """``(rate, net, tax)`` of a line in cents, by the qualification of the sale: without a rate (reverse
    charge, not subject) all of it is base; reconciled (Stripe charged no tax on a subject sale) the VAT comes
    out of the amount charged; otherwise Stripe's amounts rule (ADR-0123)."""
    if treatment not in vat.TREATMENTS_WITH_RATE:
        return Decimal("0.00"), amount + tax, 0
    if reconciled:
        base, _quota = vat.split_gross(from_cents(amount + tax), rate)
        net = to_cents(base)
        return rate, net, amount + tax - net
    return rate, amount, tax


def _payer_snapshot(hub: Hub, *, verified: bool, consultation: str) -> dict:
    """The payer as it is today (``hubs.BillingProfile``), copied onto the invoice: an edit of the profile
    never rewrites an issued invoice."""
    profile = hub.billing_profile
    if profile is None:
        return {"payer_name": "", "language": hub.language or settings.LANGUAGE_CODE}
    owner = profile.owner
    country = (profile.billing_country or "").strip().upper()
    tax_id = vies.normalise(profile.tax_id)
    return {
        "billing_profile": profile,
        "payer_account": owner,
        "payer_name": profile.billing_name or (owner.get_full_name() if owner else "") or "",
        "payer_tax_id": tax_id,
        "payer_tax_id_type": vat.tax_id_type_for(country) if tax_id else "",
        "payer_tax_id_verified": verified,
        "vat_consultation_number": consultation if verified else "",
        "payer_address": profile.billing_address or "",
        "payer_city": profile.billing_city or "",
        "payer_postal_code": (profile.billing_postal_code or "").strip().upper(),
        "payer_country": country,
        "payer_email": profile.billing_email or (owner.email if owner else ""),
        "language": (getattr(owner, "language", "") or hub.language or settings.LANGUAGE_CODE),
    }


@operation(
    "billing.invoice.record",
    kind="command",
    permission="billing.manage",
    input=InvoiceRecordIn,
    output=InvoiceRecordOut,
)
def invoice_record(ctx: OperationContext, data: InvoiceRecordIn) -> dict:
    """The webhook's door to ERPlora's invoices (the platform only; no route): a Stripe invoice of a
    business, ``open`` (listed, not collected), ``paid`` (numbered and issued) or ``void`` (Stripe gave up).
    Idempotent by the Stripe invoice: a paid one is never recorded twice, nor reopened."""
    hub = Hub.objects.select_related("billing_profile__owner").get(pk=data.hub_id)
    stripe_invoice = data.invoice
    existing = (
        Invoice.objects.select_for_update()
        .filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice.get("id") or "")
        .first()
    )
    if data.status == "void":
        return _void(ctx, existing)
    if existing is not None and existing.payment_status == Invoice.PaymentStatus.PAID:
        return _record_out(existing, "duplicate")
    total = int(stripe_invoice.get("total") or 0)
    if total < 0 and data.status == "paid":
        return _record_negative(ctx, hub, stripe_invoice)
    if total <= 0:
        return _record_out(existing, "ignored")
    if data.status == "open":
        return _record_open(ctx, hub, stripe_invoice, existing)
    return _record_paid(ctx, hub, data, existing)


def _record_out(invoice: Invoice | None, outcome: str) -> dict:
    return {
        "id": invoice.id if invoice else None,
        "number": invoice.number if invoice else "",
        "payment_status": invoice.payment_status if invoice else "",
        "outcome": outcome,
    }


def _stripe_fields(stripe_invoice: dict) -> dict:
    return {
        "stripe_number": (stripe_invoice.get("number") or "")[:64],
        "hosted_invoice_url": stripe_invoice.get("hosted_invoice_url") or "",
        "billed_at": _moment_or_none(stripe_invoice.get("created")),
        "currency": (stripe_invoice.get("currency") or "eur").upper(),
    }


def _record_open(ctx, hub: Hub, stripe_invoice: dict, existing: Invoice | None) -> dict:
    """An unpaid Stripe invoice, listed with what it asks (no number: one is given at the payment)."""
    if existing is not None:
        if existing.payment_status == Invoice.PaymentStatus.OPEN:
            Invoice.objects.filter(pk=existing.pk).update(
                hosted_invoice_url=stripe_invoice.get("hosted_invoice_url") or existing.hosted_invoice_url,
                updated_at=timezone.now(),
            )
        return _record_out(existing, "duplicate")
    total = int(stripe_invoice["total"])
    tax = tax_cents_of(stripe_invoice)
    profile = hub.billing_profile
    listed = Invoice.objects.create(
        kind=Invoice.Kind.INVOICE,
        hub=hub,
        business_name=hub.name,
        billing_profile=profile,
        payer_account=profile.owner if profile else None,
        stripe_invoice_id=stripe_invoice["id"],
        payment_status=Invoice.PaymentStatus.OPEN,
        net_cents=total - tax,
        tax_cents=tax,
        total_cents=total,
        **_stripe_fields(stripe_invoice),
    )
    _record_invoice_event(ctx, listed, events.INVOICE_RECORDED,
                          {"id": str(listed.id), "hub_id": str(hub.id), "payment_status": "open"})
    return _record_out(listed, "listed")


def _void(ctx, existing: Invoice | None) -> dict:
    """Stripe voided (or gave up on) an unpaid invoice: it leaves «not collected». A paid one never changes."""
    if existing is None or existing.payment_status != Invoice.PaymentStatus.OPEN:
        return _record_out(existing, "ignored")
    Invoice.objects.filter(pk=existing.pk).update(payment_status=Invoice.PaymentStatus.VOID, updated_at=timezone.now())
    _record_invoice_event(ctx, existing, events.INVOICE_VOIDED, {"id": str(existing.id), "hub_id": str(existing.hub_id)})
    existing.payment_status = Invoice.PaymentStatus.VOID
    return _record_out(existing, "voided")


def _record_paid(ctx, hub: Hub, data: InvoiceRecordIn, existing: Invoice | None) -> dict:
    """A paid Stripe invoice becomes ERPlora's invoice: the payer sealed, the qualification of the sale and
    each line's base, rate and quota sealed, the next number of the series; issued after the COMMIT."""
    stripe_invoice = data.invoice
    total = int(stripe_invoice["total"])
    payer = queries.payer_of(hub)
    breakdown = vat.resolve_vat(
        from_cents(total),
        customer_country=payer.country,
        customer_postal_code=payer.postal_code,
        customer_tax_id=payer.tax_id,
        customer_tax_id_type=payer.tax_id_type,
        customer_tax_id_verified=data.tax_id_verified,
        category_key=vat.SAAS_SUBSCRIPTION_CATEGORY,
        tax_cents=tax_cents_of(stripe_invoice),
        tax_included=False,
    )
    lines = []
    for position, line in enumerate((stripe_invoice.get("lines") or {}).get("data") or [], start=1):
        kind, slug, category = _item_of(_price_of(line))
        rate, net, tax = _sealed_amounts(
            int(line.get("amount") or 0),
            _line_tax_cents(line),
            treatment=breakdown.treatment,
            rate=_nominal_rate(breakdown, category) if breakdown.is_subject else Decimal("0.00"),
            reconciled=breakdown.vat_included_reconciled,
        )
        period = line.get("period") or {}
        lines.append(
            InvoiceLine(
                position=position,
                description=(line.get("description") or slug or _("Subscription"))[:255],
                item_kind=kind,
                item_slug=slug,
                quantity=max(int(line.get("quantity") or 1), 1),
                proration=_is_proration(line),
                period_start=_moment_or_none(period.get("start")),
                period_end=_moment_or_none(period.get("end")),
                tax_category_id=category,
                tax_treatment=breakdown.treatment,
                tax_rate=rate,
                net_cents=net,
                tax_cents=tax,
                total_cents=net + tax,
                stripe_line_id=line.get("id") or "",
            )
        )
    if not lines:
        # Stripe always bills a line; without one the whole amount is one line of the subscription.
        lines.append(
            InvoiceLine(
                position=1,
                description=_("Subscription"),
                tax_category_id=vat.SAAS_SUBSCRIPTION_CATEGORY,
                tax_treatment=breakdown.treatment,
                tax_rate=breakdown.rate,
                net_cents=to_cents(breakdown.base),
                tax_cents=to_cents(breakdown.tax),
                total_cents=total,
            )
        )
    net_cents = sum(line.net_cents for line in lines)
    tax_cents = sum(line.tax_cents for line in lines)
    _require_adds_up(stripe_invoice.get("id"), net_cents + tax_cents, total, hub.id)
    now = timezone.now()
    series, sequence, number, today = issue_number(Invoice.Kind.INVOICE)
    values = {
        "kind": Invoice.Kind.INVOICE,
        "hub": hub,
        "business_name": hub.name,
        "stripe_invoice_id": stripe_invoice["id"],
        **_stripe_fields(stripe_invoice),
        **_payer_snapshot(hub, verified=data.tax_id_verified, consultation=data.vat_consultation_number),
        "series": series,
        "sequence": sequence,
        "number": number,
        "issued_on": today,
        "payment_status": Invoice.PaymentStatus.PAID,
        "paid_at": _moment_or_none((stripe_invoice.get("status_transitions") or {}).get("paid_at")) or now,
        "net_cents": net_cents,
        "tax_cents": tax_cents,
        "total_cents": net_cents + tax_cents,
        "tax_treatment": breakdown.treatment,
        "tax_country": breakdown.tax_country,
        "tax_rate": _nominal_rate(breakdown, vat.SAAS_SUBSCRIPTION_CATEGORY) if breakdown.is_subject else Decimal("0.00"),
        "vat_included_reconciled": breakdown.vat_included_reconciled,
        "fiscal_status": Invoice.FiscalStatus.ISSUING,
        "fiscal_status_at": now,
        "next_post_at": now,
    }
    if existing is None:
        invoice = Invoice.objects.create(**values)
    else:
        invoice = existing
        for field, value in values.items():
            setattr(invoice, field, value)
        invoice.save()
        invoice.lines.all().delete()
    for line in lines:
        line.invoice = invoice
    InvoiceLine.objects.bulk_create(lines)
    _record_invoice_event(ctx, invoice, events.INVOICE_RECORDED,
                          {"id": str(invoice.id), "hub_id": str(hub.id), "payment_status": "paid"})
    transaction.on_commit(partial(_post_quietly, invoice.id), robust=True)
    _note_oss_threshold_quietly(invoice)
    return _record_out(invoice, "numbered")


# --- The team's notices of the OSS threshold (BILLING-F06, saas#2297, saas#2299) -------------------------

#: The share of the threshold whose passing tells the team to register in the OSS (it takes days).
OSS_WARNING_PERCENT = 80


def _counts_towards_oss(invoice: Invoice, issuer: str) -> bool:
    """The rule of ``queries.cross_border_b2c_cents``: a paid invoice to a payer of another member state
    without a VIES-verified VAT number."""
    return (
        invoice.kind == Invoice.Kind.INVOICE
        and invoice.payment_status == Invoice.PaymentStatus.PAID
        and invoice.payer_country in vat.EU_VAT_RATES
        and invoice.payer_country != issuer
        and not invoice.payer_tax_id_verified
    )


def _oss_noticed(year: int, kinds) -> bool:
    return OssNotice.objects.filter(year=year, kind__in=kinds).exists()


def _write_oss_notice(year: int, kind: str, invoice: Invoice, **values) -> OssNotice | None:
    """The year's notice of ``kind``, or ``None`` when a concurrent charge wrote it first (it tells)."""
    try:
        with transaction.atomic():
            return OssNotice.objects.create(year=year, kind=kind, invoice=invoice, **values)
    except IntegrityError:
        return None


def note_oss_threshold(invoice: Invoice) -> list[OssNotice]:
    """After charging ``invoice``: the year's crossing of the OSS threshold and its 80 % warning, each once per
    year, mailed to the team after the COMMIT. The crossing first, so a sale that jumps past the threshold is
    told once (``crossed``), never «80 %» after the fact. Nothing under a voluntary OSS registration (there is
    nothing to prepare) nor for a sale that does not count towards the threshold."""
    policy = queries.fiscal_policy()
    issuer = (policy.issuer_country or vat.DEFAULT_ISSUER_COUNTRY).strip().upper()
    if policy.oss_registered or not _counts_towards_oss(invoice, issuer):
        return []
    year = invoice.issued_on.year
    threshold = to_cents(policy.oss_threshold)
    written = []
    if not _oss_noticed(year, [OssNotice.Kind.CROSSED]):
        previous = queries.cross_border_b2c_cents(policy, year - 1)
        if previous > threshold:
            crossing = {
                "reason": OssNotice.Reason.PREVIOUS_YEAR,
                "accumulated_cents": previous,
                "effective_from": date(year, 1, 1),
            }
        else:
            # The invoice is saved as paid already: the sum includes it.
            current = queries.cross_border_b2c_cents(policy, year)
            crossing = (
                {"reason": OssNotice.Reason.CURRENT_YEAR, "accumulated_cents": current, "effective_from": invoice.issued_on}
                if current > threshold
                else None
            )
        if crossing is not None:
            written.append(
                _write_oss_notice(year, OssNotice.Kind.CROSSED, invoice, threshold_cents=threshold, **crossing)
            )
    if not _oss_noticed(year, [OssNotice.Kind.NEAR, OssNotice.Kind.CROSSED]):
        current = queries.cross_border_b2c_cents(policy, year)
        if current * 100 > threshold * OSS_WARNING_PERCENT:
            written.append(
                _write_oss_notice(
                    year, OssNotice.Kind.NEAR, invoice, accumulated_cents=current, threshold_cents=threshold
                )
            )
    written = [notice for notice in written if notice is not None]
    for notice in written:
        logger.warning(
            "[FISCAL] OSS %s %s: %s of %s cents (invoice %s)",
            notice.kind,
            notice.year,
            notice.accumulated_cents,
            notice.threshold_cents,
            invoice.number,
            extra={"event": f"billing.oss_{notice.kind}", "year": notice.year, "reason": notice.reason},
        )
        transaction.on_commit(partial(send_oss_notice, notice.id), robust=True)
    return written


def _note_oss_threshold_quietly(invoice: Invoice) -> None:
    """Charging never breaks over the notice: a failure is an ERROR, and the next charged sale tries again."""
    try:
        with transaction.atomic():
            note_oss_threshold(invoice)
    except Exception:  # noqa: BLE001 - the invoice stands; the next counted charge notes the threshold again
        logger.exception(
            "[FISCAL] The OSS threshold could not be noted for invoice %s",
            invoice.number,
            extra={"event": "billing.oss_notice_failed", "invoice_id": str(invoice.id)},
        )


def send_oss_notice(notice_id) -> bool:
    """Mail one notice to the team's mailbox (``SUPPORT_EMAIL``) and mark it sent; ``False`` when it could not
    leave (it stays owed: the daily ``retax_subscriptions`` sends it again)."""
    from billing import emails

    notice = OssNotice.objects.select_related("invoice").filter(pk=notice_id, mailed_at__isnull=True).first()
    if notice is None:
        return True
    try:
        emails.send_oss_notice(notice)
    except emails.MailNotSent:
        return False
    OssNotice.objects.filter(pk=notice.pk, mailed_at__isnull=True).update(mailed_at=timezone.now())
    return True


def send_pending_oss_notices() -> Counter:
    """Every notice whose mail has not left yet, sent again: ``notices_sent`` and ``notices_failed``."""
    counts = Counter({"notices_sent": 0, "notices_failed": 0})
    for notice_id in OssNotice.objects.filter(mailed_at__isnull=True).order_by("recorded_at").values_list("pk", flat=True):
        counts["notices_sent" if send_oss_notice(notice_id) else "notices_failed"] += 1
    return counts


class InvoiceDoesNotAddUp(Exception):
    """The lines of a Stripe document do not add up to what it charged or credited: nothing is invoiced (a 500
    for Stripe's retry and support's ERROR), never a different amount (review of L3-C)."""


class RectifiedInvoiceMissing(Exception):
    """A credit note, a refund or a negative invoice whose invoice ERPlora has not recorded (yet): Stripe does not
    order its events, so the webhook answers 500 and Stripe retries."""


def _require_adds_up(source, lines_total: int, stripe_total: int, hub_id) -> None:
    if lines_total != stripe_total:
        logger.error(
            "[INVOICE] The lines of Stripe's %s add up to %s, Stripe charged %s: nothing is invoiced",
            source, lines_total, stripe_total,
            extra={"event": "fiscal.invoice.lines_do_not_add_up", "hub_id": str(hub_id)},
        )
        raise InvoiceDoesNotAddUp(source)


def rectification_type(reason: str | None) -> str:
    """VeriFactu's type of a rectifying invoice for Stripe's reason: a refund, a duplicate, a price change or an
    order change modify the base (art. 80.1, 80.2 LIVA, or an error): R1; a fraudulent charge, R4 (other)."""
    return Invoice.RectificationType.R4 if reason == "fraudulent" else Invoice.RectificationType.R1


def _rectifying_lines(original: Invoice, items: list[dict]) -> list[InvoiceLine]:
    """The lines of a rectifying invoice, negative where they give money back, sealed with the qualification of
    the invoice they rectify (a rectifying invoice keeps it) and the rate of the line they correct. ``items``:
    ``{amount, tax, description, quantity, price, stripe_line_id, split}``; ``split`` = the amount has the VAT
    inside (a refund): it is taken out at that rate."""
    sources = list(original.lines.all())
    lines = []
    for position, item in enumerate(items, start=1):
        kind, slug, category = _item_of(item.get("price") or "")
        source = next((line for line in sources if line.stripe_line_id and line.stripe_line_id == item.get("source_line")), None)
        source = source or next((line for line in sources if slug and line.item_slug == slug), None)
        rate, net, tax = _sealed_amounts(
            item["amount"],
            item["tax"],
            treatment=original.tax_treatment,
            rate=source.tax_rate if source is not None else original.tax_rate,
            reconciled=item.get("split", False) or (original.vat_included_reconciled and not item["tax"]),
        )
        lines.append(
            InvoiceLine(
                position=position,
                description=(item.get("description") or (source.description if source else "") or _("Credit"))[:255],
                item_kind=source.item_kind if source else kind,
                item_slug=source.item_slug if source else slug,
                quantity=max(int(item.get("quantity") or 1), 1),
                proration=bool(item.get("proration")),
                period_start=item.get("period_start") or (source.period_start if source else None),
                period_end=item.get("period_end") or (source.period_end if source else None),
                tax_category_id=source.tax_category_id if source else category,
                tax_treatment=original.tax_treatment,
                tax_rate=rate,
                net_cents=net,
                tax_cents=tax,
                total_cents=net + tax,
                stripe_line_id=item.get("stripe_line_id") or "",
            )
        )
    return lines


def _rectify(ctx, original: Invoice, *, source_id: str, items: list[dict], expected_total: int, rtype: str,
             reason: str, stripe_number: str = "", billed_at: datetime | None = None) -> dict:
    """A rectifying invoice of ``original`` (``ERPR`` series, its qualification and recipient), once per Stripe
    ``source_id``; its lines must add up to what Stripe gave back, or nothing is invoiced. Issued after the
    COMMIT."""
    existing = Invoice.objects.filter(kind=Invoice.Kind.CREDIT_NOTE, stripe_source_id=source_id).first()
    if existing is not None:
        return _record_out(existing, "duplicate")
    lines = _rectifying_lines(original, items)
    net_cents = sum(line.net_cents for line in lines)
    tax_cents = sum(line.tax_cents for line in lines)
    _require_adds_up(source_id, net_cents + tax_cents, expected_total, original.hub_id)
    now = timezone.now()
    series, sequence, number, today = issue_number(Invoice.Kind.CREDIT_NOTE)
    copied = {
        field: getattr(original, field)
        for field in (
            "hub_id", "business_name", "billing_profile_id", "payer_account_id", "payer_name", "payer_tax_id",
            "payer_tax_id_type", "payer_tax_id_verified", "vat_consultation_number", "payer_address", "payer_city",
            "payer_postal_code", "payer_country", "payer_email", "language", "currency", "tax_treatment",
            "tax_country", "tax_rate", "stripe_invoice_id",
        )
    }
    rectifying = Invoice.objects.create(
        kind=Invoice.Kind.CREDIT_NOTE,
        rectifies=original,
        stripe_source_id=source_id,
        stripe_number=(stripe_number or "")[:64],
        billed_at=billed_at,
        rectification_type=rtype,
        rectification_reason=(reason or "")[:255],
        series=series,
        sequence=sequence,
        number=number,
        issued_on=today,
        payment_status=Invoice.PaymentStatus.PAID,
        paid_at=now,
        net_cents=net_cents,
        tax_cents=tax_cents,
        total_cents=net_cents + tax_cents,
        fiscal_status=Invoice.FiscalStatus.ISSUING,
        fiscal_status_at=now,
        next_post_at=now,
        **copied,
    )
    for line in lines:
        line.invoice = rectifying
    InvoiceLine.objects.bulk_create(lines)
    _record_invoice_event(ctx, rectifying, events.CREDIT_NOTE_RECORDED, {"id": str(rectifying.id),
                                                                         "rectifies": str(original.id)})
    transaction.on_commit(partial(_post_quietly, rectifying.id), robust=True)
    return _record_out(rectifying, "numbered")


def _stripe_items(stripe_lines: list[dict], *, sign: int) -> list[dict]:
    """Stripe's lines (of an invoice or a credit note) as the items of a rectifying invoice; ``sign`` -1 for a
    credit note, whose amounts Stripe gives positive."""
    items = []
    for line in stripe_lines:
        period = line.get("period") or {}
        items.append(
            {
                "amount": sign * int(line.get("amount") or 0),
                "tax": sign * _line_tax_cents(line),
                "description": line.get("description") or "",
                "quantity": line.get("quantity") or 1,
                "price": _price_of(line),
                "proration": _is_proration(line),
                "period_start": _moment_or_none(period.get("start")),
                "period_end": _moment_or_none(period.get("end")),
                "source_line": line.get("invoice_line_item") or "",
                "stripe_line_id": line.get("id") or "",
            }
        )
    return items


def _record_negative(ctx, hub: Hub, stripe_invoice: dict) -> dict:
    """A Stripe invoice of a negative total (a proration credit larger than what it bills; legacy or manual:
    downgrades wait for the end of the period) rectifies the invoice whose period its credited lines belong to
    (review of L3-C): R1, a modification of the price (art. 80.2 LIVA)."""
    lines = (stripe_invoice.get("lines") or {}).get("data") or []
    credited = [
        _moment_or_none((line.get("period") or {}).get("start"))
        for line in lines
        if int(line.get("amount") or 0) < 0
    ]
    moment = min((when for when in credited if when is not None), default=None)
    found = (
        InvoiceLine.objects.select_related("invoice")
        .filter(
            invoice__hub=hub,
            invoice__kind=Invoice.Kind.INVOICE,
            invoice__payment_status=Invoice.PaymentStatus.PAID,
            period_start__lte=moment,
            period_end__gt=moment,
        )
        .order_by("-invoice__issued_on", "-invoice__sequence")
        .first()
        if moment is not None
        else None
    )
    if found is None:
        logger.error(
            "[INVOICE] Stripe invoice %s of hub %s credits a period ERPlora has not invoiced",
            stripe_invoice.get("id"), hub.id, extra={"event": "fiscal.credit.unknown_invoice"},
        )
        raise RectifiedInvoiceMissing(stripe_invoice.get("id"))
    return _rectify(
        ctx,
        found.invoice,
        source_id=stripe_invoice["id"],
        items=_stripe_items(lines, sign=1),
        expected_total=int(stripe_invoice["total"]),
        rtype=Invoice.RectificationType.R1,
        reason=stripe_invoice.get("description") or "proration",
        stripe_number=stripe_invoice.get("number") or "",
        billed_at=_moment_or_none(stripe_invoice.get("created")),
    )


def invoice_voided(stripe_invoice: dict) -> str:
    """Stripe voided an unpaid invoice, or gave up on it (``marked_uncollectible``): it leaves «not collected»
    (it is no longer payable). An invoice ERPlora does not list is ignored."""
    listed = (
        Invoice.objects.filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice.get("id") or "")
        .values_list("hub_id", "payment_status")
        .first()
    )
    if listed is None or listed[1] != Invoice.PaymentStatus.OPEN or listed[0] is None:
        return "ignored"
    out = invoice_record(
        hub_services.system_ctx_for(listed[0]), InvoiceRecordIn(hub_id=listed[0], invoice=stripe_invoice, status="void")
    )
    return "processed" if out.outcome == "voided" else "ignored"


# --- Credit notes and refunds: rectifying invoices -------------------------------------------------------


def _issued_invoice(stripe_invoice_id: str) -> Invoice | None:
    return (
        Invoice.objects.filter(
            kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice_id, payment_status=Invoice.PaymentStatus.PAID
        )
        .only("id", "hub_id", "payer_account_id")
        .first()
    )


def _missing_original(what: str, stripe_invoice_id: str):
    logger.error(
        "[INVOICE] %s rectifies Stripe invoice %s, which ERPlora has not invoiced (yet): Stripe retries",
        what, stripe_invoice_id, extra={"event": "fiscal.credit.unknown_invoice"},
    )
    return RectifiedInvoiceMissing(stripe_invoice_id)


def credit_note_created(credit_note: dict) -> str:
    """A credit note of a paid invoice (``credit_note.created``) becomes a rectifying invoice of its own series.
    Ahead of its invoice (Stripe does not order events) it raises: Stripe retries (review of L3-C)."""
    rectified = credit_note.get("invoice") or ""
    if isinstance(rectified, dict):
        rectified = rectified.get("id") or ""
    original = _issued_invoice(rectified)
    if original is None:
        raise _missing_original(f"Credit note {credit_note.get('id')}", rectified)
    lines = stripe_service.credit_note_lines(credit_note)
    credit_note_record(
        _invoice_ctx(original),
        CreditNoteRecordIn(credit_note={**credit_note, "lines": {"object": "list", "data": lines, "has_more": False}}),
    )
    return "processed"


@operation(
    "billing.credit_note.record",
    kind="command",
    permission="billing.manage",
    input=CreditNoteRecordIn,
    output=InvoiceRecordOut,
)
def credit_note_record(ctx: OperationContext, data: CreditNoteRecordIn) -> dict:
    """A Stripe credit note as a rectifying invoice (the platform only; no route): negative amounts, the
    qualification and the payer of the invoice it rectifies, its type (``rectification_type``) and reason
    (the memo, or Stripe's reason); issued after the COMMIT. Idempotent by the credit note."""
    credit_note = data.credit_note
    rectified = credit_note.get("invoice") or ""
    if isinstance(rectified, dict):
        rectified = rectified.get("id") or ""
    original = (
        Invoice.objects.select_for_update()
        .filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=rectified, payment_status=Invoice.PaymentStatus.PAID)
        .first()
    )
    if original is None:
        raise _missing_original(f"Credit note {credit_note.get('id')}", rectified)
    lines = (credit_note.get("lines") or {}).get("data") or []
    items = _stripe_items(lines, sign=-1) or [
        {"amount": -(int(credit_note.get("total") or 0) - tax_cents_of(credit_note)), "tax": -tax_cents_of(credit_note)}
    ]
    return _rectify(
        ctx,
        original,
        source_id=credit_note["id"],
        items=items,
        expected_total=-int(credit_note.get("total") or 0),
        rtype=rectification_type(credit_note.get("reason")),
        reason=credit_note.get("memo") or credit_note.get("reason") or "credit_note",
        stripe_number=credit_note.get("number") or "",
        billed_at=_moment_or_none(credit_note.get("created")),
    )


def charge_refunded(charge: dict) -> str:
    """Money given back without a credit note (``charge.refunded``; a refund in the Dashboard): each refund is a
    rectifying invoice of the invoice the charge paid, its gross split at that invoice's rate (review of L3-C).
    A refund a credit note covers is that credit note's; one still pending waits for its next event; a charge
    that paid no invoice of Stripe is not ours."""
    intent = charge.get("payment_intent") or ""
    if isinstance(intent, dict):
        intent = intent.get("id") or ""
    stripe_invoice_id = stripe_service.invoice_paid_by(intent) if intent else None
    if not stripe_invoice_id:
        return "ignored"
    original = _issued_invoice(stripe_invoice_id)
    if original is None:
        raise _missing_original(f"Refund of charge {charge.get('id')}", stripe_invoice_id)
    covered = stripe_service.credit_note_refund_ids(stripe_invoice_id)
    for refund in stripe_service.charge_refunds(charge["id"]):
        if refund.get("status") != "succeeded" or refund["id"] in covered:
            continue
        refund_record(_invoice_ctx(original), RefundRecordIn(invoice_id=original.id, refund=refund))
    return "processed"


@operation(
    "billing.refund.record",
    kind="command",
    permission="billing.manage",
    input=RefundRecordIn,
    output=InvoiceRecordOut,
)
def refund_record(ctx: OperationContext, data: RefundRecordIn) -> dict:
    """A Stripe refund without a credit note as a rectifying invoice of ``invoice_id`` (the platform only; no
    route): one line with the gross refunded, the VAT taken out at the invoice's rate. Idempotent by the refund."""
    original = Invoice.objects.select_for_update().get(pk=data.invoice_id)
    refund = data.refund
    amount = int(refund.get("amount") or 0)
    return _rectify(
        ctx,
        original,
        source_id=refund["id"],
        items=[{"amount": -amount, "tax": 0, "description": _("Refund"), "split": True}],
        expected_total=-amount,
        rtype=rectification_type(refund.get("reason")),
        reason=refund.get("reason") or "refund",
        billed_at=_moment_or_none(refund.get("created")),
    )


def _record_invoice_event(ctx: OperationContext, invoice: Invoice, name: str, payload: dict) -> None:
    """Record an event of an invoice in the command's channel and tell, after the COMMIT, the other account that
    sees it too (its payer and its business's owner, review of L3-C): both their Billing lists re-run."""
    record_event(ctx, name, payload)
    owner = hub_queries.owner_id(invoice.hub_id) if invoice.hub_id else None
    viewers = {str(account) for account in (invoice.payer_account_id, owner) if account}
    for key in sorted(viewers - {ctx.scope.key}):
        transaction.on_commit(partial(notify, Scope("user", key), [name]), robust=True)


def _invoice_ctx(invoice: Invoice) -> OperationContext:
    """The platform acting on an invoice, in its payer's channel (its Billing lists re-run)."""
    if invoice.payer_account_id:
        return system_context(Scope("user", str(invoice.payer_account_id)))
    if invoice.hub_id:
        return hub_services.system_ctx_for(invoice.hub_id)
    return system_context(Scope("user", "system"))


# --- The platform hub issues them (PLAN-SAAS §4) -----------------------------------------------------

#: What one post of an invoice came to: answered (its status stored), the Hub away (retried), the Hub
#: refusing it (kept with its code, retried: the run fails), or nothing to post (not paid).
POSTED, UNREACHABLE, REFUSED, NOTHING_TO_POST = "posted", "unreachable", "refused", "nothing_to_post"
#: The statuses the platform hub answers (``Invoice.FiscalStatus`` without «not issued»).
PLATFORM_STATUSES = frozenset({"issuing", "issued", "accepted", "accepted_with_errors", "rejected"})
#: Issued by the platform hub: it has the QR and the PDF.
ISSUED_STATUSES = frozenset({"issued", "accepted", "accepted_with_errors"})
#: The wait before posting again an invoice the Hub did not take: one ``reconcile_platform_invoices`` run
#: (15 minutes) after the first failure, doubling, never more than 6 hours.
PLATFORM_FIRST_WAIT = timedelta(minutes=15)
PLATFORM_LONGEST_WAIT = timedelta(hours=6)
#: An invoice still «issuing» after this long is stuck: the reconcile run fails (the ``task_failed`` alarm).
PLATFORM_STUCK_AFTER = timedelta(hours=1)


def platform_backoff(attempts: int) -> timedelta:
    """How long an invoice waits after its ``attempts``-th failed post."""
    return min(PLATFORM_FIRST_WAIT * 2 ** max(attempts - 1, 0), PLATFORM_LONGEST_WAIT)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def platform_payload(invoice: Invoice) -> dict:
    """The body of ``POST /internal/platform/invoices``: the whole invoice, so the platform hub issues it in
    VeriFactu and prints its PDF without asking the SaaS anything. Keyed by ``id`` (idempotent)."""
    rectified = invoice.rectifies
    return {
        "id": str(invoice.id),
        "kind": invoice.kind,
        "series": invoice.series,
        "number": invoice.number,
        "issued_on": _iso(invoice.issued_on),
        "stripe_invoice_id": invoice.stripe_invoice_id,
        "stripe_source_id": invoice.stripe_source_id,
        "rectification": (
            {"type": invoice.rectification_type, "reason": invoice.rectification_reason}
            if invoice.kind == Invoice.Kind.CREDIT_NOTE
            else None
        ),
        "currency": invoice.currency,
        "language": invoice.language,
        "net_cents": invoice.net_cents,
        "tax_cents": invoice.tax_cents,
        "total_cents": invoice.total_cents,
        "tax_treatment": invoice.tax_treatment,
        "tax_country": invoice.tax_country,
        "tax_rate": str(invoice.tax_rate),
        "vat_included_reconciled": invoice.vat_included_reconciled,
        "vat_included_because_unverified": invoice.vat_included_because_unverified,
        "business": {"id": str(invoice.hub_id) if invoice.hub_id else None, "name": invoice.business_name},
        "recipient": {
            "name": invoice.payer_name,
            "tax_id": invoice.payer_tax_id,
            "tax_id_type": invoice.payer_tax_id_type,
            "tax_id_verified": invoice.payer_tax_id_verified,
            "vat_consultation_number": invoice.vat_consultation_number,
            "address": invoice.payer_address,
            "city": invoice.payer_city,
            "postal_code": invoice.payer_postal_code,
            "country": invoice.payer_country,
            "email": invoice.payer_email,
        },
        "lines": [
            {
                "position": line.position,
                "description": line.description,
                "item_kind": line.item_kind,
                "item_slug": line.item_slug,
                "quantity": line.quantity,
                "proration": line.proration,
                "period_start": _iso(line.period_start),
                "period_end": _iso(line.period_end),
                "tax_category": line.tax_category_id,
                "tax_treatment": line.tax_treatment or invoice.tax_treatment,
                "tax_rate": str(line.tax_rate),
                "net_cents": line.net_cents,
                "tax_cents": line.tax_cents,
                "total_cents": line.total_cents,
            }
            for line in invoice.lines.order_by("position")
        ],
        "rectifies": (
            {"id": str(rectified.id), "number": rectified.number, "issued_on": _iso(rectified.issued_on)}
            if rectified is not None
            else None
        ),
    }


def _answer_of(body) -> dict | None:
    """The platform hub's answer as ``FiscalAnswerIn``, or ``None`` for one the SaaS does not know."""
    body = body if isinstance(body, dict) else {}
    status = body.get("status")
    if status not in PLATFORM_STATUSES:
        return None
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return {
        "status": status,
        "qr": str(body.get("qr") or ""),
        "error_code": str(error.get("code") or "")[:64],
        "error": str(error.get("message") or ""),
    }


def post_platform_invoice(invoice_id) -> str:
    """Post a paid invoice to ERPlora's platform hub (``POST /internal/platform/invoices``) and store what
    it answers. Outside any transaction (a call to the Hub never holds the database). Idempotent on the
    Hub's side by the invoice's id: posting it again answers what it has."""
    invoice = Invoice.objects.select_related("rectifies").filter(pk=invoice_id).first()
    if invoice is None or invoice.payment_status != Invoice.PaymentStatus.PAID or not invoice.number:
        return NOTHING_TO_POST
    try:
        answer = hub_client.post_platform_invoice(platform_payload(invoice))
    except HubUnavailable as failed:
        _post_failed(invoice, str(failed))
        return UNREACHABLE
    except HubRefused as refused:
        logger.error(
            "[INVOICE] The platform hub refused invoice %s: %s", invoice.number, refused,
            extra={"event": "billing.platform_invoice_refused", "code": refused.code},
        )
        _post_failed(invoice, str(refused), code=refused.code, message=refused.message)
        return REFUSED
    known = _answer_of(answer.body)
    if known is None:
        logger.error("[INVOICE] The platform hub answered %r for invoice %s", answer.body, invoice.number)
        _post_failed(invoice, f"unknown answer: {answer.body!r}"[:255])
        return UNREACHABLE
    Invoice.objects.filter(pk=invoice.pk).update(
        post_attempts=F("post_attempts") + 1, next_post_at=None, last_post_error=""
    )
    invoice_apply_fiscal_status(_invoice_ctx(invoice), FiscalAnswerIn(id=invoice.id, **known))
    return POSTED


def _post_failed(invoice: Invoice, error: str, *, code: str = "", message: str = "") -> None:
    attempts = invoice.post_attempts + 1
    logger.warning("[INVOICE] Invoice %s owed to the platform hub (attempt %s): %s", invoice.number, attempts, error)
    fields = {
        "post_attempts": attempts,
        "last_post_error": error[:255],
        "next_post_at": timezone.now() + platform_backoff(attempts),
        "updated_at": timezone.now(),
    }
    if code:
        fields.update(fiscal_error_code=code[:64], fiscal_error=message)
    Invoice.objects.filter(pk=invoice.pk).update(**fields)


def refresh_platform_invoice(invoice_id) -> str:
    """Ask the platform hub how an issued invoice stands (``GET /internal/platform/invoices/{id}``): the AEAT
    accepts or rejects it after the Hub issued it. Returns its fiscal status now, or ``unreachable`` /
    ``refused``."""
    invoice = Invoice.objects.filter(pk=invoice_id).first()
    if invoice is None:
        return NOTHING_TO_POST
    try:
        answer = hub_client.get_platform_invoice(str(invoice.id))
    except HubUnavailable:
        return UNREACHABLE
    except HubRefused as refused:
        logger.error("[INVOICE] The platform hub does not know invoice %s: %s", invoice.number, refused)
        return REFUSED
    known = _answer_of(answer.body)
    if known is None:
        logger.warning("[INVOICE] The platform hub answered %r for invoice %s", answer.body, invoice.number)
        return invoice.fiscal_status
    return invoice_apply_fiscal_status(_invoice_ctx(invoice), FiscalAnswerIn(id=invoice.id, **known)).fiscal_status


@operation(
    "billing.invoice.apply_fiscal_status",
    kind="command",
    permission="billing.manage",
    input=FiscalAnswerIn,
    output=FiscalAnswerOut,
)
def invoice_apply_fiscal_status(ctx: OperationContext, data: FiscalAnswerIn) -> dict:
    """What the platform hub says of an invoice, stored as it says it (the platform only; no route). «Issuing»
    never moves an invoice back; a rejection is an ERROR for support (the Hub corrects it with a new record,
    and its next answer replaces this one). The first time it is issued, its payer gets an e-mail."""
    invoice = Invoice.objects.select_for_update().get(pk=data.id)
    status = invoice.fiscal_status if data.status == "issuing" else data.status
    fields = {"fiscal_status": status, "qr": data.qr or invoice.qr, "fiscal_error_code": data.error_code,
              "fiscal_error": data.error}
    changed = any(getattr(invoice, field) != value for field, value in fields.items())
    if not changed:
        return {"id": invoice.id, "fiscal_status": invoice.fiscal_status, "changed": False}
    first_issue = invoice.fiscal_status not in ISSUED_STATUSES and status in ISSUED_STATUSES
    now = timezone.now()
    Invoice.objects.filter(pk=invoice.pk).update(**fields, fiscal_status_at=now, updated_at=now)
    if status == Invoice.FiscalStatus.REJECTED:
        logger.error(
            "[INVOICE] The AEAT rejected invoice %s: %s %s", invoice.number, data.error_code, data.error,
            extra={"event": "billing.platform_invoice_rejected", "invoice": invoice.number},
        )
    _record_invoice_event(ctx, invoice, events.INVOICE_FISCAL_STATUS_CHANGED, {"id": str(invoice.id), "status": status})
    if first_issue and invoice.emailed_at is None:
        transaction.on_commit(partial(_email_quietly, invoice.id), robust=True)
    return {"id": invoice.id, "fiscal_status": status, "changed": True}


def _post_quietly(invoice_id) -> None:
    try:
        post_platform_invoice(invoice_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the invoice; it stays «issuing»
        logger.exception("[INVOICE] Posting invoice %s to the platform hub crashed", invoice_id)


#: What sending the payer's mail of an invoice came to.
MAILED, MAIL_SKIPPED, MAIL_FAILED = "mailed", "mail_skipped", "mail_failed"


def send_invoice_mail(invoice_id) -> str:
    """Send the payer the mail of an issued invoice (``billing.emails``) and mark it sent. Nothing to send
    (nobody to send it to) is done too; a mail that cannot leave stays owed for ``reconcile_platform_invoices``
    (review of L3-C)."""
    from billing import emails

    invoice = Invoice.objects.select_related("hub", "payer_account").get(pk=invoice_id)
    try:
        sent = emails.send_invoice_issued(invoice)
    except emails.MailNotSent:
        return MAIL_FAILED
    Invoice.objects.filter(pk=invoice_id).update(emailed_at=timezone.now())
    return MAILED if sent else MAIL_SKIPPED


def _email_quietly(invoice_id) -> None:
    try:
        send_invoice_mail(invoice_id)
    except Exception:  # noqa: BLE001 - a mail never undoes the invoice; the reconcile run sends it again
        logger.exception("[INVOICE] The e-mail of invoice %s could not be sent", invoice_id)


#: The counts of a ``reconcile_platform_invoices`` run; the failing ones make it exit with an error.
PLATFORM_COUNTS = (
    "posted", "accepted", "waiting", "mailed", "unreachable", "refused", "rejected", "stuck", "mail_failed", "errors",
)
PLATFORM_FAILING = ("unreachable", "refused", "rejected", "stuck", "mail_failed", "errors")


def reconcile_platform_invoices(now: datetime | None = None) -> Counter:
    """One pass of ``reconcile_platform_invoices`` (``saas-cron``): post again every «issuing» invoice whose
    wait passed, ask the platform hub about every issued (or rejected) one until the AEAT accepts it, and
    count the ones «issuing» for longer than ``PLATFORM_STUCK_AFTER``. One invoice never stops the others."""
    now = now or timezone.now()
    counts = Counter({key: 0 for key in PLATFORM_COUNTS})
    paid = Invoice.objects.filter(payment_status=Invoice.PaymentStatus.PAID).exclude(number="")
    due = (
        paid.filter(fiscal_status=Invoice.FiscalStatus.ISSUING)
        .filter(Q(next_post_at__isnull=True) | Q(next_post_at__lte=now))
        .order_by("series", "issued_on", "sequence")
        .values_list("id", flat=True)
    )
    for invoice_id in list(due):
        try:
            outcome = post_platform_invoice(invoice_id)
        except Exception:  # noqa: BLE001 - one invoice never stops the pass; it stays owed
            logger.exception("[INVOICE] Posting invoice %s crashed", invoice_id)
            counts["errors"] += 1
            continue
        if outcome != NOTHING_TO_POST:
            counts[outcome] += 1
    asked = paid.filter(fiscal_status__in=[Invoice.FiscalStatus.ISSUED, Invoice.FiscalStatus.REJECTED]).values_list(
        "id", flat=True
    )
    for invoice_id in list(asked):
        try:
            status = refresh_platform_invoice(invoice_id)
        except Exception:  # noqa: BLE001 - one invoice never stops the pass
            logger.exception("[INVOICE] Asking about invoice %s crashed", invoice_id)
            counts["errors"] += 1
            continue
        if status in (UNREACHABLE, REFUSED):
            counts[status] += 1
        elif status == Invoice.FiscalStatus.REJECTED:
            counts["rejected"] += 1
        elif status == Invoice.FiscalStatus.ISSUED:
            counts["waiting"] += 1
        else:
            counts["accepted"] += 1
    counts["stuck"] = paid.filter(
        fiscal_status=Invoice.FiscalStatus.ISSUING, fiscal_status_at__lte=now - PLATFORM_STUCK_AFTER
    ).count()
    unmailed = paid.filter(fiscal_status__in=ISSUED_STATUSES, emailed_at__isnull=True).values_list("id", flat=True)
    for invoice_id in list(unmailed):
        outcome = send_invoice_mail(invoice_id)
        if outcome == MAIL_FAILED:
            counts["mail_failed"] += 1
        elif outcome == MAILED:
            counts["mailed"] += 1
    return counts


def platform_run_failed(counts: Counter) -> bool:
    return any(counts[key] for key in PLATFORM_FAILING)


# --- «Pay» an invoice not collected -----------------------------------------------------------------


@operation("billing.invoice.pay", kind="command", permission="billing.pay", input=InvoicePayIn, output=InvoicePayOut)
def invoice_pay(ctx: OperationContext, data: InvoicePayIn) -> dict:
    """Stripe's page to pay an invoice not collected (the panel opens it only on the web; the apps sell
    nothing, round 17 §2.6). Only its payer pays it; with a card the bank declined, «Pay» waits until the
    card changes (409 ``billing.card_change_required``, mockups README §6.18)."""
    user = hub_queries.account_of(ctx)
    invoice = queries.invoice_of(user, data.id)
    if invoice.payment_status == Invoice.PaymentStatus.PAID:
        raise Conflict(_("This invoice is paid already."), code="billing.invoice_paid")
    if invoice.payment_status == Invoice.PaymentStatus.VOID or not invoice.hosted_invoice_url:
        raise Conflict(_("This invoice was cancelled: there is nothing to pay."), code="billing.invoice_void")
    if not queries.pays_for(user, invoice):
        raise Conflict(
            _("Only the account that pays this business can pay its invoices."), code="billing.payer_required"
        )
    if queries.card_change_required(invoice):
        raise Conflict(
            _("The bank declined the card. Change the card first, then pay the invoice."),
            code="billing.card_change_required",
        )
    return {"url": invoice.hosted_invoice_url}

