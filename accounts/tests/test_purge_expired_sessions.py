"""ACCOUNTS-G71 · ``manage.py purge_expired_sessions``: the daily sweep of what a sign-in leaves behind.

The old SaaS ran ``clearsessions_task`` (Django's expired sessions) and ``flush_expired_tokens_task`` (its JWT
blacklist) every day (``apps/core/tasks.py``, origin/develop c5ca8cae8). Here there is no JWT (PLAN-SAAS §1.1 point 2);
what a sign-in leaves is the session, the row «Active sessions» shows for it (allauth.usersessions, with the address and
the browser), the one-time code of each jump to a business (60 s) and the code of a change of email (15 min).
PLAN-SAAS §1.1, «Limpiezas y podas diarias»: ``clearsessions`` and the expired jump codes. Once a day in ``saas-cron``.
"""

from datetime import timedelta
from io import StringIO

import pytest
from allauth.usersessions.models import UserSession
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import connections
from django.utils import timezone

from accounts import services
from accounts.models import AuthExchangeCode, EmailChangeRequest

pytestmark = pytest.mark.django_db


def _run(*args) -> str:
    out = StringIO()
    call_command("purge_expired_sessions", *args, stdout=out)
    return out.getvalue()


def _session(user, *, expired: bool) -> str:
    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store.create()
    if expired:
        Session.objects.filter(session_key=store.session_key).update(expire_date=timezone.now() - timedelta(minutes=1))
    return store.session_key


def _user_session(user, session_key: str) -> UserSession:
    return UserSession.objects.create(user=user, session_key=session_key, ip="203.0.113.7", user_agent="Firefox")


def _code(user, *, seconds_left: int, used: bool = False) -> AuthExchangeCode:
    now = timezone.now()
    return AuthExchangeCode.objects.create(
        code_hash=AuthExchangeCode.hash_code(f"code-{seconds_left}-{used}"),
        user=user,
        hub_slug="bar",
        created_at=now - timedelta(seconds=60 - seconds_left),
        expires_at=now + timedelta(seconds=seconds_left),
        used_at=now if used else None,
    )


def _email_change(user, *, minutes_ago: int) -> EmailChangeRequest:
    return EmailChangeRequest.objects.create(
        user=user,
        session_key="k" * 32,
        email="ana.new@example.com",
        code_hash="0" * 64,
        created_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


class TestTheSessions:
    def test_an_expired_session_goes_and_a_live_one_stays(self, ana):
        expired = _session(ana, expired=True)
        live = _session(ana, expired=False)

        _run()

        assert not Session.objects.filter(session_key=expired).exists()
        assert Session.objects.filter(session_key=live).exists()

    def test_the_active_session_row_of_a_gone_session_goes_with_its_address(self, ana):
        gone = _user_session(ana, _session(ana, expired=True))
        never_there = _user_session(ana, "x" * 32)
        live = _user_session(ana, _session(ana, expired=False))

        _run()

        assert list(UserSession.objects.values_list("pk", flat=True)) == [live.pk]
        assert not UserSession.objects.filter(pk__in=[gone.pk, never_there.pk]).exists()


class TestTheOneTimeCodes:
    def test_an_expired_jump_code_goes_used_or_not_and_a_live_one_stays(self, ana):
        expired = _code(ana, seconds_left=-1)
        spent = _code(ana, seconds_left=-30, used=True)
        live = _code(ana, seconds_left=30)

        _run()

        assert list(AuthExchangeCode.objects.values_list("pk", flat=True)) == [live.pk]
        assert not AuthExchangeCode.objects.filter(pk__in=[expired.pk, spent.pk]).exists()

    def test_a_change_of_email_past_its_15_minutes_goes(self, ana, django_user_model):
        old = _email_change(ana, minutes_ago=16)
        bea = django_user_model.objects.create_user(email="bea@example.com", password="x")
        fresh = _email_change(bea, minutes_ago=5)

        _run()

        assert list(EmailChangeRequest.objects.values_list("pk", flat=True)) == [fresh.pk]
        assert not EmailChangeRequest.objects.filter(pk=old.pk).exists()


class TestTheRun:
    def test_it_says_what_went(self, ana):
        _user_session(ana, _session(ana, expired=True))
        _code(ana, seconds_left=-1)

        output = _run()

        assert output.strip() == "purge_expired_sessions: sessions=1 session_rows=1 jump_codes=1 email_changes=0"

    def test_a_dry_run_counts_and_deletes_nothing(self, ana):
        expired = _session(ana, expired=True)
        row = _user_session(ana, expired)
        code = _code(ana, seconds_left=-1)

        output = _run("--dry-run")

        assert output.strip() == (
            "purge_expired_sessions (dry run): sessions=1 session_rows=1 jump_codes=1 email_changes=0"
        )
        assert Session.objects.filter(session_key=expired).exists()
        assert UserSession.objects.filter(pk=row.pk).exists()
        assert AuthExchangeCode.objects.filter(pk=code.pk).exists()

    def test_a_second_run_while_one_holds_the_lock_does_nothing(self, ana):
        code = _code(ana, seconds_left=-1)
        other = connections["default"].copy()
        lock = [services.lock_name("purge_expired_sessions")]
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", lock)
            output = _run()
        finally:
            # Released by hand: closing a pooled connection gives its session back to the pool with the lock held,
            # and the next test's run would find it «already running».
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", lock)
            other.close()

        assert "already running" in output
        assert AuthExchangeCode.objects.filter(pk=code.pk).exists()

    def test_the_sweep_writes_nothing_in_the_audit_log(self, ana):
        """The audit log says who changed an account (ACCOUNTS-F36); a row that ended by itself is no change, and one
        entry per row would bury the real ones."""
        from auditlog.models import LogEntry

        _user_session(ana, _session(ana, expired=True))
        before = LogEntry.objects.count()

        output = _run()

        assert "session_rows=1" in output
        assert LogEntry.objects.count() == before
