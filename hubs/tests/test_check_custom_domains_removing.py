"""``manage.py check_custom_domains`` on a domain being removed: its certificate goes first and its row last, which
is what frees the name."""

import pytest
from django.utils import timezone
from live.errors import Conflict

from hubs import edge_client, services
from hubs.models import CustomDomain, Hub, Plan, Subscription
from hubs.schemas.custom_domains import CustomDomainRequestIn
from hubs.tests.conftest import DOMAIN, create_business, ctx_for
from hubs.tests.custom_domain_states import (
    ARN,
    State,
    certificate_issued,
    pending,
    row_of,
    run_pass,
)

pytestmark = pytest.mark.django_db


# --- removing -------------------------------------------------------------------------------------


def removing(hub, **fields):
    return pending(hub, state=State.REMOVING, **fields)


def test_a_removal_the_alb_was_holding_up_ends_with_the_next_pass(standard_business, world):
    removing(standard_business, certificate_arn=ARN, proven_at=timezone.now())
    world.expect_delete()

    run_pass(world)

    assert not CustomDomain.objects.exists()


def test_a_removal_still_held_up_keeps_its_row(standard_business, world):
    removing(standard_business, certificate_arn=ARN, proven_at=timezone.now())
    world.acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")
    world.expect_detach()

    counts = run_pass(world)

    assert row_of(standard_business).state == State.REMOVING
    assert counts["certificates_in_use"] == 1


def test_a_certificate_attached_by_a_pass_that_lost_to_its_owner_is_still_taken_off(standard_business, world, monkeypatch):
    """The pass attaches, the owner removes before it writes so, and nothing records it is on the listener. Only trying to
    delete it tells: without taking it off, the row stays «being removed» for ever and its place is lost to the count."""
    row = certificate_issued(standard_business)
    world.expect_describe("ISSUED")
    world.expect_attach()
    real_attach = edge_client.attach

    def the_owner_removes_meanwhile(arn):
        real_attach(arn)
        CustomDomain.objects.filter(pk=row.pk).update(state=State.REMOVING)

    monkeypatch.setattr(edge_client, "attach", the_owner_removes_meanwhile)
    assert services.custom_domain_checks._check_custom_domain(row.id) == "moved_on"
    row.refresh_from_db()
    assert (row.state, row.attached_at) == (State.REMOVING, None)

    world.acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")
    world.expect_detach()
    assert services.custom_domain_checks._check_custom_domain(row.id) == "certificates_in_use"
    world.alb.assert_no_pending_responses()

    world.expect_delete()
    assert services.custom_domain_checks._check_custom_domain(row.id) == "removed"
    assert not CustomDomain.objects.exists()


def test_a_removal_takes_a_certificate_still_on_the_listener_off_it_first(standard_business, world):
    removing(standard_business, certificate_arn=ARN, attached_at=timezone.now())
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    assert not CustomDomain.objects.exists()


def test_a_removal_with_nothing_on_aws_only_goes(standard_business, world):
    removing(standard_business)

    run_pass(world)

    assert not CustomDomain.objects.exists()


@pytest.mark.parametrize("status", [Hub.Status.DELETING, Hub.Status.DELETED])
def test_a_removal_goes_on_though_its_business_was_deleted(standard_business, world, status):
    removing(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(status=status)

    counts = run_pass(world)

    assert counts["removed"] == 1
    assert not CustomDomain.objects.exists()


def test_while_a_removal_is_held_up_the_name_stays_taken(owner, standard_business, world, make_user):
    """Its row goes last: that is what frees the name, once the Hub and the ALB have let go."""
    removing(standard_business, certificate_arn=ARN, proven_at=timezone.now())
    other_owner = make_user("otra@example.com")
    other = create_business(other_owner, name="Otro")
    Subscription.objects.filter(hub=other).update(plan=Plan.objects.get(slug="standard"))

    with pytest.raises(Conflict) as refused:
        services.custom_domain_requests.custom_domain_request(ctx_for(other_owner), CustomDomainRequestIn(id=other.id, domain=DOMAIN))

    assert refused.value.code == "hubs.custom_domain_taken"
