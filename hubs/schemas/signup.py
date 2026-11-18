"""Schemas of the sign-up of a business: the address proposed for its name and the business it creates."""

from ninja import Field, Schema

from hubs.schemas.common import Country, Name


class AddressProposeIn(Schema):
    name: Name


class AddressProposeOut(Schema):
    """A free address for a business called ``name`` (it may still be taken before the sign-up)."""

    slug: str
    host: str


class BusinessCreateIn(Schema):
    """The minimal sign-up: a name, a country, and a business type if the person knows."""

    name: Name
    country: Country
    business_type: str | None = Field(None, max_length=80)
    #: The address; proposed from the name when not given.
    slug: str | None = Field(None, max_length=63)


class BusinessCreateCheckIn(Schema):
    pass


class BusinessCreateCheckOut(Schema):
    """Nothing to show: ``hubs.business.create_check`` only says, by refusing, that the account cannot create one."""
