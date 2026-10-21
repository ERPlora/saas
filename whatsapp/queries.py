"""The reads of whatsapp: which business a door names and, for the Hub's snapshot, its WhatsApp channel.

Plain functions called inside the commands of ``services`` (in their transaction) and by ``hubs.queries`` for the
snapshot; none of them is a door of its own (the Hub reads the channel only in its snapshot).
"""

from uuid import UUID

from django.db.models import Q

from hubs.models import Hub
from hubs.services import LIVE_STATUSES


def known_hub(ref: str, *, live: bool = True) -> Hub | None:
    """The business ``ref`` names, by its slug or its UUID (lowercase, with hyphens, as the Hub sends it).

    ``live``: one that still works (preparing, active, past due or suspended); otherwise also one being deleted,
    whose data can still be forgotten. A purged one, never.
    """
    try:
        key = UUID(ref)
    except ValueError:
        key = None
    # 32 hex digits are a valid slug too: only the UUID's own spelling names it by id.
    named = Q(id=key) if key is not None and str(key) == ref else Q(slug=ref)
    hubs = Hub.objects.filter(named)
    hubs = hubs.filter(status__in=LIVE_STATUSES) if live else hubs.exclude(status=Hub.Status.DELETED)
    return hubs.first()
