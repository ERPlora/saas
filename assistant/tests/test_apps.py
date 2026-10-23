"""The assistant app is a platform app of the SaaS: always on, no module fields, its one permission the platform's.

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


def test_no_account_gets_its_permission():
    """Only the platform and ERPlora's staff configure the AI: no signed-in account reaches its operations."""
    config = apps.get_app_config("assistant")

    assert config.permissions == ["assistant.manage"]
    assert getattr(config, "role_permissions", {}) == {}


def test_its_name_in_the_admin_is_translated():
    config = apps.get_app_config("assistant")

    assert str(config.verbose_name) == "AI assistant"
    with translation.override("es"):
        assert str(config.verbose_name) == "Asistente de IA"
