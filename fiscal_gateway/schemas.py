"""The bodies of ``/internal/verifactu/submit|query|probe`` (contract 3 of the fiscal block, PLAN-SAAS §2.2).

``route=erplora`` presents with ERPlora's seal; ``route=own`` with the customer's own certificate, which
travels in ``certificate`` (its .p12 in base64 and its password) on every call and is never kept. Both
are ``SecretStr``: no ``repr``, ``str`` or log line of a body shows them.
"""

from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import SecretStr, StringConstraints


class CertificateIn(Schema):
    p12_base64: SecretStr
    password: SecretStr


class ProbeIn(Schema):
    hub: UUID
    nif: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)
    ]
    environment: Literal["testing", "production"]
    route: Literal["erplora", "own"]
    certificate: CertificateIn | None = None


class PresentIn(ProbeIn):
    # The Hub's exact bytes: never stripped nor touched.
    envelope: Annotated[str, StringConstraints(min_length=1)]


class AnswerOut(Schema):
    """The AEAT's answer as it came."""

    aeat_status: int
    aeat_body: str


class ProbeOut(Schema):
    ready: bool
    detail: str
