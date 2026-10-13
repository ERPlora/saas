"""apps is the platform app of the app catalog (round 16, PLAN §21.1 point 10, spec decision 18)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.meta import LiveAppConfig, all_live_app_configs, module_configs


def test_apps_is_a_platform_app_at_the_project_root():
    config = apps.get_app_config("apps")

    assert (config.name, config.label) == ("apps", "apps")
    assert Path(config.path) == settings.BASE_DIR / "apps"
    # Always on: a platform LiveAppConfig, never a module a hub turns on and off.
    assert isinstance(config, LiveAppConfig)
    assert config.kind == "platform"
    assert config in all_live_app_configs()
    assert config not in module_configs()


def test_it_is_installed_after_accounts_and_before_the_apps_that_read_it():
    """``hubs`` (``BusinessType.clean()``) and ``public`` (the store) read the catalog."""
    installed = settings.INSTALLED_APPS

    assert (
        installed.index("accounts") < installed.index("apps") < installed.index("hubs")
    )
    assert installed.index("apps") < installed.index("public")


def test_its_name_is_translated():
    """The admin's index lists it by ``verbose_name``."""
    config = apps.get_app_config("apps")

    assert str(config.verbose_name) == "Apps"
    with translation.override("es"):
        assert str(config.verbose_name) == "Apps"
