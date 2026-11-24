"""``fiscal_gateway`` is a platform app: always on, at the project root, no module."""

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


def test_the_platform_hub_goes_by_its_name_and_the_one_it_had_and_no_customer_can_take_them():
    """The platform's hub presents in ERPlora's name through its seal (``PLATFORM_HUB_SLUGS``): a business
    bearing one of its names would too, so they are reserved (``live.slugs``), and there is no other."""
    assert sorted(settings.PLATFORM_HUB_SLUGS) == ["erp", "erplora"]
    assert all(is_reserved_hub_slug(slug) for slug in settings.PLATFORM_HUB_SLUGS)
