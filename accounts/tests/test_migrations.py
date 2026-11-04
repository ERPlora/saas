"""Data migrations of accounts: the prefixed customer roles, the platform's ``support`` group and the retirement of the
copy of a business's members, its table included.

Customer roles (``hub_*``) live in ``hubs.HubMember``; platform roles are Django's superuser and the ``support`` group
(staff, view only on accounts). Each migration is reversible.
"""

import functools
from importlib import import_module

import pytest
from auditlog.models import LogEntry
from django.apps import apps as global_apps
from django.contrib.admin.models import CHANGE
from django.contrib.admin.models import LogEntry as AdminLogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

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
    @pytest.fixture(autouse=True)
    def the_table_of_the_copy(self):
        """What this migration read and wrote: ``0012`` dropped it, and the test's transaction takes this one away."""
        with connection.schema_editor() as editor:
            editor.create_model(_copy())

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


def _go_back_to_0011() -> None:
    """Where the table still was: ``0012`` undone, with the checks a migration's own COMMIT would run first."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    call_command("migrate", "accounts", "0011", verbosity=0)


class TestTheCopyOfTheMembersRetires:
    """0011 (saas#199): the model leaves the code and its table stays, without its foreign key, for the tasks of the
    previous release, which go on reading and writing it until they stop. Going back rebuilds it from the members: the
    Hub trusts the role the SaaS answers, and a copy left as it was would let in whoever has left since."""

    @pytest.fixture(autouse=True)
    def at_0011(self):
        _go_back_to_0011()

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
        call_command("migrate", "accounts", "0011", verbosity=0)

        assert self._foreign_keys() == []
        assert list(copy.objects.values_list("hub_slug", "user_id", "role")) == [("a", ana.pk, "hub_owner")]


class TestTheTableOfTheCopyGoes:
    """0012 (saas#220), the contract step of 0011: the table, its four permissions and its content type go.

    ``auditlog.LogEntry.content_type`` cascades and ``cleanup_old_logs`` keeps 90 days of the entries of that type, so
    the content type stays while one of them names it: ``cleanup_old_logs`` takes it with the last one. Going back
    recreates the table empty, as 0011 left it, and from there 0011's own way back rebuilds it from the members."""

    KIND = {"app_label": "accounts", "model": "hubmembership"}
    PERMISSIONS = {"add_hubmembership", "change_hubmembership", "delete_hubmembership", "view_hubmembership"}

    def _kind(self):
        return ContentType.objects.filter(**self.KIND)

    @staticmethod
    def _permissions():
        return Permission.objects.filter(content_type__app_label="accounts", codename__endswith="_hubmembership")

    @staticmethod
    def _table_exists() -> bool:
        return "accounts_hubmembership" in connection.introspection.table_names()

    @staticmethod
    def _check_now() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def _audit_entry(self) -> LogEntry:
        return LogEntry.objects.create(
            content_type=self._kind().get(),
            object_pk="1",
            object_repr="ana@example.com @ bar-pepe (Admin)",
            action=LogEntry.Action.UPDATE,
            changes={"role": ["hub_admin", "hub_owner"]},
        )

    def test_the_model_and_the_migrations_agree(self):
        call_command("makemigrations", "accounts", "--check", "--dry-run", verbosity=0)

    def test_its_state_holds_all_that_points_at_a_content_type(self):
        """A cascade in a migration reaches only the models of its own state: without these, deleting the type would
        fail at the COMMIT on a line of the admin history, and the look for audit entries would not even run."""
        state = MigrationLoader(connection).project_state(("accounts", "0012_drop_the_hub_membership_copy"))

        assert {("admin", "logentry"), ("auditlog", "logentry"), ("auth", "permission")} <= set(state.models)

    def test_the_table_is_gone(self):
        assert not self._table_exists()

    def test_no_permission_of_it_is_left_and_support_no_longer_views_it(self):
        assert not self._permissions().exists()
        assert not any("hubmembership" in permission for permission in _perms(Group.objects.get(name="support")))

    def test_with_no_audit_entry_of_that_type_its_content_type_goes(self):
        assert not self._kind().exists()

    def test_an_audit_entry_of_that_type_stays_and_keeps_its_content_type(self):
        _go_back_to_0011()
        entry = self._audit_entry()
        self._check_now()

        call_command("migrate", "accounts", verbosity=0)

        assert not self._table_exists()
        assert not self._permissions().exists()
        assert LogEntry.objects.get(pk=entry.pk).content_type == self._kind().get()

    def test_a_line_of_the_admin_history_stays_without_its_type_when_the_type_goes(self, ana):
        _go_back_to_0011()
        line = AdminLogEntry.objects.create(
            user=ana, content_type=self._kind().get(), object_id="1", object_repr="ana @ a", action_flag=CHANGE
        )
        self._check_now()

        call_command("migrate", "accounts", verbosity=0)
        self._check_now()

        assert not self._kind().exists()
        assert AdminLogEntry.objects.get(pk=line.pk).content_type is None

    def test_going_back_recreates_the_table_empty_as_0011_left_it(self):
        _go_back_to_0011()

        assert self._table_exists()
        assert not _copy().objects.exists()
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(cursor, "accounts_hubmembership")}
            constraints = connection.introspection.get_constraints(cursor, "accounts_hubmembership")
        assert columns == {"id", "user_id", "hub_slug", "role", "created_at"}
        assert constraints["accounts_membership_user_hub"]["unique"]
        assert constraints["accounts_membership_user_hub"]["columns"] == ["user_id", "hub_slug"]
        assert not any(constraint["foreign_key"] for constraint in constraints.values())

    def test_going_back_gives_back_the_content_type_the_permissions_and_what_support_views(self):
        _go_back_to_0011()

        assert self._kind().exists()
        assert set(self._permissions().values_list("codename", flat=True)) == self.PERMISSIONS
        assert self._permissions().get(codename="view_hubmembership").name == "Can view hub membership"
        assert "accounts.view_hubmembership" in _perms(Group.objects.get(name="support"))

    def test_going_back_keeps_the_content_type_an_audit_entry_kept(self):
        _go_back_to_0011()
        entry = self._audit_entry()
        self._check_now()
        call_command("migrate", "accounts", verbosity=0)

        _go_back_to_0011()

        assert LogEntry.objects.get(pk=entry.pk).content_type == self._kind().get()
        assert self._kind().count() == 1

    def test_going_back_without_the_support_group_gives_nothing_and_does_not_fail(self):
        Group.objects.filter(name="support").delete()

        _go_back_to_0011()

        assert set(self._permissions().values_list("codename", flat=True)) == self.PERMISSIONS
        assert not Group.objects.filter(name="support").exists()

    def test_going_all_the_way_back_rebuilds_the_copy_from_the_members(self, ana):
        enter(ana, "a", "hub_owner")
        _go_back_to_0011()
        self._check_now()

        call_command("migrate", "accounts", "0010", verbosity=0)

        assert list(_copy().objects.values_list("hub_slug", "user_id", "role")) == [("a", ana.pk, "hub_owner")]

    def test_it_is_applied_and_it_can_go_back_and_forward_again(self):
        _go_back_to_0011()
        self._check_now()
        call_command("migrate", "accounts", verbosity=0)

        applied = MigrationRecorder(connection).applied_migrations()
        assert ("accounts", "0012_drop_the_hub_membership_copy") in applied
        assert not self._table_exists()
        assert not self._kind().exists()

    def test_every_operation_of_accounts_can_be_reversed(self):
        migrations = [
            migration
            for (app, _), migration in MigrationLoader(None, ignore_no_migrations=True).disk_migrations.items()
            if app == "accounts"
        ]

        assert migrations
        assert all(operation.reversible for migration in migrations for operation in migration.operations)
