"""The data migrations of hubs over the businesses: the hubs of the Hub's seed become businesses (0006) and
the businesses already suspended get their clock (0016)."""

import functools
from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from hubs.tests.conftest import create_business
from hubs.tests.data_migrations import _imported_modules, _SchemaEditor

# --- 0006: the hubs of the Hub's seed become businesses ------------------------------------------

ADOPTION = "0006_adopt_seed_hubs"


def _adoption():
    return import_module(f"hubs.migrations.{ADOPTION}")


@functools.cache
def _with_the_copy():
    """The apps as they were the last time ``accounts.HubMembership`` was a model (``accounts/0011`` took it out)."""
    return (
        MigrationLoader(connection)
        .project_state([("accounts", "0010_user_store_review_account"), ("hubs", "0024_support_views_the_daily_usage")])
        .apps
    )


def _copy():
    """``accounts.HubMembership``, what ``0006`` read and wrote."""
    return _with_the_copy().get_model("accounts", "HubMembership")


def _adopt():
    _adoption().adopt_seed_hubs(_with_the_copy(), _SchemaEditor())


def _answered_members():
    from hubs.models import HubMember

    answered = HubMember.objects.filter(accepted_at__isnull=False)
    return sorted(answered.values_list("hub__slug", "user_id", "role"))


def _rows_of_the_copy():
    return sorted(_copy().objects.values_list("hub_slug", "user_id", "role"))


@pytest.mark.django_db
class TestTheSeedHubsBecomeBusinesses:
    @pytest.fixture(autouse=True)
    def the_table_of_the_copy(self):
        """What ``0006`` read and wrote: ``accounts/0012`` dropped it, and the test's transaction takes this one away."""
        with connection.schema_editor() as editor:
            editor.create_model(_copy())

    @pytest.fixture
    def people(self):
        make = get_user_model().objects.create_user
        return {
            "olga": make(email="olga@example.com", password=None, language="es"),
            "eva": make(email="eva@example.com", password=None),
            "ana": make(email="ana@example.com", password=None),
        }

    def _membership(self, user, slug, role, days_ago=0):
        return _copy().objects.create(
            user_id=user.pk, hub_slug=slug, role=role, created_at=timezone.now() - timedelta(days=days_ago)
        )

    def test_a_seed_hub_becomes_an_active_ready_business_that_owes_the_hub_nothing(self, people, plans):
        from hubs.models import Hub, HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner", days_ago=2)
        self._membership(people["eva"], "bar-pepe", "hub_employee", days_ago=1)

        _adopt()

        hub = Hub.objects.get(slug="bar-pepe")
        assert (hub.name, hub.country, hub.language, hub.status) == ("bar-pepe", "ES", "es", "active")
        assert hub.ready_at is not None and hub.provision_requested_at is None
        assert (hub.pending_hub_call, hub.pushed_state_version, hub.state_version) == ("", 1, 1)
        members = {m.user.email: m for m in HubMember.objects.filter(hub=hub).select_related("user")}
        assert {email: m.role for email, m in members.items()} == {
            "olga@example.com": "hub_owner",
            "eva@example.com": "hub_employee",
        }
        assert all(m.accepted_at == m.joined_at for m in members.values())
        assert hub.subscription.plan.slug == "free"

    def test_without_the_free_plan_there_is_no_subscription(self, people):
        from hubs.models import Hub, Plan, Subscription

        Plan.objects.all().delete()
        self._membership(people["olga"], "bar-pepe", "hub_owner")

        _adopt()

        assert not Subscription.objects.filter(hub=Hub.objects.get(slug="bar-pepe")).exists()

    def test_without_an_owner_the_oldest_member_becomes_it_in_both_tables(self, people):
        from hubs.models import HubMember

        self._membership(people["ana"], "bar-pepe", "hub_employee", days_ago=1)
        self._membership(people["eva"], "bar-pepe", "hub_admin", days_ago=5)

        _adopt()

        assert HubMember.objects.get(user=people["eva"]).role == "hub_owner"
        assert _copy().objects.get(user_id=people["eva"].pk).role == "hub_owner"
        assert HubMember.objects.get(user=people["ana"]).role == "hub_employee"

    def test_two_owners_keep_the_oldest_and_the_other_becomes_admin(self, people):
        from hubs.models import HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner", days_ago=3)
        self._membership(people["eva"], "bar-pepe", "hub_owner", days_ago=1)

        _adopt()

        assert HubMember.objects.get(user=people["olga"]).role == "hub_owner"
        assert HubMember.objects.get(user=people["eva"]).role == "hub_admin"
        assert _copy().objects.get(user_id=people["eva"].pk).role == "hub_admin"

    @pytest.mark.parametrize("slug", ["www", "hubs", "-bad-", "xn--abc"])
    def test_a_slug_that_is_no_hubs_gives_no_business_and_its_dead_rows_go(self, people, slug):
        """``is_hub_slug`` already refused them at the jump: they opened nothing."""
        from hubs.models import Hub

        self._membership(people["olga"], slug, "hub_owner")

        _adopt()

        assert not Hub.objects.exists()
        assert not _copy().objects.exists()

    def test_a_business_of_the_panel_has_its_mirror_put_right(self, business, owner, people):
        """A row of somebody who is no member (an older ``demo_seed``) is dropped, a missing one is added."""
        self._membership(people["ana"], business.slug, "hub_admin")

        _adopt()

        assert list(_copy().objects.values_list("user_id", "role")) == [(owner.pk, "hub_owner")]

    def test_a_deleted_business_keeps_no_access(self, business, owner):
        from hubs.models import Hub

        self._membership(owner, business.slug, "hub_owner")
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        _adopt()

        assert not _copy().objects.exists()

    def test_after_it_both_tables_agree_and_running_it_again_changes_nothing(self, people, business):
        from hubs.models import Hub, HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        self._membership(people["eva"], "cafe-lola", "hub_manager")

        _adopt()
        counts = (Hub.objects.count(), HubMember.objects.count())
        _adopt()

        assert _rows_of_the_copy() == _answered_members()
        assert (Hub.objects.count(), HubMember.objects.count()) == counts == (3, 3)

    def test_the_adopted_hubs_are_not_provisioned_again(self, people, hub_double):
        """``reconcile_hub_states`` finds nothing owed: no registry, no snapshot, no poll."""
        from io import StringIO

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        _adopt()

        call_command("reconcile_hub_states", stdout=StringIO())

        assert hub_double.calls == []

    def test_going_back_keeps_the_businesses_and_coming_forward_finds_them(self, people):
        from hubs.models import Hub

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        _adopt()
        first = Hub.objects.get(slug="bar-pepe").pk

        _adoption().keep_the_businesses(_with_the_copy(), _SchemaEditor())
        _adopt()

        assert list(Hub.objects.values_list("pk", flat=True)) == [first]


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_adoption_and_forward_again(django_user_model):
    """``migrate hubs 0005`` and back: the round trip of the data migration (its reverse keeps the rows).

    The plans are in the database (0013), so the adoption gives the business its Free subscription. The whole
    round trip runs in the test's one transaction, where a deferred foreign key check would still be pending when
    a later migration alters ``hubs_subscription``: the checks run at once, as each migration's own COMMIT does.

    Going back also takes back ``accounts/0012``, which recreates the copy's table, and ``accounts/0011``, which depends
    on ``hubs/0024`` and rebuilds the copy from the members: the seed's row goes in after it, as the copy held it before
    the adoption."""
    from hubs.models import Hub

    olga = django_user_model.objects.create_user(email="olga@example.com", password=None)
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    call_command("migrate", "hubs", "0005", verbosity=0)
    _copy().objects.create(user_id=olga.pk, hub_slug="bar-pepe", role="hub_owner")
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    call_command("migrate", "hubs", verbosity=0)

    hub = Hub.objects.get(slug="bar-pepe", status="active")
    assert hub.subscription.plan.slug == "free"


# --- 0016: the clock of a suspended business (HUBS-F20) ----------------------------------------------------------

CLOCK = "0016_hub_suspension_clock"


def _clock():
    return import_module(f"hubs.migrations.{CLOCK}")


@pytest.mark.django_db
class TestTheBusinessesAlreadySuspendedGetTheirClock:
    """A business suspended before the clock arrived has no date: without one the hourly pass would only log it,
    forever. Its clock starts on the day of the deploy, so it is never deleted sooner than a new suspension."""

    def test_a_business_already_suspended_counts_from_the_deploy(self, business):
        from hubs.models import Hub

        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED, suspended_at=None)
        before = timezone.now()

        _clock().date_the_suspended(global_apps, _SchemaEditor())

        business.refresh_from_db()
        assert business.suspended_at is not None
        assert business.suspended_at >= before

    def test_a_dated_suspension_and_a_running_business_are_left_as_they_are(self, business, make_user):
        from hubs.models import Hub

        dated = create_business(make_user("dora@example.com"), name="Dora's")
        since = timezone.now() - timedelta(days=40)
        Hub.objects.filter(pk=dated.pk).update(status=Hub.Status.SUSPENDED, suspended_at=since)

        _clock().date_the_suspended(global_apps, _SchemaEditor())

        assert Hub.objects.get(pk=dated.pk).suspended_at == since
        assert Hub.objects.get(pk=business.pk).suspended_at is None

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        assert [name for name in _imported_modules(_clock()) if name.startswith("hubs")] == []


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_clock_and_forward_again_dating_the_suspended(owner, plans):
    """``migrate hubs 0015`` and back: the deploy itself dates a business that was already suspended (the deferred
    foreign key checks run at once, as in the round trip of 0006)."""
    from hubs.models import Hub

    business = create_business(owner)
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED)
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    call_command("migrate", "hubs", "0015", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)

    assert Hub.objects.get(pk=business.pk).suspended_at is not None
