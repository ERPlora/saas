"""The migrations of hubs are reversible and match the models.

The round trip runs inside the test's transaction (Postgres DDL is transactional), so it leaves the
test database as it found it.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

HUBS_TABLES = {
    "hubs_plan",
    "hubs_sector",
    "hubs_businesstype",
    # The account plane of a business (0002).
    "hubs_billingprofile",
    "hubs_hub",
    "hubs_hubmember",
    "hubs_hubownershiptransfer",
    "hubs_subscription",
    "hubs_subscriptionitem",
}


def _tables():
    return set(connection.introspection.table_names())


def test_every_operation_of_hubs_can_be_reversed():
    migrations = [m for (app, _), m in MigrationLoader(None, ignore_no_migrations=True).disk_migrations.items() if app == "hubs"]

    assert migrations
    assert all(operation.reversible for migration in migrations for operation in migration.operations)


@pytest.mark.django_db
def test_hubs_migrates_to_zero_and_back():
    call_command("migrate", "hubs", "zero", verbosity=0)
    assert _tables().isdisjoint(HUBS_TABLES)

    call_command("migrate", "hubs", verbosity=0)
    assert HUBS_TABLES <= _tables()


@pytest.mark.django_db
def test_the_models_and_the_migrations_agree():
    """``makemigrations --check`` exits non-zero when a model changed without its migration."""
    call_command("makemigrations", "hubs", "--check", "--dry-run", verbosity=0)


# --- 0006: the hubs of the phase-1 seed become businesses (plan 2026-10-13, L1-A2) -----------------

from datetime import timedelta  # noqa: E402
from importlib import import_module  # noqa: E402

from django.apps import apps as global_apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

ADOPTION = "0006_adopt_seed_hubs"


def _adoption():
    return import_module(f"hubs.migrations.{ADOPTION}")


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _adopt():
    _adoption().adopt_seed_hubs(global_apps, _SchemaEditor())


@pytest.mark.django_db
class TestTheSeedHubsBecomeBusinesses:
    @pytest.fixture
    def people(self):
        make = get_user_model().objects.create_user
        return {
            "olga": make(email="olga@example.com", password=None, language="es"),
            "eva": make(email="eva@example.com", password=None),
            "ana": make(email="ana@example.com", password=None),
        }

    def _membership(self, user, slug, role, days_ago=0):
        from accounts.models import HubMembership

        return HubMembership.objects.create(
            user=user, hub_slug=slug, role=role, created_at=timezone.now() - timedelta(days=days_ago)
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

    def test_without_the_free_plan_seeded_there_is_no_subscription(self, people):
        from hubs.models import Hub, Subscription

        self._membership(people["olga"], "bar-pepe", "hub_owner")

        _adopt()

        assert not Subscription.objects.filter(hub=Hub.objects.get(slug="bar-pepe")).exists()

    def test_without_an_owner_the_oldest_member_becomes_it_in_both_tables(self, people):
        from accounts.models import HubMembership
        from hubs.models import HubMember

        self._membership(people["ana"], "bar-pepe", "hub_employee", days_ago=1)
        self._membership(people["eva"], "bar-pepe", "hub_admin", days_ago=5)

        _adopt()

        assert HubMember.objects.get(user=people["eva"]).role == "hub_owner"
        assert HubMembership.objects.get(user=people["eva"]).role == "hub_owner"
        assert HubMember.objects.get(user=people["ana"]).role == "hub_employee"

    def test_two_owners_keep_the_oldest_and_the_other_becomes_admin(self, people):
        from accounts.models import HubMembership
        from hubs.models import HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner", days_ago=3)
        self._membership(people["eva"], "bar-pepe", "hub_owner", days_ago=1)

        _adopt()

        assert HubMember.objects.get(user=people["olga"]).role == "hub_owner"
        assert HubMember.objects.get(user=people["eva"]).role == "hub_admin"
        assert HubMembership.objects.get(user=people["eva"]).role == "hub_admin"

    @pytest.mark.parametrize("slug", ["www", "hubs", "-bad-", "xn--abc"])
    def test_a_slug_that_is_no_hubs_gives_no_business_and_its_dead_rows_go(self, people, slug):
        """``is_hub_slug`` already refused them at the jump: they opened nothing."""
        from accounts.models import HubMembership
        from hubs.models import Hub

        self._membership(people["olga"], slug, "hub_owner")

        _adopt()

        assert not Hub.objects.exists()
        assert not HubMembership.objects.exists()

    def test_a_business_of_the_panel_has_its_mirror_put_right(self, business, owner, people):
        """A row written around ``sync_access`` (``demo_seed`` before L1-A2) is dropped, a missing one is added."""
        from accounts.models import HubMembership
        from hubs import queries

        HubMembership.objects.filter(hub_slug=business.slug).delete()
        self._membership(people["ana"], business.slug, "hub_admin")

        _adopt()

        assert queries.verify_access_mirror() == []
        assert list(HubMembership.objects.values_list("user_id", "role")) == [(owner.pk, "hub_owner")]

    def test_a_deleted_business_keeps_no_access(self, business, owner):
        from accounts.models import HubMembership
        from hubs.models import Hub

        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        _adopt()

        assert not HubMembership.objects.exists()

    def test_after_it_both_tables_agree_and_running_it_again_changes_nothing(self, people, business):
        from hubs import queries
        from hubs.models import Hub, HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        self._membership(people["eva"], "cafe-lola", "hub_manager")

        _adopt()
        counts = (Hub.objects.count(), HubMember.objects.count())
        _adopt()

        assert queries.verify_access_mirror() == []
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

        _adoption().keep_the_businesses(global_apps, _SchemaEditor())
        _adopt()

        assert list(Hub.objects.values_list("pk", flat=True)) == [first]


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_adoption_and_forward_again(django_user_model):
    """``migrate hubs 0005`` and back: the round trip of the data migration (its reverse keeps the rows)."""
    from accounts.models import HubMembership
    from hubs.models import Hub

    olga = django_user_model.objects.create_user(email="olga@example.com", password=None)
    HubMembership.objects.create(user=olga, hub_slug="bar-pepe", role="hub_owner")

    call_command("migrate", "hubs", "0005", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)

    assert Hub.objects.filter(slug="bar-pepe", status="active").exists()


# --- 0007: support sees the account plane (view only) ----------------------------------------------

SUPPORT_VIEWS = {
    "hubs.view_hub",
    "hubs.view_hubmember",
    "hubs.view_hubownershiptransfer",
    "hubs.view_billingprofile",
    "hubs.view_subscription",
    "hubs.view_subscriptionitem",
    "hubs.view_sessionrevocation",
}


def _hubs_perms_of_support():
    from django.contrib.auth.models import Group

    group = Group.objects.get(name="support")
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.select_related("content_type")
            if p.content_type.app_label == "hubs"}


@pytest.mark.django_db
def test_support_views_the_account_plane_and_nothing_more():
    assert _hubs_perms_of_support() == SUPPORT_VIEWS


@pytest.mark.django_db
def test_reverting_0007_takes_the_views_away_and_applying_it_again_restores_them():
    support = import_module("hubs.migrations.0007_support_views_the_account_plane")

    support.stop_support_viewing(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == set()

    support.let_support_view(global_apps, _SchemaEditor())
    support.let_support_view(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == SUPPORT_VIEWS
