"""fiscal is a platform app at the root of saas-next, next to ``hubs/`` (round 15, PLAN §20.2): the review of
the documentation a hub sends so ERPlora can file its VeriFactu records (plan 2026-10-15)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.meta import (
    LiveAppConfig,
    all_live_app_configs,
    module_configs,
    permissions_for_role,
)

from base.operations import ACCOUNT_ROLE


def fiscal():
    return apps.get_app_config("fiscal")


def test_fiscal_is_a_platform_app_at_the_project_root():
    config = fiscal()

    assert (config.name, config.label) == ("fiscal", "fiscal")
    assert type(config).__name__ == "FiscalConfig"
    assert Path(config.path) == settings.BASE_DIR / "fiscal"
    assert isinstance(config, LiveAppConfig)
    assert config.kind == "platform"
    assert config in all_live_app_configs()
    assert config not in module_configs()


def test_fiscal_declares_no_module_fields():
    config = fiscal()

    assert (config.requires, config.navigation, config.category, config.premium) == (
        [],
        [],
        None,
        False,
    )


def test_fiscal_comes_after_the_businesses_it_reads():
    installed = settings.INSTALLED_APPS

    assert installed.index("fiscal") > installed.index("hubs")


def test_an_account_may_only_read_the_state_of_its_businesses_documentation():
    """``fiscal.view`` is every account's (each operation checks the business); ``fiscal.manage`` is the
    platform's and the staff's alone, never a role's."""
    granted = permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)

    assert set(fiscal().permissions) == {"fiscal.view", "fiscal.manage"}
    assert "fiscal.view" in granted
    assert "fiscal.manage" not in granted


def test_the_admin_names_the_app_in_both_languages():
    with translation.override("en"):
        assert str(fiscal().verbose_name) == "Fiscal documentation"
    with translation.override("es"):
        assert str(fiscal().verbose_name) == "Documentación fiscal"
