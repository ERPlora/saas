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

from datetime import UTC, timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from accounts.models import HubMembership
from hubs import hub_client, queries, services
from hubs.models import Hub, Subscription
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db

#: The advisory lock a run holds (the SaaS's convention, as ``base/tests/test_report_seal_expiry.py``).
LOCK_KEY = "hashtext('erplora.saas.reconcile_hub_states')"


def run(command, *args):
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def fresh(hub):
    return Hub.objects.get(pk=hub.pk)


def stuck(hub):
    """A sign-up the Hub took (202) and has not reported ready for longer than the threshold."""
    services.sync_hub(hub.id)
    Hub.objects.filter(pk=hub.pk).update(provision_requested_at=timezone.now() - timedelta(minutes=5))




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
        real = services.sync_outcome  # what the pass calls for each business (``_sync_counted``)

        def flaky(hub_id):
            if hub_id == first.id:
                raise RuntimeError("boom")
            return real(hub_id)

        monkeypatch.setattr(services, "sync_outcome", flaky)

        with pytest.raises(CommandError):
            run("reconcile_hub_states")

        assert fresh(second).pending_hub_call == ""
        assert fresh(first).pending_hub_call == "put"

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

    @pytest.mark.parametrize("status", ["requested", "creating", "migrating", "seeding"])
    def test_a_stuck_sign_up_the_hub_is_still_preparing_keeps_waiting(self, business, hub_double, status):
        """The asynchronous sign-up (202 «requested», PLAN-SAAS §3.1): each step the Hub reports is «still preparing»."""
        stuck(business)
        hub_double.registry[str(business.id)]["status"] = status

        output = run("reconcile_hub_states")

        assert (fresh(business).status, fresh(business).last_hub_error) == ("preparing", "")
        assert "preparing=1" in output

    def test_a_sign_up_the_hub_could_not_prepare_is_shown_and_fails_the_run(self, business, hub_double):
        """``failed``: the panel says it could not be prepared (and that it is retried), never «preparing» for ever."""
        stuck(business)
        hub_double.registry[str(business.id)]["status"] = "failed"

        with pytest.raises(CommandError) as failed:
            run("reconcile_hub_states")

        assert "provision_failed=1" in str(failed.value)
        assert (fresh(business).status, fresh(business).last_hub_error) == ("preparing", services.PROVISION_FAILED)
        assert queries.open_blocked_reason(fresh(business)) == "error"

    def test_a_failed_sign_up_the_hub_prepares_later_opens_without_the_error(self, business, hub_double):
        stuck(business)
        hub_double.registry[str(business.id)]["status"] = "failed"
        with pytest.raises(CommandError):
            run("reconcile_hub_states")
        hub_double.registry[str(business.id)]["status"] = "ready"

        output = run("reconcile_hub_states")

        assert (fresh(business).status, fresh(business).last_hub_error) == ("active", "")
        assert "ready=1" in output

    def test_a_snapshot_delivered_meanwhile_does_not_hide_the_failed_preparation(self, business, hub_double):
        """A delivered push clears the Hub's last refusal, not the preparation it still owes."""
        stuck(business)
        hub_double.registry[str(business.id)]["status"] = "failed"
        with pytest.raises(CommandError):
            run("reconcile_hub_states")
        services.bump_state(business.id)

        assert services.sync_outcome(business.id) == services.DELIVERED
        assert fresh(business).last_hub_error == services.PROVISION_FAILED

    @pytest.mark.parametrize("status", ["cancelled", "expired", "purged", "dropped", None])
    def test_a_status_the_sign_up_cannot_have_is_logged_and_fails_the_run(self, business, hub_double, status, caplog):
        """A business the SaaS is preparing that the Hub calls ended (or anything off the contract) is a person's job."""
        stuck(business)
        hub_double.registry[str(business.id)]["status"] = status

        with pytest.raises(CommandError) as failed:
            run("reconcile_hub_states")

        assert "unexpected=1" in str(failed.value)
        assert fresh(business).status == "preparing"
        assert f"hubs.reconcile.unexpected_status hub={business.id}" in caplog.text

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

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
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
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")

        output = run("reconcile_hub_states")

        assert hub_double.calls == []
        assert "already running" in output
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

    def test_the_lock_is_released_after_a_run(
        self, business, hub_double, other_session
    ):
        run("reconcile_hub_states")

        taken = other_session.execute(f"SELECT pg_try_advisory_lock({LOCK_KEY})").fetchone()[0]

        assert taken is True
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

    def test_the_lock_is_released_when_a_run_fails(
        self, business, offline_hub, other_session
    ):
        with pytest.raises(CommandError):
            run("reconcile_hub_states")

        assert other_session.execute(f"SELECT pg_try_advisory_lock({LOCK_KEY})").fetchone()[0] is True
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")


# --- «We'll let you know»: the copy of a deleted business's data is ready (PLAN-DB round 2026-10-30, (a), (k)) -----


def deleted_at(hub, moment):
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.DELETING, deletion_requested_at=moment)
    return Hub.objects.get(pk=hub.pk)


def offboarding_copy(hub, made):
    stamp = made.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return {"id": f"{hub.id.hex}/{stamp}-offboarding.dump", "kind": "offboarding", "created_at": made.isoformat(), "bytes": 4096}


def dump_calls(double):
    return double.calls_to("GET", "/dumps")


class TestDataCopyReady:
    def test_the_owner_hears_once_that_the_copy_of_a_deleted_business_is_ready(self, business, owner, hub_double, settings):
        settings.PUBLIC_HOST = "erplora.com"
        moment = timezone.now() - timedelta(minutes=10)
        hub = deleted_at(business, moment)
        hub_double.dumps[str(hub.id)] = [offboarding_copy(hub, moment + timedelta(seconds=30))]

        output = run("reconcile_hub_states")

        (message,) = mail.outbox
        assert message.to == [owner.email]
        assert f"https://erplora.com/dashboard/businesses/{hub.id}" in message.body
        assert "data_copies_told=1" in output
        assert fresh(hub).data_copy_mailed_at is not None
        run("reconcile_hub_states")
        assert len(mail.outbox) == 1
        assert len(dump_calls(hub_double)) == 1  # told: the Hub is not asked again

    def test_no_mail_while_the_hub_has_no_copy_yet_and_it_is_asked_again(self, business, hub_double):
        hub = deleted_at(business, timezone.now())
        hub_double.dumps[str(hub.id)] = []

        run("reconcile_hub_states")
        run("reconcile_hub_states")

        assert mail.outbox == []
        assert len(dump_calls(hub_double)) == 2
        assert fresh(hub).data_copy_mailed_at is None

    @pytest.mark.parametrize("kind", ["offboarding", "reset"])
    def test_a_copy_that_is_not_this_deletions_tells_nothing(self, business, hub_double, kind):
        """A copy from an earlier deletion (recovered since), or the one made before a reset, is not this one."""
        moment = timezone.now()
        hub = deleted_at(business, moment)
        old = offboarding_copy(hub, moment - timedelta(days=3))
        hub_double.dumps[str(hub.id)] = [{**old, "kind": kind}]

        run("reconcile_hub_states")

        assert mail.outbox == []

    def test_deleted_again_after_a_recovery_the_owner_hears_of_the_new_copy(self, business, hub_double):
        moment = timezone.now()
        hub = deleted_at(business, moment)
        Hub.objects.filter(pk=hub.pk).update(data_copy_mailed_at=moment - timedelta(days=5))
        hub_double.dumps[str(hub.id)] = [offboarding_copy(hub, moment + timedelta(seconds=5))]

        run("reconcile_hub_states")

        assert len(mail.outbox) == 1

    def test_the_hub_away_fails_the_run_and_tells_nobody(self, business, offline_hub):
        deleted_at(business, timezone.now())

        with pytest.raises(CommandError) as failed:
            run("reconcile_hub_states")

        assert "unreachable=1" in str(failed.value)
        assert mail.outbox == []

    def test_a_mail_that_cannot_leave_fails_the_run_and_is_sent_again(self, business, hub_double, monkeypatch):
        moment = timezone.now()
        hub = deleted_at(business, moment)
        hub_double.dumps[str(hub.id)] = [offboarding_copy(hub, moment)]
        monkeypatch.setattr(services.emails, "send_data_copy_ready", lambda *args, **kwargs: False)

        with pytest.raises(CommandError) as failed:
            run("reconcile_hub_states")

        assert "data_copy_unsent=1" in str(failed.value)
        assert fresh(hub).data_copy_mailed_at is None

    def test_a_business_that_will_never_have_a_copy_is_promised_nothing(self, business, hub_double):
        """``available: false``: a business without its own database never gets a copy, so no mail is due."""
        hub = deleted_at(business, timezone.now())
        hub_double.dumps[str(hub.id)] = []
        hub_double.without_copies.add(str(hub.id))

        output = run("reconcile_hub_states")

        assert mail.outbox == []
        assert "data_copy_none=1" in output
        assert fresh(hub).data_copy_mailed_at is None

    def test_a_business_that_lives_is_not_asked(self, business, hub_double):
        run("reconcile_hub_states")

        assert dump_calls(hub_double) == []


def test_the_lock_follows_the_saas_convention_and_is_its_own():
    """``hashtext('erplora.saas.<command>')``, the key ``base``'s commands take (``migrate``,
    ``report_seal_expiry``): one namespace for every lock of the SaaS's database."""
    assert services.lock_name("reconcile_hub_states") == "erplora.saas.reconcile_hub_states"
    assert services.lock_name("push_hub_snapshots") != services.lock_name("reconcile_hub_states")


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
