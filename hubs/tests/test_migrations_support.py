"""Support sees the account plane and the daily usage of every business, view only (hubs 0007 and 0024)."""

from importlib import import_module

import pytest
from django.apps import apps as global_apps

from hubs.tests.data_migrations import _SchemaEditor

# --- 0007 and 0024: support sees the account plane and the daily usage (view only) -------------------

SUPPORT_VIEWS_THE_DAILY_USAGE = "hubs.view_hubusagedaily"
SUPPORT_VIEWS = {
    "hubs.view_hub",
    "hubs.view_hubmember",
    "hubs.view_hubownershiptransfer",
    "hubs.view_billingprofile",
    "hubs.view_subscription",
    "hubs.view_subscriptionitem",
    "hubs.view_sessionrevocation",
    SUPPORT_VIEWS_THE_DAILY_USAGE,
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
    assert _hubs_perms_of_support() == {SUPPORT_VIEWS_THE_DAILY_USAGE}

    support.let_support_view(global_apps, _SchemaEditor())
    support.let_support_view(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == SUPPORT_VIEWS


def _support_views_the_daily_usage():
    return import_module("hubs.migrations.0024_support_views_the_daily_usage")


@pytest.mark.django_db
def test_reverting_0024_takes_only_the_daily_usage_away_and_applying_it_again_restores_it():
    support = _support_views_the_daily_usage()

    support.stop_support_viewing(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == SUPPORT_VIEWS - {SUPPORT_VIEWS_THE_DAILY_USAGE}

    support.let_support_view(global_apps, _SchemaEditor())
    support.let_support_view(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == SUPPORT_VIEWS


@pytest.mark.django_db
def test_0024_creates_the_permission_when_it_does_not_exist_yet():
    """On a fresh database Django creates the permissions after migrating."""
    from django.contrib.auth.models import Permission

    Permission.objects.filter(content_type__app_label="hubs", codename="view_hubusagedaily").delete()
    assert SUPPORT_VIEWS_THE_DAILY_USAGE not in _hubs_perms_of_support()

    _support_views_the_daily_usage().let_support_view(global_apps, _SchemaEditor())

    assert _hubs_perms_of_support() == SUPPORT_VIEWS


@pytest.mark.django_db
def test_0024_without_the_group_gives_nothing_and_does_not_fail():
    from django.contrib.auth.models import Group, Permission

    Group.objects.filter(name="support").delete()
    support = _support_views_the_daily_usage()

    support.let_support_view(global_apps, _SchemaEditor())
    support.stop_support_viewing(global_apps, _SchemaEditor())

    assert not Group.objects.filter(name="support").exists()
    assert Permission.objects.filter(content_type__app_label="hubs", codename="view_hubusagedaily").exists()
