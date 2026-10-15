"""The bodies of ``/internal/verifactu/submit|query|probe`` (contract 3 of the fiscal block, PLAN-SAAS §2.2).

``route=erplora`` presents with ERPlora's seal; ``route=own`` with the customer's own certificate, which
travels in ``certificate`` (its .p12 in base64 and its password) on every call and is never kept. Both
are ``SecretStr``: no ``repr``, ``str`` or log line of a body shows them.

``hub`` names the calling hub: in phase 1 the slug of its host (``ctx.scope.key``), later the registry's
UUID in lowercase. Both fit ``live.slugs.HUB_SLUG_RE``, the single source of the slug format, checked
with ``fullmatch`` (its ``$`` would admit a trailing newline). The gateway presents for a business it
knows only (``hub_unknown``), and through ``erplora`` only with that business's approved authorisation.
"""

from typing import Annotated, Literal

from live.slugs import HUB_SLUG_RE
from ninja import Schema
from pydantic import AfterValidator, SecretStr, StringConstraints


def _hub_ref(value: str) -> str:
    # The message never echoes the value.
    if not HUB_SLUG_RE.fullmatch(value):
        raise ValueError("not a hub slug nor a lowercase UUID")
    return value


# A hub's slug or its UUID in lowercase.
HubRef = Annotated[str, AfterValidator(_hub_ref)]


class CertificateIn(Schema):
    p12_base64: SecretStr
    password: SecretStr


class ProbeIn(Schema):
    hub: HubRef
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
