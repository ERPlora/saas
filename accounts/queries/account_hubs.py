"""The hubs an account enters, with its role on each, and the list of them the launcher shows."""

from typing import Any
from urllib.parse import urlsplit

from django.utils.translation import gettext
from live import operations
from live.context import OperationContext
from live.errors import Unauthorized
from live.operations import INTERNAL, operation

from accounts.queries.hub_links import hub_origin, hub_start_url
from accounts.schemas import HubListIn, HubListOut


#: Who enters which business, ``hubs``' to say (called by its name: accounts never imports hubs).
MEMBER_LIST_MINE = "hubs.member.list_mine"


def as_account(user) -> OperationContext:
    """The context ``user`` gets from a request, outside one: to read what it sees through other apps' operations."""
    from live.context import Scope
    from live.meta import all_live_app_configs, permissions_for_role

    from base.operations import ACCOUNT_ROLE

    return OperationContext(
        scope=Scope("user", str(user.pk)),
        actor=user,
        permissions=permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE),
        language=user.language,
    )


def hub_roles_of(user) -> dict[str, str]:
    """The ``hub_*`` role of ``user`` on each hub it enters, by slug, alphabetically: what the jump reads."""
    mine = operations.get(MEMBER_LIST_MINE)
    return {row.slug: row.role for row in mine(as_account(user), mine.input()).rows}


def hub_slugs_of(user) -> list[str]:
    """The slugs of the hubs ``user`` enters, alphabetically."""
    return list(hub_roles_of(user))


@operation(
    "accounts.hub.list",
    kind="query",
    permission=None,
    input=HubListIn,
    output=HubListOut,
    ai=INTERNAL,  # screen
)
def hub_list(ctx: OperationContext, data: HubListIn) -> dict[str, Any]:
    """The hubs of the signed-in account, alphabetically, each with its host and the jump to it.

    No permission: every account may read its own hubs. But only an account: a caller without one
    (anonymous) is refused, whatever route or stream asks.
    """
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to see your businesses."))
    return {
        "hubs": [
            {"slug": slug, "host": urlsplit(hub_origin(slug)).netloc, "url": hub_start_url(slug)}
            for slug in hub_slugs_of(ctx.actor)
        ]
    }
