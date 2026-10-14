"""Read operations of base."""

from typing import Any

from django.utils import translation
from live.context import OperationContext
from live.operations import operation

from base import navigation
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

    No permission: an anonymous visitor gets ``user: None`` and no menu, which tells the shell to
    send it to the login. A signed-in account gets the panel's menu (``base/navigation.py``, round
    17), translated; ``apps`` stays empty: the SaaS has no modules (PLAN §20.3.5).
    """
    # The labels are lazy translations and a live re-run happens outside the request that
    # activated the language, so it is set here.
    with translation.override(ctx.language):
        return {
            "user": _user(ctx.actor),
            "scope": {"kind": ctx.scope.kind, "key": ctx.scope.key},
            "permissions": sorted(ctx.permissions),
            "menu": navigation.menu() if ctx.actor is not None else [],
            "apps": [],
            "language": ctx.language,
        }


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    return {
        "id": str(actor.pk),
        "label": actor.get_full_name() or actor.get_username(),
        "email": actor.email,
    }
