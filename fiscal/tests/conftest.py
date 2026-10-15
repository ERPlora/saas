"""Fixtures of the fiscal tests: the businesses and accounts of hubs, the Hub double, PDFs in base64, a
valid submission, a reviewer of the staff and grants written as the services leave them."""

import base64

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from live.context import OperationContext, Scope

from hubs.tests import conftest as hubs_fixtures

# The businesses, their people and the Hub double, offered here as fixtures of their own (an import would be
# shadowed by the fixtures below that take them as arguments).
business = hubs_fixtures.business
hub_double = hubs_fixtures.hub_double
make_user = hubs_fixtures.make_user
offline_hub = hubs_fixtures.offline_hub
owner = hubs_fixtures.owner
plans = hubs_fixtures.plans
signup_trial = hubs_fixtures.signup_trial
team = hubs_fixtures.team

#: The smallest bytes a reader takes for a PDF (only the magic number is checked).
PDF = b"%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def pdf_b64(marker: str = "") -> str:
    """A PDF in base64, with ``marker`` inside so each document of a submission differs."""
    return base64.b64encode(PDF + marker.encode()).decode()


def submission(**overrides) -> dict:
    """The body the Hub posts for a natural person with a DNI (the contract of plan 2026-10-15)."""
    documents = overrides.pop("documents", None)
    return {
        "taxpayer_tax_id": "12345678Z",
        "taxpayer_name": "Manolo García",
        "signer_tax_id": "12345678Z",
        "signer_name": "Manolo García",
        "signer_document_type": "dni",
        "documents": documents
        if documents is not None
        else {"signed_model": pdf_b64("signed"), "id_copy": pdf_b64("id")},
        **overrides,
    }


def staff_ctx(user, language: str = "en") -> OperationContext:
    """The context the admin's review page builds for a member of the staff (``fiscal.admin``)."""
    return OperationContext(
        scope=Scope("user", str(user.pk)),
        actor=user,
        permissions=frozenset({"fiscal.manage"}),
        language=language,
    )


@pytest.fixture
def other_business(make_user, plans):
    """A second business, of another owner (one Free business per account)."""
    from hubs.tests.conftest import create_business

    return create_business(make_user("paco@example.com", first_name="Paco"), name="Bar Paco", slug="bar-paco")


@pytest.fixture
def reviewer(make_user):
    """A member of the staff who may decide on authorisations: ``fiscal.change_representationgrant``."""
    user = make_user("reviewer@erplora.com", first_name="Rita", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="fiscal", codename="change_representationgrant"
        )
    )
    return user


def make_grant(hub, *, version=1, status="submitted", **fields):
    """A row as the services leave it, written directly (the documents encrypted)."""
    from fiscal import crypto
    from fiscal.models import RepresentationGrant

    values = {
        "taxpayer_tax_id": "12345678Z",
        "taxpayer_name": "Manolo García",
        "signer_tax_id": "12345678Z",
        "signer_name": "Manolo García",
        "signer_document_type": "dni",
        "signed_model": crypto.encrypt(PDF + b"signed"),
        "id_copy": crypto.encrypt(PDF + b"id"),
        "submitted_at": timezone.now(),
        **fields,
    }
    return RepresentationGrant.objects.create(
        hub=hub, version=version, status=status, **values
    )
