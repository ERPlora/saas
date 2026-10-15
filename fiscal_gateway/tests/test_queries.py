"""What the gateway reads before it presents through ERPlora: the business a call names (its slug or its UUID)
and the taxpayer its authorisation in force covers (``fiscal.RepresentationGrant``, approved).

Only ``fiscal_gateway.queries`` reads the database; the views call it.
"""

import uuid

import pytest

from fiscal.tests.conftest import make_grant
from fiscal_gateway import queries
from fiscal_gateway.tests.conftest import HUB, HUB_SLUG
from hubs.models import Hub

pytestmark = pytest.mark.django_db


# The business a call names


def test_a_business_is_found_by_its_slug(business):
    assert queries.hub_id_for(HUB_SLUG) == business.id


def test_a_business_is_found_by_its_uuid(business):
    assert queries.hub_id_for(HUB) == business.id


@pytest.mark.parametrize("ref", ["bar-paco", str(uuid.uuid7())], ids=["slug", "uuid"])
def test_an_unknown_business_is_none(business, ref):
    assert queries.hub_id_for(ref) is None


def test_a_purged_business_is_unknown(business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

    assert queries.hub_id_for(HUB_SLUG) is None
    assert queries.hub_id_for(HUB) is None


def test_a_deleted_business_within_its_retention_is_still_known(business):
    """Its records already issued still have to reach the AEAT while it can be restored."""
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

    assert queries.hub_id_for(HUB_SLUG) == business.id


def test_a_slug_of_32_hex_digits_is_a_slug_not_a_uuid(business):
    """``uuid.UUID`` reads 32 hex digits without hyphens too; the Hub sends the UUID with them."""
    looks_like_a_uuid = uuid.UUID(HUB).hex
    Hub.objects.create(slug=looks_like_a_uuid, name="Hex", country="ES")

    assert queries.hub_id_for(looks_like_a_uuid) != business.id
    assert queries.hub_id_for(looks_like_a_uuid) is not None


# The taxpayer of the authorisation in force


def test_without_an_authorisation_there_is_no_taxpayer(business):
    assert queries.approved_taxpayer(business.id) is None


@pytest.mark.parametrize("status", ["submitted", "returned", "revoked"])
def test_an_authorisation_not_in_force_covers_nobody(business, status):
    make_grant(business, status=status, taxpayer_tax_id="B12345674")

    assert queries.approved_taxpayer(business.id) is None


def test_the_approved_authorisation_covers_its_taxpayer_normalised(business):
    make_grant(business, status="submitted", version=2, taxpayer_tax_id="B99999999")
    make_grant(business, status="approved", version=1, taxpayer_tax_id="b12345674")

    assert queries.approved_taxpayer(business.id) == "B12345674"


def test_another_business_s_approval_covers_nobody_here(business):
    other = Hub.objects.create(slug="bar-paco", name="Bar Paco", country="ES")
    make_grant(other, status="approved", taxpayer_tax_id="B12345674")

    assert queries.approved_taxpayer(business.id) is None
