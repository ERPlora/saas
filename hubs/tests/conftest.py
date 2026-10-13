"""Fixtures of the hubs tests: the Hub double, accounts, contexts and a business with its four roles."""

from decimal import Decimal
from io import StringIO

import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.operations import ACCOUNT_ROLE
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


@pytest.fixture
def plans(db):
    """Free (no trial) and Starter (15 days) as the seed writes them, and the rest of the ladder."""
    call_command("sync_hub_plans", stdout=StringIO())


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
    """The business with one person per role, a pending invitee and a stranger."""
    from hubs.models import HubMember

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

@pytest.fixture
def other_session(django_db_setup):
    """A second database session, as a second run of the command would have."""
    params = connections["default"].settings_dict
    session = psycopg.connect(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
        autocommit=True,
    )
    yield session
    session.close()
