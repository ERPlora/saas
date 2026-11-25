"""One pass of ``reconcile_hub_states``: what it counts, the order of its steps, where it is cut short, who each step
leaves alone and what never stops it. What each step does is in ``test_reconcile_hub_states.py``."""

import logging
from datetime import timedelta

import pytest
from django.db.models import F
from django.utils import timezone

from apps.models import Module
from hubs import hub_client
from hubs.models import Hub, HubMember, SessionRevocation, Subscription
from hubs.queries import businesses, data_copies
from hubs.services import hub_push, reconciliation, subscription_sync
from hubs.tests.conftest import add_member, create_business, member_of

pytestmark = pytest.mark.django_db

LONG_AGO = timedelta(minutes=5)


def fresh(hub):
    return Hub.objects.get(pk=hub.pk)


def settled(hub, **fields):
    """A business the pass has nothing to do with, except for ``fields``."""
    now = timezone.now()
    facts = {"status": Hub.Status.ACTIVE, "ready_at": now, "pending_hub_call": "", "pushed_state_version": F("state_version")}
    Hub.objects.filter(pk=hub.pk).update(**{**facts, **fields})
    return fresh(hub)


def stuck(hub, **fields):
    return settled(hub, status=Hub.Status.PREPARING, ready_at=None, provision_requested_at=timezone.now() - LONG_AGO, **fields)


def deleted(hub, **fields):
    return settled(hub, **{"status": Hub.Status.DELETING, "deletion_requested_at": timezone.now(), **fields})


def revocation(user, **fields):
    return SessionRevocation.objects.create(user_id=user.pk, **fields)


def asked(double):
    return [(call.method, call.path) for call in double.calls]


@pytest.fixture
def several(owner, plans, make_user):
    """Three businesses, each of its own owner, the oldest first."""
    others = [make_user(f"owner{n}@example.com") for n in (2, 3)]
    return [create_business(user, name=f"Bar {n}") for n, user in enumerate([owner, *others], 1)]


# --- What it counts -----------------------------------------------------------------------------------


def test_every_count_is_there_though_nothing_happened(plans):
    assert list(reconciliation.reconcile().items()) == [
        (key, 0)
        for key in (
            "purged",
            "trials_ended",
            "delivered",
            "owed",
            "refused",
            "ready",
            "re_registered",
            "preparing",
            "provision_failed",
            "unexpected",
            "unreachable",
            "failed",
            "data_copies_told",
            "data_copy_unsent",
            "data_copy_none",
            "sessions_ended",
            "sessions_pending",
            "cut_short",
        )
    ]


# --- Its order, and where it is cut short -------------------------------------------------------------


@pytest.fixture
def work(several, owner, hub_double):
    """Something for each step that calls the Hub, in the order the pass does them."""
    owed, waiting, gone = several
    waiting, gone = stuck(waiting), deleted(gone)
    hub_double.registry[str(waiting.id)] = {"status": "creating"}
    hub_double.dumps[str(gone.id)] = []
    revocation(owner, hub_id=owed.id)
    return [
        [("PUT", f"/internal/hubs/{owed.id}"), ("PUT", f"/internal/hubs/{owed.id}/state")],
        [("GET", f"/internal/hubs/{waiting.id}")],
        [("GET", f"/internal/hubs/{gone.id}/dumps")],
        [("POST", "/internal/sessions/revoke")],
    ]


def test_it_delivers_what_is_owed_then_asks_then_tells_and_last_ends_sessions(work, hub_double):
    counts = reconciliation.reconcile()

    assert asked(hub_double) == [call for step in work for call in step]
    assert (counts["delivered"], counts["preparing"], counts["sessions_ended"]) == (1, 1, 1)
    assert counts["cut_short"] == 0


@pytest.mark.parametrize("done", range(4))
def test_cut_short_before_any_of_its_calls_it_makes_none_of_the_rest(work, hub_double, done):
    questions = []

    def go_on():
        questions.append(1)
        return len(questions) <= done

    counts = reconciliation.reconcile(go_on=go_on)

    assert asked(hub_double) == [call for step in work[:done] for call in step]
    assert counts["cut_short"] == 1
    assert len(questions) == done + 1


def test_with_time_for_everything_it_is_not_cut_short(work, hub_double):
    counts = reconciliation.reconcile(go_on=lambda: True)

    assert asked(hub_double) == [call for step in work for call in step]
    assert counts["cut_short"] == 0


def test_cut_short_it_still_does_what_only_touches_the_database(business, hub_double):
    long_gone = timezone.now() - timedelta(days=91)
    deleted(business, deletion_requested_at=long_gone)

    counts = reconciliation.reconcile(go_on=lambda: False)

    assert counts["purged"] == 1
    assert fresh(business).status == Hub.Status.DELETED


def test_the_business_owed_for_longest_goes_first(several, hub_double):
    first, second, third = several
    now = timezone.now()
    for hub, minutes in ((second, 30), (third, 20), (first, 10)):
        Hub.objects.filter(pk=hub.pk).update(updated_at=now - timedelta(minutes=minutes))

    reconciliation.reconcile()

    registered = [call.hub_id for call in hub_double.calls_to("PUT") if not call.path.endswith("/state")]
    assert registered == [str(hub.id) for hub in (second, third, first)]


def test_the_revocation_due_for_longest_goes_first(several, owner, hub_double, make_user):
    for hub in several:
        settled(hub)
    now = timezone.now()
    late = revocation(owner, next_attempt_at=now - timedelta(minutes=1))
    later = revocation(make_user("other@example.com"), next_attempt_at=now - timedelta(minutes=9))

    reconciliation.reconcile()

    assert [call.body["user_id"] for call in hub_double.calls_to("POST", "/revoke")] == [str(later.user_id), str(late.user_id)]


# --- Purging ------------------------------------------------------------------------------------------


def test_a_purge_is_dated(business):
    now = timezone.now()
    deleted(business, deletion_requested_at=now - timedelta(days=91))

    counts = reconciliation.reconcile(now=now)

    assert (fresh(business).status, fresh(business).updated_at) == (Hub.Status.DELETED, now)
    assert counts["purged"] == 1


@pytest.mark.parametrize(
    ("status", "days"),
    [(Hub.Status.ACTIVE, 91), (Hub.Status.DELETING, 1)],
    ids=["recovered", "recovered and deleted again"],
)
def test_a_business_that_moved_since_the_purge_read_it_is_left_alone(business, hub_double, monkeypatch, status, days):
    settled(business, status=status, deletion_requested_at=timezone.now() - timedelta(days=days))
    monkeypatch.setattr(businesses, "expired_deletions", lambda cutoff: [business.id])

    counts = reconciliation.reconcile()

    assert fresh(business).status == status
    assert counts["purged"] == 0


# --- Ending trials ------------------------------------------------------------------------------------


def trying(hub, until, **fields):
    Subscription.objects.filter(hub=hub).update(status=Subscription.Status.TRIALING, trial_end=until, **fields)
    return Subscription.objects.get(hub=hub)


def test_a_trial_that_goes_on_is_left_alone(business, hub_double):
    settled(business)
    trial = trying(business, timezone.now() + timedelta(days=1))

    counts = reconciliation.reconcile()

    trial.refresh_from_db()
    assert trial.status == Subscription.Status.TRIALING
    assert counts["trials_ended"] == 0


def test_the_end_of_a_trial_is_dated(business, hub_double):
    settled(business)
    now = timezone.now()
    trial = trying(business, now - LONG_AGO)

    reconciliation.reconcile(now=now)

    trial.refresh_from_db()
    assert (trial.status, trial.updated_at) == (Subscription.Status.ACTIVE, now)


def test_a_trial_paid_for_since_the_pass_read_it_is_left_alone(several, hub_double, monkeypatch):
    for hub in several[:2]:
        trying(settled(hub), timezone.now() - LONG_AGO)
    settled(several[2])
    real = subscription_sync.sync_plan_modules

    def the_other_pays(subscription, now):
        Subscription.objects.filter(status=Subscription.Status.TRIALING).update(status=Subscription.Status.PAST_DUE)
        return real(subscription, now)

    monkeypatch.setattr(reconciliation, "sync_plan_modules", the_other_pays)

    counts = reconciliation.reconcile()

    assert counts["trials_ended"] == 1
    assert sorted(Subscription.objects.filter(hub__in=several[:2]).values_list("status", flat=True)) == ["active", "past_due"]
    assert counts["delivered"] == 1


@pytest.mark.usefixtures("signup_trial")
def test_what_only_the_trial_included_ends_at_the_time_of_the_pass(business, hub_double):
    Module.objects.create(slug="inventory", tier=Module.Tier.BASIC)
    subscription_sync.sync_plan_modules(Subscription.objects.get(hub=business))
    settled(business)
    trial = trying(business, timezone.now() + timedelta(days=1))
    assert trial.items.exists()

    reconciliation.reconcile(now=timezone.now() + timedelta(days=2))

    assert not trial.items.exists()


# --- Who each step leaves alone -----------------------------------------------------------------------


def test_a_purged_business_is_owed_nothing(business, hub_double):
    settled(business, status=Hub.Status.DELETED, pending_hub_call=Hub.HubCall.DELETE)

    reconciliation.reconcile()

    assert hub_double.calls == []


def test_a_deleted_business_owes_no_snapshot(business, hub_double):
    deleted(business, pushed_state_version=0)

    counts = reconciliation.reconcile()

    assert counts["delivered"] == 0
    assert hub_double.calls_to("PUT") == []


@pytest.mark.parametrize(
    "fields",
    [{"status": Hub.Status.ACTIVE}, {"ready_at": timezone.now()}],
    ids=["not being prepared", "ready already"],
)
def test_only_a_sign_up_still_being_prepared_is_asked_about(business, hub_double, fields):
    Hub.objects.filter(pk=stuck(business).pk).update(**fields)

    reconciliation.reconcile()

    assert hub_double.calls == []


def test_a_sign_up_the_hub_refuses_is_not_asked_about(business, hub_double):
    stuck(business, pending_hub_call=Hub.HubCall.PUT)
    hub_double.answer("PUT", r"/internal/hubs/[^/]+$", 422, {"error": {"code": "unknown_vertical"}})

    counts = reconciliation.reconcile()

    assert (counts["owed"], counts["refused"]) == (1, 1)
    assert hub_double.calls_to("GET") == []


def test_the_copy_of_a_business_whose_owner_left_is_told_to_nobody_else(business, owner, make_user, hub_double):
    add_member(business, make_user("admin@example.com"), HubMember.Role.ADMIN, invited_by=owner)
    member_of(business, owner).delete()
    deleted(business)

    reconciliation.reconcile()

    assert hub_double.calls == []


def test_a_deletion_without_a_date_is_not_asked_for_its_copy(business, hub_double):
    deleted(business, deletion_requested_at=None)

    reconciliation.reconcile()

    assert hub_double.calls == []


# --- What never stops it ------------------------------------------------------------------------------


@pytest.fixture
def logged(caplog):
    caplog.set_level(logging.INFO, logger="hubs.services.reconciliation")
    return caplog


def breaks_for(monkeypatch, module, name, broken):
    """``module.name`` raises when its first argument is ``broken``."""
    real = getattr(module, name)

    def breaks(one):
        if one == broken:
            raise RuntimeError("a bug")
        return real(one)

    monkeypatch.setattr(module, name, breaks)


def test_a_sign_up_that_crashes_is_counted_and_logged(business, hub_double, monkeypatch, logged):
    stuck(business)
    breaks_for(monkeypatch, hub_client, "get_hub", str(business.id))

    counts = reconciliation.reconcile()

    assert counts["failed"] == 1
    assert f"hubs.reconcile.crashed hub={business.id}" in logged.messages


def test_a_copy_that_crashes_never_stops_the_others(several, hub_double, monkeypatch, logged):
    first, second = (deleted(hub) for hub in several[:2])
    settled(several[2])
    hub_double.dumps[str(second.id)] = []
    hub_double.without_copies.add(str(second.id))
    breaks_for(monkeypatch, data_copies, "hub_data_copies", first.id)

    counts = reconciliation.reconcile()

    assert (counts["failed"], counts["data_copy_none"]) == (1, 1)
    assert f"hubs.data_copy.crashed hub={first.id}" in logged.messages


def test_a_revocation_that_crashes_stays_pending_and_never_stops_the_others(business, owner, make_user, hub_double, monkeypatch, logged):
    settled(business)
    first = revocation(owner)
    second = revocation(make_user("other@example.com"))
    breaks_for(monkeypatch, reconciliation, "deliver_revocation", first.id)

    counts = reconciliation.reconcile()

    assert (counts["sessions_ended"], counts["sessions_pending"]) == (1, 1)
    assert f"hubs.revoke.crashed revocation={first.id}" in logged.messages
    second.refresh_from_db()
    assert second.delivered_at is not None


def test_a_business_that_crashes_stays_owed_and_is_logged(business, hub_double, monkeypatch, logged):
    breaks_for(monkeypatch, reconciliation, "sync_outcome", business.id)

    counts = reconciliation.reconcile()

    assert (counts["owed"], counts["refused"], counts["failed"]) == (1, 0, 0)
    assert f"hubs.sync.crashed hub={business.id}" in logged.messages


def test_a_pass_that_is_told_the_time_uses_it(business, hub_double):
    hub_push.sync_hub(business.id)
    hub_double.calls.clear()

    counts = reconciliation.reconcile(now=timezone.now() + LONG_AGO)

    assert counts["preparing"] == 1
