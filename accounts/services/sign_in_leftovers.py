"""What a sign-in leaves behind (``manage.py purge_expired_sessions``, daily)."""

from datetime import timedelta

from django.db import transaction
from django.db.models import QuerySet

from accounts.models import AuthExchangeCode, EmailChangeRequest


def expired_sign_in_leftovers(now) -> dict[str, QuerySet]:
    """What has outlived its use at ``now``, by kind: the sessions past their expiry, the «Active sessions» rows whose
    session is gone (with the address and the browser they keep), the jump codes past their 60 s (used or not) and the
    changes of email past their code's 15 minutes."""
    from allauth.usersessions.models import UserSession
    from django.contrib.sessions.models import Session

    from accounts.queries import EMAIL_CODE_LIFETIME

    return {
        "sessions": Session.objects.filter(expire_date__lt=now),
        "session_rows": UserSession.objects.exclude(
            session_key__in=Session.objects.filter(expire_date__gte=now).values("session_key")
        ),
        "jump_codes": AuthExchangeCode.objects.filter(expires_at__lt=now),
        "email_changes": EmailChangeRequest.objects.filter(created_at__lt=now - timedelta(seconds=EMAIL_CODE_LIFETIME)),
    }


def count_expired_sign_in_leftovers(now) -> dict[str, int]:
    return {kind: rows.count() for kind, rows in expired_sign_in_leftovers(now).items()}


def purge_expired_sign_in_leftovers(now) -> dict[str, int]:
    """Delete them, the rows of «Active sessions» first (they name the sessions), each kind in its own transaction;
    how many went of each, as the database counts them. Outside the audit log: it says who changed an
    account, and a row that ended by itself is no change; one entry per row would bury the real ones."""
    from auditlog.context import disable_auditlog

    leftovers = expired_sign_in_leftovers(now)
    gone = {}
    with disable_auditlog():
        for kind in ("session_rows", "sessions", "jump_codes", "email_changes"):
            with transaction.atomic():
                gone[kind] = leftovers[kind].model.objects.filter(pk__in=leftovers[kind].values("pk")).delete()[0]
    return {kind: gone[kind] for kind in leftovers}
