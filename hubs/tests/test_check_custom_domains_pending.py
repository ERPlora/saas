"""``manage.py check_custom_domains`` on a pending domain: what each pass counts it as, what it keeps of ACM's record, the
lines it logs and what it leaves untouched. Its way to active is in ``test_check_custom_domains.py``."""

import logging
import uuid
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from hubs.domain_checks import Probe
from hubs.models import CustomDomain, Hub
from hubs.queries import custom_domains
from hubs.tests.conftest import DOMAIN, certificate_arn, pointing
from hubs.tests.custom_domain_states import (
    ARN,
    Reason,
    State,
    active,
    attached,
    certificate_issued,
    hub_of,
    pending,
    row_of,
    run_pass,
    second_business,
    state_pushes,
)

pytestmark = pytest.mark.django_db

RECORD = (f"_abc.{DOMAIN}", "_def.acm-validations.aws")


@pytest.fixture
def logged(caplog):
    caplog.set_level(logging.INFO, logger="hubs.services.custom_domain_checks")
    return caplog


@pytest.fixture
def full_listener(settings, make_user):
    """Another business's lapsed domain counts as the only certificate the listener takes."""
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 1
    other = second_business(make_user)
    CustomDomain.objects.create(
        hub=other, hostname="www.otro.es", state=State.LAPSED, reason=Reason.VALIDATION_TIMED_OUT, attached_at=timezone.now()
    )


def record_of(hub):
    row = row_of(hub)
    return row.validation_name, row.validation_value


# --- What the pass counts it as -----------------------------------------------------------------------


def test_waiting_for_a_place_to_ask_for_its_certificate(standard_business, world, full_listener):
    pending(standard_business)

    assert run_pass(world, attached=1)["waiting"] == 1


def test_waiting_for_the_record_of_its_certificate(standard_business, world):
    pending(standard_business, certificate_arn=ARN)
    world.expect_describe("PENDING_VALIDATION")

    assert run_pass(world)["waiting"] == 1


def test_waiting_for_a_place_on_the_listener(standard_business, world, full_listener):
    certificate_issued(standard_business)
    world.expect_describe("ISSUED")

    assert run_pass(world, attached=1)["waiting"] == 1
    assert record_of(standard_business) == RECORD


def test_waiting_because_aws_has_no_place_left(standard_business, world, logged):
    certificate_issued(standard_business)
    world.expect_describe("ISSUED")
    world.alb.add_client_error("add_listener_certificates", "TooManyCertificates", "at the quota")

    assert run_pass(world)["waiting"] == 1
    assert record_of(standard_business) == RECORD
    assert logged.messages == [f"hubs.custom_domain.listener_full domain={DOMAIN}"]


def test_waiting_for_a_dns_that_cannot_answer(standard_business, world, dns_world, logged):
    attached(standard_business)
    dns_world[(DOMAIN, "CNAME")] = TimeoutError("SERVFAIL")
    world.expect_describe("ISSUED")

    assert run_pass(world, attached=1)["waiting"] == 1
    assert logged.messages == [f"hubs.custom_domain.dns domain={DOMAIN}: SERVFAIL"]


def test_waiting_for_its_cname(standard_business, world):
    attached(standard_business)
    world.expect_describe("ISSUED")

    assert run_pass(world, attached=1)["waiting"] == 1


def test_waiting_for_the_business_that_holds_the_name(standard_business, world, dns_world, make_user):
    active(second_business(make_user), failures=0)
    attached(standard_business)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")

    counts = run_pass(world, attached=2)

    assert (counts["waiting"], row_of(standard_business).reason) == (1, Reason.TAKEN)


def test_waiting_for_the_hub_to_hear(standard_business, world, dns_world, offline_hub):
    attached(standard_business)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")

    counts = run_pass(world, attached=1)

    assert (counts["hub_away"], row_of(standard_business).reason) == (1, Reason.PROBE_FAILED)


def test_waiting_for_the_probe(standard_business, world, dns_world, probe_says):
    attached(standard_business, proven_at=timezone.now(), reason=Reason.DNS_UNAVAILABLE)
    pointing(dns_world, standard_business)
    probe_says.answer = Probe.NOT_SERVED
    world.expect_describe("ISSUED")

    counts = run_pass(world, attached=1)

    assert (counts["waiting"], row_of(standard_business).reason) == (1, Reason.PROBE_FAILED)


def test_activated_with_its_count_of_failures_at_zero(standard_business, world, dns_world, logged):
    attached(standard_business, failures=2)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")

    counts = run_pass(world, attached=1)

    assert (counts["activated"], row_of(standard_business).failures) == (1, 0)
    assert logged.messages == [f"hubs.custom_domain.active domain={DOMAIN} hub={standard_business.id}"]


def test_acm_away_is_logged(standard_business, world, logged):
    pending(standard_business, certificate_arn=ARN)
    world.acm.add_client_error("describe_certificate", "ThrottlingException", "later")

    run_pass(world)

    (message,) = logged.messages
    assert message.startswith(f"hubs.custom_domain.aws domain={DOMAIN}: ThrottlingException")
    assert row_of(standard_business).reason == Reason.CERTIFICATE_UNAVAILABLE


# --- What it keeps ------------------------------------------------------------------------------------


def test_acm_without_its_record_yet_leaves_the_one_there_was(standard_business, world):
    certificate_issued(standard_business)
    world.expect_describe("PENDING_VALIDATION", record=False)

    run_pass(world)

    assert record_of(standard_business) == ("_a", "_b")


def test_the_certificate_that_goes_on_the_listener_keeps_its_record(standard_business, world):
    certificate_issued(standard_business)
    world.expect_describe("ISSUED")
    world.expect_attach()

    run_pass(world, attached=1)

    assert record_of(standard_business) == RECORD


def test_a_domain_proved_before_keeps_its_reason_until_the_hub_hears(standard_business, world, dns_world, offline_hub):
    attached(standard_business, proven_at=timezone.now(), reason=Reason.DNS_UNAVAILABLE)
    Hub.objects.filter(pk=standard_business.pk).update(state_version=hub_of(standard_business).state_version + 1)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    assert row_of(standard_business).reason == Reason.DNS_UNAVAILABLE


def test_a_domain_never_in_the_snapshot_sends_the_hub_nothing_while_its_cname_is_missing(standard_business, world, hub_double):
    attached(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(state_version=hub_of(standard_business).state_version + 1)
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    assert state_pushes(hub_double) == []


# --- What ends it -------------------------------------------------------------------------------------


def test_a_certificate_refused_is_logged_with_its_why(standard_business, world, logged):
    pending(standard_business, certificate_arn=ARN)
    world.expect_describe("FAILED", failure="CAA_ERROR")
    world.expect_delete()

    counts = run_pass(world)

    assert counts["lapsed"] == 1
    assert f"hubs.custom_domain.certificate domain={DOMAIN} FAILED CAA_ERROR" in logged.messages


def test_aws_away_while_a_refused_certificate_goes_leaves_it_for_the_next_pass(standard_business, world, logged):
    attached(standard_business)
    world.expect_describe("EXPIRED")
    world.alb.add_client_error("remove_listener_certificates", "AccessDenied", "no")

    counts = run_pass(world, attached=1)

    row = row_of(standard_business)
    assert (row.state, row.reason, row.certificate_arn) == (State.LAPSED, Reason.CERTIFICATE_FAILED, ARN)
    assert any(message.startswith(f"hubs.custom_domain.aws domain={DOMAIN}: AccessDenied") for message in logged.messages)
    # It left pending before AWS failed, so the pass finds it moved on.
    assert counts["moved_on"] == 1

    world.expect_detach()
    world.expect_delete()
    run_pass(world)
    assert row_of(standard_business).certificate_arn == ""


def test_a_domain_that_never_finished_gives_its_place_back_without_a_mail(standard_business, world):
    certificate_issued(standard_business, attached_at=timezone.now() - timedelta(days=15))
    world.expect_describe("ISSUED")
    world.expect_detach()
    world.expect_delete()

    counts = run_pass(world)

    assert counts["lapsed"] == 1
    assert mail.outbox == []


# --- What the pass finds ------------------------------------------------------------------------------


def test_a_domain_that_went_since_the_pass_listed_it_is_gone(standard_business, world, monkeypatch):
    monkeypatch.setattr(custom_domains, "custom_domain_ids", lambda: [uuid.uuid7()])

    counts = run_pass(world)

    assert (counts["gone"], counts["crashed"]) == (1, 0)


def test_aws_away_outside_the_way_to_active_is_counted_and_logged(standard_business, world, logged):
    pending(standard_business, state=State.REMOVING, certificate_arn=certificate_arn(), attached_at=timezone.now())
    world.alb.add_client_error("remove_listener_certificates", "AccessDenied", "no")

    counts = run_pass(world, attached=1)

    assert counts["aws_unavailable"] == 1
    (message,) = logged.messages
    assert message.startswith(f"hubs.custom_domain.aws domain={DOMAIN}: AccessDenied")
    assert row_of(standard_business).state == State.REMOVING
