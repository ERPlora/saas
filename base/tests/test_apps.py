"""The base app of saas-next is the platform: a LiveAppConfig of kind "platform", always on, never a module.

Round 15 (PLAN §20) supersedes "base is a plain AppConfig, not a LiveAppConfig": every app of ours
extends LiveAppConfig so the API mounts its router and the live checks see it, and ``kind`` tells
the platform from the modules a hub turns on and off (saas-next has no modules).
"""

from django.apps import apps
from django.core import checks
from live.meta import LiveAppConfig, all_live_app_configs, module_configs


def base():
    return apps.get_app_config("base")


def test_base_is_the_platform_app():
    config = base()

    assert (config.name, config.label) == ("base", "base")
    assert str(config.verbose_name) == "Base"
    assert isinstance(config, LiveAppConfig)
    assert type(config).__name__ == "BaseConfig"
    assert config.kind == "platform"


def test_base_is_one_of_ours_but_not_a_module():
    assert base() in all_live_app_configs()
    assert base() not in module_configs()


def test_base_declares_no_module_fields():
    config = base()

    assert (config.requires, config.navigation, config.category, config.premium) == ([], [], None, False)


def test_every_installed_app_passes_the_live_checks():
    """base and accounts as platform apps, with no module fields (live.checks)."""
    assert checks.run_checks(tags=["live"]) == []
