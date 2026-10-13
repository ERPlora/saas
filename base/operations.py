"""Context builder of saas-next (``settings.LIVE["context_builder"]``): the scope is the user.

PLAN §14.1, «SaaS → usuario»: every operation runs for the signed-in account and its live
notifications go to that account's channel. The context comes from the session, never from the
payload. No permission is granted yet: the panel's apps bring theirs.
"""

import dataclasses
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from live.context import OperationContext, Scope
from live.errors import Unauthorized

from accounts import queries as account_queries

#: Scope key of a request without a session (a live stream refuses it before using it).
ANONYMOUS_KEY = "anonymous"


def _actor(request: HttpRequest) -> Any:
    user: Any = getattr(request, "user", None)
    return user if user is not None and user.is_authenticated else None


class UserScopeResolver:
    def resolve(self, request: HttpRequest) -> Scope:
        actor = _actor(request)
        return Scope("user", str(actor.pk) if actor is not None else ANONYMOUS_KEY)


class UserContextBuilder:
    def __init__(self, resolver: UserScopeResolver | None = None) -> None:
        self.resolver = resolver or UserScopeResolver()

    def from_request(self, request: HttpRequest) -> OperationContext:
        return OperationContext(
            scope=self.resolver.resolve(request),
            actor=_actor(request),
            permissions=frozenset(),
            language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
            request=request,
        )

    def refresh(self, ctx: OperationContext) -> OperationContext:
        """Re-read the account before a live re-run; one deleted or deactivated ends its stream."""
        if ctx.actor is None:
            return ctx
        user = account_queries.active_user(ctx.actor.pk)
        if user is None:
            raise Unauthorized("The account is no longer active.")
        return dataclasses.replace(ctx, actor=user)
