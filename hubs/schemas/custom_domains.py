"""Schemas of the domain of its own a business's public website may go on."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema


class CustomDomainRequestIn(Schema):
    """A business and the domain its owner wants for its public website, as it was typed (``hubs.domain_names``)."""

    id: UUID
    domain: str = Field(max_length=300)


class DnsRecordOut(Schema):
    type: str = "CNAME"
    name: str
    value: str


class CustomDomainOut(Schema):
    """A business's own domain: the two records to create, and what is missing (HUBS-F17)."""

    id: UUID
    domain: str
    state: str
    state_label: str
    #: Where it is stuck (``CustomDomain.Reason``), empty when nothing is missing, and that in the customer's words.
    reason: str
    reason_label: str
    #: Validates the certificate and renews it, so it stays for good; empty for the few seconds until ACM has it.
    validation: DnsRecordOut | None
    #: Takes the visits to ERPlora, and proves the domain is this business's: once the certificate is on, not before.
    traffic: DnsRecordOut
    failures: int
    checked_at: datetime | None
    activated_at: datetime | None


class CustomDomainStatusOut(Schema):
    #: Whether this deployment connects domains at all (``CUSTOM_DOMAINS_ENABLED``).
    available: bool
    #: Whether the plan the business has now includes one.
    in_plan: bool
    domain: CustomDomainOut | None


class CustomDomainRecordIn(Schema):
    """What the hourly check learned of a domain in ``expected_state``: if it left that state meanwhile, nothing is
    written. Only what is given changes."""

    id: UUID
    expected_state: str
    state: str | None = None
    reason: str | None = None
    certificate_arn: str | None = None
    #: The next certificate is another one: a token gives back the same one for an hour, and that one may be deleted.
    new_token: bool = False
    attached: bool | None = None
    proven: bool | None = None
    validation_name: str | None = None
    validation_value: str | None = None
    failures: int | None = None
    #: The Hub has to be told again (it answered that it does not know the domain).
    owe_snapshot: bool = False
    #: The row is done: it goes, and the name is free.
    forget: bool = False


class CustomDomainRecordOut(Schema):
    recorded: bool
