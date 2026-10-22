"""The audit trail of the account models (django-auditlog; ACCOUNTS-F36, PLAN-SAAS §1.1).

Who changed an account, its access to a business, its API keys and its signed-in sessions, when and from where; the
staff read it in the admin («Entradas del registro»), and ``cleanup_old_logs`` keeps 90 days of it. Registered from
``AccountsConfig.ready``. The billing and fiscal models are registered by their own apps.

Every registration serializes only the logged fields (``serialize_auditlog_fields_only``, #957 of the old SaaS:
without it the serialized copy carried the excluded password hash). Never logged: the secrets (the password hash, a
key's hash, a session's key and data) and the fields that move on every request (``last_login``, a key's
``last_used_at``, a session's ``last_seen_at``: the sign-in is the session's own row).
"""

from allauth.usersessions.models import UserSession
from auditlog.middleware import AuditlogMiddleware
from auditlog.registry import auditlog
from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete
from django.utils.functional import LazyObject

from accounts import services
from accounts.models import ApiKey, HubMembership

_ONLY_LOGGED_FIELDS = {"serialize_data": True, "serialize_auditlog_fields_only": True}


def register() -> None:
    user = get_user_model()
    auditlog.register(user, exclude_fields=["password", "last_login"], **_ONLY_LOGGED_FIELDS)
    # After auditlog's own receiver: the account's last entry is written before its author is let go.
    post_delete.connect(services.forget_deleted_actor, sender=user, dispatch_uid="accounts.forget_deleted_actor")
    auditlog.register(HubMembership, **_ONLY_LOGGED_FIELDS)
    auditlog.register(ApiKey, exclude_fields=["key_hash", "last_used_at"], **_ONLY_LOGGED_FIELDS)
    auditlog.register(UserSession, exclude_fields=["session_key", "data", "last_seen_at"], **_ONLY_LOGGED_FIELDS)


class AuditActorMiddleware(AuditlogMiddleware):
    """auditlog's middleware, with the address and the actor of this project.

    The address is ``REMOTE_ADDR``, which ``public.client_ip`` already set to the visitor the ALB saw, never the first
    ``X-Forwarded-For`` entry the stock middleware takes (the visitor may type it). The actor is read when an entry
    is written, not when the request comes in: a request with an API key acts as the key's account, which
    ``accounts.api_auth`` sets after this middleware ran. After ``AuthenticationMiddleware``.
    """

    @staticmethod
    def _get_remote_addr(request):
        return request.META.get("REMOTE_ADDR")

    @staticmethod
    def _get_actor(request):
        return _ActingAccount(request)


class _ActingAccount(LazyObject):
    """The account ``request`` acts as, read again each time: never cached, so signing in, signing out or an API key
    within the request change who the next entry names (a cached one named an account already deleted)."""

    def __init__(self, request):
        self.__dict__["_request"] = request

    @property
    def _wrapped(self):
        return getattr(self.__dict__["_request"], "user", None)
