"""Input and output schemas of billing's operations (OpenAPI, the 422's ``fields``)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from ninja import Field, Schema
from pydantic import AfterValidator

#: The verdict a VAT number gets (``billing.services.clear_tax_id_for_stripe``):
#: ``verified`` (VIES confirmed it, with proof: reverse charge), ``invalid`` (not in VIES),
#: ``unavailable`` (VIES could not answer, or answered without proof), ``national`` (ERPlora's own
#: country: nothing to prove, never reverse charge), ``outside_vies`` (a UK number, HMRC's register).
VatStatus = Literal["verified", "invalid", "unavailable", "national", "outside_vies"]
#: What the preview knows of a VAT number without asking VIES: the statuses above from the log, ``absent``
#: (none typed: a consumer) or ``unchecked`` (nobody asked VIES about it yet: ``billing.vat_check.run``).
PreviewVatStatus = Literal[
    "verified",
    "invalid",
    "unavailable",
    "national",
    "outside_vies",
    "absent",
    "unchecked",
]

CountryCode = Annotated[str, Field(pattern=r"^[A-Za-z]{2}$"), AfterValidator(str.upper)]


class VatCheckIn(Schema):
    """A VAT number to check in VIES; without its country prefix, it is read in ``country``."""

    vat_number: str = Field(
        max_length=40, description="The VAT number, e.g. DE812871812."
    )
    country: CountryCode | Literal[""] = Field(
        "",
        description="ISO 3166-1 alpha-2 of the payer, for a number typed without its prefix.",
    )


class VatCheckOut(Schema):
    """The verdict that will price a sale to this number."""

    vat_number: str
    status: VatStatus
    #: True: in VIES. False: not in VIES. None: nobody could say (VIES down) or nothing to ask.
    valid: bool | None
    #: As VIES has them (empty when the member state does not share them).
    name: str
    address: str
    consultation_number: str
    checked_at: datetime | None
    is_current: bool
    #: The sale goes without VAT (intra-EU B2B): only a current VIES proof or a manual override.
    reverse_charge: bool
    manual_override: bool


class TaxPreviewIn(Schema):
    """Who pays and what: the payer's place, its VAT number (none = a consumer) and the net price."""

    country: CountryCode
    postal_code: str = Field(
        "", max_length=20, description="Decides the Canary Islands, Ceuta and Melilla."
    )
    vat_number: str = Field("", max_length=40)
    net: Decimal = Field(
        Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Net price in euros.",
    )
    category: Literal["plan", "module"] = "plan"


class TaxPreviewOut(Schema):
    """The tax a sale to that payer carries. ``resolvable`` false: no rule for that territory, the sale is
    refused (``treatment``, ``rate``, ``tax`` and ``total`` null)."""

    country: str
    resolvable: bool
    treatment: Literal["domestic", "oss", "reverse_charge", "not_subject"] | None
    tax_country: str
    rate: Decimal | None
    net: Decimal
    tax: Decimal | None
    total: Decimal | None
    #: A VAT number was given: the payer says it is a business.
    b2b: bool
    vat_status: PreviewVatStatus
    reverse_charge: bool
