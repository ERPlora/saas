"""billing is a platform app at the root of saas-next, next to ``base/`` (round 15, PLAN §20.2; plan 2026-10-13 §3)."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import checks
from django.utils import translation
from live.meta import LiveAppConfig, all_live_app_configs, module_configs


def billing():
    return apps.get_app_config("billing")


def test_billing_is_a_platform_app_at_the_project_root():
    config = billing()

    assert (config.name, config.label) == ("billing", "billing")
    assert type(config).__name__ == "BillingConfig"
    assert Path(config.path) == settings.BASE_DIR / "billing"
    # Always on: a platform LiveAppConfig, never a module a hub turns on and off.
    assert isinstance(config, LiveAppConfig)
    assert config.kind == "platform"
    assert config in all_live_app_configs()
    assert config not in module_configs()


def test_billing_declares_no_module_fields():
    """live.checks (d): a platform app leaves requires, navigation, category and premium alone."""
    config = billing()

    assert (config.requires, config.navigation, config.category, config.premium) == (
        [],
        [],
        None,
        False,
    )


def test_billing_comes_after_what_it_reads():
    """The SaaS's graph ``accounts ← hubs ← billing`` (plan §2, point 15): billing reads the payer of
    a business (``hubs.BillingProfile``). Without a ``requires`` between platform apps, INSTALLED_APPS
    keeps that order."""
    installed = settings.INSTALLED_APPS

    assert (
        installed.index("accounts")
        < installed.index("hubs")
        < installed.index("billing")
    )


def test_the_admin_names_the_app_in_both_languages():
    with translation.override("en"):
        assert str(billing().verbose_name) == "Billing"
    with translation.override("es"):
        assert str(billing().verbose_name) == "Facturación"


def test_a_signed_in_account_previews_checks_and_pays_but_does_not_manage_billing():
    """The role ``account`` (base.operations) may preview the tax, check a VAT number and reach the
    operations that pay (``billing.pay``: buy, change, cancel, the portal), each of which checks that the
    account OWNS the business (round 17 §2.7); ``billing.manage`` is not handed to every account (review of
    L2-A)."""
    config = billing()

    assert config.permissions == ["billing.view", "billing.vat_check", "billing.pay", "billing.manage"]
    assert config.role_permissions == {"account": ["billing.view", "billing.vat_check", "billing.pay"]}


def test_every_installed_app_passes_the_live_checks():
    assert checks.run_checks(tags=["live"]) == []
