"""Fixtures of the billing tests: no real VIES, ERPlora's identity, accounts and their contexts."""

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.operations import ACCOUNT_ROLE

#: ERPlora's own VAT identity, as the Modelo 036 states it (the requester VIES must see).
ISSUER = {
    "legal_name": "ERPLORA CLOUD SL",
    "tax_id": "B27593136",
    "street": "Avda. de Lisboa, 17, 2º C",
    "city": "Coslada",
    "postal_code": "28822",
    "country": "ES",
}


@pytest.fixture
def issuer_identity(db):
    """ERPlora's identity on file, whatever the seed left: without it no query identifies the requester."""
    from billing.models import CompanyConfig

    company = CompanyConfig.objects.first() or CompanyConfig()
    for field, value in ISSUER.items():
        setattr(company, field, value)
    company.save()
    return company


def ctx_for(user, language: str = "en") -> OperationContext:
    """The context a signed-in account gets from a request (``base.operations``)."""
    if user is None:
        return OperationContext(
            scope=Scope("user", "anonymous"), actor=None, language=language
        )
    return OperationContext(
        scope=Scope("user", str(user.pk)),
        actor=user,
        permissions=permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE),
        language=language,
    )


@pytest.fixture
def make_user(db):
    def make(email: str, **extra):
        return get_user_model().objects.create_user(email=email, password=None, **extra)

    return make


@pytest.fixture
def buyer(make_user):
    return make_user("buyer@example.com", first_name="Berta")


@pytest.fixture
def business_paid_by(db):
    """A business whose payer (``hubs.BillingProfile``) is where it says, written as the owner's form
    leaves it: ``business_paid_by("ES", "35001")``, ``business_paid_by("DE", "10115", tax_id="DE…")``.
    ``country=None`` leaves the business without a payer at all."""
    from hubs.models import BillingProfile, Hub

    made = []

    def make(country: str | None = "ES", postal_code: str = "28001", tax_id: str = ""):
        profile = None
        if country is not None:
            profile = BillingProfile.objects.create(
                billing_name="Payer SL",
                billing_country=country,
                billing_postal_code=postal_code,
                tax_id=tax_id,
            )
        made.append(profile)
        return Hub.objects.create(
            name=f"Business {len(made)}",
            slug=f"billing-business-{len(made)}",
            country="ES",
            billing_profile=profile,
        )

    return make
