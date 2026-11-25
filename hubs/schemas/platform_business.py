"""Schemas of ERPlora's own business as erplora.com takes it from the Hub."""

from uuid import UUID

from ninja import Field, Schema


class PlatformBusinessIn(Schema):
    #: The id its row has in the Hub: erplora.com never makes one.
    id: UUID
    #: The account that owns it; it exists already.
    owner_email: str = Field(max_length=255)


class PlatformBusinessOut(Schema):
    id: UUID
    slug: str
    #: ``False``: it was here already and nothing changed.
    created: bool
