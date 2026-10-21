"""The reads of whatsapp: which business a door names (its slug in phase 1, its UUID in phase 2)."""

import pytest

from hubs.models import Hub
from whatsapp import queries

pytestmark = pytest.mark.django_db


def test_a_business_is_named_by_its_slug_or_its_uuid(business):
    assert queries.known_hub("bar-manolo") == business
    assert queries.known_hub(str(business.id)) == business


def test_32_hex_digits_are_a_slug_not_an_id(business):
    assert queries.known_hub(business.id.hex) is None


def test_an_unknown_business_is_none(business):
    assert queries.known_hub("nobody") is None


@pytest.mark.parametrize("status", [Hub.Status.DELETING, Hub.Status.DELETED])
def test_a_business_that_left_sends_nothing(business, status):
    Hub.objects.filter(pk=business.pk).update(status=status)

    assert queries.known_hub("bar-manolo") is None


def test_a_business_being_deleted_can_still_be_forgotten(business):
    """RGPD: what the Hub asks to forget is forgotten while the business is within its retention."""
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

    assert queries.known_hub("bar-manolo", live=False) == business
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)
    assert queries.known_hub("bar-manolo", live=False) is None
