"""Fixtures of the billing tests: no real VIES, ERPlora's identity, accounts and their contexts."""

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.operations import ACCOUNT_ROLE
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another saas-cron task
from hubs.tests.conftest import hub_double, offline_hub  # noqa: F401 - the Hub double, for what billing pushes

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


# --- Stripe ------------------------------------------------------------------------------------------


@pytest.fixture
def stripe_keys(settings):
    """Stripe configured with TEST keys, as local development has it (never a real key in a test)."""
    from billing.tests.stripe_double import WEBHOOK_SECRET

    settings.STRIPE_SECRET_KEY = "rk_test_double"
    settings.STRIPE_PUBLISHABLE_KEY = "pk_test_double"
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    settings.STRIPE_PORTAL_CONFIGURATION = "bpc_test_double"
    return settings


@pytest.fixture
def stripe_double(stripe_keys, monkeypatch):
    """Stripe at the boundary: ``billing.stripe_service.client()`` returns the double (no network)."""
    from billing import stripe_service
    from billing.tests.stripe_double import StripeDouble

    double = StripeDouble()
    monkeypatch.setattr(stripe_service, "client", lambda: double)
    return double


# --- Businesses that buy -----------------------------------------------------------------------------

#: The Stripe prices of the paid plans, as the admin fills them (``Plan.stripe_price_id*``).
PLAN_PRICES = {slug: (f"price_{slug}_month", f"price_{slug}_year") for slug in ("starter", "standard", "pro", "max")}


@pytest.fixture
def plans(db):
    """The plans as ``sync_hub_plans`` seeds them, with their Stripe prices filled in."""
    from io import StringIO

    from django.core.management import call_command

    from hubs.models import Plan

    call_command("sync_hub_plans", stdout=StringIO())
    for slug, (month, year) in PLAN_PRICES.items():
        Plan.objects.filter(slug=slug).update(stripe_price_id=month, stripe_price_id_annual=year)


@pytest.fixture
def owner(make_user):
    return make_user("owner@example.com", first_name="Olga", last_name="López", language="es")


@pytest.fixture
def shop(owner, plans):
    """A business on Free (with the 15 days of Starter of every sign-up), its payer in Madrid."""
    from hubs.models import Hub
    from hubs.tests.conftest import create_business

    hub = create_business(owner, name="Panadería López")
    profile = hub.billing_profile
    profile.billing_name = "Panadería López SL"
    profile.billing_address = "Calle Mayor 1"
    profile.billing_city = "Madrid"
    profile.billing_postal_code = "28001"
    profile.save()
    return Hub.objects.select_related("billing_profile").get(pk=hub.pk)


@pytest.fixture
def inventory(db):
    """A paid module on sale: 10 € a month, 100 € a year (net). Enterprise tier, so no plan the tests buy
    (Starter, Standard: basic) includes it (lot L2-C: a plan includes the modules its level reaches)."""
    from apps.models import Module

    return Module.objects.create(
        slug="inventory",
        tier=Module.Tier.ENTERPRISE,
        price_monthly_cents=1000,
        price_annual_cents=10000,
        stripe_price_id_monthly="price_inventory_month",
        stripe_price_id_annual="price_inventory_year",
    )


def pay(hub, *, plan="starter", interval="month", modules=(), status="active", cancel_at_period_end=False,
        sub_id="sub_1", customer="cus_1", **extra):
    """The business as its Stripe subscription leaves it once paid (what the webhook applies)."""
    from datetime import timedelta

    from django.utils import timezone

    from hubs import services as hub_services
    from hubs.models import Hub
    from hubs.schemas import ModuleRightIn, SubscriptionApplyIn

    now = timezone.now()
    hub_services.subscription_apply(
        hub_services.system_ctx_for(hub.id),
        SubscriptionApplyIn(
            hub_id=hub.id,
            plan=plan,
            billing_interval=interval,
            status=status,
            stripe_customer_id=customer,
            stripe_subscription_id=sub_id,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=cancel_at_period_end,
            modules=[ModuleRightIn(module_slug=slug, stripe_item_id=f"si_{slug}") for slug in modules],
            **extra,
        ),
    )
    return Hub.objects.select_related("billing_profile").get(pk=hub.pk)
