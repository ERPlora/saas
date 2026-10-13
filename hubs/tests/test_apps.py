"""hubs is a platform app at the root of saas-next, next to ``base/`` (round 15, PLAN §20.2; §21.4)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import checks
from django.utils import translation
from live.meta import LiveAppConfig, all_live_app_configs, module_configs


def hubs():
    return apps.get_app_config("hubs")


def test_hubs_is_a_platform_app_at_the_project_root():
    config = hubs()

    assert (config.name, config.label) == ("hubs", "hubs")
    assert type(config).__name__ == "HubsConfig"
    assert Path(config.path) == settings.BASE_DIR / "hubs"
    # Always on: a platform LiveAppConfig, never a module a hub turns on and off.
    assert isinstance(config, LiveAppConfig)
    assert config.kind == "platform"
    assert config in all_live_app_configs()
    assert config not in module_configs()


def test_hubs_declares_no_module_fields():
    """live.checks (d): a platform app leaves requires, navigation, category and premium alone."""
    config = hubs()

    assert (config.requires, config.navigation, config.category, config.premium) == ([], [], None, False)


def test_hubs_sits_between_what_it_reads_and_what_reads_it():
    """The SaaS's graph (PLAN §21.4): hubs reads accounts and apps, public reads hubs. Without a
    ``requires`` between platform apps, INSTALLED_APPS keeps that order."""
    installed = settings.INSTALLED_APPS
    position = installed.index("hubs")

    assert all(installed.index(app) < position for app in ("accounts", "apps") if app in installed)
    assert all(installed.index(app) > position for app in ("public",) if app in installed)


def test_the_admin_names_the_app_in_both_languages():
    with translation.override("en"):
        assert str(hubs().verbose_name) == "Businesses"
    with translation.override("es"):
        assert str(hubs().verbose_name) == "Negocios"


def test_every_installed_app_passes_the_live_checks():
    assert checks.run_checks(tags=["live"]) == []


def test_every_signed_in_account_may_read_and_act_on_its_businesses():
    """The role ``account`` (base.operations) gets both permissions; which business and what on it is
    decided inside each operation by the account's ``HubMember`` role (plan 2026-10-13 §3)."""
    config = hubs()

    assert config.permissions == ["hubs.view", "hubs.manage"]
    assert config.role_permissions == {"account": ["hubs.*"]}
    assert checks.run_checks(tags=["live"]) == []
