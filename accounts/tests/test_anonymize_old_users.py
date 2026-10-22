"""ACCOUNTS-F35 · ``manage.py anonymize_old_users``: the accounts unused for two years go (GDPR art. 5.1.e, storage
limitation; ACCOUNTS-G97, G07, G52, G61). Weekly in ``saas-cron``.

Ported from ERPlora/saas ``apps/auth/users/management/commands/anonymize_old_users.py`` and its test
``test_anonymize_skips_hub_owners.py`` (saas#2567), with what the old one left behind (SAAS_AUTH-F15: the real email in
the addresses, the names, the linked Google account and the sessions' addresses): an account goes as its owner deletes
it (ACCOUNTS-F27), with all of that, and ERPlora's invoices stay with their recipient as issued.

Which: active, not staff, and its last sign-in (or, never signed in, its creation) more than ``--inactive-days`` (730)
ago. Never one that belongs to a business that is not deleted, owner, payer or member: ``last_login`` only moves when
signing in on erplora.com, so whoever works in a business every day (its session, its PIN) looks unused here, and
erasing them would take them out of the business (the old SaaS spared only the owners). Google's policy for inactive
accounts spares the accounts of organisations the same way.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connections
from django.utils import timezone

from accounts import events, services, signals
from accounts.models import ApiKey, UserPreferences
from hubs.tests.conftest import add_member, create_business, plans  # noqa: F401 - the plans fixture

pytestmark = pytest.mark.django_db

User = get_user_model()


def _account(email: str, *, last_login_days: int | None, joined_days: int = 1000, **fields):
    now = timezone.now()
    user = User.objects.create_user(email=email, password="x", **fields)
    User.objects.filter(pk=user.pk).update(
        date_joined=now - timedelta(days=joined_days),
        last_login=None if last_login_days is None else now - timedelta(days=last_login_days),
    )
    return User.objects.get(pk=user.pk)


def _run(*args) -> str:
    out = StringIO()
    call_command("anonymize_old_users", *args, stdout=out)
    return out.getvalue()


def _exists(user) -> bool:
    return User.objects.filter(pk=user.pk).exists()


@pytest.fixture
def received():
    calls = []

    def sessions_ended(sender, user_id, **kwargs):
        calls.append(("sessions_ended", user_id))

    def account_deleting(sender, user_id, **kwargs):
        calls.append(("account_deleting", user_id))

    signals.sessions_ended.connect(sessions_ended, dispatch_uid="test-anonymize-sessions-ended")
    signals.account_deleting.connect(account_deleting, dispatch_uid="test-anonymize-account-deleting")
    yield calls
    signals.sessions_ended.disconnect(dispatch_uid="test-anonymize-sessions-ended")
    signals.account_deleting.disconnect(dispatch_uid="test-anonymize-account-deleting")


class TestWhichAccountsGo:
    def test_two_years_without_signing_in_goes_and_a_day_less_stays(self):
        old = _account("old@example.com", last_login_days=731)
        recent = _account("recent@example.com", last_login_days=729)

        output = _run()

        assert (_exists(old), _exists(recent)) == (False, True)
        assert "erased=1" in output

    def test_never_signed_in_counts_from_its_creation(self):
        forgotten = _account("forgotten@example.com", last_login_days=None, joined_days=731)
        new = _account("new@example.com", last_login_days=None, joined_days=10)

        _run()

        assert (_exists(forgotten), _exists(new)) == (False, True)

    def test_the_period_comes_from_the_option(self):
        user = _account("ninety@example.com", last_login_days=100)

        _run("--inactive-days", "90")

        assert not _exists(user)

    def test_the_staff_and_an_account_already_deactivated_stay(self):
        staff = _account("staff@example.com", last_login_days=900, is_staff=True)
        root = User.objects.create_superuser(email="root@example.com", password="x")
        User.objects.filter(pk=root.pk).update(last_login=timezone.now() - timedelta(days=900))
        off = _account("off@example.com", last_login_days=900, is_active=False)

        _run()

        assert (_exists(staff), _exists(root), _exists(off)) == (True, True, True)


class TestWhoeverBelongsToABusinessStays:
    def test_the_owner_of_a_business_stays(self, plans):  # noqa: F811 - saas#2567
        owner = _account("owner@example.com", last_login_days=900)
        create_business(owner, name="Panadería López")

        assert "skipped_member=1" in _run()
        assert _exists(owner)

    def test_a_member_of_a_business_stays_and_the_business_keeps_it(self, plans):  # noqa: F811
        from hubs.models import HubMember

        owner = _account("owner@example.com", last_login_days=1)
        cook = _account("cook@example.com", last_login_days=900)
        business = create_business(owner, name="Bar Manolo")
        add_member(business, cook, HubMember.Role.EMPLOYEE, invited_by=owner)

        _run()

        assert _exists(cook)
        assert HubMember.objects.filter(hub=business, user=cook).exists()

    def test_a_business_already_deleted_holds_nobody(self, plans):  # noqa: F811
        from hubs.models import Hub

        owner = _account("gone@example.com", last_login_days=900)
        business = create_business(owner)
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING, deletion_requested_at=timezone.now())

        _run()

        assert not _exists(owner)


class TestItGoesAsItsOwnerWouldDeleteIt:
    def test_what_hangs_from_it_goes_and_the_businesses_end_its_sessions(self, received):
        user = _account("old@example.com", last_login_days=900)
        UserPreferences.objects.create(user=user, theme_mode="dark")
        _, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=user, name="k", prefix=prefix, key_hash=key_hash)

        _run()

        assert not (UserPreferences.objects.exists() or ApiKey.objects.exists())
        assert received == [("account_deleting", user.pk), ("sessions_ended", user.pk)]

    def test_its_event_goes_to_its_own_channel_and_nothing_of_another_account_moves(self):
        from live.models import OutboxEvent

        old = _account("old@example.com", last_login_days=900)
        kept = _account("kept@example.com", last_login_days=3, first_name="Kept")

        _run()

        assert list(OutboxEvent.objects.values_list("name", "scope_key", "actor")) == [
            (events.PROFILE_DELETED, str(old.pk), "system")
        ]
        assert User.objects.get(pk=kept.pk).first_name == "Kept"

    def test_erploras_invoices_stay_with_their_recipient_as_issued(self, plans):  # noqa: F811
        from billing.models import Invoice
        from billing.tests.test_invoice_queries import issue
        from hubs.models import Hub

        user = _account("old@example.com", last_login_days=900)
        business = create_business(user, name="Panadería López")
        invoice = issue(business, 7, payer=user, payer_tax_id="B12345678", payer_email="old@example.com")
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED, deletion_requested_at=timezone.now())

        _run()

        kept = Invoice.objects.get(pk=invoice.pk)
        assert (kept.number, kept.payer_tax_id, kept.payer_account_id) == ("ERP-2026-00007", "B12345678", None)

    def test_a_sign_in_after_it_was_picked_keeps_it(self, monkeypatch):
        """The account is read again under its lock: a sign-in between the pick and the erasure saves it."""
        user = _account("back@example.com", last_login_days=900)
        picked = services.inactive_account_ids

        def pick_then_sign_in(*args, **kwargs):
            ids = picked(*args, **kwargs)
            User.objects.filter(pk=user.pk).update(last_login=timezone.now())
            return ids

        monkeypatch.setattr(services, "inactive_account_ids", pick_then_sign_in)

        assert "skipped_active=1" in _run()
        assert _exists(user)


class TestTheRun:
    def test_a_dry_run_counts_and_erases_nothing(self):
        user = _account("old@example.com", last_login_days=900)

        output = _run("--dry-run")

        assert _exists(user)
        assert "would_erase=1" in output
        assert "old@example.com" not in output

    def test_one_account_that_fails_never_stops_the_others_and_the_run_ends_in_error(self, monkeypatch):
        first = _account("first@example.com", last_login_days=900, joined_days=2000)
        second = _account("second@example.com", last_login_days=900, joined_days=1500)
        erase = services.erase_inactive_account

        def failing(user_id, **options):
            if user_id == first.pk:
                raise RuntimeError("boom")
            return erase(user_id, **options)

        monkeypatch.setattr(services, "erase_inactive_account", failing)

        with pytest.raises(CommandError, match="failed=1"):
            _run()
        assert (_exists(first), _exists(second)) == (True, False)

    def test_a_second_run_while_one_holds_the_lock_does_nothing(self):
        user = _account("old@example.com", last_login_days=900)
        other = connections["default"].copy()
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [services.lock_name("anonymize_old_users")])
            output = _run()
        finally:
            # Unlocked by hand: closing a pooled connection keeps its session, and its lock with it.
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [services.lock_name("anonymize_old_users")])
            other.close()

        assert "already running" in output
        assert _exists(user)
        # Given back: the pool keeps the other session open, and a lock left in it stopped every later run of
        # the process ("already running"; the billing prune test after the cleanup's twin, 2026-10-22).
        assert _lock_is_free(services.lock_name("anonymize_old_users"))


def _lock_is_free(name: str) -> bool:
    """Whether another session may take ``name`` now (taken and given back at once)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [name])
        taken = cursor.fetchone()[0]
        if taken:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])
    return taken
