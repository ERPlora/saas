"""``manage.py check_custom_domains`` between businesses: two asking for one domain, an owner who changes it during
a pass, and the event on each owner's channel."""

import pytest
from django.utils import timezone
from live.models import OutboxEvent

from hubs import domain_checks, events, services
from hubs.models import CustomDomain
from hubs.tests.conftest import DOMAIN, certificate_arn, pointing
from hubs.tests.custom_domain_states import (
    ARN,
    Reason,
    State,
    active,
    attached,
    pending,
    row_of,
    run_pass,
    second_business,
)

pytestmark = pytest.mark.django_db


# --- Between businesses -----------------------------------------------------------------------------


def test_two_businesses_asking_for_one_domain_only_the_one_it_points_at_gets_it(
    standard_business, world, dns_world, make_user, hub_double
):
    mine, theirs = standard_business, second_business(make_user)
    attached(mine)
    CustomDomain.objects.create(hub=theirs, hostname=DOMAIN, certificate_arn=certificate_arn(2), attached_at=timezone.now(), validation_name="_a", validation_value="_b")
    pointing(dns_world, theirs)
    world.expect_describe("ISSUED")
    world.expect_describe("ISSUED", arn=certificate_arn(2))

    run_pass(world, attached=2)

    assert row_of(mine).state == State.PENDING
    assert row_of(mine).proven_at is None
    assert row_of(theirs).state == State.ACTIVE


def test_a_domain_that_moved_waits_for_the_one_that_held_it(standard_business, world, dns_world, make_user, hub_double):
    """The Hub serves nobody's while two name it, so the second proof waits for the first to fall (three hours at most)."""
    mine, theirs = standard_business, second_business(make_user)
    active(mine, failures=2)
    CustomDomain.objects.create(hub=theirs, hostname=DOMAIN, certificate_arn=certificate_arn(2), attached_at=timezone.now(), validation_name="_a", validation_value="_b")
    pointing(dns_world, theirs)
    world.expect_detach()
    world.expect_delete()
    world.expect_describe("ISSUED", arn=certificate_arn(2))

    counts = run_pass(world, attached=1)

    assert counts["crashed"] == 0
    assert row_of(mine).state == State.LAPSED
    assert row_of(theirs).state == State.ACTIVE


def test_a_second_proof_while_the_first_stands_says_it_is_taken(standard_business, world, dns_world, make_user, hub_double):
    mine, theirs = standard_business, second_business(make_user)
    active(mine)
    other = CustomDomain.objects.create(hub=theirs, hostname=DOMAIN, certificate_arn=certificate_arn(2), attached_at=timezone.now(), validation_name="_a", validation_value="_b")
    pointing(dns_world, theirs)
    world.expect_describe("ISSUED", arn=certificate_arn(2))

    services.custom_domain_checks._check_custom_domain(other.id)

    assert row_of(theirs).state == State.PENDING
    assert row_of(theirs).reason == Reason.TAKEN
    assert row_of(theirs).proven_at is None


def test_the_owner_removing_it_during_the_pass_wins(standard_business, world, dns_world, monkeypatch):
    """A pass read the row before the owner wrote: what it learned about a state that left is not written."""
    row = attached(standard_business)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")
    real = domain_checks.points_at

    def the_owner_removes_meanwhile(domain, target):
        CustomDomain.objects.filter(pk=row.pk).update(state=State.REMOVING)
        return real(domain, target)

    monkeypatch.setattr(domain_checks, "points_at", the_owner_removes_meanwhile)

    services.custom_domain_checks._check_custom_domain(row.id)

    row.refresh_from_db()
    assert row.state == State.REMOVING
    assert row.proven_at is None


def test_each_domain_is_recorded_on_its_owners_channel(standard_business, world):
    pending(standard_business, certificate_arn=ARN)
    world.expect_describe("PENDING_VALIDATION")

    run_pass(world)

    event = OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).latest("id")
    assert event.payload == {"business_id": str(standard_business.id)}


def test_a_pass_that_learns_nothing_new_wakes_nobody(standard_business, world, dns_world):
    """Every domain, every hour: an event only when what its owner sees changed, or every open page reads again for nothing."""
    active(standard_business)
    pointing(dns_world, standard_business)
    before = OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).count()

    run_pass(world, attached=1)

    assert OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).count() == before
