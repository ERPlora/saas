"""What the schemas of several billing entities share: the billing of a plan, the label of a module, the reference
to a business and the business a row names."""

from typing import Annotated, Literal
from uuid import UUID

from ninja import Field, Schema

Interval = Literal["month", "year"]
#: The label of an app of the Hub (``apps.Module.slug``).
ModuleSlug = Annotated[str, Field(max_length=63, pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")]


class HubIn(Schema):
    hub_id: UUID


class InvoiceBusinessOut(Schema):
    #: ``None`` once the business is gone; its name stays as it was on the invoice.
    id: UUID | None
    name: str
