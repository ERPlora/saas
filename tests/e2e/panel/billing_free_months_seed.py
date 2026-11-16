"""The account, businesses, promo code and invoice the spec of free months opens (billing-free-months.spec.ts).

``uv run python tests/e2e/panel/billing_free_months_seed.py seed|clear`` from the repo, against the local database of
``.env`` (development only: a known password, refused without ``DEBUG``). ``seed`` starts from ``clear``. Rows are
written with the ORM: nothing reaches Stripe, the Hub nor the platform hub.

- ``e2e-free-months`` (password ``e2e-panel``) owns two businesses:
  - Café Libre: on Free, its payer on file (the checkout goes straight to paying);
  - Panadería Gratis: pays Starter monthly with a code of six free months used on its subscription, and its first
    month's invoice of 0 €, issued and accepted (the plan's price on its line, all of it discounted).
- The promo code ``e2e_testers``: six free months.
"""

import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
EMAIL = "e2e-free-months@example.com"
PASSWORD = os.environ.get("QA_PANEL_PASSWORD", "e2e-panel")
SLUG_PREFIX = "e2e-free-months-"
CODE = "e2e_testers"
SERIES = "E2EFM"


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model

    from billing.models import Invoice, PromoCode
    from hubs.models import BillingProfile, Hub

    Invoice.objects.filter(series=SERIES).delete()
    PromoCode.objects.filter(code=CODE).delete()
    hubs = Hub.objects.filter(slug__startswith=SLUG_PREFIX)
    profiles = list(hubs.values_list("billing_profile_id", flat=True))
    hubs.delete()
    BillingProfile.objects.filter(pk__in=profiles).delete()
    get_user_model().objects.filter(email=EMAIL).delete()


def business(user, slug: str, name: str, *, plan, paying: bool):
    from django.utils import timezone

    from hubs.models import BillingProfile, Hub, HubMember, Subscription

    now = timezone.now()
    profile = BillingProfile.objects.create(
        owner=user,
        billing_name=f"{name} SL",
        billing_email=EMAIL,
        billing_address="Calle Mayor 1",
        billing_city="Madrid",
        billing_postal_code="28001",
        billing_country="ES",
        stripe_customer_id=f"cus_{slug}" if paying else "",
    )
    hub = Hub.objects.create(
        slug=f"{SLUG_PREFIX}{slug}",
        name=name,
        country="ES",
        timezone="Europe/Madrid",
        language="es",
        billing_profile=profile,
        status=Hub.Status.ACTIVE,
        ready_at=now - timedelta(days=60),
    )
    Subscription.objects.create(
        hub=hub,
        plan=plan,
        current_period_start=now - timedelta(days=12),
        current_period_end=now + timedelta(days=18) if paying else None,
        stripe_customer_id=f"cus_{slug}" if paying else "",
        stripe_subscription_id=f"sub_{SLUG_PREFIX}{slug}" if paying else "",
    )
    HubMember.objects.create(
        hub=hub, user=user, role=HubMember.Role.OWNER, joined_at=now - timedelta(days=60), accepted_at=now
    )
    return hub


def free_month_invoice(hub) -> None:
    """The invoice of the first free month: Starter's price on its line, all of it taken off by the code."""
    from django.utils import timezone

    from billing.models import Invoice, InvoiceLine

    today = timezone.localdate()
    invoice = Invoice.objects.create(
        hub=hub,
        business_name=hub.name,
        billing_profile=hub.billing_profile,
        payer_account=hub.billing_profile.owner,
        stripe_invoice_id=f"in_{SLUG_PREFIX}first",
        payment_status=Invoice.PaymentStatus.PAID,
        series=SERIES,
        sequence=1,
        number=f"{SERIES}-{today.year}-00001",
        issued_on=today,
        paid_at=timezone.now(),
        billed_at=timezone.now(),
        tax_treatment="domestic",
        tax_country="ES",
        tax_rate=Decimal("21.00"),
        fiscal_status=Invoice.FiscalStatus.ACCEPTED,
        payer_name=f"{hub.name} SL",
        payer_country="ES",
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        position=1,
        description="1 × Starter",
        item_kind=InvoiceLine.ItemKind.PLAN,
        item_slug="starter",
        tax_category_id="service.saas_subscription",
        tax_treatment="domestic",
        tax_rate=Decimal("21.00"),
        discount_cents=2999,
    )


def seed() -> None:
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from billing.models import PromoCode, PromoRedemption
    from hubs.models import Plan

    user = get_user_model().objects.create_user(email=EMAIL, password=PASSWORD)
    user.first_name, user.last_name, user.language = "Marta", "Ruiz", "en"
    user.save(update_fields=["first_name", "last_name", "language"])
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    business(user, "cafe", "Café Libre", plan=Plan.objects.get(slug="free"), paying=False)
    bakery = business(user, "bakery", "Panadería Gratis", plan=Plan.objects.get(slug="starter"), paying=True)
    promo = PromoCode.objects.create(code=CODE, free_months=6, note="E2E")
    PromoRedemption.objects.create(
        promo=promo,
        hub=bakery,
        stripe_customer_id="cus_bakery",
        stripe_subscription_id=f"sub_{SLUG_PREFIX}bakery",
        free_until=timezone.now() + timedelta(days=150),
    )
    free_month_invoice(bakery)


def main(action: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("billing_free_months_seed.py only runs with DEBUG=True")
    with transaction.atomic():
        clear()
        if action == "seed":
            seed()
    print(f"{action}: free months e2e account, businesses, promo code and invoice")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: billing_free_months_seed.py seed|clear")
    main(sys.argv[1])
