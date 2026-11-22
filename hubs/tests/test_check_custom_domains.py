"""``manage.py check_custom_domains``: the hourly pass that moves each domain between its states (HUBS-F17; ``aws``
README, «Dominio propio de un negocio»). Every transition has its row here or in a sibling
``test_check_custom_domains_<topic>.py``:

    pending  → certificate requested → ISSUED → on the listener → CNAME → in the snapshot → probe → active
    active   → three failures in a row → lapsed (out of the snapshot, certificate gone), and the owner is told
    lapsed   → the CNAME is back → pending
    removing → certificate gone → the row is gone

AWS is botocore's Stubber, so a test that expects no call proves there was none; the DNS is ``dns_world`` and the probe
(its own tests are in ``test_domain_checks.py``) answers what ``probe_says`` says.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from hubs import services
from hubs.domain_checks import Probe
from hubs.models import CustomDomain
from hubs.tests.conftest import DOMAIN, certificate_arn, create_business, pointing
from hubs.tests.custom_domain_states import (
    ARN,
    Reason,
    State,
    attached,
    certificate_issued,
    hub_of,
    pending,
    row_of,
    run_pass,
    state_pushes,
)

pytestmark = pytest.mark.django_db


# --- pending -----------------------------------------------------------------------------------------


def test_pending_without_a_certificate_asks_for_it(standard_business, world):
    row = pending(standard_business)
    world.expect_request(token=row.certificate_token)
    world.expect_describe()

    run_pass(world)

    row = row_of(standard_business)
    assert row.certificate_arn == ARN
    assert row.state == State.PENDING
    assert row.reason == Reason.CERTIFICATE_PENDING
    assert row.checked_at is not None


def test_pending_at_the_quota_asks_for_no_certificate(standard_business, world, settings, make_user):
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 1
    other = create_business(make_user("otra@example.com"), name="Otro")
    CustomDomain.objects.create(
        hub=other,
        hostname="www.otro.es",
        state=State.LAPSED,
        certificate_arn=certificate_arn(9),
        attached_at=timezone.now(),
    )
    row = pending(standard_business)

    services.custom_domain_checks._check_custom_domain(row.id)

    row.refresh_from_db()
    assert row.certificate_arn == ""
    assert row.reason == Reason.QUOTA_FULL


def test_a_certificate_waiting_for_its_record_only_keeps_the_record(standard_business, world):
    pending(standard_business, certificate_arn=ARN)
    world.expect_describe("PENDING_VALIDATION")

    run_pass(world)

    row = row_of(standard_business)
    assert (row.validation_name, row.validation_value) == (f"_abc.{DOMAIN}", "_def.acm-validations.aws")
    assert row.reason == Reason.CERTIFICATE_PENDING
    assert row.attached_at is None
    assert row.proven_at is None


def test_an_issued_certificate_goes_on_the_listener_and_waits_for_the_cname(standard_business, world, hub_double):
    certificate_issued(standard_business)
    world.expect_describe("ISSUED")
    world.expect_attach()

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.attached_at is not None
    assert row.proven_at is None
    assert row.reason == Reason.CNAME_MISSING
    assert state_pushes(hub_double) == []


def test_an_issued_certificate_at_the_quota_stays_off_the_listener(standard_business, world, settings, make_user):
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 1
    other = create_business(make_user("otra@example.com"), name="Otro")
    CustomDomain.objects.create(hub=other, hostname="www.otro.es", state=State.LAPSED, reason=Reason.VALIDATION_TIMED_OUT, certificate_arn=certificate_arn(9), attached_at=timezone.now())
    row = certificate_issued(standard_business)
    world.expect_describe("ISSUED")

    services.custom_domain_checks._check_custom_domain(row.id)

    row.refresh_from_db()
    assert row.attached_at is None
    assert row.reason == Reason.QUOTA_FULL


def test_too_many_certificates_from_aws_is_the_same_and_tries_again(standard_business, world):
    """The real limit, with a certificate put there by hand: what is active does not notice."""
    certificate_issued(standard_business)
    world.expect_describe("ISSUED")
    world.alb.add_client_error("add_listener_certificates", "TooManyCertificates", "at the quota")

    run_pass(world)

    row = row_of(standard_business)
    assert row.attached_at is None
    assert row.reason == Reason.QUOTA_FULL

    world.expect_describe("ISSUED")
    world.expect_attach()
    run_pass(world, attached=1)
    assert row_of(standard_business).attached_at is not None


def test_aws_failing_on_the_listener_leaves_it_for_the_next_pass(standard_business, world):
    certificate_issued(standard_business)
    world.expect_describe("ISSUED")
    world.alb.add_client_error("add_listener_certificates", "AccessDenied", "no")

    counts = run_pass(world)

    row = row_of(standard_business)
    assert row.attached_at is None
    assert row.reason == Reason.CERTIFICATE_UNAVAILABLE
    assert counts["aws_unavailable"] == 1


def test_a_cname_onto_this_business_puts_it_in_the_snapshot_and_the_probe_activates_it(
    standard_business, world, dns_world, hub_double, probe_says
):
    attached(standard_business)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")
    version = hub_of(standard_business).state_version

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.ACTIVE
    assert row.proven_at is not None and row.activated_at is not None
    assert row.reason == ""
    assert row.failures == 0
    pushed = state_pushes(hub_double)[-1].body
    assert pushed["custom_domain"] == DOMAIN
    assert pushed["version"] == version + 1
    assert probe_says.asked == [(DOMAIN, f"hub-{standard_business.id}.erplora.com", standard_business.id)]


def test_the_whole_way_from_pending_to_active_in_one_pass(standard_business, world, dns_world, hub_double):
    row = pending(standard_business)
    pointing(dns_world, standard_business)
    world.expect_request(token=row.certificate_token)
    world.expect_describe("ISSUED")
    world.expect_attach()

    run_pass(world, attached=1)

    assert row_of(standard_business).state == State.ACTIVE


@pytest.mark.parametrize(
    "record",
    ["otro-negocio.erplora.com", "hub-00000000-0000-7000-8000-000000000000.erplora.com"],
    ids=["its slug or anything else", "another business's name"],
)
def test_a_cname_onto_another_name_proves_nothing(standard_business, world, dns_world, hub_double, probe_says, record):
    """Why a validation CNAME left behind cannot hand the domain to whoever asks next."""
    attached(standard_business)
    dns_world[(DOMAIN, "CNAME")] = [record]
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.PENDING
    assert row.proven_at is None
    assert row.reason == Reason.CNAME_MISSING
    assert state_pushes(hub_double) == []
    assert probe_says.asked == []


def test_a_pending_domain_whose_cname_went_leaves_the_snapshot(standard_business, world, dns_world, hub_double):
    attached(standard_business, proven_at=timezone.now(), reason=Reason.PROBE_FAILED)
    world.expect_describe("ISSUED")
    version = hub_of(standard_business).state_version

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.proven_at is None
    assert row.reason == Reason.CNAME_MISSING
    assert hub_of(standard_business).state_version == version + 1
    assert "custom_domain" not in state_pushes(hub_double)[-1].body


def test_a_dns_that_cannot_answer_leaves_a_pending_domain_as_it_was(standard_business, world, dns_world, hub_double):
    attached(standard_business)
    dns_world[(DOMAIN, "CNAME")] = TimeoutError("SERVFAIL")
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.PENDING
    assert row.reason == Reason.DNS_UNAVAILABLE
    assert state_pushes(hub_double) == []


@pytest.mark.parametrize("answer", [Probe.NOT_SERVED, Probe.UNREACHABLE])
def test_a_probe_that_fails_keeps_it_pending_and_tries_again_without_a_new_version(
    standard_business, world, dns_world, hub_double, probe_says, answer
):
    """The Hub reads what it knows every 30 s: its 400 is «not yet», and the snapshot it got stands."""
    attached(standard_business)
    pointing(dns_world, standard_business)
    probe_says.answer = answer
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.PENDING
    assert row.reason == Reason.PROBE_FAILED
    assert row.proven_at is not None
    version = hub_of(standard_business).state_version

    probe_says.answer = Probe.SERVED
    world.expect_describe("ISSUED")
    run_pass(world, attached=1)

    assert row_of(standard_business).state == State.ACTIVE
    assert hub_of(standard_business).state_version == version
    assert len(state_pushes(hub_double)) == 1


def test_with_the_hub_away_the_probe_waits_for_the_snapshot(standard_business, world, dns_world, offline_hub, probe_says):
    attached(standard_business)
    pointing(dns_world, standard_business)
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    row = row_of(standard_business)
    assert row.state == State.PENDING
    assert row.proven_at is not None
    assert probe_says.asked == []


@pytest.mark.parametrize(
    ("status", "failure", "reason"),
    [
        ("VALIDATION_TIMED_OUT", None, Reason.VALIDATION_TIMED_OUT),
        ("FAILED", "CAA_ERROR", Reason.CERTIFICATE_FAILED),
        ("EXPIRED", None, Reason.CERTIFICATE_FAILED),
        ("REVOKED", None, Reason.CERTIFICATE_FAILED),
        ("INACTIVE", None, Reason.CERTIFICATE_FAILED),
    ],
)
def test_a_certificate_that_will_never_issue_lapses_and_is_deleted(standard_business, world, status, failure, reason):
    pending(standard_business, certificate_arn=ARN)
    world.expect_describe(status, failure=failure)
    world.expect_delete()

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.reason == reason
    assert row.certificate_arn == ""
    assert len(mail.outbox) == 0


def test_a_certificate_on_the_listener_that_stops_being_valid_is_taken_off_too(standard_business, world):
    attached(standard_business)
    world.expect_describe("EXPIRED")
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.attached_at is None and row.certificate_arn == ""


def test_acm_away_leaves_a_pending_domain_as_it_was(standard_business, world):
    pending(standard_business, certificate_arn=ARN)
    world.acm.add_client_error("describe_certificate", "ThrottlingException", "later")

    counts = run_pass(world)

    assert row_of(standard_business).state == State.PENDING
    assert counts["aws_unavailable"] == 1


def test_a_certificate_on_the_listener_with_no_cname_for_too_long_gives_its_place_back(standard_business, world):
    """24 places shared by every business: one that never finished does not keep one for ever."""
    attached_long_ago = timezone.now() - timedelta(days=14, hours=1)
    certificate_issued(standard_business, attached_at=attached_long_ago)
    world.expect_describe("ISSUED")
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    row = row_of(standard_business)
    assert row.state == State.LAPSED
    assert row.reason == Reason.CNAME_MISSING
    assert row.attached_at is None and row.certificate_arn == ""


def test_just_before_the_limit_it_keeps_its_place(standard_business, world):
    recently = timezone.now() - timedelta(days=13, hours=23)
    certificate_issued(standard_business, attached_at=recently)
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    assert row_of(standard_business).state == State.PENDING
