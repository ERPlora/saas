"""Data migrations of accounts: the prefixed customer roles and the platform's ``support`` group.

Customer roles (``hub_*``) live in ``HubMembership``; platform roles are Django's superuser and
the ``support`` group (staff, view only on accounts). Each migration is reversible.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.contrib.auth.models import Group, Permission
from django.db import connection

from accounts.models import HubMembership

pytestmark = pytest.mark.django_db



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

        assert _perms(group) == {
            "accounts.view_user",
            "accounts.view_hubmembership",
            "accounts.view_authexchangecode",
        }
        assert not any(p.codename.startswith(("add_", "change_", "delete_")) for p in group.permissions.all())

    def test_reverting_removes_the_group_and_applying_again_restores_it(self):
        _support().remove_support_group(global_apps, _SchemaEditor())
        assert not Group.objects.filter(name="support").exists()

        _support().create_support_group(global_apps, _SchemaEditor())
        _support().create_support_group(global_apps, _SchemaEditor())

        assert Group.objects.filter(name="support").count() == 1
        assert len(_perms(Group.objects.get(name="support"))) == 3

    def test_creates_the_view_permissions_when_they_do_not_exist_yet(self):
        # On a fresh database, Django's own permissions arrive after the migrations (post_migrate).
        Permission.objects.filter(content_type__app_label="accounts", codename__startswith="view_").delete()
        _support().remove_support_group(global_apps, _SchemaEditor())

        _support().create_support_group(global_apps, _SchemaEditor())

        assert len(_perms(Group.objects.get(name="support"))) == 3


class TestPrefixedRoles:
    def test_roles_saved_without_the_prefix_get_it_and_lose_it_on_revert(self, ana):
        HubMembership.objects.bulk_create(
            [
                HubMembership(user=ana, hub_slug="a", role="admin"),
                HubMembership(user=ana, hub_slug="b", role="manager"),
                HubMembership(user=ana, hub_slug="c", role="employee"),
                HubMembership(user=ana, hub_slug="d", role="hub_owner"),
            ]
        )

        _roles().add_prefix(global_apps, _SchemaEditor())
        assert dict(HubMembership.objects.values_list("hub_slug", "role")) == {
            "a": "hub_admin",
            "b": "hub_manager",
            "c": "hub_employee",
            "d": "hub_owner",
        }

        _roles().remove_prefix(global_apps, _SchemaEditor())
        # Before this migration there was no owner: the owner goes back as an admin.
        assert dict(HubMembership.objects.values_list("hub_slug", "role")) == {
            "a": "admin",
            "b": "manager",
            "c": "employee",
            "d": "admin",
        }
