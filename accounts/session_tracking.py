"""The account's sessions as ``allauth.usersessions`` keeps them (Account → Security; PLAN-SAAS §6).

allauth records a session when it signs in. ``SessionActivityMiddleware`` records it again (its address,
browser and last use) at most once every ``TOUCH_EVERY`` seconds of use: a session opened some other way
(the admin, one older than ``allauth.usersessions``) shows too, and «last used» moves without a write per
request (allauth's own ``USERSESSIONS_TRACK_ACTIVITY`` writes on every one). The mark lives in the cache, and is
read back before writing: with the cache down (``base.cache.FailSoftRedisCache`` then answers every ``add`` as
done and every ``get`` as empty) a session is simply not touched. The rate limits over that cache let requests
through meanwhile (``RATELIMIT_FAIL_OPEN``); the ones that must hold count in the database (the email codes).

Only the session's own account is recorded: a request acting with an API key (``request.auth``), or as anybody
else than the account the session signed in, never moves a session to another account.

``UserSessionsAdapter`` (``USERSESSIONS_ADAPTER``): however a session is ended, by the Account page's operations or by
allauth.headless ``auth/sessions``, the account's businesses are asked to end theirs (``services.end_sessions``).
"""

from allauth.usersessions.adapter import DefaultUserSessionsAdapter
from django.contrib.auth import SESSION_KEY
from django.core.cache import cache

from accounts import services
from accounts.models import ApiKey

#: Seconds between two records of the same session's use.
TOUCH_EVERY = 300


def _seen_key(session_key: str) -> str:
    return f"accounts:session-seen:{session_key}"


class SessionActivityMiddleware:
    """After ``AuthenticationMiddleware`` (it reads ``request.user``). It looks once the view answered, and only at
    a session the request already used: loading one nobody asked for would make Django drop a cookie it cannot
    read, and the public web never signs anybody out (saas#975)."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = getattr(request, "session", None)
        session_key = getattr(session, "session_key", None)
        if (
            session_key
            and session.accessed
            and not isinstance(getattr(request, "auth", None), ApiKey)
            and request.user.is_authenticated
            and session.get(SESSION_KEY) == str(request.user.pk)
            and _mark(session_key)
        ):
            services.track_session(request)
        return response


def _mark(session_key: str) -> bool:
    """Whether the session is due a record now: its mark was not in the cache, and the cache kept the new one."""
    key = _seen_key(session_key)
    return cache.add(key, 1, timeout=TOUCH_EVERY) and cache.get(key) == 1


class UserSessionsAdapter(DefaultUserSessionsAdapter):
    def end_sessions(self, sessions) -> None:
        """allauth's ``auth/sessions`` (and its Google sign-in that ends the others): the sessions end, the businesses
        are asked to end theirs and the accounts' live streams wake (``services.announce_ended_sessions``), as the
        Account page's «Close» records its event. Ending this browser's own session also signs it out, which wakes
        them once more (``AccountAdapter.logout``)."""
        sessions = list(sessions)
        services.end_sessions(sessions)
        for user_id in dict.fromkeys(session.user_id for session in sessions):
            services.announce_ended_sessions(user_id)
