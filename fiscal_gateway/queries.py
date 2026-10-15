"""What the gateway reads before it presents (PLAN-SAAS §4, round 2026-10-15): the business a call names and
the taxpayer ERPlora may present for on its behalf.

The only module of the gateway that reads the database; ``internal`` calls it. Plain functions, not
operations: the caller is the Hub, server to server, signed (no user, no session). Neither reads a document
of an authorisation nor anything a log could leak: an id, a tax ID.
"""

from uuid import UUID

from django.db.models import Q

from billing.nif import normalise_nif
from fiscal.models import RepresentationGrant
from hubs.models import Hub


def hub_id_for(ref: str) -> UUID | None:
    """The id of the business ``ref`` names, by its slug or its UUID (lowercase, with hyphens, as the Hub
    sends it); ``None`` if it is unknown or purged. A business deleted within its retention is still known:
    the records it already issued still have to reach the AEAT."""
    try:
        key = UUID(ref)
    except ValueError:
        key = None
    # 32 hex digits are a valid slug too: only the UUID's own spelling names it by id.
    named = Q(id=key) if key is not None and str(key) == ref else Q(slug=ref)
    return (
        Hub.objects.filter(named)
        .exclude(status=Hub.Status.DELETED)
        .values_list("id", flat=True)
        .first()
    )


def approved_taxpayer(hub_id: UUID) -> str | None:
    """The tax ID (normalised) of the taxpayer the business's authorisation in force covers, or ``None``
    without one: under review, returned or withdrawn is not in force."""
    tax_id = (
        RepresentationGrant.objects.filter(
            hub_id=hub_id, status=RepresentationGrant.Status.APPROVED
        )
        .values_list("taxpayer_tax_id", flat=True)
        .first()
    )
    return None if tax_id is None else normalise_nif(tax_id)
