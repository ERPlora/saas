"""``push_hub_snapshots`` (``saas-cron``, nightly at 00:30 UTC, run without flags by ``scheduler.tf``):
the safety net of PLAN-SAAS §2.2, every night for every business. By default it pushes the snapshot of
EVERY live business, each with a newer version (the Hub ignores an equal one), so a Hub that lost what
it had acknowledged is put right overnight. ``--behind-only`` pushes only the snapshots the Hub is
behind on. Under a Postgres advisory lock (a second run returns at once); a business that fails
stays owed, never stops the batch, and makes the run end with an error after the pass.

Review of L1-A, finding 3: the first version pushed only the businesses behind by default, so the
nightly run the infra schedules never re-sent an acknowledged snapshot.
"""

import pytest
from django.core.management.base import CommandError

from hubs import services
from hubs.models import Hub, HubMember
from hubs.tests.conftest import add_member, create_business
from hubs.tests.test_reconcile_hub_states import fresh, run

pytestmark = pytest.mark.django_db


def test_by_default_every_live_business_is_pushed_again(
    business, owner, hub_double, make_user
):
    services.sync_hub(business.id)
    deleted = create_business(make_user("lola@example.com"), name="Café Lola")
    Hub.objects.filter(pk=deleted.pk).update(
        status=Hub.Status.DELETING, pending_hub_call=""
    )
    version = fresh(business).state_version
    hub_double.calls.clear()

    output = run("push_hub_snapshots")

    (call,) = hub_double.calls_to("PUT", "/state")
    assert call.hub_id == str(business.id)
    assert call.body["version"] == version + 1 == fresh(business).pushed_state_version
    assert hub_double.versions[str(business.id)] == version + 1
    assert "pushed=1" in output


def test_every_night_the_hub_applies_it_again(business, hub_double):
    run("push_hub_snapshots")
    run("push_hub_snapshots")

    states = hub_double.calls_to("PUT", "/state")
    assert [call.body["version"] for call in states][-2:] == [2, 3]
    assert hub_double.versions[str(business.id)] == 3


def test_behind_only_pushes_what_the_hub_is_behind_on(business, team, hub_double):
    services.sync_hub(business.id)
    add_member(business, team["stranger"], HubMember.Role.EMPLOYEE)
    services.bump_state(business.id)
    hub_double.calls.clear()

    output = run("push_hub_snapshots", "--behind-only")

    (call,) = hub_double.calls_to("PUT", "/state")
    assert (
        call.body["version"]
        == fresh(business).state_version
        == fresh(business).pushed_state_version
    )
    assert "pushed=1" in output


def test_behind_only_a_second_run_does_nothing(business, hub_double):
    run("push_hub_snapshots", "--behind-only")
    sent = len(hub_double.calls)

    output = run("push_hub_snapshots", "--behind-only")

    assert len(hub_double.calls) == sent
    assert "pushed=0" in output


def test_a_deleted_business_gets_no_snapshot(business, hub_double):
    Hub.objects.filter(pk=business.pk).update(
        status=Hub.Status.DELETING, pending_hub_call="", state_version=4
    )

    run("push_hub_snapshots")

    assert hub_double.calls == []


def test_with_the_hub_away_the_pass_ends_and_the_run_fails(
    owner, plans, offline_hub, make_user
):
    """Review of L1-A, finding 4: the cron fails loudly (``task_failed`` alarm), after the whole pass."""
    first = create_business(owner)
    second = create_business(make_user("lola@example.com"), name="Café Lola")

    with pytest.raises(CommandError) as failed:
        run("push_hub_snapshots")

    assert "owed=2" in str(failed.value)
    assert (
        fresh(first).state_version == fresh(second).state_version == 2
    )  # both were tried


def test_a_second_run_returns_at_once_while_one_holds_the_lock(
    business, hub_double, other_session
):
    other_session.execute(
        "SELECT pg_advisory_lock(%s)", [services.lock_key("push_hub_snapshots")]
    )

    output = run("push_hub_snapshots")

    assert hub_double.calls == []
    assert "already running" in output
    other_session.execute(
        "SELECT pg_advisory_unlock(%s)", [services.lock_key("push_hub_snapshots")]
    )
