"""What the schemas of several entities share: the markets ERPlora serves, the roles, the checked text
fields, a page of a list and the reference to a business."""

import re
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils.translation import gettext as _
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints

from accounts.adapters import folded_email
from accounts.queries.hub_links import local_path
from billing.vat import SOLD_TO_COUNTRIES


T = TypeVar("T")

#: The markets ERPlora serves (the EU-27, as the old ``CountryCompliance`` catalog).
COUNTRIES = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()
)
#: The roles an invitation or a role change may hand out: never the owner (it only moves by a transfer).
InvitableRole = Literal["hub_admin", "hub_manager", "hub_employee"]
Role = Literal["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _country(value: str) -> str:
    code = value.strip().upper()
    if code not in COUNTRIES:
        raise ValueError(_("Choose one of the countries ERPlora serves."))
    return code


def _email(value: str) -> str:
    # The form an account keeps its address in: another case or look-alike full-width letters are the same
    # address, so an invitation never makes a second account that looks the same.
    email = folded_email(value)
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError(_("Enter a valid email address."))
    return email


def _local_path(value: str) -> str:
    """A path on the hub (``/…``), never another host: the rule of ``accounts.queries.hub_links.local_path``, which
    turns anything else into ``/``; an input refuses it instead (422)."""
    if local_path(value) != value:
        raise ValueError(_("Enter a path of the business, starting with /."))
    return value


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(_("Choose a valid time zone.")) from None
    return value


#: An ISO 3166-1 alpha-2 code of the markets served; its JSON schema lists them, so a client (and the assistant's
#: model) sends «ES», never «España».
Country = Annotated[
    str,
    AfterValidator(_country),
    Field(
        description="ISO 3166-1 alpha-2 code of a country ERPlora serves (e.g. ES).",
        json_schema_extra={"enum": sorted(COUNTRIES)},
    ),
]
#: The country of a payer: shaped as any market, and offered (to a client and the assistant's model) as the countries
#: ERPlora sells to; ``hubs.billing_profile.update`` refuses the rest once «use the business's data» is resolved.
BillingCountry = Annotated[
    str,
    AfterValidator(_country),
    Field(
        description="ISO 3166-1 alpha-2 code of the country the payer is billed in; ERPlora sells to Spain only (ES).",
        json_schema_extra={"enum": sorted(SOLD_TO_COUNTRIES)},
    ),
]
Email = Annotated[str, AfterValidator(_email)]
LocalPath = Annotated[str, Field(max_length=500), AfterValidator(_local_path)]
TimeZone = Annotated[str, Field(max_length=64), AfterValidator(_timezone)]


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int
    limit: int
    offset: int


class ByIdIn(Schema):
    id: UUID


class HubRefOut(Schema):
    id: UUID
    slug: str
    name: str
