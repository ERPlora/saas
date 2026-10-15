"""Fixtures of the hubs tests: the Hub double, accounts, contexts and a business with its four roles."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.operations import ACCOUNT_ROLE
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another saas-cron task
from hubs.tests.hub_double import HubDouble

SECRET = "test-internal-secret"


@pytest.fixture
def hub_double(settings):
    """hub-next's ``/internal`` on a free local port; the SaaS's client points at it."""
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
    """The plans the migrations leave (``hubs/0013``; pytest builds its database by running them). A transactional
    test starts from a database the one before flushed: there the data migration that writes them runs again."""
    from importlib import import_module

    from django.apps import apps

    from hubs.models import Plan

    if not Plan.objects.exists():
        import_module("hubs.migrations.0013_plans_in_the_database").put_the_catalogue_in(apps, None)


@pytest.fixture
def plans(db):
    """The catalogue (``put_the_catalogue_back``), none with a trial since 2026-10-15."""
    put_the_catalogue_back()


@pytest.fixture
def no_plans(db):
    """An empty plan table, for a test that builds the plans it reads: the catalogue the migrations leave goes."""
    from hubs.models import Plan

    Plan.objects.all().delete()


@pytest.fixture
def signup_trial(plans):
    """Starter with a 15-day trial, as staff would give it in the admin. No plan carries one since 2026-10-15 (the
    Free plan is the way in), but the mechanism stays, dormant, and these tests exercise it."""
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
    """A member written as an accepted invitation would leave it (or a pending one), with its access."""
    from datetime import timedelta

    from django.utils import timezone

    from hubs import services
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
    services.sync_access(hub)
    return member


@pytest.fixture
def owner(make_user):
    return make_user("owner@example.com", first_name="Olga", last_name="Owner", language="es")


@pytest.fixture
def business(owner, plans):
    return create_business(owner)


@pytest.fixture
def team(business, owner, make_user):
    """The business with one person per role, a pending invitee and a stranger. Five people do not fit in Free
    (three), so the business is on Starter, as one that pays (no plan lends a trial since 2026-10-15)."""
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
