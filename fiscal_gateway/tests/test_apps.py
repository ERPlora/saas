"""``fiscal_gateway`` is a platform app (round 15, PLAN §20): always on, at the project root, no module."""

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.meta import LiveAppConfig, module_configs
from live.slugs import is_reserved_hub_slug


def test_the_gateway_is_a_platform_app():
    config = apps.get_app_config("fiscal_gateway")

    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == (
        "fiscal_gateway",
        "fiscal_gateway",
        "platform",
    )
    assert config not in module_configs()


def test_its_name_has_its_spanish_translation():
    with translation.override("es"):
        assert str(apps.get_app_config("fiscal_gateway").verbose_name) == "Pasarela fiscal"


def test_the_platform_hub_is_a_slug_no_customer_can_take():
    """The platform's hub presents in ERPlora's name through its seal (``PLATFORM_HUB_SLUG``): a business
    bearing that slug would too, so it is a reserved one (``live.slugs``), ``erplora`` unless configured."""
    assert is_reserved_hub_slug(settings.PLATFORM_HUB_SLUG)
