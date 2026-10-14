"""The VIES client: is a customer's VAT number in the European Commission's register, and the proof.

Ported from ERPlora/saas ``apps/dashboard/fiscal/vies.py`` (origin/develop), split by where the code lives
now: this module is the HTTP client and the reading of the Commission's answer (no ORM); asking as the
identified requester, logging the answer as a ``VatCheck`` and deciding with it are ``billing.services``.

Invoicing an EU business without VAT needs a VAT number VALID IN VIES, and the burden of proof is the
issuer's (Directive 2006/112/EC): at 0 % against a nonexistent number the AEAT claims the VAT from
ERPlora, with interest. So the rule fails closed: ``verified`` is the only verdict that invoices without
VAT; ``pending``, ``unavailable``, ``invalid`` or none mean the same — the VAT is charged.

The proof is VIES' ``requestIdentifier`` (the consultation number), and VIES only returns it when the
query IDENTIFIES THE REQUESTER (``requesterMemberStateCode`` + ``requesterNumber``): there is no anonymous
query here. The REST endpoint (``settings.VIES_ENDPOINT``) is the one that accepts those fields; the
timeout (``settings.VIES_TIMEOUT_SECONDS``) is short because a person waits for the answer.

``ask`` never raises: whatever goes wrong (no network, a timeout, an HTTP error, an answer that is not
JSON or not VIES') is an ``unavailable`` answer, logged with its cause. Contract:
``architecture/contracts/vies-vat-contract.md``.
"""

import logging
import threading
from dataclasses import dataclass

import requests
from django.conf import settings

from billing.nif import normalise_nif
from billing.vat import EU_VAT_RATES

logger = logging.getLogger("billing.vies")

VERIFIED = "verified"
INVALID = "invalid"
UNAVAILABLE = "unavailable"
PENDING = "pending"

#: VIES errors that mean «I could not answer», not «it does not exist». VIES goes down often, and that is
#: not «not yet»: it is «not verified» (contract §7).
#: VIES refuses OUR requester identity (``CompanyConfig``): every check fails until it is fixed.
INVALID_REQUESTER_INFO = "INVALID_REQUESTER_INFO"

_UNAVAILABLE_ERRORS = frozenset(
    {
        "MS_UNAVAILABLE",
        "MS_MAX_CONCURRENT_REQ",
        "MS_MAX_CONCURRENT_REQ_TIME",
        "SERVICE_UNAVAILABLE",
        "GLOBAL_MAX_CONCURRENT_REQ",
        "GLOBAL_MAX_CONCURRENT_REQ_TIME",
        "TIMEOUT",
        "SERVER_BUSY",
        "VAT_BLOCKED",
        "IP_BLOCKED",
        INVALID_REQUESTER_INFO,
    }
)

#: A VIES query holds a database connection while it waits (it runs inside the operation's
#: transaction), so a process asks at most this many at once; one more is ``unavailable`` at once
#: rather than waiting for a slot (review of L2-A).
VIES_SLOTS = threading.BoundedSemaphore(3)

#: The VIES prefix of a member state whose VAT numbers do not start with its ISO code: Greece files ``EL``.
VIES_PREFIX_BY_COUNTRY = {"GR": "EL"}
#: Every prefix VIES answers about.
VIES_PREFIXES = frozenset(
    VIES_PREFIX_BY_COUNTRY.get(country, country) for country in EU_VAT_RATES
)
#: The prefixes HMRC issues (the UK and Northern Ireland, on the same registration): not VIES material.
UK_PREFIXES = frozenset({"GB", "XI"})


@dataclass(frozen=True)
class ViesAnswer:
    """What the Commission said about a number, as a verdict of ours."""

    status: str
    consultation_number: str = ""
    name: str = ""
    address: str = ""


def normalise(vat_number: str | None) -> str:
    """Without spaces, dashes nor dots and in upper case: how a number is indexed (``nif.normalise_nif``).
    A Greek number typed with its ISO code (``GR``) is the one VIES files under ``EL``."""
    value = normalise_nif(vat_number)
    if value.startswith("GR") and len(value) > 2:
        return "EL" + value[2:]
    return value


def split_vat_number(vat_number: str | None) -> tuple[str, str]:
    """The country prefix and the number, or ``("", "")`` when it has no VAT number's shape."""
    value = normalise(vat_number)
    if len(value) < 3 or not value[:2].isalpha():
        return "", ""
    return value[:2], value[2:]


def vies_prefix(country: str) -> str:
    """The prefix VIES knows a member state's numbers by (``GR`` → ``EL``)."""
    country = (country or "").strip().upper()
    return VIES_PREFIX_BY_COUNTRY.get(country, country)


def with_country_prefix(vat_number: str | None, country: str, *, issuer_country: str) -> str:
    """``vat_number`` with the prefix VIES knows it by when it was typed bare: read in the payer's
    ``country`` (``812871812`` paid from DE is ``DE812871812``; Greece is ``EL``, the UK ``GB``). A number
    with a prefix, a national one (the issuer's country, kept as typed) or one from a country with no VAT
    register of ours is left as it is."""
    value = normalise(vat_number)
    country = (country or "").strip().upper()
    if not value or split_vat_number(value)[0] or country == (issuer_country or "").strip().upper():
        return value
    if country == "GB":
        return "GB" + value
    if country in EU_VAT_RATES:
        return vies_prefix(country) + value
    return value


def is_uk_vat_number(vat_number: str | None) -> bool:
    """Is this HMRC's number rather than a member state's? Then VIES has nothing to say: it answers
    ``INVALID_INPUT`` to a ``GB`` prefix since Brexit (checked live on 2026-09-24, saas#2205)."""
    return split_vat_number(vat_number)[0] in UK_PREFIXES


def is_domestic_vat_number(
    vat_number: str | None, *, issuer_country: str, customer_country: str = ""
) -> bool:
    """Is the VAT number from the ISSUER's own country? Then there is nothing to prove.

    The single rule for «this number needs a VIES verdict». Always against the issuer's country, never
    the sale's jurisdiction, which under OSS is the customer's (saas#1633). A number without a prefix is
    placed by the customer's country; with neither, it is foreign (asking more than needed does no harm).
    """
    country = (
        split_vat_number(vat_number)[0] or (customer_country or "").strip().upper()
    )
    issuer = (issuer_country or "").strip().upper()
    return bool(country and issuer and country in {issuer, vies_prefix(issuer)})


def ask(vat_number: str, *, requester: tuple[str, str]) -> ViesAnswer:
    """Ask VIES about ``vat_number`` as the identified ``requester`` (member state, number). Never raises."""
    value = normalise(vat_number)
    country, number = split_vat_number(value)
    requester_country, requester_number = requester
    payload = {
        "countryCode": country,
        "vatNumber": number,
        "requesterMemberStateCode": requester_country,
        "requesterNumber": requester_number,
    }
    if not VIES_SLOTS.acquire(blocking=False):
        logger.warning("[VIES] Three queries already in flight in this process: %s is not asked, VAT is charged", value)
        return ViesAnswer(UNAVAILABLE)
    try:
        return _post(value, payload)
    finally:
        VIES_SLOTS.release()


def _post(value: str, payload: dict) -> ViesAnswer:
    try:
        response = requests.post(
            settings.VIES_ENDPOINT,
            json=payload,
            timeout=(settings.VIES_CONNECT_TIMEOUT_SECONDS, settings.VIES_TIMEOUT_SECONDS),
        )
    except OSError:
        # requests' ConnectionError and Timeout are OSErrors, as a refused or reset socket is.
        logger.exception(
            "[VIES] %s could not be asked about %s: VAT is charged",
            settings.VIES_ENDPOINT,
            value,
        )
        return ViesAnswer(UNAVAILABLE)
    if response.status_code >= 400:
        logger.error(
            "[VIES] %s answered HTTP %s about %s: VAT is charged",
            settings.VIES_ENDPOINT,
            response.status_code,
            value,
        )
        return ViesAnswer(UNAVAILABLE)
    try:
        body = response.json()
    except ValueError:
        logger.exception(
            "[VIES] The answer about %s is not JSON: VAT is charged", value
        )
        return ViesAnswer(UNAVAILABLE)
    return read_answer(body, value)


def read_answer(body, vat_number: str) -> ViesAnswer:
    """Turn the Commission's answer into a verdict of ours.

    The REST endpoint says ``valid``; the per-member-state one, ``isValid``: both are read, so a renamed
    field cannot end in invoices at 0 %. A «valid» WITHOUT a consultation number proves nothing (contract
    §3): it is what VIES returns when the request does not identify the requester, so it is
    ``unavailable``.
    """
    if not isinstance(body, dict):
        logger.error("[VIES] Unintelligible answer about %s: %r", vat_number, body)
        return ViesAnswer(UNAVAILABLE)
    valid = body.get("valid")
    if valid is None:
        valid = body.get("isValid")
    user_error = str(body.get("userError") or "").upper()
    consultation_number = str(body.get("requestIdentifier") or "").strip()

    if user_error == INVALID_REQUESTER_INFO:
        logger.error(
            "[VIES] VIES refuses the requester (%s) asking about %s: ERPlora's own VAT number in "
            "CompanyConfig is wrong, and every check fails until it is fixed. VAT is charged",
            user_error,
            vat_number,
        )
        return ViesAnswer(UNAVAILABLE, consultation_number=consultation_number)
    if user_error in _UNAVAILABLE_ERRORS:
        logger.warning(
            "[VIES] %s could not be checked (%s): VAT is charged",
            vat_number,
            user_error,
        )
        return ViesAnswer(UNAVAILABLE, consultation_number=consultation_number)

    if valid is True:
        if not consultation_number:
            logger.error(
                "[VIES] %s came back VALID but WITHOUT a consultation number: there is no proof to keep, so "
                "it does not invoice without VAT. Check that the request carries requesterMemberStateCode "
                "and requesterNumber (the issuer's identity)",
                vat_number,
            )
            return ViesAnswer(UNAVAILABLE)
        return ViesAnswer(
            VERIFIED,
            consultation_number=consultation_number,
            name=_shared(body.get("name"))[:255],
            address=_shared(body.get("address")),
        )

    if valid is False:
        logger.info(
            "[VIES] %s is NOT registered in VIES (%s): VAT is charged",
            vat_number,
            user_error or "INVALID",
        )
        return ViesAnswer(INVALID, consultation_number=consultation_number)

    logger.error("[VIES] Unintelligible answer about %s: %r", vat_number, body)
    return ViesAnswer(UNAVAILABLE)


def _shared(value) -> str:
    """A field of the answer, or ``""`` when the member state does not share it (VIES says ``---``)."""
    text = str(value or "").strip()
    return "" if text == "---" else text
