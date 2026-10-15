"""``fiscal_gateway.E001``: the platform's hub (``PLATFORM_HUB_SLUG``) is a reserved slug. It presents in
ERPlora's name through the seal without an authorisation, so a business that could take its slug would too:
``check`` (``migrate`` and the deploy run it) refuses to start with one that is not reserved."""

from django.core import checks
from django.test import override_settings

from fiscal_gateway.checks import check_platform_hub_slug


def test_the_default_platform_hub_passes():
    assert check_platform_hub_slug(None) == []


@override_settings(PLATFORM_HUB_SLUG="hubs")
def test_another_reserved_slug_passes():
    assert check_platform_hub_slug(None) == []


@override_settings(PLATFORM_HUB_SLUG="erplora-cloud")
def test_a_slug_a_business_could_take_is_an_error():
    (error,) = check_platform_hub_slug(None)

    assert (error.id, error.level) == ("fiscal_gateway.E001", checks.ERROR)
    assert "PLATFORM_HUB_SLUG" in error.msg


def test_the_check_is_registered():
    assert check_platform_hub_slug in checks.registry.registry.get_checks()
