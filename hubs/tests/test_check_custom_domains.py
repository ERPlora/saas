"""``manage.py check_custom_domains``: the hourly pass that moves each domain between its states (HUBS-F17; ``aws`` README,
«Dominio propio de un negocio»; hub#812). Every transition has its row here:

    pending  → certificate requested → ISSUED → on the listener → CNAME → in the snapshot → probe → active
    active   → three failures in a row → lapsed (out of the snapshot, certificate gone), and the owner is told
    lapsed   → the CNAME is back → pending
    removing → certificate gone → the row is gone

AWS is botocore's Stubber, so a test that expects no call proves there was none; the DNS is ``dns_world`` and the probe
(its own tests are in ``test_domain_checks.py``) answers what ``probe_says`` says.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from live.errors import Conflict
from live.models import OutboxEvent

from hubs import domain_checks, events, queries, services
from hubs.domain_checks import Probe
from hubs.models import CustomDomain, Hub, Plan, Subscription
from hubs.schemas import CustomDomainRequestIn
from hubs.tests.conftest import DOMAIN, certificate_arn, create_business, ctx_for, pointing

pytestmark = pytest.mark.django_db

ARN = certificate_arn()
LOCK_KEY = "hashtext('erplora.saas.check_custom_domains')"
State = CustomDomain.State
Reason = CustomDomain.Reason


@pytest.fixture
def probe_says(monkeypatch):
    """What the probe answers, a list of its asks: ``answer`` to change it."""

    class Says:
        answer = Probe.SERVED
        asked: list = []

    says = Says()
    says.asked = []

    def probe(domain, target, hub_id):
        says.asked.append((domain, target, hub_id))
        return says.answer

    monkeypatch.setattr(domain_checks, "probe", probe)
    return says


@pytest.fixture
def world(custom_domains_on, hub_double, probe_says, dns_world):
    return custom_domains_on


def run_pass(world, *, attached=0):
    """One pass, with the metric it publishes at its end."""
    world.expect_metric(attached)
    counts = services.check_custom_domains()
    return counts


def row_of(hub):
    return CustomDomain.objects.get(hub=hub)


def hub_of(hub):
    return Hub.objects.get(pk=hub.pk)


def pending(hub, **fields):
    return CustomDomain.objects.create(hub=hub, hostname=DOMAIN, **fields)


def certificate_issued(hub, **fields):
    """A pending domain whose certificate is on its way to the listener."""
    return pending(hub, certificate_arn=ARN, validation_name="_a", validation_value="_b", **fields)


def attached(hub, **fields):
    return certificate_issued(hub, attached_at=timezone.now(), **fields)


def active(hub, **fields):
    now = timezone.now()
    row = attached(hub, state=State.ACTIVE, proven_at=now, activated_at=now, **fields)
    Hub.objects.filter(pk=hub.pk).update(pushed_state_version=hub_of(hub).state_version)
    return row


def state_pushes(hub_double):
    return hub_double.calls_to("PUT", "/state")


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

    services._check_custom_domain(row.id)

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

    services._check_custom_domain(row.id)

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
    """Why a validation CNAME left behind cannot hand the domain to whoever asks next (ADR-0502)."""
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
    attached_long_ago = timezone.now() - services.CUSTOM_DOMAIN_PENDING_LIMIT - timedelta(hours=1)
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
    recently = timezone.now() - services.CUSTOM_DOMAIN_PENDING_LIMIT + timedelta(hours=1)
    certificate_issued(standard_business, attached_at=recently)
    world.expect_describe("ISSUED")

    run_pass(world, attached=1)

    assert row_of(standard_business).state == State.PENDING


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
    assert queries.hub_snapshot(standard_business.id)["custom_domain"] == DOMAIN

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


def test_the_mail_goes_in_the_owners_language(standard_business, world, owner):
    assert owner.language == "es"
    active(standard_business, failures=2)
    world.expect_detach()
    world.expect_delete()

    run_pass(world)

    sent = mail.outbox[0]
    assert "dominio" in sent.subject.lower()
    assert standard_business.name in sent.body


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

    counts = run_pass(world)

    assert row_of(standard_business).state == State.REMOVING
    assert counts["certificates_in_use"] == 1


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


def test_while_a_removal_is_held_up_the_name_stays_taken(owner, standard_business, world, make_user):
    """Its row goes last: that is what frees the name, once the Hub and the ALB have let go (ADR-0496)."""
    removing(standard_business, certificate_arn=ARN, proven_at=timezone.now())
    other_owner = make_user("otra@example.com")
    other = create_business(other_owner, name="Otro")
    Subscription.objects.filter(hub=other).update(plan=Plan.objects.get(slug="standard"))

    with pytest.raises(Conflict) as refused:
        services.custom_domain_request(ctx_for(other_owner), CustomDomainRequestIn(id=other.id, domain=DOMAIN))

    assert refused.value.code == "hubs.custom_domain_taken"


# --- Between businesses -----------------------------------------------------------------------------


def second_business(make_user):
    other = create_business(make_user("otra@example.com"), name="Otro")
    Subscription.objects.filter(hub=other).update(plan=Plan.objects.get(slug="standard"))
    Hub.objects.filter(pk=other.pk).update(status=Hub.Status.ACTIVE, pending_hub_call="")
    return Hub.objects.get(pk=other.pk)


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

    services._check_custom_domain(other.id)

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

    services._check_custom_domain(row.id)

    row.refresh_from_db()
    assert row.state == State.REMOVING
    assert row.proven_at is None


def test_each_domain_is_recorded_on_its_owners_channel(standard_business, world):
    pending(standard_business, certificate_arn=ARN)
    world.expect_describe("PENDING_VALIDATION")

    run_pass(world)

    event = OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).latest("id")
    assert event.payload == {"business_id": str(standard_business.id)}


# --- The metric and the command ------------------------------------------------------------------------


def run_command(*args):
    out = StringIO()
    call_command("check_custom_domains", *args, stdout=out)
    return out.getvalue()


def test_the_metric_counts_the_certificates_on_the_listener(standard_business, world, make_user):
    other = second_business(make_user)
    CustomDomain.objects.create(hub=other, hostname="www.otro.es", state=State.REMOVING, certificate_arn=certificate_arn(2), attached_at=timezone.now())
    world.expect_detach(arn=certificate_arn(2))
    world.expect_delete(arn=certificate_arn(2))
    active(standard_business, failures=0)

    run_pass(world, attached=1)


def test_the_metric_says_zero_too(world):
    run_pass(world, attached=0)


def test_the_command_says_what_it_did_and_publishes(standard_business, world, dns_world):
    active(standard_business)
    pointing(dns_world, standard_business)
    world.expect_metric(1)

    out = run_command()

    assert "check_custom_domains:" in out
    assert "checked=1" in out


@pytest.mark.parametrize("variable", [False, None], ids=["false", "absent"])
def test_with_the_variable_off_the_command_looks_at_nothing(settings, aws_edge, dns_world, standard_business, variable):
    """A domain there from before stays as it is: no call, no DNS, no metric, no snapshot."""
    settings.CUSTOM_DOMAINS_ENABLED = bool(variable)
    now = timezone.now()
    CustomDomain.objects.create(hub=standard_business, hostname=DOMAIN, state=State.ACTIVE, failures=2, certificate_arn=ARN, attached_at=now, proven_at=now)
    dns_world[(DOMAIN, "CNAME")] = AssertionError("nobody looks at the DNS")
    version = hub_of(standard_business).state_version

    out = run_command()

    assert "nothing done" in out
    row = row_of(standard_business)
    assert (row.state, row.failures) == (State.ACTIVE, 2)
    assert hub_of(standard_business).state_version == version


def test_one_domain_that_breaks_never_stops_the_pass_and_the_run_ends_in_error(
    standard_business, world, dns_world, make_user, monkeypatch
):
    mine, theirs = standard_business, second_business(make_user)
    active(mine)
    now = timezone.now()
    CustomDomain.objects.create(hub=theirs, hostname="www.otro.es", state=State.ACTIVE, certificate_arn=certificate_arn(2), attached_at=now, proven_at=now, activated_at=now)
    pointing(dns_world, theirs, domain="www.otro.es")
    real = domain_checks.points_at

    def breaks_for_mine(domain, target):
        if domain == DOMAIN:
            raise RuntimeError("a bug")
        return real(domain, target)

    monkeypatch.setattr(domain_checks, "points_at", breaks_for_mine)
    world.expect_metric(2)

    with pytest.raises(CommandError, match="crashed=1"):
        run_command()

    assert row_of(theirs).checked_at is not None


def test_a_metric_that_cannot_be_published_ends_the_run_in_error_after_the_pass(standard_business, world, dns_world):
    active(standard_business)
    pointing(dns_world, standard_business)
    world.cloudwatch.add_client_error("put_metric_data", "AccessDenied", "no")

    with pytest.raises(CommandError, match="metric"):
        run_command()

    assert row_of(standard_business).checked_at is not None


def test_a_second_run_returns_at_once(world, other_session):
    other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")

    assert "already running" in run_command()


def test_aws_or_the_hub_being_away_is_no_error_of_the_run(standard_business, world):
    """They come back: the next pass tries again, and a failed task every hour of an AWS incident is not news."""
    pending(standard_business, certificate_arn=ARN)
    world.acm.add_client_error("describe_certificate", "ThrottlingException", "later")
    world.expect_metric(0)

    assert "aws_unavailable=1" in run_command()
