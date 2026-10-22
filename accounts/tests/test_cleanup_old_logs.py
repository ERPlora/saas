"""ACCOUNTS-F37 · ``manage.py cleanup_old_logs``: the audit log keeps 90 days (GDPR art. 5.1.e, storage limitation;
ACCOUNTS-G08, G53, G62 and G28, its task). Daily in ``saas-cron``.

Ported from ERPlora/saas ``apps/auth/users/management/commands/cleanup_old_logs.py`` and its tests
(``tests/unit/test_gdpr_retention_policy.py``, ``test_gdpr_retention_noinput.py``): the entries older than
``--retention-days`` (90) go, the younger stay, ``--dry-run`` only counts. Changed: no question is asked (the old
``--no-input`` is the only way, #970: a prompt killed the scheduled run), one batch per transaction instead of one
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
    """#970: under the scheduled task there is nobody to answer, and a question killed the run."""
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("cleanup_old_logs asked a question"))
    old = entry(120)

    _run()

    assert _left(old) == [False]


def test_a_second_run_while_one_holds_the_lock_does_nothing(entry):
    old = entry(120)
    other = connections["default"].copy()
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [services.lock_name("cleanup_old_logs")])
        output = _run()
    finally:
        other.close()

    assert "already running" in output
    assert _left(old) == [True]
