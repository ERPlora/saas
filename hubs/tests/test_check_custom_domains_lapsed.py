"""``manage.py check_custom_domains`` on a lapsed domain, and on who may keep one: a plan that includes it and a
business that is still there."""

import pytest
from django.core import mail

from hubs.models import CustomDomain, Hub, Plan, Subscription
from hubs.tests.conftest import DOMAIN, pointing
from hubs.tests.custom_domain_states import (
    ARN,
    Reason,
    State,
    active,
    hub_of,
    pending,
    row_of,
    run_pass,
    state_pushes,
)

pytestmark = pytest.mark.django_db


# --- lapsed -----------------------------------------------------------------------------------------


def lapsed(hub, reason=Reason.CHECKS_FAILED, **fields):
    return pending(hub, state=State.LAPSED, reason=reason, **fields)


def test_a_lapsed_domain_without_its_cname_asks_for_nothing(standard_business, world, hub_double):
    lapsed(standard_business)

    run_pass(world)

    assert row_of(standard_business).state == State.LAPSED
    assert state_pushes(hub_double) == []


def test_a_lapsed_domain_whose_cname_is_back_starts_again_with_a_new_token(standard_business, world, dns_world):
    old_token = lapsed(standard_business).certificate_token
    pointing(dns_world, standard_business)
    world.expect_request()
    world.expect_describe("PENDING_VALIDATION")

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.PENDING
    assert row.reason == Reason.CERTIFICATE_PENDING
    assert row.certificate_arn == ARN
    assert row.certificate_token != old_token


def test_it_comes_back_active_when_acm_issues_at_once(standard_business, world, dns_world, hub_double):
    """The validation CNAME stays for good, so ACM issues the new one by itself."""
    lapsed(standard_business)
    pointing(dns_world, standard_business)
    world.expect_request()
    world.expect_describe("ISSUED")
    world.expect_attach()

    run_pass(world, attached=1)

    assert row_of(standard_business).state == State.ACTIVE
    assert state_pushes(hub_double)[-1].body["custom_domain"] == DOMAIN


@pytest.mark.parametrize("reason", [Reason.VALIDATION_TIMED_OUT, Reason.CERTIFICATE_FAILED])
def test_a_certificate_that_was_refused_is_not_asked_for_again_by_itself(standard_business, world, dns_world, reason):
    """Its owner asks again once the record is there: every hour, one CAA would spend ACM's yearly certificates."""
    lapsed(standard_business, reason=reason)
    pointing(dns_world, standard_business)

    run_pass(world)

    row = row_of(standard_business)
    assert (row.state, row.reason) == (State.LAPSED, reason)


def test_a_dns_that_cannot_answer_leaves_a_lapsed_domain_as_it_was(standard_business, world, dns_world):
    lapsed(standard_business)
    dns_world[(DOMAIN, "CNAME")] = TimeoutError("SERVFAIL")

    run_pass(world)

    assert row_of(standard_business).state == State.LAPSED
    assert row_of(standard_business).reason == Reason.CHECKS_FAILED


# --- Who may keep one ------------------------------------------------------------------------------


def on_free(hub):
    Subscription.objects.filter(hub=hub).update(plan=Plan.objects.get(slug="free"))


def test_a_plan_that_stopped_including_it_takes_it_down_quietly(standard_business, world, dns_world, hub_double):
    """Its snapshot lost the key with the change of plan; the place on the listener goes back here."""
    active(standard_business)
    pointing(dns_world, standard_business)
    on_free(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(state_version=hub_of(standard_business).state_version + 1)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.reason == Reason.NOT_IN_PLAN
    assert row.proven_at is None
    assert len(mail.outbox) == 0
    assert "custom_domain" not in state_pushes(hub_double)[-1].body


def test_a_pending_domain_without_a_plan_asks_for_nothing(standard_business, world, dns_world):
    pending(standard_business)
    on_free(standard_business)

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.reason == Reason.NOT_IN_PLAN


def test_with_no_plan_at_all_nothing_includes_a_domain(standard_business, world, dns_world):
    pending(standard_business)
    Subscription.objects.filter(hub=standard_business).delete()
    Plan.objects.filter(slug="free").delete()

    counts = run_pass(world)

    assert counts["crashed"] == 0
    assert row_of(standard_business).reason == Reason.NOT_IN_PLAN


def test_the_plan_back_and_the_cname_there_bring_it_back(standard_business, world, dns_world):
    lapsed(standard_business, reason=Reason.NOT_IN_PLAN)
    pointing(dns_world, standard_business)
    world.expect_request()
    world.expect_describe("PENDING_VALIDATION")

    run_pass(world)

    assert row_of(standard_business).state == State.PENDING


def test_without_the_plan_a_lapsed_domain_stays_lapsed(standard_business, world, dns_world):
    lapsed(standard_business, reason=Reason.NOT_IN_PLAN)
    pointing(dns_world, standard_business)
    on_free(standard_business)

    run_pass(world)

    assert row_of(standard_business).state == State.LAPSED


def test_a_deleted_business_gives_its_domain_up(standard_business, world, hub_double):
    active(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(status=Hub.Status.DELETING)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.reason == Reason.BUSINESS_GONE
    assert row.certificate_arn == ""
    assert len(mail.outbox) == 0


def test_a_purged_business_leaves_nothing_behind(standard_business, world):
    active(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(status=Hub.Status.DELETED)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    assert not CustomDomain.objects.exists()


def test_a_suspended_business_keeps_its_domain(standard_business, world, dns_world):
    """The Hub answers its probe and shows nothing on the page; paying brings it back at once."""
    active(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(status=Hub.Status.SUSPENDED)
    pointing(dns_world, standard_business)

    run_pass(world, attached=1)

    assert row_of(standard_business).state == State.ACTIVE
