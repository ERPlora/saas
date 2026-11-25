"""``fiscal_gateway.E001``: the names of the platform's hub (``PLATFORM_HUB_SLUGS``) are reserved slugs. It presents in
ERPlora's name through the seal without an authorisation, so a business that could take one of them would too:
``check`` (``migrate`` and the deploy run it) refuses to start with one that is not reserved."""

import pytest
from django.core import checks
from django.test import override_settings

from fiscal_gateway.checks import check_platform_hub_slugs


def test_the_platform_hubs_names_pass():
    assert check_platform_hub_slugs(None) == []


@override_settings(PLATFORM_HUB_SLUGS=("hubs", "platform"))
def test_other_reserved_slugs_pass():
    assert check_platform_hub_slugs(None) == []


@pytest.mark.parametrize(
    "slugs", [("erplora-cloud", "erplora"), ("erplora", "erplora-cloud")]
)
def test_a_slug_a_business_could_take_is_an_error_wherever_it_is(settings, slugs):
    settings.PLATFORM_HUB_SLUGS = slugs

    (error,) = check_platform_hub_slugs(None)

    assert (error.id, error.level) == ("fiscal_gateway.E001", checks.ERROR)
    assert "PLATFORM_HUB_SLUGS" in error.msg
    assert "'erplora-cloud'" in error.msg


@override_settings(PLATFORM_HUB_SLUGS=("erplora-cloud", "erplora-sl"))
def test_every_slug_a_business_could_take_is_named():
    errors = check_platform_hub_slugs(None)

    assert [error.id for error in errors] == ["fiscal_gateway.E001"] * 2
    assert "'erplora-cloud'" in errors[0].msg
    assert "'erplora-sl'" in errors[1].msg


def test_the_check_is_registered():
    assert check_platform_hub_slugs in checks.registry.registry.get_checks()
