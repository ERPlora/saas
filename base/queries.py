"""Read operations of base."""

from typing import Any

from django.utils import translation
from live.context import OperationContext
from live.operations import operation

from accounts.queries import preferences_of
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
    17), translated; ``apps`` stays empty: the SaaS has no modules (PLAN §20.3.5). With it, what the
    shell paints with before any page asks: its theme mode (Cuenta → Preferencias, ``system`` until it
    chooses) and its own language (``User.language``, which wins over the cookie: ``base.language``).
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
            **_account(ctx.actor),
        }


def _account(actor: Any) -> dict[str, Any]:
    if actor is None:
        return {"preferences": None, "account_language": None}
    return {
        "preferences": {"theme_mode": preferences_of(actor)["theme_mode"]},
        "account_language": actor.language,
    }


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    return {
        "id": str(actor.pk),
        "label": actor.get_full_name() or actor.get_username(),
        "email": actor.email,
    }
