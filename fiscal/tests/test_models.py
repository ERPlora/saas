"""``RepresentationGrant``: each authorisation a business sends, one row per version, with its review.

Ported in behaviour from ERPlora/saas ``apps/dashboard/fiscal/models.py`` (origin/develop), keyed by the
business instead of the taxpayer's NIF (the Hub reads «validated or not» per business in its snapshot): a
version per business that is never reused, at most one approved per business, the documents encrypted.
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from fiscal.models import RepresentationGrant
from fiscal.tests.conftest import make_grant
from hubs.models import Hub

pytestmark = pytest.mark.django_db


def test_a_grant_is_keyed_by_a_uuid7(business):
    grant = make_grant(business)

    assert grant.id.version == 7
    assert (grant.hub_id, grant.version, grant.status) == (business.id, 1, "submitted")


def test_the_statuses_are_the_four_of_the_contract():
    """«none» is the absence of rows; the Hub reads none|submitted|approved|returned|revoked."""
    assert RepresentationGrant.Status.values == [
        "submitted",
        "approved",
        "returned",
        "revoked",
    ]
    assert RepresentationGrant.DocumentType.values == ["dni", "nie"]


def test_a_version_is_never_used_twice_in_a_business(business):
    make_grant(business, version=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_grant(business, version=1, status="returned")


def test_two_businesses_may_each_have_their_version_1(business, other_business):
    make_grant(business, version=1)
    make_grant(other_business, version=1)

    assert RepresentationGrant.objects.filter(version=1).count() == 2


def test_a_business_has_at_most_one_approved_grant(business):
    make_grant(business, version=1, status="approved")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_grant(business, version=2, status="approved")


def test_an_approved_grant_lives_beside_revoked_and_pending_ones(business):
    make_grant(business, version=1, status="revoked")
    make_grant(business, version=2, status="approved")
    make_grant(business, version=3, status="submitted")

    assert RepresentationGrant.objects.filter(hub=business).count() == 3


def test_the_latest_is_the_highest_version(business):
    make_grant(business, version=1, status="approved")
    newest = make_grant(business, version=2, status="returned")

    assert RepresentationGrant.latest_for(business.id) == newest
    assert (
        RepresentationGrant.latest_for(
            Hub.objects.create(slug="empty", name="Empty", country="ES").id
        )
        is None
    )


def test_the_approved_one_is_found(business):
    approved = make_grant(business, version=1, status="approved")
    make_grant(business, version=2, status="submitted")

    assert RepresentationGrant.approved_for(business.id) == approved


def test_without_an_approved_one_there_is_none(business):
    make_grant(business, version=1, status="returned")

    assert RepresentationGrant.approved_for(business.id) is None


def test_the_last_change_is_the_latest_of_its_dates(business):
    submitted = timezone.now() - timedelta(days=3)
    grant = make_grant(
        business,
        status="revoked",
        submitted_at=submitted,
        reviewed_at=submitted + timedelta(days=1),
        revoked_at=submitted + timedelta(days=2),
    )

    assert grant.changed_at == submitted + timedelta(days=2)
    assert (
        make_grant(business, version=2, submitted_at=submitted).changed_at == submitted
    )


def test_it_reads_well_in_the_admin(business):
    grant = make_grant(
        business, taxpayer_name="Manolo García", taxpayer_tax_id="12345678Z"
    )

    assert str(grant) == "Bar Manolo (bar-manolo) · v1 · 12345678Z"


def test_the_grants_go_with_their_business(business):
    make_grant(business)

    Hub.objects.filter(pk=business.pk).delete()

    assert not RepresentationGrant.objects.exists()


def test_a_reviewer_who_leaves_leaves_the_trail_without_a_name(business, make_user):
    reviewer = make_user("reviewer@erplora.com", is_staff=True)
    grant = make_grant(
        business, status="approved", reviewed_by=reviewer, reviewed_at=timezone.now()
    )

    reviewer.delete()

    grant.refresh_from_db()
    assert (grant.status, grant.reviewed_by, grant.reviewed_at is not None) == (
        "approved",
        None,
        True,
    )
