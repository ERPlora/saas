"""``manage.py check_custom_domains`` on an active domain: it stays while it still points here, and three failures
in a row take it down and tell the owner once."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from accounts.models import UserPreferences
from hubs import queries
from hubs.domain_checks import Probe
from hubs.models import HubMember
from hubs.tests.conftest import DOMAIN, pointing
from hubs.tests.custom_domain_states import (
    ARN,
    Reason,
    State,
    active,
    hub_of,
    row_of,
    run_pass,
    state_pushes,
)

pytestmark = pytest.mark.django_db


# --- active -----------------------------------------------------------------------------------------


def test_an_active_domain_that_still_points_here_stays_and_writes_no_snapshot(
    standard_business, world, dns_world, hub_double
):
    active(standard_business, failures=2)
    pointing(dns_world, standard_business)
    version = hub_of(standard_business).state_version

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.ACTIVE
    assert row.failures == 0
    assert row.checked_at is not None
    assert hub_of(standard_business).state_version == version
    assert state_pushes(hub_double) == []


def test_three_failures_in_a_row_take_it_down_and_tell_the_owner_once(standard_business, world, dns_world, hub_double):
    active(standard_business)

    run_pass(world, attached=1)
    assert (row_of(standard_business).state, row_of(standard_business).failures) == (State.ACTIVE, 1)
    assert queries.hub_sync.hub_snapshot(standard_business.id)["custom_domain"] == DOMAIN

    run_pass(world, attached=1)
    assert (row_of(standard_business).state, row_of(standard_business).failures) == (State.ACTIVE, 2)
    assert len(mail.outbox) == 0

    world.expect_detach()
    world.expect_delete()
    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.reason == Reason.CHECKS_FAILED
    assert row.proven_at is None
    assert row.attached_at is None and row.certificate_arn == ""
    assert row.failures == 0
    assert "custom_domain" not in state_pushes(hub_double)[-1].body
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["owner@example.com"]
    assert DOMAIN in mail.outbox[0].body

    run_pass(world)
    assert len(mail.outbox) == 1


def test_two_failures_then_a_pass_start_the_count_again(standard_business, world, dns_world):
    active(standard_business)
    run_pass(world, attached=1)
    run_pass(world, attached=1)
    assert row_of(standard_business).failures == 2

    pointing(dns_world, standard_business)
    run_pass(world, attached=1)
    assert row_of(standard_business).failures == 0

    del dns_world[(DOMAIN, "CNAME")]
    run_pass(world, attached=1)
    assert (row_of(standard_business).state, row_of(standard_business).failures) == (State.ACTIVE, 1)


def test_a_dns_that_cannot_answer_is_no_failure(standard_business, world, dns_world):
    active(standard_business, failures=2)
    dns_world[(DOMAIN, "CNAME")] = TimeoutError("SERVFAIL")

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert (row.state, row.failures) == (State.ACTIVE, 2)
    assert row.reason == Reason.DNS_UNAVAILABLE


def test_the_platform_failing_is_no_failure(standard_business, world, dns_world, probe_says):
    """Three hours of a Hub or an ALB away must not take every customer's domain with them."""
    active(standard_business, failures=2)
    pointing(dns_world, standard_business)
    probe_says.answer = Probe.UNREACHABLE

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert (row.state, row.failures) == (State.ACTIVE, 2)
    assert row.reason == Reason.PROBE_FAILED


def test_the_hub_not_serving_it_is_a_failure_and_owes_it_the_snapshot_again(
    standard_business, world, dns_world, probe_says, hub_double
):
    active(standard_business)
    pointing(dns_world, standard_business)
    probe_says.answer = Probe.NOT_SERVED
    version = hub_of(standard_business).state_version

    run_pass(world, attached=1)

    assert (row_of(standard_business).state, row_of(standard_business).failures) == (State.ACTIVE, 1)
    assert hub_of(standard_business).state_version == version + 1
    assert state_pushes(hub_double)[-1].body["custom_domain"] == DOMAIN


def test_a_cname_gone_is_a_failure_without_asking_the_probe(standard_business, world, probe_says):
    active(standard_business)
    run_pass(world, attached=1)
    assert row_of(standard_business).failures == 1
    assert probe_says.asked == []


def test_the_certificate_the_alb_has_not_let_go_of_is_deleted_by_the_next_pass(standard_business, world, dns_world):
    active(standard_business, failures=2)
    world.expect_detach()
    world.acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")

    counts = run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.certificate_arn == ARN
    assert row.attached_at is None
    assert counts["certificates_in_use"] == 1

    world.expect_delete()
    run_pass(world)

    assert row_of(standard_business).certificate_arn == ""


def test_taking_it_down_with_the_hub_away_leaves_the_certificate_until_the_hub_heard(
    standard_business, world, offline_hub, settings, hub_double
):
    settings.HUB_INTERNAL_URL = "http://127.0.0.1:9"
    active(standard_business, failures=2)

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.attached_at is not None and row.certificate_arn == ARN

    settings.HUB_INTERNAL_URL = hub_double.url
    world.expect_detach()
    world.expect_delete()
    run_pass(world)

    assert row_of(standard_business).certificate_arn == ""
    assert "custom_domain" not in state_pushes(hub_double)[-1].body


def test_a_mail_that_cannot_leave_does_not_undo_it(standard_business, world, monkeypatch):
    def fails(*args, **kwargs):
        raise OSError("no mail today")

    monkeypatch.setattr("hubs.emails.branded_message", fails)
    active(standard_business, failures=2)
    world.expect_detach()
    world.expect_delete()

    counts = run_pass(world)

    assert row_of(standard_business).state == State.LAPSED
    assert counts["crashed"] == 0


def test_the_mail_goes_to_the_owner_and_to_nobody_else_of_the_business(standard_business, world, make_user):
    long_ago = timezone.now() - timedelta(days=400)
    HubMember.objects.create(
        hub=standard_business, user=make_user("admin@example.com"), role=HubMember.Role.ADMIN, accepted_at=long_ago, joined_at=long_ago
    )
    active(standard_business, failures=2)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    assert [sent.to for sent in mail.outbox] == [["owner@example.com"]]


def test_an_owner_who_turned_the_business_notices_off_gets_no_mail_and_it_still_falls(standard_business, world, owner):
    UserPreferences.objects.create(user=owner, hub_alerts=False)
    active(standard_business, failures=2)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    assert mail.outbox == []
    assert row_of(standard_business).state == State.LAPSED


def test_the_mail_goes_in_the_owners_language(standard_business, world, owner):
    assert owner.language == "es"
    active(standard_business, failures=2)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    sent = mail.outbox[0]
    assert "dominio" in sent.subject.lower()
    assert standard_business.name in sent.body
