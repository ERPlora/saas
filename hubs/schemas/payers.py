"""Schemas of a business's payer: who ERPlora invoices for it."""

import re
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext as _
from ninja import Field, Schema
from pydantic import StringConstraints

from hubs.schemas.common import BillingCountry, Email


class BillingProfileGetIn(Schema):
    hub_id: UUID


#: A Spanish postal code: five digits, the first two its province, which decides the tax (the Canary
#: Islands, Ceuta and Melilla are outside VAT; «3500» is not Las Palmas).
SPANISH_POSTAL_CODE = re.compile(r"^\d{5}$")


def postal_code_problem(country: str, postal_code: str) -> str | None:
    """Why ``postal_code`` is not one of ``country`` (only Spain's has a shape the tax depends on), or
    ``None``. Empty is fine: the payer may wait for the first checkout, which asks for it."""
    if country == "ES" and postal_code and not SPANISH_POSTAL_CODE.match(postal_code):
        return _("A Spanish postal code has five digits, e.g. 28001.")
    return None


class BillingProfileIn(Schema):
    """Who ERPlora invoices for this business. With ``same_as_business``, its name and country are
    copied from the business: a copy, not a sync. The postal code must be one of the payer's country
    (``postal_code_problem``)."""

    hub_id: UUID
    billing_name: str = Field("", max_length=255)
    tax_id: str = Field("", max_length=50)
    billing_address: str = Field("", max_length=500)
    billing_city: str = Field("", max_length=100)
    billing_postal_code: Annotated[str, StringConstraints(strip_whitespace=True)] = Field("", max_length=20)
    billing_country: BillingCountry | Literal[""] = ""
    billing_email: Email | Literal[""] = ""
    same_as_business: bool = False


class BillingProfileOut(Schema):
    """The business's payer as its owner edits it. A payer is somebody's: one set up by another account
    (the owner before a transfer) keeps paying, but its data is not shown (``paid_by_another_account``)
    and saving gives the business a payer of the current owner."""

    hub_id: UUID
    paid_by_another_account: bool
    billing_name: str
    tax_id: str
    billing_address: str
    billing_city: str
    billing_postal_code: str
    billing_country: str
    billing_email: str
    same_as_business: bool
