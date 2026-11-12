"""A business's own domain, its operations and its snapshot (HUBS-F17; ``aws`` README, «Dominio propio de un
negocio»). The hourly check that moves a domain between its states is ``test_check_custom_domains.py``.

AWS is botocore's Stubber (``hubs/tests/conftest.py``): a call the test did not expect fails, so a test that expects none
proves nothing reached AWS.
"""

import json
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.live_registry import live_registry
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import AI, INTERNAL, registry

from hubs import domain_checks, events, queries, services
from hubs.models import CustomDomain, Hub, HubMember, Plan, Subscription
from hubs.schemas import ByIdIn, CustomDomainRequestIn
from hubs.tests.conftest import DOMAIN, add_member, certificate_arn, create_business, ctx_for

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def ask(user, hub, domain=DOMAIN):
    return services.custom_domain_request(ctx_for(user), CustomDomainRequestIn(id=hub.id, domain=domain))


def row_of(hub):
    return CustomDomain.objects.get(hub=hub)


def make_row(hub, *, hostname=DOMAIN, state=CustomDomain.State.PENDING, **fields):
    return CustomDomain.objects.create(hub=hub, hostname=hostname, state=state, **fields)


def active_row(hub, **fields):
    now = timezone.now()
    return make_row(
        hub,
        state=CustomDomain.State.ACTIVE,
        certificate_arn=certificate_arn(),
        attached_at=now,
        proven_at=now,
        activated_at=now,
        **fields,
    )


# --- hubs.custom_domain.request -------------------------------------------------------------------------


def test_asking_for_a_domain_returns_the_two_records_to_create(owner, standard_business, custom_domains_on):
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    answer = ask(owner, standard_business)

    assert answer.domain == DOMAIN
    assert answer.state == "pending"
    assert (answer.validation.type, answer.validation.name, answer.validation.value) == (
        "CNAME",
        f"_abc.{DOMAIN}",
        "_def.acm-validations.aws",
    )
    assert (answer.traffic.type, answer.traffic.name, answer.traffic.value) == (
        "CNAME",
        DOMAIN,
        f"hub-{standard_business.id}.erplora.com",
    )
    row = row_of(standard_business)
    assert row.certificate_arn == certificate_arn()
    assert (row.validation_name, row.validation_value) == (f"_abc.{DOMAIN}", "_def.acm-validations.aws")
    assert row.proven_at is None and row.attached_at is None


def test_the_domain_goes_to_acm_in_lowercase_and_its_token_is_the_rows(owner, standard_business, custom_domains_on):
    """IAM's Deny on our own names is case sensitive; the token keeps one certificate for an hour if anything fails."""
    custom_domains_on.expect_request(domain=DOMAIN)
    custom_domains_on.expect_describe()

    ask(owner, standard_business, domain="  WWW.MiNegocio.ES. ")

    row = row_of(standard_business)
    assert row.hostname == DOMAIN
    assert len(row.certificate_token) == 32 and row.certificate_token.isalnum()


def test_a_renamed_business_keeps_the_name_its_cname_points_at(owner, standard_business, settings):
    """By its id, which is never taken again; a slug can be, and a CNAME left behind would prove it for a stranger."""
    settings.CUSTOM_DOMAINS_TARGET_TEMPLATE = "hub-{hub_id}.erplora.com"
    make_row(standard_business, validation_name="_a", validation_value="_b")
    before = queries.custom_domain_get(ctx_for(owner), ByIdIn(id=standard_business.id)).domain.traffic.value

    Hub.objects.filter(pk=standard_business.pk).update(slug="otra-direccion")

    assert queries.custom_domain_get(ctx_for(owner), ByIdIn(id=standard_business.id)).domain.traffic.value == before


def test_asking_takes_the_row_of_the_business_so_two_requests_never_interleave(owner, standard_business, custom_domains_on):
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    with CaptureQueriesContext(connection) as seen:
        ask(owner, standard_business)

    assert any('FROM "hubs_hub"' in query["sql"] and "FOR UPDATE" in query["sql"] for query in seen.captured_queries)


def test_a_token_is_never_shared_between_two_rows(owner, standard_business, make_user, plans):
    first = make_row(standard_business, hostname="www.uno.es")
    other = create_business(make_user("otra@example.com"), name="Otro")
    second = make_row(other, hostname="www.dos.es")
    assert first.certificate_token and first.certificate_token != second.certificate_token


def test_an_international_domain_goes_to_acm_in_its_ascii_form(owner, standard_business, custom_domains_on):
    custom_domains_on.expect_request(domain="www.xn--peluquera-n5a.es")
    custom_domains_on.expect_describe(domain="www.xn--peluquera-n5a.es")

    answer = ask(owner, standard_business, domain="www.peluquería.es")

    assert answer.domain == "www.xn--peluquera-n5a.es"


def test_the_validation_record_can_arrive_after_the_answer(owner, standard_business, custom_domains_on):
    """ACM takes some seconds: the wait is bounded, the row keeps the certificate and the record comes with the next read."""
    custom_domains_on.expect_request()
    for _ in range(services.VALIDATION_RECORD_TRIES):
        custom_domains_on.expect_describe(record=False)

    answer = ask(owner, standard_business)

    assert answer.validation is None
    assert answer.traffic.value == f"hub-{standard_business.id}.erplora.com"
    assert row_of(standard_business).certificate_arn == certificate_arn()


def test_the_record_that_arrives_during_the_wait_is_in_the_answer(owner, standard_business, custom_domains_on):
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe(record=False)
    custom_domains_on.expect_describe()

    answer = ask(owner, standard_business)

    assert answer.validation.name == f"_abc.{DOMAIN}"


@pytest.mark.parametrize(
    ("typed", "code"),
    [
        ("https://www.minegocio.es", "hubs.custom_domain_invalid"),
        ("www.minegocio.es:8443", "hubs.custom_domain_invalid"),
        ("*.minegocio.es", "hubs.custom_domain_invalid"),
        ("192.168.1.10", "hubs.custom_domain_invalid"),
        ("minegocio", "hubs.custom_domain_invalid"),
        ("erplora.com", "hubs.custom_domain_ours"),
        ("www.erplora.com", "hubs.custom_domain_ours"),
        ("HUB.ERPLORA.INTERNAL", "hubs.custom_domain_ours"),
    ],
)
def test_a_name_the_hub_would_refuse_never_reaches_aws_nor_a_row(owner, standard_business, custom_domains_on, typed, code):
    with pytest.raises(InvalidPayload) as refused:
        ask(owner, standard_business, domain=typed)

    assert refused.value.code == code
    assert set(refused.value.fields) == {"domain"}
    assert not CustomDomain.objects.exists()


@pytest.mark.parametrize(
    ("zone", "code"),
    [(domain_checks.Zone.APEX, "hubs.custom_domain_apex"), (domain_checks.Zone.UNREGISTERED, "hubs.custom_domain_unregistered")],
)
def test_a_root_domain_and_an_unregistered_one_are_refused_with_their_reason(
    owner, standard_business, custom_domains_on, monkeypatch, zone, code
):
    monkeypatch.setattr(domain_checks, "zone_of", lambda domain: zone)

    with pytest.raises(InvalidPayload) as refused:
        ask(owner, standard_business)

    assert refused.value.code == code
    assert not CustomDomain.objects.exists()


def test_a_dns_that_cannot_answer_does_not_refuse_the_domain(owner, standard_business, custom_domains_on, monkeypatch):
    """It cannot be told apart now, and a root domain cannot prove itself later with no CNAME: nothing is promised."""

    def unavailable(domain):
        raise domain_checks.DnsUnavailable("SERVFAIL")

    monkeypatch.setattr(domain_checks, "zone_of", unavailable)
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    assert ask(owner, standard_business).state == "pending"


def test_a_plan_that_does_not_include_it_refuses_without_a_row_nor_a_call(owner, business, custom_domains_on):
    assert not business.subscription.plan.includes_custom_domain

    with pytest.raises(Conflict) as refused:
        ask(owner, business)

    assert refused.value.code == "hubs.custom_domain_not_in_plan"
    assert not CustomDomain.objects.exists()


def test_a_trial_of_a_plan_that_includes_it_opens_it(owner, business, custom_domains_on):
    Subscription.objects.filter(hub=business).update(
        trial_plan=Plan.objects.get(slug="standard"), trial_end=timezone.now() + timedelta(days=5)
    )
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    assert ask(owner, business).state == "pending"


@pytest.mark.parametrize("variable", [False, None], ids=["false", "absent"])
def test_with_the_variable_off_asking_does_nothing(owner, standard_business, settings, aws_edge, variable):
    settings.CUSTOM_DOMAINS_ENABLED = bool(variable)

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business)

    assert refused.value.code == "hubs.custom_domains_off"
    assert not CustomDomain.objects.exists()


def test_only_the_owner_asks(standard_business, make_user, custom_domains_on):
    admin = make_user("admin@example.com")
    add_member(standard_business, admin, HubMember.Role.ADMIN)

    with pytest.raises(PermissionDenied):
        ask(admin, standard_business)
    assert not CustomDomain.objects.exists()


def test_somebody_outside_the_business_does_not_learn_it_exists(standard_business, make_user, custom_domains_on):
    with pytest.raises(NotFound):
        ask(make_user("stranger@example.com"), standard_business)


def test_a_deleted_business_asks_for_nothing(owner, standard_business, custom_domains_on):
    Hub.objects.filter(pk=standard_business.pk).update(status=Hub.Status.DELETING)

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business)

    assert refused.value.code == "hubs.business_deleted"


def test_at_the_quota_it_asks_for_no_certificate_and_says_why(owner, standard_business, custom_domains_on, settings, make_user):
    """«En MAX el SaaS no pide el certificado»: the domain waits, and the next check tries again."""
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 1
    other = create_business(make_user("otra@example.com"), name="Otro")
    make_row(other, hostname="www.otro.es", certificate_arn=certificate_arn(9), attached_at=timezone.now())

    answer = ask(owner, standard_business)

    assert answer.state == "pending"
    assert answer.reason == "quota_full"
    assert answer.validation is None
    assert answer.traffic.value == f"hub-{standard_business.id}.erplora.com"
    assert row_of(standard_business).certificate_arn == ""


def test_a_certificate_attached_to_a_lapsing_row_still_counts_for_the_quota(owner, standard_business, custom_domains_on, settings, make_user):
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 1
    other = create_business(make_user("otra@example.com"), name="Otro")
    make_row(other, hostname="www.otro.es", state=CustomDomain.State.LAPSED, certificate_arn=certificate_arn(9), attached_at=timezone.now())

    assert ask(owner, standard_business).reason == "quota_full"


def test_a_certificate_requested_but_not_attached_does_not_count_for_the_quota(owner, standard_business, custom_domains_on, settings, make_user):
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 1
    other = create_business(make_user("otra@example.com"), name="Otro")
    make_row(other, hostname="www.otro.es", certificate_arn=certificate_arn(9))
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    assert ask(owner, standard_business).reason != "quota_full"


def test_aws_refusing_the_certificate_leaves_the_domain_to_the_next_check(owner, standard_business, custom_domains_on):
    custom_domains_on.acm.add_client_error("request_certificate", "AccessDeniedException", "no")

    answer = ask(owner, standard_business)

    assert answer.reason == "certificate_unavailable"
    row = row_of(standard_business)
    assert row.certificate_arn == "" and row.certificate_token


def test_asking_again_for_the_same_domain_asks_aws_for_nothing(owner, standard_business, custom_domains_on):
    make_row(standard_business, certificate_arn=certificate_arn(), validation_name="_a.www", validation_value="_b.aws")

    answer = ask(owner, standard_business, domain="WWW.minegocio.es")

    assert answer.domain == DOMAIN
    assert CustomDomain.objects.count() == 1


def test_asking_for_another_domain_needs_the_first_one_gone(owner, standard_business, custom_domains_on):
    make_row(standard_business)

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business, domain="www.otro.es")

    assert refused.value.code == "hubs.custom_domain_exists"


def test_a_domain_on_its_way_out_cannot_be_asked_for_until_it_left(owner, standard_business, custom_domains_on):
    make_row(standard_business, state=CustomDomain.State.REMOVING, certificate_arn=certificate_arn())

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business)

    assert refused.value.code == "hubs.custom_domain_exists"


def test_a_domain_another_business_proved_is_refused(owner, standard_business, custom_domains_on, make_user):
    other = create_business(make_user("otra@example.com"), name="Otro")
    active_row(other)

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business)

    assert refused.value.code == "hubs.custom_domain_taken"


def test_a_domain_on_its_way_out_of_another_business_stays_taken(owner, standard_business, custom_domains_on, make_user):
    other = create_business(make_user("otra@example.com"), name="Otro")
    make_row(other, state=CustomDomain.State.REMOVING, proven_at=timezone.now())

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business)

    assert refused.value.code == "hubs.custom_domain_taken"


def test_a_domain_nobody_proved_yet_is_nobodys(owner, standard_business, custom_domains_on, make_user):
    """Otherwise anybody could keep a stranger's domain from its owner by asking first and never proving it."""
    other = create_business(make_user("otra@example.com"), name="Otro")
    make_row(other)
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    assert ask(owner, standard_business).state == "pending"
    assert CustomDomain.objects.filter(hostname=DOMAIN).count() == 2


def test_only_one_business_can_hold_the_proof_of_a_name(standard_business, make_user, plans):
    other = create_business(make_user("otra@example.com"), name="Otro")
    make_row(standard_business, proven_at=timezone.now())

    with pytest.raises(IntegrityError), transaction.atomic():
        make_row(other, proven_at=timezone.now())


def test_a_lapsed_domain_asked_for_again_starts_over_with_a_new_token(owner, standard_business, custom_domains_on):
    """ACM gives back the same certificate for the same token for an hour, and that one may be deleted."""
    make_row(standard_business, state=CustomDomain.State.LAPSED, reason=CustomDomain.Reason.VALIDATION_TIMED_OUT)
    old_token = row_of(standard_business).certificate_token
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    answer = ask(owner, standard_business)

    assert answer.state == "pending"
    assert answer.reason == "certificate_pending"
    row = row_of(standard_business)
    assert row.certificate_token != old_token
    assert row.certificate_arn == certificate_arn()


def test_a_lapsed_domain_whose_certificate_is_still_going_cannot_start_over_yet(owner, standard_business, custom_domains_on):
    make_row(standard_business, state=CustomDomain.State.LAPSED, certificate_arn=certificate_arn())

    with pytest.raises(Conflict) as refused:
        ask(owner, standard_business)

    assert refused.value.code == "hubs.custom_domain_exists"


def test_asking_for_another_domain_after_it_lapsed_takes_its_place(owner, standard_business, custom_domains_on):
    make_row(standard_business, state=CustomDomain.State.LAPSED, reason=CustomDomain.Reason.VALIDATION_TIMED_OUT)
    custom_domains_on.expect_request(domain="www.otro.es")
    custom_domains_on.expect_describe(domain="www.otro.es")

    answer = ask(owner, standard_business, domain="www.otro.es")

    assert answer.domain == "www.otro.es"
    assert CustomDomain.objects.get().hostname == "www.otro.es"


def test_asking_records_its_event(owner, standard_business, custom_domains_on):
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()

    ask(owner, standard_business)

    event = OutboxEvent.objects.get(name=events.CUSTOM_DOMAIN_CHANGED)
    assert event.payload == {"business_id": str(standard_business.id)}


# --- hubs.custom_domain.get --------------------------------------------------------------------------


def read(user, hub):
    return queries.custom_domain_get(ctx_for(user), ByIdIn(id=hub.id))


def test_reading_a_business_without_a_domain_says_it_can_ask(owner, standard_business, settings):
    settings.CUSTOM_DOMAINS_ENABLED = True
    status = read(owner, standard_business)
    assert (status.available, status.in_plan, status.domain) == (True, True, None)


@pytest.mark.parametrize("variable", [False, None], ids=["false", "absent"])
def test_with_the_variable_off_reading_says_it_is_not_available(owner, standard_business, settings, variable):
    settings.CUSTOM_DOMAINS_ENABLED = bool(variable)
    status = read(owner, standard_business)
    assert status.available is False


def test_a_plan_that_does_not_include_it_does_not_offer_it(owner, business, settings):
    settings.CUSTOM_DOMAINS_ENABLED = True
    assert read(owner, business).in_plan is False


def test_reading_gives_the_two_records_and_the_reason_of_a_pending_domain(owner, standard_business, custom_domains_on):
    make_row(
        standard_business,
        certificate_arn=certificate_arn(),
        validation_name=f"_abc.{DOMAIN}",
        validation_value="_def.acm-validations.aws",
        reason=CustomDomain.Reason.CNAME_MISSING,
    )

    domain = read(owner, standard_business).domain

    assert domain.domain == DOMAIN
    assert domain.reason == "cname_missing"
    assert domain.reason_label
    assert domain.state_label
    assert domain.validation.name == f"_abc.{DOMAIN}"
    assert domain.traffic.value == f"hub-{standard_business.id}.erplora.com"


def test_reading_asks_acm_for_a_validation_record_the_row_does_not_have_yet(owner, standard_business, custom_domains_on):
    make_row(standard_business, certificate_arn=certificate_arn())
    custom_domains_on.expect_describe()

    assert read(owner, standard_business).domain.validation.name == f"_abc.{DOMAIN}"


@pytest.mark.parametrize("state", [CustomDomain.State.ACTIVE, CustomDomain.State.LAPSED, CustomDomain.State.REMOVING])
def test_reading_asks_acm_only_for_a_domain_on_its_way(owner, standard_business, custom_domains_on, state):
    make_row(standard_business, state=state, certificate_arn=certificate_arn())

    assert read(owner, standard_business).domain.validation is None


def test_reading_with_the_variable_off_asks_acm_for_nothing(owner, standard_business, settings, aws_edge):
    settings.CUSTOM_DOMAINS_ENABLED = False
    settings.CUSTOM_DOMAINS_TARGET_TEMPLATE = "hub-{hub_id}.erplora.com"
    make_row(standard_business, certificate_arn=certificate_arn())

    assert read(owner, standard_business).domain.validation is None


def test_reading_with_acm_away_gives_the_rest(owner, standard_business, custom_domains_on):
    make_row(standard_business, certificate_arn=certificate_arn())
    custom_domains_on.acm.add_client_error("describe_certificate", "ThrottlingException", "later")

    domain = read(owner, standard_business).domain

    assert domain.validation is None
    assert domain.traffic.name == DOMAIN


def test_an_admin_reads_but_an_employee_does_not(standard_business, make_user, settings):
    settings.CUSTOM_DOMAINS_ENABLED = True
    admin, employee = make_user("admin@example.com"), make_user("employee@example.com")
    add_member(standard_business, admin, HubMember.Role.ADMIN)
    add_member(standard_business, employee, HubMember.Role.EMPLOYEE)

    assert read(admin, standard_business).available is True
    with pytest.raises(PermissionDenied):
        read(employee, standard_business)


def test_two_businesses_read_their_own_domain(owner, standard_business, make_user, settings, plans):
    settings.CUSTOM_DOMAINS_ENABLED = True
    settings.CUSTOM_DOMAINS_TARGET_TEMPLATE = "hub-{hub_id}.erplora.com"
    theirs_owner = make_user("otra@example.com")
    theirs = create_business(theirs_owner, name="Otro")
    make_row(standard_business, hostname="www.mio.es", validation_name="_a", validation_value="_b")
    make_row(theirs, hostname="www.suyo.es", validation_name="_c", validation_value="_d")

    assert read(owner, standard_business).domain.domain == "www.mio.es"
    assert read(theirs_owner, theirs).domain.domain == "www.suyo.es"
    with pytest.raises(NotFound):
        read(owner, theirs)


# --- hubs.custom_domain.remove -------------------------------------------------------------------------


def remove(user, hub):
    return services.custom_domain_remove(ctx_for(user), ByIdIn(id=hub.id))


def snapshot_domain(hub):
    return queries.hub_snapshot(hub.id).get("custom_domain", "absent")


def test_removing_takes_it_out_of_the_snapshot_before_anything_else(
    owner, standard_business, custom_domains_on, hub_double, django_capture_on_commit_callbacks
):
    active_row(standard_business)
    version = Hub.objects.get(pk=standard_business.pk).state_version
    custom_domains_on.expect_detach()
    custom_domains_on.expect_delete()

    with django_capture_on_commit_callbacks(execute=True):
        answer = remove(owner, standard_business)

    assert answer.domain.state == "removing"
    pushed = hub_double.calls_to("PUT", "/state")[-1].body
    assert "custom_domain" not in pushed
    assert pushed["version"] == version + 1
    assert not CustomDomain.objects.exists()


def test_removing_what_is_already_being_removed_says_nothing_new(
    owner, standard_business, custom_domains_on, hub_double, django_capture_on_commit_callbacks
):
    active_row(standard_business)
    custom_domains_on.expect_detach()
    custom_domains_on.acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")
    with django_capture_on_commit_callbacks(execute=True):
        remove(owner, standard_business)
    said = OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).count()
    version = Hub.objects.get(pk=standard_business.pk).state_version

    custom_domains_on.acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")
    custom_domains_on.expect_detach()
    with django_capture_on_commit_callbacks(execute=True):
        remove(owner, standard_business)

    assert OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).count() == said
    assert Hub.objects.get(pk=standard_business.pk).state_version == version


def test_a_certificate_the_alb_holds_stays_for_the_next_check_and_the_row_with_it(
    owner, standard_business, custom_domains_on, hub_double, django_capture_on_commit_callbacks
):
    """The row goes last, and that is what frees the name."""
    active_row(standard_business)
    custom_domains_on.expect_detach()
    custom_domains_on.acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")

    with django_capture_on_commit_callbacks(execute=True):
        remove(owner, standard_business)

    row = row_of(standard_business)
    assert row.state == CustomDomain.State.REMOVING
    assert row.certificate_arn == certificate_arn()
    assert row.attached_at is None
    assert row.proven_at is not None


def test_with_the_hub_away_the_certificate_waits_for_the_snapshot(
    owner, standard_business, custom_domains_on, offline_hub, django_capture_on_commit_callbacks
):
    """The Hub stops serving it first; only then the certificate goes (no call is expected from AWS)."""
    active_row(standard_business)

    with django_capture_on_commit_callbacks(execute=True):
        remove(owner, standard_business)

    row = row_of(standard_business)
    assert row.state == CustomDomain.State.REMOVING
    assert row.certificate_arn == certificate_arn()
    assert row.attached_at is not None


def test_removing_a_domain_without_a_certificate_goes_at_once(
    owner, standard_business, custom_domains_on, hub_double, django_capture_on_commit_callbacks
):
    make_row(standard_business)

    with django_capture_on_commit_callbacks(execute=True):
        remove(owner, standard_business)

    assert not CustomDomain.objects.exists()
    assert hub_double.calls_to("PUT", "/state") == []


def test_removing_one_that_was_never_in_the_snapshot_does_not_bump_it(
    owner, standard_business, custom_domains_on, hub_double, django_capture_on_commit_callbacks
):
    make_row(standard_business, certificate_arn=certificate_arn())
    version = Hub.objects.get(pk=standard_business.pk).state_version
    custom_domains_on.expect_delete()

    with django_capture_on_commit_callbacks(execute=True):
        remove(owner, standard_business)

    assert Hub.objects.get(pk=standard_business.pk).state_version == version
    assert not CustomDomain.objects.exists()


def test_removing_what_is_not_there_is_not_found(owner, standard_business, custom_domains_on):
    with pytest.raises(NotFound):
        remove(owner, standard_business)


def test_removing_twice_does_it_once(owner, standard_business, custom_domains_on):
    make_row(standard_business, state=CustomDomain.State.REMOVING, certificate_arn=certificate_arn())
    version = Hub.objects.get(pk=standard_business.pk).state_version

    assert remove(owner, standard_business).domain.state == "removing"
    assert Hub.objects.get(pk=standard_business.pk).state_version == version


def test_only_the_owner_removes(standard_business, make_user, custom_domains_on):
    admin = make_user("admin@example.com")
    add_member(standard_business, admin, HubMember.Role.ADMIN)
    active_row(standard_business)

    with pytest.raises(PermissionDenied):
        remove(admin, standard_business)
    assert row_of(standard_business).state == CustomDomain.State.ACTIVE


def test_with_the_variable_off_removing_does_nothing(owner, standard_business, settings, aws_edge):
    settings.CUSTOM_DOMAINS_ENABLED = False
    active_row(standard_business)

    with pytest.raises(Conflict) as refused:
        remove(owner, standard_business)

    assert refused.value.code == "hubs.custom_domains_off"
    assert row_of(standard_business).state == CustomDomain.State.ACTIVE


def test_removing_records_its_event(owner, standard_business, custom_domains_on):
    active_row(standard_business)

    remove(owner, standard_business)

    assert OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED).exists()


# --- The snapshot -------------------------------------------------------------------------------------


def test_a_business_without_a_domain_sends_a_snapshot_without_the_key(standard_business):
    assert "custom_domain" not in queries.hub_snapshot(standard_business.id)


@pytest.mark.parametrize(
    ("state", "proven", "named"),
    [
        (CustomDomain.State.PENDING, False, False),
        (CustomDomain.State.PENDING, True, True),
        (CustomDomain.State.ACTIVE, True, True),
        (CustomDomain.State.REMOVING, True, False),
        (CustomDomain.State.LAPSED, False, False),
    ],
)
def test_the_snapshot_names_a_domain_from_its_proof_until_it_goes(standard_business, state, proven, named):
    make_row(standard_business, state=state, proven_at=timezone.now() if proven else None)
    assert snapshot_domain(standard_business) == (DOMAIN if named else "absent")


def test_a_plan_that_does_not_include_it_sends_the_snapshot_without_the_key(standard_business):
    active_row(standard_business)
    Subscription.objects.filter(hub=standard_business).update(plan=Plan.objects.get(slug="free"))
    assert snapshot_domain(standard_business) == "absent"


def test_a_snapshot_with_the_domain_is_what_the_hub_takes(standard_business, hub_double):
    active_row(standard_business)
    Hub.objects.filter(pk=standard_business.pk).update(state_version=7, pushed_state_version=6)

    assert services.sync_hub(standard_business.id) is True

    assert hub_double.calls_to("PUT", "/state")[-1].body["custom_domain"] == DOMAIN


def test_the_hub_refusing_a_domain_refuses_the_whole_snapshot(standard_business, hub_double):
    """Why nothing it refuses may ever reach a row: this business would get no more snapshots at all."""
    make_row(standard_business, hostname="www.erplora.com", proven_at=timezone.now())
    Hub.objects.filter(pk=standard_business.pk).update(state_version=7, pushed_state_version=6)

    assert services.sync_hub(standard_business.id) is False
    assert Hub.objects.get(pk=standard_business.pk).pushed_state_version == 6


def test_the_snapshot_of_one_business_never_names_anothers_domain(standard_business, make_user, plans):
    other = create_business(make_user("otra@example.com"), name="Otro")
    Subscription.objects.filter(hub=other).update(plan=Plan.objects.get(slug="standard"))
    active_row(standard_business)
    assert "custom_domain" not in queries.hub_snapshot(other.id)


# --- The doors --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["hubs.custom_domain.request", "hubs.custom_domain.get", "hubs.custom_domain.remove"]
)
def test_the_doors_of_the_panel_are_tools_of_the_assistant_too(name):
    spec = registry[name].ai_spec()
    assert isinstance(spec, AI)
    assert set(spec.asks) == {"en", "es"}


def test_an_api_key_reads_the_domain_and_only_reads_it():
    assert registry["hubs.custom_domain.get"].expose_api is True
    assert registry["hubs.custom_domain.request"].expose_api is False
    assert registry["hubs.custom_domain.remove"].expose_api is False


def test_removing_stops_at_the_card_and_asks_to_type_no_word():
    """It stops being served and comes back by asking for it again, with nothing lost: «Run» on the card is its confirmation.
    Only the five writes of ASSISTANT-F25, step 5, ask to type the word (``base/tests/test_assistant_turn.py``)."""
    assert registry["hubs.custom_domain.remove"].ai_spec().risk != "high"


def test_what_only_the_check_writes_is_no_tool():
    assert registry["hubs.custom_domain.record"].ai_spec() is INTERNAL


def test_a_write_of_the_check_is_only_the_platforms(owner, standard_business):
    from hubs.schemas import CustomDomainRecordIn

    row = make_row(standard_business)
    with pytest.raises(PermissionDenied):
        services.custom_domain_record(ctx_for(owner), CustomDomainRecordIn(id=row.id, expected_state="pending", reason=""))


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/hubs/businesses/custom-domain", None),
        ("post", "/api/hubs/businesses/custom-domain", {"domain": DOMAIN}),
        ("post", "/api/hubs/businesses/custom-domain/remove", {}),
    ],
)
def test_the_routes_ask_for_a_session(client, standard_business, settings, method, path, body):
    settings.CUSTOM_DOMAINS_ENABLED = False
    data = {"id": str(standard_business.id), **(body or {})}
    answer = (
        client.get(path, data, HTTP_HOST=HOST)
        if method == "get"
        else client.post(path, json.dumps(data), content_type="application/json", HTTP_HOST=HOST)
    )
    assert answer.status_code == 401


def test_the_route_asks_and_reads_for_the_owner(client, owner, standard_business, custom_domains_on, django_capture_on_commit_callbacks):
    custom_domains_on.expect_request()
    custom_domains_on.expect_describe()
    client.force_login(owner)
    url = "/api/hubs/businesses/custom-domain"

    with django_capture_on_commit_callbacks(execute=True):
        asked = client.post(
            url, json.dumps({"id": str(standard_business.id), "domain": DOMAIN}), content_type="application/json", HTTP_HOST=HOST
        )
    assert asked.status_code == 200, asked.content
    assert asked.json()["traffic"]["value"] == f"hub-{standard_business.id}.erplora.com"

    read_back = client.get(url, {"id": str(standard_business.id)}, HTTP_HOST=HOST)
    assert read_back.status_code == 200, read_back.content
    assert read_back.json()["domain"]["validation"]["name"] == f"_abc.{DOMAIN}"


def test_the_route_answers_a_bad_name_with_its_field(client, owner, standard_business, custom_domains_on):
    client.force_login(owner)
    answer = client.post(
        "/api/hubs/businesses/custom-domain",
        json.dumps({"id": str(standard_business.id), "domain": "*.minegocio.es"}),
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "hubs.custom_domain_invalid"
    assert set(answer.json()["error"]["fields"]) == {"domain"}


def test_the_panel_hears_of_a_change_of_its_domain():
    assert "hubs.custom_domain.get" in live_registry.affected([events.CUSTOM_DOMAIN_CHANGED])
