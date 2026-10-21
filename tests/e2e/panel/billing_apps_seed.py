"""The account, businesses, paid apps and invoices of part 2 of billing (billing-apps.spec.ts, APP-BILLING-2).

``uv run python tests/e2e/panel/billing_apps_seed.py seed|clear`` from saas/, against the run's database (the
local one of ``.env`` or the stack's own; development only: a known password, refused without ``DEBUG``).
``seed`` starts from ``clear``. Rows are written with the ORM (nothing is pushed to the Hub, nothing reaches
Stripe): the spec plays Stripe and the operations that call it at the browser's boundary.

- ``e2e-billing-apps`` (password ``e2e-panel``, English) owns and pays three businesses, one payer for all:
  - Panadería López: Starter monthly; E2E Apps Bookings bought (running) and E2E Apps Reports bought and then
    taken off sale (it still pays it, saas#2589); one invoice with its plan and module lines, issued by the
    platform hub, and the credit note that rectifies it;
  - Bar Norte: Starter monthly; E2E Apps Loyalty cancelled (works until the renewal) and E2E Apps Bookings,
    whose cancellation ended yesterday (on sale again);
  - Café Central: on Free, its payer on file (the checkout goes straight to paying).
- Apps of the catalog (as the Hub's ``register_apps`` writes them), premium: Bookings and Loyalty on sale,
  Reports off sale.
"""

import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
EMAIL = os.environ.get("QA_BILLING_APPS_EMAIL", "e2e-billing-apps@example.com")
PASSWORD = os.environ.get("QA_BILLING_APPS_PASSWORD", "e2e-panel")
SLUG_PREFIX = "e2e-billing-apps-"
#: Every Stripe id of these rows starts so: the invoices outlive their business (``SET_NULL``).
STRIPE_PREFIX = "in_e2e_billing_apps_"
#: app id → (English name, Spanish name, monthly net cents, on sale)
APPS = {
    "e2e_apps_bookings": ("E2E Apps Bookings", "E2E Apps Reservas", 900, True),
    "e2e_apps_loyalty": ("E2E Apps Loyalty", "E2E Apps Fidelización", 600, True),
    "e2e_apps_reports": ("E2E Apps Reports", "E2E Apps Informes", 700, False),
}


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model

    from accounts.models import HubMembership
    from apps.models import App, Module
    from billing.models import Invoice
    from hubs.models import BillingProfile, Hub

    # A credit note protects the invoice it rectifies: the credit notes go first.
    Invoice.objects.filter(stripe_invoice_id__startswith=STRIPE_PREFIX, kind=Invoice.Kind.CREDIT_NOTE).delete()
    Invoice.objects.filter(stripe_invoice_id__startswith=STRIPE_PREFIX).delete()
    hubs = Hub.objects.filter(slug__startswith=SLUG_PREFIX)
    slugs = list(hubs.values_list("slug", flat=True))
    profiles = list(hubs.values_list("billing_profile_id", flat=True))
    hubs.delete()
    BillingProfile.objects.filter(pk__in=profiles).delete()
    HubMembership.objects.filter(hub_slug__in=slugs).delete()
    get_user_model().objects.filter(email=EMAIL).delete()
    Module.objects.filter(slug__in=APPS).delete()
    App.objects.filter(pk__in=APPS).delete()


def seed() -> None:
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from accounts.models import HubMembership
    from apps.models import Module
    from apps.tests.factories import make_app
    from billing.models import Invoice, InvoiceLine
    from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription, SubscriptionItem

    now = timezone.now()
    today = timezone.localdate()
    renewal = now + timedelta(days=18)
    user = get_user_model().objects.create_user(email=EMAIL, password=PASSWORD)
    user.first_name, user.last_name, user.language = "Laura", "Martín", "en"
    user.save(update_fields=["first_name", "last_name", "language"])
    # Proven address: every account proves it before its first session (the code a sign-up mails).
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    free = Plan.objects.get(slug="free")
    starter = Plan.objects.get(slug="starter")

    for app_id, (name_en, name_es, cents, on_sale) in APPS.items():
        make_app(app_id, name_en=name_en, name_es=name_es, category="sales", premium=True)
        Module.objects.create(
            slug=app_id,
            tier=Module.Tier.ENTERPRISE,
            price_monthly_cents=cents,
            price_annual_cents=cents * 10,
            stripe_price_id_monthly=f"price_{app_id}_month",
            stripe_price_id_annual=f"price_{app_id}_year",
            is_active=on_sale,
        )
    profile = BillingProfile.objects.create(
        owner=user,
        billing_name="Panadería López S.L.",
        tax_id="B12345678",
        billing_email=EMAIL,
        billing_address="C/ Mayor 12",
        billing_city="Madrid",
        billing_postal_code="28013",
        billing_country="ES",
        stripe_customer_id="cus_e2e_billing_apps",
    )

    def business(slug, name, *, plan, paying=True):
        hub = Hub.objects.create(
            slug=f"{SLUG_PREFIX}{slug}",
            name=name,
            country="ES",
            timezone="Europe/Madrid",
            language="es",
            billing_profile=profile,
            status=Hub.Status.ACTIVE,
            ready_at=now - timedelta(days=200),
        )
        made = Subscription.objects.create(
            hub=hub,
            plan=plan,
            current_period_start=now - timedelta(days=12),
            current_period_end=renewal if paying else None,
            stripe_customer_id="cus_e2e_billing_apps" if paying else "",
            stripe_subscription_id=f"sub_e2e_billing_apps_{slug}" if paying else "",
        )
        HubMember.objects.create(
            hub=hub,
            user=user,
            role=HubMember.Role.OWNER,
            joined_at=now - timedelta(days=200),
            accepted_at=now - timedelta(days=200),
        )
        HubMembership.objects.create(user=user, hub_slug=hub.slug, role=HubMember.Role.OWNER)
        return hub, made

    def item(subscription, slug, *, valid_until=None, stripe_item_id=""):
        SubscriptionItem.objects.create(
            subscription=subscription,
            module_slug=slug,
            source=SubscriptionItem.Source.PURCHASE,
            valid_until=valid_until,
            stripe_item_id=stripe_item_id,
        )

    bakery, bakery_sub = business("panaderia", "Panadería López", plan=starter)
    item(bakery_sub, "e2e_apps_bookings", stripe_item_id="si_e2e_apps_bookings")
    item(bakery_sub, "e2e_apps_reports", stripe_item_id="si_e2e_apps_reports")
    norte, norte_sub = business("norte", "Bar Norte", plan=starter)
    item(norte_sub, "e2e_apps_loyalty", valid_until=renewal)
    item(norte_sub, "e2e_apps_bookings", valid_until=now - timedelta(days=1))
    business("cafe", "Café Central", plan=free, paying=False)

    def invoice(key, *, number, series, sequence, lines, kind=Invoice.Kind.INVOICE, **extra):
        net = sum(line[1] for line in lines)
        tax = sum(line[2] for line in lines)
        made = Invoice.objects.create(
            hub=bakery,
            kind=kind,
            business_name=bakery.name,
            billing_profile=profile,
            payer_account=user,
            stripe_invoice_id=f"{STRIPE_PREFIX}{key}",
            stripe_number=f"E2EAPPS{key.upper()}-0001",
            billed_at=now - timedelta(days=10),
            payment_status=Invoice.PaymentStatus.PAID,
            paid_at=now - timedelta(days=10),
            series=series,
            sequence=sequence,
            number=number,
            issued_on=today - timedelta(days=10),
            net_cents=net,
            tax_cents=tax,
            total_cents=net + tax,
            tax_rate=Decimal("21.00"),
            tax_country="ES",
            tax_treatment="domestic",
            payer_name=profile.billing_name,
            payer_tax_id=profile.tax_id,
            payer_address=profile.billing_address,
            payer_city=profile.billing_city,
            payer_postal_code=profile.billing_postal_code,
            payer_country="ES",
            payer_email=EMAIL,
            fiscal_status=Invoice.FiscalStatus.ACCEPTED,
            qr="https://e2e/qr",
            **extra,
        )
        for position, (description, line_net, line_tax, kind_of_item, slug, proration) in enumerate(lines, start=1):
            InvoiceLine.objects.create(
                invoice=made,
                position=position,
                description=description,
                item_kind=kind_of_item,
                item_slug=slug,
                proration=proration,
                period_start=now - timedelta(days=10),
                period_end=renewal,
                tax_rate=Decimal("21.00"),
                net_cents=line_net,
                tax_cents=line_tax,
                total_cents=line_net + line_tax,
            )
        return made

    original = invoice(
        "bakery",
        number="ERP-2026-90201",
        series="ERP",
        sequence=90201,
        lines=[
            ("Starter (monthly)", 1999, 420, "plan", "starter", False),
            ("E2E Apps Bookings", 540, 113, "module", "e2e_apps_bookings", True),
        ],
    )
    invoice(
        "bakery_refund",
        kind=Invoice.Kind.CREDIT_NOTE,
        number="ERPR-2026-90007",
        series="ERPR",
        sequence=90007,
        lines=[("E2E Apps Bookings", -540, -113, "module", "e2e_apps_bookings", True)],
        rectifies=original,
        rectification_type="R1",
        rectification_reason="Duplicate charge",
        stripe_source_id="cn_e2e_billing_apps",
    )


def main(action: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("billing_apps_seed.py only runs with DEBUG=True")
    with transaction.atomic():
        clear()
        if action == "seed":
            seed()
    print(f"{action}: billing part 2 e2e account, businesses, apps and invoices")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: billing_apps_seed.py seed|clear")
    main(sys.argv[1])
