"""The whatsapp app is a platform app of the SaaS: always on, no module fields, its one permission the platform's."""

from django.apps import apps
from live.meta import LiveAppConfig


def test_it_is_an_installed_platform_app():
    config = apps.get_app_config("whatsapp")

    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == ("whatsapp", "whatsapp", "platform")


def test_no_account_gets_its_permission():
    """Only the platform acts on WhatsApp (the Hub through ``/internal``, Meta through its webhook, the
    staff through the admin): no signed-in account reaches its operations."""
    config = apps.get_app_config("whatsapp")

    assert config.permissions == ["whatsapp.manage"]
    assert getattr(config, "role_permissions", {}) == {}
