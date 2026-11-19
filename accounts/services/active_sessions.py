"""Account → Security → Active sessions, and the sessions a new password ends."""

import logging

from django.contrib.auth import get_user_model, logout
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import LiveMisuse, NotFound
from live.operations import AI, INTERNAL, operation
from live.outbox import record_event

from accounts import events, signals
from accounts.queries import account_lookup, account_sessions
from accounts.schemas import (
    SessionCloseAnyIn,
    SessionCloseIn,
    SessionCloseOthersIn,
    SessionsClosedOut,
    SessionsEndedIn,
    SessionsEndedOut,
)
from accounts.services.trusted_browsers import forget_trusted_browsers

logger = logging.getLogger("accounts.services")


def record_sign_in(sender, request, user, **kwargs) -> None:
    """allauth's ``user_logged_in``, in place of ``allauth.usersessions``' own receiver: the account's sessions that
    no longer sign it in go (``account_sessions.live_sessions``: gone, expired, or opened with an old password) and
    this one is recorded. allauth's ``purge_and_list`` asks about each session on its own, about three queries for
    every open one on every sign-in, so an account with many sessions waited tens of seconds for the mailed code.
    Here it is two queries and one delete, however many there are.

    Only the sessions recorded before the live ones are told apart may go: one recorded meanwhile by another sign-in
    of the account is live (its session row comes first) but not among them yet, and it stays."""
    from allauth.usersessions.models import UserSession

    recorded = list(UserSession.objects.filter(user=user).values_list("pk", flat=True))
    live = {pk for pk, _ in account_sessions.live_sessions(user)}
    UserSession.objects.filter(pk__in=[pk for pk in recorded if pk not in live]).delete()
    UserSession.objects.create_from_request(request)


def track_session(request) -> None:
    """Record the session of a signed-in request: its address, browser and last use (allauth.usersessions).
    A request whose address cannot be told (allauth refuses it) is not recorded, and the request goes on."""
    from allauth.usersessions.models import UserSession
    from django.core.exceptions import PermissionDenied

    try:
        UserSession.objects.create_from_request(request)
    except PermissionDenied:
        logger.warning("accounts.session_not_tracked user=%s: no client address", request.user.pk)


def end_sessions(sessions: list, *, user=None) -> None:
    """End ``sessions`` of the SaaS and ask the businesses of each account (and of ``user``, even with no
    session to end) to end theirs (``signals.sessions_ended``)."""
    accounts = [user.pk] if user is not None else []
    for session in sessions:
        session.end()
        if session.user_id not in accounts:
            accounts.append(session.user_id)
    for user_id in accounts:
        signals.sessions_ended.send(sender=get_user_model(), user_id=user_id)


def _end_and_sign_out(ctx: OperationContext, sessions: list, *, user=None) -> None:
    current = account_sessions.current_session_key(ctx.request)
    end_sessions(sessions, user=user)
    if any(session.session_key == current for session in sessions):
        logout(ctx.request)


@operation(
    "accounts.session.close",
    kind="command",
    permission="accounts.manage",
    input=SessionCloseIn,
    output=SessionsClosedOut,
    ai=AI(
        description="Ends one session of the account (this one signs it out).",
        asks={
            "en": ("sign out the iPad", "close the session on my old phone", "log me out of that Chrome on Windows"),
            "es": (
                "cierra la sesión del iPad",
                "desconecta el móvil viejo",
                "sácame de la sesión de Chrome en Windows",
            ),
        },
    ),
)
def session_close(ctx: OperationContext, data: SessionCloseIn) -> dict:
    """End one session of the account (this one too: the answer signs it out)."""
    from allauth.usersessions.models import UserSession

    user = account_lookup.account_of(ctx)
    session = UserSession.objects.filter(user=user, pk=data.id).first()
    if session is None:
        raise NotFound(gettext("That session does not exist or has already ended."))
    _end_and_sign_out(ctx, [session])
    record_event(ctx, events.SESSION_CLOSED)
    return {"closed": 1}


@operation(
    "accounts.session.close_others",
    kind="command",
    permission="accounts.manage",
    input=SessionCloseOthersIn,
    output=SessionsClosedOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Ends every session of the account except this one.",
        asks={
            "en": ("log me out everywhere else", "close all my other sessions", "kick out every other device"),
            "es": (
                "cierra todas las demás sesiones",
                "desconéctame de los otros dispositivos",
                "echa a todos menos a este navegador",
            ),
        },
    ),
)
def session_close_others(ctx: OperationContext, data: SessionCloseOthersIn) -> dict:
    """End every session of the account but this one; the businesses are asked even when none was left here
    (the apps' sessions in them may outlive their session in the SaaS)."""
    from allauth.usersessions.models import UserSession

    user = account_lookup.account_of(ctx)
    current = account_sessions.current_session_key(ctx.request)
    others = [session for session in UserSession.objects.filter(user=user) if session.session_key != current]
    closed = sum(1 for _, key in account_sessions.live_sessions(user) if key != current)
    _end_and_sign_out(ctx, others, user=user)
    record_event(ctx, events.SESSION_CLOSED)
    return {"closed": closed}


#: The admin's «Close sessions»: a system context only (no role grants it), on the owner's channel.
CLOSE_ANY_SESSIONS = "accounts.close_any_sessions"


@operation(
    "accounts.session.close_any",
    kind="command",
    permission=CLOSE_ANY_SESSIONS,
    input=SessionCloseAnyIn,
    output=SessionsClosedOut,
    ai=INTERNAL,  # staff
)
def session_close_any(ctx: OperationContext, data: SessionCloseAnyIn) -> dict:
    """End sessions of any account from the admin, as its owner would: the picked ones (``ids``) or, without them, every
    one and the trust of its browsers (an incident). Its businesses are asked to end theirs; the event goes to the
    owner's channel (the context's scope), so its live list refreshes. Called only by ``close_sessions``; no route."""
    from allauth.usersessions.models import UserSession

    if ctx.scope.key != str(data.user_id):
        raise LiveMisuse(f"accounts.session.close_any runs on the account's channel, not {ctx.scope.key!r}.")
    user = get_user_model().objects.filter(pk=data.user_id).first()
    if user is None:
        raise NotFound(gettext("That account does not exist."))
    sessions = UserSession.objects.filter(user=user)
    if data.ids is not None:
        sessions = sessions.filter(pk__in=data.ids)
    sessions = list(sessions)
    end_sessions(sessions, user=user)
    if data.ids is None:
        forget_trusted_browsers(user)
    record_event(ctx, events.SESSION_CLOSED)
    return {"closed": len(sessions)}


def close_sessions(*, by, users=(), sessions=()) -> int:
    """The admin's «Close sessions»: every session of the accounts ``users`` (ids) and the trust of
    their browsers, or the picked ``sessions`` (``UserSession`` rows), each through its owner's channel; how many
    ended."""
    from live.context import Scope, system_context

    picked: dict = {}
    for session in sessions:
        picked.setdefault(session.user_id, []).append(session.pk)
    count = 0
    for user_id, ids in [*((user_id, None) for user_id in users), *picked.items()]:
        ctx = system_context(Scope("user", str(user_id)))
        count += session_close_any(ctx, SessionCloseAnyIn(user_id=user_id, ids=ids)).closed
    logger.warning("accounts.sessions_closed_by_staff staff=%s count=%s", by.pk, count)
    return count


#: A session ended outside the Account page (allauth's sign-out, a new password, its ``auth/sessions``): a system
#: context only (no role grants it), on the account's channel.
ANNOUNCE_ENDED_SESSIONS = "accounts.announce_ended_sessions"


@operation(
    "accounts.session.announce_ended",
    kind="command",
    permission=ANNOUNCE_ENDED_SESSIONS,
    input=SessionsEndedIn,
    output=SessionsEndedOut,
    ai=INTERNAL,  # platform
)
def session_announce_ended(ctx: OperationContext, data: SessionsEndedIn) -> dict:
    """The account's event of a closed session (``accounts.session.closed``, as «Close the other sessions» records it)
    on the context's channel: each live stream of the account re-runs, and the ones whose session ended leave for the
    sign-in (``base.operations``). Called only by :func:`announce_ended_sessions`; no route."""
    record_event(ctx, events.SESSION_CLOSED)
    return {"announced": True}


def announce_ended_sessions(user_id) -> None:
    """Wake the live streams of the account ``user_id`` once a session of it ended outside the Account page. Called
    after the session is gone: the notice goes at the COMMIT, and a stream it woke before would still find its session
    and stay. By the system, so the outbox keeps no email of the account (``forget_in_outbox``)."""
    from live.context import Scope, system_context

    session_announce_ended(system_context(Scope("user", str(user_id))), SessionsEndedIn())


def password_changed_ends_sessions(sender, request=None, user=None, **kwargs) -> None:
    """allauth's ``password_changed``, ``password_set`` and ``password_reset``: a new password ends the account's
    other sessions here (Django), and in every business too (``signals.sessions_ended``); the account's
    tabs open with them leave for the sign-in by themselves (``announce_ended_sessions``)."""
    if user is None:
        return
    signals.sessions_ended.send(sender=get_user_model(), user_id=user.pk)
    announce_ended_sessions(user.pk)
