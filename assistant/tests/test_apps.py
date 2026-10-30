"""The assistant app is a platform app of the SaaS: always on, no module fields; configuring it is the platform's and
the staff's, asking the panel's assistant every account's.

Its name in the admin goes through the catalog (saas#2489 of the old product: «Assistant (Hub ↔ Cloud ↔ LLM)» was a
literal, so the Spanish admin showed it in English).
"""

from django.apps import apps
from django.utils import translation
from live.meta import LiveAppConfig


def test_it_is_an_installed_platform_app():
    config = apps.get_app_config("assistant")

    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == ("assistant", "assistant", "platform")


def test_no_account_configures_the_ai():
    """Only the platform and ERPlora's staff configure the AI: no signed-in account reaches its operations."""
    from live.meta import all_live_app_configs, permissions_for_role

    assert "assistant.manage" in apps.get_app_config("assistant").permissions
    assert "assistant.manage" not in permissions_for_role(all_live_app_configs(), "account")


def test_every_account_may_ask_the_panels_assistant():
    """PLAN-SAAS §23: the assistant of erplora.com's own panel is every signed-in account's (``assistant.ask``)."""
    from live.meta import all_live_app_configs, permissions_for_role

    config = apps.get_app_config("assistant")

    assert config.permissions == ["assistant.manage", "assistant.ask"]
    assert config.role_permissions == {"account": ["assistant.ask"]}
    assert "assistant.ask" in permissions_for_role(all_live_app_configs(), "account")


def test_its_name_in_the_admin_is_translated():
    config = apps.get_app_config("assistant")

    assert str(config.verbose_name) == "AI assistant"
    with translation.override("es"):
        assert str(config.verbose_name) == "Asistente de IA"
