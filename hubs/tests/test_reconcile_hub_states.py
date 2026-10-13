"""The ``saas-cron`` commands that keep the Hub equal to the SaaS (aws-next README, the app ↔ infra contract;
plan 2026-10-13 §3, the push to the Hub):

- ``reconcile_hub_states`` (every 15 minutes): retries what the Hub still owes an answer to (the
  registry, a deletion, a restoration, a snapshot), asks the Hub about an sign-up stuck without its
  ``ready`` callback (``GET /internal/hubs/{id}``), ends the trials that ran out and marks purged the
  businesses past their 90 days;
- ``push_hub_snapshots`` (nightly): pushes every snapshot the Hub is behind on; ``--all`` pushes every
  business's (the safety net of PLAN-SAAS §2.2).

Both are idempotent (a second run with nothing new does nothing) and hold a Postgres advisory lock, so
two runs never overlap: the second returns at once. A business that fails never stops the batch.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from accounts.models import HubMembership
from hubs import hub_client, services
from hubs.models import Hub, Subscription
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db


def run(command, *args):
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def fresh(hub):
    return Hub.objects.get(pk=hub.pk)




# --- reconcile_hub_states -------------------------------------------------------------------------


class TestReconcile:
    def test_a_sign_up_the_hub_never_got_is_retried(self, business, hub_double):
        output = run("reconcile_hub_states")

        assert [(c.method, c.path) for c in hub_double.calls] == [
            ("PUT", f"/internal/hubs/{business.id}"),
            ("PUT", f"/internal/hubs/{business.id}/state"),
        ]
        assert fresh(business).pending_hub_call == ""
        assert "delivered=1" in output

    def test_a_second_run_with_nothing_new_does_nothing(self, business, hub_double):
        run("reconcile_hub_states")
        sent = len(hub_double.calls)

        output = run("reconcile_hub_states")

        assert len(hub_double.calls) == sent
        assert "delivered=0" in output

    def test_with_the_hub_away_it_stays_owed_and_the_run_fails_after_the_pass(self, owner, plans, offline_hub, make_user):
        """Review of L1-A, finding 4: an unreachable Hub fails the run (exit ≠ 0, the ``task_failed``
        alarm), but only after every business was tried."""
        first = create_business(owner)
        second = create_business(make_user("lola@example.com"), name="Café Lola")

        with pytest.raises(CommandError) as failed:
            run("reconcile_hub_states")

        assert "owed=2" in str(failed.value)
        assert fresh(first).pending_hub_call == fresh(second).pending_hub_call == "put"

    def test_a_refusal_of_the_hub_fails_the_run_and_is_visible(self, business, hub_double):
        hub_double.answer("PUT", r"/internal/hubs/[^/]+$", 422, {"error": {"code": "unknown_vertical"}})

        with pytest.raises(CommandError):
            run("reconcile_hub_states")

        assert fresh(business).last_hub_error == "unknown_vertical"

    def test_one_stuck_business_that_crashes_does_not_stop_the_pass(self, owner, plans, hub_double, make_user, monkeypatch):
        first = create_business(owner)
        second = create_business(make_user("lola@example.com"), name="Café Lola")
        for hub in (first, second):
            services.sync_hub(hub.id)
            hub_double.registry[str(hub.id)]["status"] = "ready"
        Hub.objects.update(provision_requested_at=timezone.now() - timedelta(minutes=5))
        real = hub_client.get_hub

        def crashing(hub_id):
            if hub_id == str(first.id):
                raise RuntimeError("boom")
            return real(hub_id)

        monkeypatch.setattr(hub_client, "get_hub", crashing)

        with pytest.raises(CommandError):
            run("reconcile_hub_states")

        assert (fresh(first).status, fresh(second).status) == ("preparing", "active")

    def test_a_business_that_fails_never_stops_the_batch(
        self, owner, plans, hub_double, make_user, monkeypatch
    ):
        first = create_business(owner)
        second = create_business(make_user("lola@example.com"), name="Café Lola")
        real = services.sync_hub

        def flaky(hub_id):
            if hub_id == first.id:
                raise RuntimeError("boom")
            return real(hub_id)

        monkeypatch.setattr(services, "sync_hub", flaky)

        run("reconcile_hub_states")

        assert fresh(second).pending_hub_call == ""

    def test_a_stuck_sign_up_the_hub_finished_is_marked_ready(self, business, hub_double):
        services.sync_hub(business.id)
        Hub.objects.filter(pk=business.pk).update(
            provision_requested_at=timezone.now() - timedelta(minutes=5)
        )
        hub_double.registry[str(business.id)]["status"] = "ready"

        output = run("reconcile_hub_states")

        assert (fresh(business).status, fresh(business).ready_at is not None) == (
            "active",
            True,
        )
        assert "ready=1" in output

    def test_a_stuck_sign_up_the_hub_does_not_know_is_registered_again(
        self, business, hub_double
    ):
        Hub.objects.filter(pk=business.pk).update(
            pending_hub_call="",
            pushed_state_version=1,
            provision_requested_at=timezone.now() - timedelta(minutes=5),
        )

        output = run("reconcile_hub_states")

        assert [c.method for c in hub_double.calls][:2] == ["GET", "PUT"]
        assert hub_double.calls_to("PUT", str(business.id))
        assert "re_registered=1" in output

    def test_a_sign_up_younger_than_the_threshold_is_left_alone(
        self, business, hub_double
    ):
        services.sync_hub(business.id)
        hub_double.calls.clear()

        run("reconcile_hub_states")

        assert hub_double.calls == []

    def test_the_threshold_is_an_option(self, business, hub_double):
        services.sync_hub(business.id)
        Hub.objects.filter(pk=business.pk).update(
            provision_requested_at=timezone.now() - timedelta(minutes=5)
        )
        hub_double.calls.clear()

        run("reconcile_hub_states", "--stuck-minutes", "10")

        assert hub_double.calls == []

    def test_a_trial_that_ran_out_reaches_the_hub_as_free(self, business, hub_double):
        services.sync_hub(business.id)
        Subscription.objects.filter(hub=business).update(
            trial_end=timezone.now() - timedelta(minutes=1)
        )

        output = run("reconcile_hub_states")

        assert Subscription.objects.get(hub=business).status == "active"
        assert hub_double.calls_to("PUT", "/state")[-1].body["plan"]["slug"] == "free"
        assert "trials_ended=1" in output

    def test_a_deleted_business_past_its_ninety_days_is_purged(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.DELETING,
            deletion_requested_at=timezone.now() - timedelta(days=91),
            pending_hub_call="",
        )

        output = run("reconcile_hub_states")

        assert fresh(business).status == "deleted"
        assert "purged=1" in output

    def test_a_deletion_the_hub_never_got_is_retried(self, business, hub_double):
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.DELETING,
            deletion_requested_at=timezone.now(),
            pending_hub_call="delete",
        )

        run("reconcile_hub_states")

        assert hub_double.calls_to("DELETE")
        assert fresh(business).pending_hub_call == ""

    def test_a_second_run_returns_at_once_while_one_holds_the_lock(
        self, business, hub_double, other_session
    ):
        other_session.execute(
            "SELECT pg_advisory_lock(%s)", [services.lock_key("reconcile_hub_states")]
        )

        output = run("reconcile_hub_states")

        assert hub_double.calls == []
        assert "already running" in output
        other_session.execute(
            "SELECT pg_advisory_unlock(%s)", [services.lock_key("reconcile_hub_states")]
        )

    def test_the_lock_is_released_after_a_run(
        self, business, hub_double, other_session
    ):
        run("reconcile_hub_states")

        taken = other_session.execute(
            "SELECT pg_try_advisory_lock(%s)",
            [services.lock_key("reconcile_hub_states")],
        ).fetchone()[0]

        assert taken is True
        other_session.execute(
            "SELECT pg_advisory_unlock(%s)", [services.lock_key("reconcile_hub_states")]
        )


def test_the_two_commands_hold_different_locks():
    assert services.lock_key("push_hub_snapshots") != services.lock_key(
        "reconcile_hub_states"
    )


def test_nobody_enters_a_purged_business(business, owner):
    Hub.objects.filter(pk=business.pk).update(
        status=Hub.Status.DELETING,
        deletion_requested_at=timezone.now() - timedelta(days=91),
        pending_hub_call="",
    )

    run("reconcile_hub_states")

    assert not HubMembership.objects.filter(hub_slug=business.slug).exists()


def test_a_business_restored_while_the_purge_runs_keeps_its_people(business, owner, hub_double, monkeypatch):
    """Review of L1-A: the purge re-checks the row it updates; one restored meanwhile is left alone."""
    monkeypatch.setattr(services, "expired_deletions", lambda cutoff: [business.id])  # read before the restore

    run("reconcile_hub_states")

    assert fresh(business).status == "preparing"
    assert HubMembership.objects.filter(hub_slug=business.slug, user=owner).exists()
