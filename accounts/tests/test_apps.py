"""accounts is a platform app at the root of saas-next, next to ``base/`` (round 15, PLAN §20.2)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.meta import LiveAppConfig, all_live_app_configs, module_configs


def test_accounts_is_a_platform_app_at_the_project_root():
    config = apps.get_app_config("accounts")

    assert (config.name, config.label) == ("accounts", "accounts")
    assert Path(config.path) == settings.BASE_DIR / "accounts"
    # Always on: a platform LiveAppConfig, never a module a hub turns on and off.
    assert isinstance(config, LiveAppConfig)
    assert config.kind == "platform"
    assert config in all_live_app_configs()
    assert config not in module_configs()


def test_its_name_is_translated():
    """The admin's index lists it by ``verbose_name``."""
    config = apps.get_app_config("accounts")

    assert str(config.verbose_name) == "Accounts"
    with translation.override("es"):
        assert str(config.verbose_name) == "Cuentas"
