"""Read operations of base, and the maintenance switch every request reads (``maintenance_state``)."""

import logging
from typing import Any

from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Unauthorized
from live.operations import INTERNAL, operation

from accounts.queries import preferences_of
from assistant import queries as gateway_queries
from assistant.schemas import Caller
from base import navigation
from base.schemas import AssistantUsageIn, AssistantUsageOut, SessionMeIn, SessionMeOut

logger = logging.getLogger(__name__)


@operation(
    "base.session.me",
    kind="query",
    permission=None,
    input=SessionMeIn,
    output=SessionMeOut,
    ai=INTERNAL,  # screen
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


# --- The maintenance mode (ACCOUNTS-G82; base.maintenance) ----------------------------------------------------------

#: Seconds a task keeps the switch before reading it again; a change in the admin drops it from the shared cache at
#: once (``SiteSettings.save``), so this only bounds a cache that missed that.
MAINTENANCE_KEEP_SECONDS = 60


def _read_maintenance() -> dict[str, str] | None:
    """The switch as the database has it: ``None`` when off (or never set), its two messages when on."""
    from base.models import SiteSettings

    row = (
        SiteSettings.objects.filter(maintenance_mode=True)
        .values("maintenance_message_en", "maintenance_message_es")
        .first()
    )
    if row is None:
        return None
    return {"en": row["maintenance_message_en"], "es": row["maintenance_message_es"]}


def maintenance_state() -> dict[str, str] | None:
    """Whether erplora.com is in maintenance: ``None`` when it is not, its messages by language when it is.

    Read through the default cache (Valkey in AWS, shared by every task) and kept ``MAINTENANCE_KEEP_SECONDS``. When the
    switch cannot be read, whatever the reason (the database down, or a failure nobody foresaw), the site stays open,
    as the old SaaS did, and the log says why: a switch nobody can read must never close erplora.com, nor answer 500
    on every page.
    """
    from django.core.cache import cache

    from base.models import MAINTENANCE_CACHE_KEY

    try:
        kept = cache.get(MAINTENANCE_CACHE_KEY)
        if kept is not None:
            return kept["state"]
        state = _read_maintenance()
    except Exception as exc:  # noqa: BLE001 - logged and left open, never a 500 on every page
        logger.warning("base.maintenance_unreadable error=%s", type(exc).__name__)
        return None
    cache.set(MAINTENANCE_CACHE_KEY, {"state": state}, MAINTENANCE_KEEP_SECONDS)
    return state


# --- The panel's assistant (PLAN-SAAS §23) --------------------------------------------------------------------------


@operation(
    "base.assistant.usage",
    kind="query",
    permission="assistant.ask",
    input=AssistantUsageIn,
    output=AssistantUsageOut,
    ai=INTERNAL,  # panel
)
def assistant_usage(ctx: OperationContext, data: AssistantUsageIn) -> dict[str, Any]:
    """This month's messages of the panel's assistant of the session's account (``ASSISTANT_ACCOUNT_MESSAGES``): used,
    of how many, and when they come back (the first of next month, UTC). Its businesses' are their own, in their Hub."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to talk to the assistant."))
    usage = gateway_queries.usage_of(Caller(user_id=ctx.actor.pk), timezone.now())
    return {**usage, "resets_at": usage["resets_at"].isoformat().replace("+00:00", "Z") if usage["resets_at"] else None}
