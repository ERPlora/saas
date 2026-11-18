"""Schemas of the copies the Hub keeps of a business's data: ``hubs.data_copy.*``."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import StringConstraints


class DataCopyListIn(Schema):
    business_id: UUID


class DataCopyOut(Schema):
    """A copy of the business's whole data (``pg_dump -Fc``, restorable with ``pg_restore``): ``id`` is its key at the
    Hub, ``kind`` when it was made (``offboarding``: when the business was deleted; ``reset``: before its data was
    reset), ``created_at`` and its size in bytes. Its link is asked on each click (``hubs.data_copy.link``)."""

    id: str
    kind: Literal["offboarding", "reset"]
    created_at: datetime
    bytes: int


class DataCopyListOut(Schema):
    business_id: UUID
    #: False: the business has no database of its own, so it never gets a copy (the page promises nothing).
    available: bool
    #: Newest first; empty while the Hub has none yet (or is away).
    copies: list[DataCopyOut]


class DataCopyLinkIn(Schema):
    business_id: UUID
    copy_id: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class DataCopyLinkOut(Schema):
    """Where the browser downloads the copy: a link of the Hub's that lasts 15 minutes."""

    url: str
