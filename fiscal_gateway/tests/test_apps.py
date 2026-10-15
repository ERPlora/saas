"""``fiscal_gateway`` is a platform app (round 15, PLAN §20): always on, at the project root, no module."""

from django.apps import apps
from django.utils import translation
from live.meta import LiveAppConfig, module_configs


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
