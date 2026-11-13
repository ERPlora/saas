"""ACCOUNTS-F37 · ``manage.py cleanup_old_logs``: the audit log keeps 90 days (GDPR art. 5.1.e, storage limitation;
ACCOUNTS-G08, G53, G62 and G28, its task). Daily in ``saas-cron``.

Ported from ERPlora/saas ``apps/auth/users/management/commands/cleanup_old_logs.py`` and its tests
(``tests/unit/test_gdpr_retention_policy.py``, ``test_gdpr_retention_noinput.py``): the entries older than
``--retention-days`` (90) go, the younger stay, ``--dry-run`` only counts. Changed: no question is asked (the old
``--no-input`` is the only way: a prompt killed the scheduled run), one batch per transaction instead of one
transaction for the whole run, and the advisory lock of ``anonymize_old_users`` so two runs never overlap.
"""

from datetime import timedelta
from io import StringIO

import pytest
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from django.db import connections
from django.utils import timezone

from accounts import services

pytestmark = pytest.mark.django_db


@pytest.fixture
def entry(ana):
    """An audit entry about ``ana`` written ``days`` ago."""

    def make(days: float) -> LogEntry:
        written = LogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(get_user_model()),
            object_pk=str(ana.pk),
            object_repr=str(ana),
            action=LogEntry.Action.UPDATE,
        )
        LogEntry.objects.filter(pk=written.pk).update(timestamp=timezone.now() - timedelta(days=days))
        return written

    return make


def _run(*args) -> str:
    out = StringIO()
    call_command("cleanup_old_logs", *args, stdout=out)
    return out.getvalue()


def _left(*entries) -> list[bool]:
    return [LogEntry.objects.filter(pk=entry.pk).exists() for entry in entries]


def test_older_than_90_days_goes_and_younger_stays(entry):
    recent, almost, old, very_old = entry(30), entry(89), entry(91), entry(200)

    output = _run()

    assert _left(recent, almost, old, very_old) == [True, True, False, False]
    assert "deleted=2" in output


def test_the_edge_is_90_days_to_the_hour(entry):
    # Whole days around the edge leave it loose (a 91-day period still deletes an entry of 91 days): an hour each side
    # of the 90th day pins it.
    inside, past = entry(90 - 1 / 24), entry(90 + 1 / 24)

    _run()

    assert _left(inside, past) == [True, False]


def test_the_period_comes_from_the_option(entry):
    recent, old = entry(30), entry(60)

    _run("--retention-days", "50")

    assert _left(recent, old) == [True, False]


def test_a_dry_run_counts_and_deletes_nothing(entry):
    old, very_old = entry(120), entry(200)

    output = _run("--dry-run")

    assert _left(old, very_old) == [True, True]
    assert "would_delete=2" in output


def test_nothing_to_delete_says_so(entry):
    entry(30)

    assert "deleted=0" in _run()


def test_a_period_under_a_day_is_refused(entry):
    old = entry(120)

    with pytest.raises(CommandError, match="--retention-days"):
        _run("--retention-days", "0")
    assert _left(old) == [True]


def test_it_deletes_batch_after_batch_until_none_is_left(entry, monkeypatch):
    monkeypatch.setattr(services, "AUDIT_LOG_BATCH", 2)
    old = [entry(100 + day) for day in range(5)]
    recent = entry(10)

    output = _run()

    assert _left(*old, recent) == [False] * 5 + [True]
    assert "deleted=5" in output


def test_it_never_asks(entry, monkeypatch):
    """Under the scheduled task there is nobody to answer, and a question killed the run."""
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("cleanup_old_logs asked a question"))
    old = entry(120)

    _run()

    assert _left(old) == [False]


def test_a_second_run_while_one_holds_the_lock_does_nothing(entry):
    old = entry(120)
    other = connections["default"].copy()
    lock = [services.lock_name("cleanup_old_logs")]
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", lock)
        output = _run()
    finally:
        # Released by hand: closing a pooled connection gives its session back to the pool with the lock held, and
        # a later run (fiscal's test of this command too) would find it «already running» (conftest.py guards it).
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", lock)
        other.close()

    assert "already running" in output
    # Given back: the pool keeps the other session open, and a lock left in it stopped every later run of the
    # process ("already running"; the billing prune test after this one, 2026-10-22).
    assert _lock_is_free(services.lock_name("cleanup_old_logs"))
    assert _left(old) == [True]


def _lock_is_free(name: str) -> bool:
    """Whether another session may take ``name`` now (taken and given back at once)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [name])
        taken = cursor.fetchone()[0]
        if taken:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])
    return taken


class TestTheContentTypeOfTheRetiredCopy:
    """saas#220: ``accounts.hubmembership`` outlives its table only while an audit entry names it. Deleting a content
    type takes its entries with it, so it goes with the run that prunes the last one, and never before."""

    KIND = {"app_label": "accounts", "model": "hubmembership"}

    def _written(self, days: float) -> LogEntry:
        kind, _ = ContentType.objects.get_or_create(**self.KIND)
        written = LogEntry.objects.create(
            content_type=kind, object_pk="1", object_repr="ana @ a (Admin)", action=LogEntry.Action.UPDATE
        )
        LogEntry.objects.filter(pk=written.pk).update(timestamp=timezone.now() - timedelta(days=days))
        return written

    def _kind_left(self) -> bool:
        return ContentType.objects.filter(**self.KIND).exists()

    def test_it_stays_while_an_entry_is_younger_than_90_days(self):
        young, old = self._written(30), self._written(91)

        _run()

        assert _left(young, old) == [True, False]
        assert self._kind_left()

    def test_the_run_that_prunes_the_last_entry_takes_it(self):
        old = self._written(91)

        _run()

        assert _left(old) == [False]
        assert not self._kind_left()

    def test_with_no_entry_left_a_run_that_prunes_nothing_takes_it(self):
        ContentType.objects.get_or_create(**self.KIND)

        assert "deleted=0" in _run()

        assert not self._kind_left()

    def test_a_dry_run_leaves_it_with_its_entry_and_without_any(self):
        old = self._written(91)

        _run("--dry-run")

        assert _left(old) == [True]
        assert self._kind_left()

        LogEntry.objects.filter(pk=old.pk).delete()

        _run("--dry-run")

        assert self._kind_left()

    def test_a_run_that_finds_another_one_running_leaves_it(self, monkeypatch):
        from contextlib import contextmanager

        @contextmanager
        def taken(_name):
            yield False

        ContentType.objects.get_or_create(**self.KIND)
        monkeypatch.setattr(services, "run_exclusively", taken)

        assert "already running" in _run()

        assert self._kind_left()

    def test_no_other_type_without_a_model_goes(self):
        other, _ = ContentType.objects.get_or_create(app_label="accounts", model="sometimeslater")

        _run()

        assert ContentType.objects.filter(pk=other.pk).exists()

    def test_deleting_the_type_regardless_would_take_its_entries(self):
        """The positive of the guard: the cascade is real, which is why the run looks first."""
        young = self._written(30)

        ContentType.objects.filter(**self.KIND).delete()

        assert _left(young) == [False]
