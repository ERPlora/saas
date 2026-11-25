"""Who calls from the Hub.

- ``assistant.caller.resolve``: the business (or the demo) a call of the Hub names, if its people can use the
  assistant now.
"""

from uuid import UUID

from django.db.models import Q
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied
from live.operations import INTERNAL, operation
from live.slugs import is_demo_slug, validate_hub_slug

from assistant.queries.gates import platform_only
from assistant.schemas import Caller, CallerIn
from hubs.models import Hub


#: The states of a business whose people use the assistant: working, or with a payment pending (its grace days).
WORKING = (Hub.Status.ACTIVE, Hub.Status.PAST_DUE)


def unknown_hub() -> NotFound:
    return NotFound("No business the SaaS knows goes by that hub.", code="hub_unknown")


def working(hub: Hub | None) -> Hub:
    """``hub`` if its people can use the assistant now: 404 ``hub_unknown`` (unknown or purged), 403 ``hub_inactive``
    (preparing, suspended or being deleted)."""
    if hub is None or hub.status == Hub.Status.DELETED:
        raise unknown_hub()
    if hub.status not in WORKING:
        raise PermissionDenied("The business does not work now: its people cannot use the assistant.", code="hub_inactive")
    return hub


@operation(
    "assistant.caller.resolve",
    kind="query",
    permission="assistant.manage",
    input=CallerIn,
    output=Caller,
    ai=INTERNAL,  # platform
)
def caller_resolve(ctx: OperationContext, data: CallerIn) -> dict:
    """The business (or the demo) a call of the Hub names in ``hub`` (the platform only): a business by its address
    or its id (the UUID's own spelling), a demo by its ``demo-…`` address. 404 ``hub_unknown`` (unknown or purged; and
    ERPlora's own, which has no plan and so no messages), 403 ``hub_inactive`` (preparing, suspended or being deleted:
    its people cannot be in it)."""
    platform_only(ctx)
    ref = data.hub.strip()
    if is_demo_slug(ref):
        try:
            slug = validate_hub_slug(ref.lower(), allow_demo=True)
        except ValueError:
            raise unknown_hub() from None
        return {"hub_id": None, "demo": slug, "slug": slug}
    try:
        key = UUID(ref)
    except ValueError:
        key = None
    named = Q(id=key) if key is not None and str(key) == ref else Q(slug=ref)
    hub = working(Hub.objects.filter(named, is_platform=False).exclude(status=Hub.Status.DELETED).first())
    return {"hub_id": hub.id, "demo": "", "slug": hub.slug}
