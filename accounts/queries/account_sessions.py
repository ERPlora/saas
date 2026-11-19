"""Account → Security → Active sessions: the sessions that still sign the account in."""

from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from live.context import OperationContext
from live.operations import AI, operation

from accounts.queries.account_lookup import account_of
from accounts.schemas import SessionListIn, SessionListOut


def current_session_key(request) -> str | None:
    return getattr(getattr(request, "session", None), "session_key", None)


def live_sessions(user) -> list[tuple[int, str]]:
    """``(id, session key)`` of the account's sessions that still sign it in, the last used first: their session
    exists, has not expired and was opened with the account's current password (Django ends the others when it
    changes). One query brings the unexpired ones with their data, checked here: no session load per row (a
    thousand sessions were a thousand queries on every run of the list). Read only: unlike
    ``django.contrib.auth.get_user``, a dead session is not flushed here."""
    from importlib import import_module

    from allauth.usersessions.models import UserSession
    from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
    from django.db.models import OuterRef, Subquery

    store = import_module(settings.SESSION_ENGINE).SessionStore
    stored = store.get_model_class().objects.filter(session_key=OuterRef("session_key"), expire_date__gt=timezone.now())
    sessions = (
        UserSession.objects.filter(user=user)
        .annotate(session_data=Subquery(stored.values("session_data")[:1]))
        .filter(session_data__isnull=False)
        .order_by("-last_seen_at", "-pk")
        .values_list("pk", "session_key", "session_data")
    )
    hashes = [user.get_session_auth_hash(), *getattr(user, "get_session_auth_fallback_hash", lambda: ())()]
    decode = store().decode

    def signs_in(data: dict) -> bool:
        stored_hash = data.get(HASH_SESSION_KEY) or ""
        return data.get(SESSION_KEY) == str(user.pk) and any(constant_time_compare(stored_hash, h) for h in hashes)

    return [(pk, key) for pk, key, data in sessions if signs_in(decode(data))]


def session_row(session, current: str | None) -> dict[str, Any]:
    from accounts.devices import describe

    device = describe(session.user_agent)
    return {
        "id": session.pk,
        "device": device.platform,
        "browser": device.browser,
        "browser_version": device.browser_version,
        "app_version": device.app_version,
        "ip": session.ip,
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
        "is_current": session.session_key == current,
    }


@operation(
    "accounts.session.list",
    kind="query",
    permission="accounts.view",
    input=SessionListIn,
    output=SessionListOut,
    ai=AI(
        description="The account's active sessions (browsers and apps), this one first.",
        asks={
            "en": ("where am I logged in?", "which devices have my account open?", "show my active sessions"),
            "es": (
                "¿dónde tengo la sesión abierta?",
                "¿qué dispositivos están conectados a mi cuenta?",
                "¿qué sesiones tengo abiertas?",
            ),
        },
    ),
)
def session_list(ctx: OperationContext, data: SessionListIn) -> dict[str, Any]:
    """Account → Security → Active sessions, a page at a time: this session first, then the rest by last use."""
    from allauth.usersessions.models import UserSession

    user = account_of(ctx)
    current = current_session_key(ctx.request)
    sessions = sorted(live_sessions(user), key=lambda session: session[1] != current)
    page = [pk for pk, _ in sessions[data.offset : data.offset + data.limit]]
    found = UserSession.objects.in_bulk(page)
    return {
        "rows": [session_row(found[pk], current) for pk in page if pk in found],
        "total": len(sessions),
        "limit": data.limit,
        "offset": data.offset,
        "others": sum(1 for _, key in sessions if key != current),
    }
