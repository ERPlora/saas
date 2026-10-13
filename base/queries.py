"""Read operations of base."""

from typing import Any

from live.context import OperationContext
from live.operations import operation

from base.schemas import SessionMeIn, SessionMeOut


@operation(
    "base.session.me",
    kind="query",
    permission=None,
    input=SessionMeIn,
    output=SessionMeOut,
)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The account in front of the SPA, in the shape the shell reads.

    No permission: an anonymous visitor gets ``user: None``, which tells the shell to send it to
    the login. The SaaS has no apps menu yet: the panel's apps bring ``menu`` and ``apps``.
    """
    return {
        "user": _user(ctx.actor),
        "scope": {"kind": ctx.scope.kind, "key": ctx.scope.key},
        "permissions": sorted(ctx.permissions),
        "menu": [],
        "apps": [],
        "language": ctx.language,
    }


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    return {"id": str(actor.pk), "label": actor.get_full_name() or actor.get_username()}
