"""Context builder of saas-next (``settings.LIVE["context_builder"]``): the scope is the user.

PLAN §14.1, «SaaS → usuario»: every operation runs for the signed-in account and its live
notifications go to that account's channel. The context comes from the session, never from the
payload. A signed-in account has the role ``account``, which the panel's apps grant their permissions
in ``role_permissions``; who may act on a business is decided inside each operation. A live stream ends
(``bye``) at its next re-run once its account or its session is gone (:meth:`UserContextBuilder.refresh`).
"""

import dataclasses
from typing import Any

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.http import HttpRequest
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext
from live.context import OperationContext, Scope
from live.errors import Unauthorized
from live.meta import all_live_app_configs, permissions_for_role

from accounts import queries as account_queries

#: Scope key of a request without a session (a live stream refuses it before using it).
ANONYMOUS_KEY = "anonymous"
#: The role of every signed-in account in the SaaS (an anonymous visitor has none).
ACCOUNT_ROLE = "account"


def _actor(request: HttpRequest) -> Any:
    user: Any = getattr(request, "user", None)
    return user if user is not None and user.is_authenticated else None


def _permissions(actor: Any) -> frozenset[str]:
    if actor is None:
        return frozenset()
    return permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)


class SessionEnded(Unauthorized):
    """The session a live stream was opened with ended: the stream ends (``bye``) and its reconnection, without that
    session, is anonymous. The Hub's code (hub#190), with which ``@erplora/ui`` takes the tab to the sign-in (ui#25)."""

    code = "base.session_ended"


def _session_ended(request: HttpRequest | None, user: Any) -> bool:
    """Whether the session ``request`` came with no longer signs ``user`` in: gone from the store (a sign-out,
    «Close the other sessions»), expired, or opened with an old password (Django keeps that one's row and refuses it
    at its next request; ``accounts.queries.live_sessions`` tells them apart the same way). One query, read only:
    unlike ``django.contrib.auth.get_user`` it neither flushes nor cycles the session. A request without one (the
    system's, a test's) has none to end."""
    session = getattr(request, "session", None)
    key = getattr(session, "session_key", None)
    if key is None:
        return False
    data = type(session)(session_key=key).load()
    stored_hash = data.get(HASH_SESSION_KEY) or ""
    hashes = [user.get_session_auth_hash(), *user.get_session_auth_fallback_hash()]
    return data.get(SESSION_KEY) != str(user.pk) or not any(constant_time_compare(stored_hash, h) for h in hashes)


class UserScopeResolver:
    def resolve(self, request: HttpRequest) -> Scope:
        actor = _actor(request)
        return Scope("user", str(actor.pk) if actor is not None else ANONYMOUS_KEY)


class UserContextBuilder:
    def __init__(self, resolver: UserScopeResolver | None = None) -> None:
        self.resolver = resolver or UserScopeResolver()

    def from_request(self, request: HttpRequest) -> OperationContext:
        actor = _actor(request)
        return OperationContext(
            scope=self.resolver.resolve(request),
            actor=actor,
            permissions=_permissions(actor),
            language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
            request=request,
        )

    def refresh(self, ctx: OperationContext) -> OperationContext:
        """Re-read the account and its session before a live re-run; an account deleted or deactivated, or a
        session that ended (a sign-out, «Close the other sessions», a new password: ``SessionEnded``), ends its
        stream. The run speaks the account's language as it is now (a change in Cuenta → Preferencias,
        ``base.language``)."""
        if ctx.actor is None:
            return ctx
        user = account_queries.active_user(ctx.actor.pk)
        if user is None:
            raise Unauthorized(gettext("The account is no longer active."))
        if _session_ended(ctx.request, user):
            raise SessionEnded(gettext("Your session ended: sign in again."))
        language = user.language if user.language in dict(settings.LANGUAGES) else ctx.language
        return dataclasses.replace(ctx, actor=user, language=language)
