"""What a business may name as its own domain (HUBS-F17; no ORM, no network).

The Hub takes a snapshot whole: a domain it would refuse (``base.schemas.custom_domain_of_photo``, 422) would block every
snapshot of that business, so nothing it refuses reaches a row. ``normalized`` is that check, and the form ACM and the Hub
are given: lowercase, because IAM's ``Deny`` on our own names is case sensitive, without a final dot and in ASCII
(``xn--…``). A zone apex needs the DNS to be told apart, so it is ``hubs.domain_checks``'s.
"""

from enum import StrEnum

import idna
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import DomainNameValidator

#: The zones of ERPlora: no customer's domain is there, and the Hub already answers them, so it would refuse the snapshot.
OUR_ZONES = ("erplora.com", "erplora.internal", "localhost")

#: ACM refuses a certificate whose first name is longer («cannot exceed 64 octets, including periods»).
MAX_LENGTH = 64

_is_a_domain_name = DomainNameValidator(accept_idna=False)


class Refusal(StrEnum):
    NOT_A_DOMAIN = "not_a_domain"
    OURS = "ours"


class DomainRefused(ValueError):
    """``typed`` cannot be a business's own domain; ``reason`` says why (a ``Refusal``)."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


def normalized(typed: str) -> str:
    """``typed`` in the form everybody is given, or ``DomainRefused``."""
    name = _ascii(typed.strip().removesuffix("."))
    try:
        _is_a_domain_name(name)
    except ValidationError:
        raise DomainRefused(Refusal.NOT_A_DOMAIN) from None
    # The validator takes a number as a last label; the Hub reads that as an address.
    if len(name) > MAX_LENGTH or name.endswith(".") or name.rpartition(".")[2].isdigit():
        raise DomainRefused(Refusal.NOT_A_DOMAIN)
    if any(name == zone or name.endswith(f".{zone}") for zone in (*OUR_ZONES, settings.PUBLIC_HOST)):
        raise DomainRefused(Refusal.OURS)
    return name


def _ascii(name: str) -> str:
    """``name`` in lowercase ASCII as a browser would ask for it (UTS #46, which also folds the case)."""
    try:
        return idna.encode(name, uts46=True).decode("ascii")
    except idna.IDNAError:
        raise DomainRefused(Refusal.NOT_A_DOMAIN) from None
