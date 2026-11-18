"""Schemas of the public taxonomy: the sectors and business types of the sign-up and the industry pages."""

from datetime import datetime

from ninja import Schema


class SectorListIn(Schema):
    pass


class SectorOut(Schema):
    """A sector in the caller's language."""

    code: str
    name: str
    description: str
    icon: str
    color: str
    #: When the row last changed (the public sitemap's ``lastmod``).
    updated_at: datetime


class SectorListOut(Schema):
    sectors: list[SectorOut]


class BusinessTypeListIn(Schema):
    #: Only the business types of the sector with this code.
    sector: str | None = None


class SectorRefOut(Schema):
    code: str
    name: str


class BusinessTypeOut(Schema):
    """A business type in the caller's language, with its sector and its vertical ("" for none)."""

    code: str
    name: str
    description: str
    icon: str
    color: str
    sector: SectorRefOut | None
    vertical: str
    #: When the row last changed (the public sitemap's ``lastmod``).
    updated_at: datetime


class BusinessTypeListOut(Schema):
    business_types: list[BusinessTypeOut]
