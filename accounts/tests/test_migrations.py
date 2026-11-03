"""Data migrations of accounts: the prefixed customer roles, the platform's ``support`` group and the retirement of the
copy of a business's members.

Customer roles (``hub_*``) live in ``hubs.HubMember``; platform roles are Django's superuser and the ``support`` group
(staff, view only on accounts). Each migration is reversible.
"""

import functools
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from accounts.tests.conftest import enter

pytestmark = pytest.mark.django_db



@functools.cache
def _with_the_copy():
    """The apps as they were the last time ``HubMembership`` was a model (``0011`` took it out)."""
    return (
        MigrationLoader(connection)
        .project_state([("accounts", "0010_user_store_review_account"), ("hubs", "0024_support_views_the_daily_usage")])
        .apps
    )


def _copy():
    return _with_the_copy().get_model("accounts", "HubMembership")


def _migration(name: str):
    return import_module(f"accounts.migrations.{name}")


def _roles():
    return _migration("0002_prefixed_hub_roles")


def _support():
    return _migration("0003_support_group")


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _perms(group: Group) -> set[str]:
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.select_related("content_type")}


class TestSupportGroup:
    def test_exists_after_migrating_with_view_only_permissions_on_accounts(self):
        group = Group.objects.get(name="support")

        # Of accounts' models these (the Account page's, 0006, L3-A); hubs adds the views of the account plane (hubs
        # 0007, L1-A2).
        assert {perm for perm in _perms(group) if perm.startswith("accounts.")} == {
            "accounts.view_user",
            "accounts.view_hubmembership",
            "accounts.view_authexchangecode",
            "accounts.view_apikey",
            "accounts.view_userpreferences",
            "accounts.view_profilephoto",
        }
        assert not any(p.codename.startswith(("add_", "change_", "delete_")) for p in group.permissions.all())

    def test_reverting_removes_the_group_and_applying_again_restores_it(self):
        _support().remove_support_group(_with_the_copy(), _SchemaEditor())
        assert not Group.objects.filter(name="support").exists()

        _support().create_support_group(_with_the_copy(), _SchemaEditor())
        _support().create_support_group(_with_the_copy(), _SchemaEditor())

        assert Group.objects.filter(name="support").count() == 1
        assert len(_perms(Group.objects.get(name="support"))) == 3

    def test_creates_the_view_permissions_when_they_do_not_exist_yet(self):
        # On a fresh database, Django's own permissions arrive after the migrations (post_migrate).
        Permission.objects.filter(content_type__app_label="accounts", codename__startswith="view_").delete()
        _support().remove_support_group(_with_the_copy(), _SchemaEditor())

        _support().create_support_group(_with_the_copy(), _SchemaEditor())

        assert len(_perms(Group.objects.get(name="support"))) == 3


class TestPrefixedRoles:
    def test_roles_saved_without_the_prefix_get_it_and_lose_it_on_revert(self, ana):
        copy = _copy()
        copy.objects.bulk_create(
            [
                copy(user_id=ana.pk, hub_slug="a", role="admin"),
                copy(user_id=ana.pk, hub_slug="b", role="manager"),
                copy(user_id=ana.pk, hub_slug="c", role="employee"),
                copy(user_id=ana.pk, hub_slug="d", role="hub_owner"),
            ]
        )

        _roles().add_prefix(_with_the_copy(), _SchemaEditor())
        assert dict(copy.objects.values_list("hub_slug", "role")) == {
            "a": "hub_admin",
            "b": "hub_manager",
            "c": "hub_employee",
            "d": "hub_owner",
        }

        _roles().remove_prefix(_with_the_copy(), _SchemaEditor())
        # Before this migration there was no owner: the owner goes back as an admin.
        assert dict(copy.objects.values_list("hub_slug", "role")) == {
            "a": "admin",
            "b": "manager",
            "c": "employee",
            "d": "admin",
        }


class TestSupportSeesTheAccountPage:
    """0006: ``support`` views the account's preferences, photo, API keys and sessions (allauth.usersessions), and
    changes nothing; reversible."""

    def _migration(self):
        return _migration("0006_support_views_account_settings")

    def test_after_migrating(self):
        group = Group.objects.get(name="support")

        assert "usersessions.view_usersession" in _perms(group)

    def test_reverting_takes_them_away_and_applying_again_gives_them_back(self):
        group = Group.objects.get(name="support")

        self._migration().stop_support_viewing(global_apps, _SchemaEditor())
        assert not {"accounts.view_apikey", "usersessions.view_usersession"} & _perms(group)

        self._migration().let_support_view(global_apps, _SchemaEditor())
        assert {"accounts.view_apikey", "usersessions.view_usersession"} <= _perms(group)


class TestTheCopyOfTheMembersRetires:
    """0011 (saas#199): the model leaves the code and its table stays, without its foreign key, for the tasks of the
    previous release, which go on reading and writing it until they stop. Dropping it is the contract step of a later
    release. Going back rebuilds it from the members: the Hub trusts the role the SaaS answers, and a copy left as it
    was would let in whoever has left since."""

    @staticmethod
    def _foreign_keys() -> list[str]:
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "accounts_hubmembership")
        return [name for name, constraint in constraints.items() if constraint["foreign_key"]]

    @staticmethod
    def _check_now() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_the_table_stays_without_its_foreign_key(self):
        assert "accounts_hubmembership" in connection.introspection.table_names()
        assert self._foreign_keys() == []

    def test_the_model_and_the_migrations_agree(self):
        call_command("makemigrations", "accounts", "--check", "--dry-run", verbosity=0)

    def test_an_account_with_a_row_left_in_the_table_can_be_deleted(self, ana):
        """The code no longer knows the table, so nothing cascades: with its foreign key this delete would fail."""
        _copy().objects.create(user_id=ana.pk, hub_slug="a", role="hub_owner")

        ana.delete()
        self._check_now()

        assert not get_user_model().objects.filter(email="ana@example.com").exists()

    def test_going_back_rebuilds_it_from_the_members_and_the_foreign_key_returns(self, ana, django_user_model):
        from hubs.models import Hub

        gone = django_user_model.objects.create_user(email="gone@example.com", password=None)
        invited = django_user_model.objects.create_user(email="invited@example.com", password=None)
        left = django_user_model.objects.create_user(email="left@example.com", password=None)
        enter(ana, "a", "hub_owner")
        enter(invited, "a", "hub_employee", accepted=False)
        enter(ana, "closing", "hub_owner", status=Hub.Status.DELETING)
        enter(ana, "closed", "hub_owner", status=Hub.Status.DELETED)
        copy = _copy()
        # Written by the previous release: somebody who left the business, and an account deleted since.
        copy.objects.create(user_id=left.pk, hub_slug="a", role="hub_admin")
        copy.objects.create(user_id=gone.pk, hub_slug="b", role="hub_owner")
        gone.delete()
        self._check_now()

        call_command("migrate", "accounts", "0010", verbosity=0)

        assert list(copy.objects.values_list("hub_slug", "user_id", "role")) == [("a", ana.pk, "hub_owner")]
        assert len(self._foreign_keys()) == 1

        self._check_now()
        call_command("migrate", "accounts", verbosity=0)

        assert self._foreign_keys() == []
        assert list(copy.objects.values_list("hub_slug", "user_id", "role")) == [("a", ana.pk, "hub_owner")]
