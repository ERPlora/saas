"""Fixtures of the hubs tests: the Hub double, accounts, contexts and a business with its four roles."""

from decimal import Decimal

import boto3
import pytest
from botocore.exceptions import StubResponseError
from botocore.stub import ANY, Stubber
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.operations import ACCOUNT_ROLE
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another saas-cron task
from hubs.tests.hub_double import HubDouble

SECRET = "test-internal-secret"


@pytest.fixture
def hub_double(settings):
    """The Hub's ``/internal`` on a free local port; the SaaS's client points at it."""
    settings.INTERNAL_SHARED_SECRET = SECRET
    double = HubDouble(SECRET).start()
    settings.HUB_INTERNAL_URL = double.url
    yield double
    double.stop()


@pytest.fixture
def offline_hub(settings):
    """No Hub at all: every call to it fails as a closed port does."""
    settings.HUB_INTERNAL_URL = "http://127.0.0.1:9"


def ctx_for(user, language: str = "en") -> OperationContext:
    """The context a signed-in account gets from a request (``base.operations``)."""
    if user is None:
        return OperationContext(
            scope=Scope("user", "anonymous"), actor=None, language=language
        )
    return OperationContext(
        scope=Scope("user", str(user.pk)),
        actor=user,
        permissions=permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE),
        language=language,
    )


@pytest.fixture
def make_user(db):
    def make(email: str, **extra):
        # No password: hashing one costs a tenth of a second per account and no test signs in with it.
        return get_user_model().objects.create_user(email=email, password=None, **extra)

    return make


def put_the_catalogue_back():
    """The plans the migrations leave (``hubs/0013``, the module caps of ``hubs/0019``, the paid cards of
    ``hubs/0020``, the cards on sale of ``hubs/0021``, Standard's card without the custom domain of ``hubs/0026`` and
    the database line that says what a recovery keeps of ``hubs/0029``; pytest builds its database by running them). A
    transactional test starts from a database the one before flushed: there the data migrations that write them run
    again, in their order."""
    from importlib import import_module

    from django.apps import apps

    from hubs.models import Plan

    if not Plan.objects.exists():
        import_module("hubs.migrations.0013_plans_in_the_database").put_the_catalogue_in(apps, None)
        import_module("hubs.migrations.0019_plan_max_apps").give_module_caps(apps, None)
        import_module("hubs.migrations.0020_paid_plan_copy").describe_what_the_plans_give(apps, None)
        import_module("hubs.migrations.0021_plan_copy_on_sale").describe_the_cards_on_sale(apps, None)
        import_module("hubs.migrations.0026_no_custom_domain_on_sale").stop_selling_the_custom_domain(apps, None)
        import_module("hubs.migrations.0029_backups_keep_what_was_sent").say_what_a_recovery_keeps(apps, None)


@pytest.fixture
def plans(db):
    """The catalogue (``put_the_catalogue_back``), none with a trial."""
    put_the_catalogue_back()


@pytest.fixture
def no_plans(db):
    """An empty plan table, for a test that builds the plans it reads: the catalogue the migrations leave goes."""
    from hubs.models import Plan

    Plan.objects.all().delete()


@pytest.fixture
def signup_trial(plans):
    """Starter with a 15-day trial, as staff would give it in the admin. No plan carries one (the Free plan is the
    way in), but the mechanism stays, dormant, and these tests exercise it."""
    from hubs.models import Plan

    Plan.objects.filter(slug="starter").update(trial_period_days=15)


@pytest.fixture
def free_plan(db):
    from hubs.models import Plan

    return Plan.objects.create(
        slug="free",
        name_en="Free",
        price_monthly=Decimal("0"),
        max_users=3,
        display_order=10,
    )


# --- Businesses and their people ------------------------------------------------------------------


def create_business(user, **data):
    """A business created through ``hubs.business.create``, as the panel creates it."""
    from hubs import services
    from hubs.models import Hub
    from hubs.schemas import BusinessCreateIn

    created = services.business_create(ctx_for(user), BusinessCreateIn(**{"name": "Bar Manolo", "country": "ES", **data}))
    return Hub.objects.get(pk=created.id)


def add_member(hub, user, role, *, accepted=True, invited_by=None, invited_days_ago=0):
    """A member written as an accepted invitation would leave it (or a pending one)."""
    from datetime import timedelta

    from django.utils import timezone

    from hubs.models import HubMember

    invited = timezone.now() - timedelta(days=invited_days_ago)
    member = HubMember.objects.create(
        hub=hub,
        user=user,
        role=role,
        invited_by=invited_by,
        invited_at=invited,
        invitation_expires_at=invited + HubMember.INVITATION_WINDOW,
        joined_at=invited,
        accepted_at=timezone.now() if accepted else None,
    )
    return member


def role_on(user, slug: str) -> str | None:
    """What ``user`` is on the business at ``slug`` for the jump to a hub; ``None``: it does not enter."""
    from hubs import queries

    return dict(queries.access_of(user.pk)).get(slug)


@pytest.fixture
def owner(make_user):
    return make_user("owner@example.com", first_name="Olga", last_name="Owner", language="es")


@pytest.fixture
def business(owner, plans):
    return create_business(owner)


@pytest.fixture
def team(business, owner, make_user):
    """The business with one person per role, a pending invitee and a stranger. Five people do not fit in Free
    (three), so the business is on Starter, as one that pays (no plan lends a trial)."""
    from hubs.models import HubMember, Plan, Subscription

    Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="starter"))

    people = {
        "owner": owner,
        "admin": make_user("admin@example.com", first_name="Adela"),
        "manager": make_user("manager@example.com", first_name="Manu"),
        "employee": make_user("employee@example.com", first_name="Elena"),
        "invitee": make_user("invitee@example.com"),
        "stranger": make_user("stranger@example.com"),
    }
    add_member(business, people["admin"], HubMember.Role.ADMIN, invited_by=owner)
    add_member(business, people["manager"], HubMember.Role.MANAGER, invited_by=owner)
    add_member(business, people["employee"], HubMember.Role.EMPLOYEE, invited_by=owner)
    add_member(business, people["invitee"], HubMember.Role.EMPLOYEE, invited_by=owner, accepted=False)
    return people


def member_of(hub, user):
    from hubs.models import HubMember

    return HubMember.objects.get(hub=hub, user=user)


# --- A business's own domain (HUBS-F17): AWS through botocore's Stubber, and a DNS with no real name in it --------------


LISTENER_ARN = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:listener/app/erplora/abc/def"
DOMAIN = "www.minegocio.es"


def certificate_arn(number: int = 1) -> str:
    return f"arn:aws:acm:eu-west-1:123456789012:certificate/0193a0a0-0000-7000-8000-{number:012d}"


def fake_aws_client(monkeypatch, service):
    """A real client of ``service`` to put a Stubber on: dummy credentials from the environment, as
    ``public/tests/test_downloads.py``, and a session of its own, so nothing stays in boto3's default one."""
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    return boto3.session.Session().client(service, region_name="eu-west-1")


class StrictStubber(Stubber):
    """A Stubber that remembers what it refused. Its errors are ``BotoCoreError``s, which ``hubs.edge_client`` turns into
    ``EdgeUnavailable`` as it must: without this, a call nobody expected would pass for AWS being away, and a test that
    expects none would prove nothing."""

    def __init__(self, client):
        super().__init__(client)
        self.refused: list[str] = []

    def _assert_expected_call_order(self, model, params):
        try:
            super()._assert_expected_call_order(model, params)
        except StubResponseError as refused:
            self.refused.append(f"{model.name}: {refused}")
            raise

    def _assert_expected_params(self, model, params, context, **kwargs):
        try:
            super()._assert_expected_params(model, params, context, **kwargs)
        except StubResponseError as refused:
            self.refused.append(f"{model.name}: {refused}")
            raise

    def assert_all_as_expected(self):
        assert self.refused == [], "calls to AWS nobody expected, or with other parameters"
        self.assert_no_pending_responses()


class AwsEdge:
    """ACM, the ALB and CloudWatch, each a real client with a Stubber: a call the test did not expect fails."""

    def __init__(self, acm, alb, cloudwatch):
        self.acm, self.alb, self.cloudwatch = acm, alb, cloudwatch

    def expect_request(self, domain=DOMAIN, arn=None, token=None):
        expected = {
            "DomainName": domain,
            "ValidationMethod": "DNS",
            "IdempotencyToken": token if token is not None else ANY,
            "Tags": [{"Key": "Purpose", "Value": "custom-domain"}],
        }
        self.acm.add_response("request_certificate", {"CertificateArn": arn or certificate_arn()}, expected)

    def expect_describe(self, status="PENDING_VALIDATION", arn=None, *, record=True, failure=None, domain=DOMAIN):
        arn = arn or certificate_arn()
        answer = {"CertificateArn": arn, "Status": status}
        if record:
            answer["DomainValidationOptions"] = [
                {
                    "DomainName": domain,
                    "ResourceRecord": {
                        "Name": f"_abc.{domain}.",
                        "Type": "CNAME",
                        "Value": "_def.acm-validations.aws.",
                    },
                }
            ]
        if failure:
            answer["FailureReason"] = failure
        self.acm.add_response("describe_certificate", {"Certificate": answer}, {"CertificateArn": arn})

    def expect_attach(self, arn=None):
        self.alb.add_response(
            "add_listener_certificates",
            {},
            {"ListenerArn": LISTENER_ARN, "Certificates": [{"CertificateArn": arn or certificate_arn()}]},
        )

    def expect_detach(self, arn=None):
        self.alb.add_response(
            "remove_listener_certificates",
            {},
            {"ListenerArn": LISTENER_ARN, "Certificates": [{"CertificateArn": arn or certificate_arn()}]},
        )

    def expect_delete(self, arn=None):
        self.acm.add_response("delete_certificate", {}, {"CertificateArn": arn or certificate_arn()})

    def expect_metric(self, value):
        self.cloudwatch.add_response(
            "put_metric_data",
            {},
            {
                "Namespace": "ERPlora/CustomDomains",
                "MetricData": [
                    {
                        "MetricName": "CertificatesAttached",
                        "Dimensions": [{"Name": "Environment", "Value": "prod"}],
                        "Value": float(value),
                        "Unit": "Count",
                    }
                ],
            },
        )


@pytest.fixture
def aws_edge(monkeypatch):
    """No test reaches AWS: an unexpected call fails on its Stubber, and an expected one that was not made fails here."""
    from hubs import edge_client

    acm = fake_aws_client(monkeypatch, "acm")
    elbv2 = fake_aws_client(monkeypatch, "elbv2")
    cloudwatch = fake_aws_client(monkeypatch, "cloudwatch")
    monkeypatch.setattr(edge_client, "_acm", lambda: acm)
    monkeypatch.setattr(edge_client, "_elbv2", lambda: elbv2)
    monkeypatch.setattr(edge_client, "_cloudwatch", lambda: cloudwatch)
    with StrictStubber(acm) as acm_stub, StrictStubber(elbv2) as alb_stub, StrictStubber(cloudwatch) as metric_stub:
        yield AwsEdge(acm_stub, alb_stub, metric_stub)
        acm_stub.assert_all_as_expected()
        alb_stub.assert_all_as_expected()
        metric_stub.assert_all_as_expected()


@pytest.fixture
def dns_world(monkeypatch):
    """``{(name, rdtype): [text]}``, the answers of the DNS: a name it does not hold has no record, and an exception is a
    question that could not be answered. No real name is ever looked up."""
    from hubs import domain_checks

    world: dict[tuple[str, str], object] = {}

    def lookup(name, rdtype):
        answer = world.get((name, rdtype), [])
        if isinstance(answer, Exception):
            raise domain_checks.DnsUnavailable(str(answer))
        return answer

    monkeypatch.setattr(domain_checks, "_lookup", lookup)
    return world


@pytest.fixture
def custom_domains_on(settings, aws_edge, dns_world, monkeypatch):
    """The deployment as ``aws`` ``custom_domains.tf`` leaves it, with a name that is a subdomain by default."""
    from hubs import domain_checks

    settings.CUSTOM_DOMAINS_ENABLED = True
    settings.CUSTOM_DOMAINS_LISTENER_ARN = LISTENER_ARN
    settings.CUSTOM_DOMAINS_TARGET_TEMPLATE = "hub-{hub_id}.erplora.com"
    settings.CUSTOM_DOMAINS_MAX_CERTIFICATES = 24
    settings.ERPLORA_ENVIRONMENT = "prod"
    monkeypatch.setattr(domain_checks, "zone_of", lambda domain: domain_checks.Zone.SUBDOMAIN)
    # The wait for ACM's validation record is a test's to time, never a second of the run.
    monkeypatch.setattr("hubs.services.sleep", lambda seconds: None)
    return aws_edge


@pytest.fixture
def standard_business(business):
    """The business on the plan that includes an own domain, with nothing owed to the Hub."""
    from django.db.models import F

    from hubs.models import Hub, Plan, Subscription

    Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="standard"))
    Hub.objects.filter(pk=business.pk).update(
        status=Hub.Status.ACTIVE, pending_hub_call="", pushed_state_version=F("state_version")
    )
    business.refresh_from_db()
    return business


def pointing(dns_world, hub, domain=DOMAIN):
    """The customer's CNAME, onto the name of ``hub``."""
    dns_world[(domain, "CNAME")] = [f"hub-{hub.id}.erplora.com"]
