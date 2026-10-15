"""The account, businesses, subscriptions and invoices Billing's spec opens (billing.spec.ts).

``uv run python tests/e2e/panel/billing_seed.py seed|clear`` from saas-next/, against the local database of
``.env`` (development only: a known password, refused without ``DEBUG``). ``seed`` starts from ``clear``.
Rows are written with the ORM (nothing is pushed to the Hub, nothing reaches Stripe): the spec plays Stripe's
pages and the platform hub at their boundaries.

- ``e2e-billing`` (password ``e2e-panel``, English) owns and pays four businesses:
  - Panadería López: Starter monthly with the module E2E Bill Bookings; two invoices, one issued by the
    platform hub (its PDF exists) and one still being issued;
  - Bar La Plaza: Starter, payment pending since 4 days ago: the bank declined the card (``card_declined``),
    so «Pay» waits for another card;
  - Bar Norte: Starter, payment pending since 2 days ago, a soft failure: «Pay» goes to Stripe's page;
  - Café Central: on Free, without invoices.
"""

import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
# The QA user of the root .env (README «Usuarios QA»), with its value there as the default.
EMAIL = os.environ.get("QA_BILLING_EMAIL", "e2e-billing@example.com")
PASSWORD = os.environ.get("QA_BILLING_PASSWORD", "e2e-panel")
SLUG_PREFIX = "e2e-billing-"
#: Every Stripe id of these rows starts so: the invoices outlive their business (``SET_NULL``).
STRIPE_PREFIX = "in_e2e_billing_"
APP = ("e2e_bill_bookings", "E2E Bill Bookings", "E2E Reservas de facturación", 900)


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model

    from accounts.models import HubMembership
    from apps.models import App, Module
    from billing.models import Invoice, PaymentFailure
    from hubs.models import BillingProfile, Hub

    Invoice.objects.filter(stripe_invoice_id__startswith=STRIPE_PREFIX).delete()
    PaymentFailure.objects.filter(stripe_invoice_id__startswith=STRIPE_PREFIX).delete()
    hubs = Hub.objects.filter(slug__startswith=SLUG_PREFIX)
    slugs = list(hubs.values_list("slug", flat=True))
    profiles = list(hubs.values_list("billing_profile_id", flat=True))
    hubs.delete()
    BillingProfile.objects.filter(pk__in=profiles).delete()
    HubMembership.objects.filter(hub_slug__in=slugs).delete()
    get_user_model().objects.filter(email=EMAIL).delete()
    Module.objects.filter(slug=APP[0]).delete()
    App.objects.filter(pk=APP[0]).delete()


def seed() -> None:
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from accounts.models import HubMembership
    from apps.models import Module
    from apps.tests.factories import make_app
    from billing.models import Invoice, PaymentFailure
    from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription, SubscriptionItem

    now = timezone.now()
    today = timezone.localdate()
    user = get_user_model().objects.create_user(email=EMAIL, password=PASSWORD)
    user.first_name, user.last_name, user.language = "Laura", "Martín", "en"
    user.save(update_fields=["first_name", "last_name", "language"])
    # Proven address: every account proves it before its first session (the code a sign-up mails).
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    free = Plan.objects.get(slug="free")
    starter = Plan.objects.get(slug="starter")

    app_id, name_en, name_es, cents = APP
    make_app(app_id, name_en=name_en, name_es=name_es, category="sales", premium=True)
    Module.objects.create(
        slug=app_id,
        tier=Module.Tier.BASIC,
        price_monthly_cents=cents,
        price_annual_cents=cents * 10,
        stripe_price_id_monthly=f"price_{app_id}_month",
        stripe_price_id_annual=f"price_{app_id}_year",
    )
    # One payer for every business: one card, one set of billing details (mockups «Paga: …»).
    profile = BillingProfile.objects.create(
        owner=user,
        billing_name="Panadería López S.L.",
        tax_id="B12345678",
        billing_email=EMAIL,
        billing_address="C/ Mayor 12",
        billing_city="Madrid",
        billing_postal_code="28013",
        billing_country="ES",
        stripe_customer_id="cus_e2e_billing",
    )

    def business(slug, name, *, plan, paying=True, hub_status=Hub.Status.ACTIVE, **subscription):
        hub = Hub.objects.create(
            slug=f"{SLUG_PREFIX}{slug}",
            name=name,
            country="ES",
            timezone="Europe/Madrid",
            language="es",
            billing_profile=profile,
            status=hub_status,
            ready_at=now - timedelta(days=200),
        )
        made = Subscription.objects.create(
            hub=hub,
            plan=plan,
            current_period_start=now - timedelta(days=12),
            current_period_end=now + timedelta(days=18) if paying else None,
            stripe_customer_id="cus_e2e_billing" if paying else "",
            stripe_subscription_id=f"sub_e2e_billing_{slug}" if paying else "",
            **subscription,
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

    def invoice(hub, key, *, number="", days_ago, total=3629, fiscal="", open_url="", **extra):
        net = round(total / Decimal("1.21")) if total else 0
        paid = bool(number)
        return Invoice.objects.create(
            hub=hub,
            business_name=hub.name,
            billing_profile=profile,
            payer_account=user,
            stripe_invoice_id=f"{STRIPE_PREFIX}{key}",
            stripe_number=f"E2E{key.upper()}-0001",
            hosted_invoice_url=open_url,
            billed_at=now - timedelta(days=days_ago),
            payment_status=Invoice.PaymentStatus.PAID if paid else Invoice.PaymentStatus.OPEN,
            paid_at=now - timedelta(days=days_ago) if paid else None,
            series="ERP" if paid else "",
            sequence=int(number[-5:]) if paid else None,
            number=number,
            issued_on=today - timedelta(days=days_ago) if paid else None,
            net_cents=net,
            tax_cents=total - net,
            total_cents=total,
            tax_rate=Decimal("21.00"),
            tax_country="ES",
            tax_treatment="domestic",
            payer_name=profile.billing_name,
            payer_tax_id=profile.tax_id,
            payer_country="ES",
            fiscal_status=fiscal,
            **extra,
        )

    bakery, bakery_sub = business("panaderia", "Panadería López", plan=starter)
    SubscriptionItem.objects.create(
        subscription=bakery_sub, module_slug=app_id, source=SubscriptionItem.Source.PURCHASE, stripe_item_id="si_e2e_bill"
    )
    invoice(bakery, "bakery_aug", number="ERP-2026-90071", days_ago=60, fiscal=Invoice.FiscalStatus.ACCEPTED, qr="https://e2e/qr")
    invoice(bakery, "bakery_sep", number="ERP-2026-90098", days_ago=30, fiscal=Invoice.FiscalStatus.ISSUING)

    declined_since = now - timedelta(days=4)
    plaza, _ = business(
        "plaza",
        "Bar La Plaza",
        plan=starter,
        hub_status=Hub.Status.PAST_DUE,
        status=Subscription.Status.PAST_DUE,
        unpaid_reason=Subscription.UnpaidReason.CARD_DECLINED,
        unpaid_since=declined_since,
        # What Stripe's `invoice.payment_failed` webhook writes: the page to pay it (the panel's «Pay»).
        unpaid_invoice_url="https://invoice.stripe.com/i/e2e-billing-plaza",
    )
    invoice(plaza, "plaza", days_ago=4, open_url="https://invoice.stripe.com/i/e2e-billing-plaza")
    PaymentFailure.objects.create(
        hub=plaza,
        stripe_invoice_id=f"{STRIPE_PREFIX}plaza",
        stripe_subscription_id="sub_e2e_billing_plaza",
        stripe_customer_id="cus_e2e_billing",
        reason=PaymentFailure.Reason.CARD_DECLINED,
        decline_code="generic_decline",
        hosted_invoice_url="https://invoice.stripe.com/i/e2e-billing-plaza",
        invoice_created_at=declined_since,
        failed_at=declined_since,
    )

    soft_since = now - timedelta(days=2)
    norte, _ = business(
        "norte",
        "Bar Norte",
        plan=starter,
        hub_status=Hub.Status.PAST_DUE,
        status=Subscription.Status.PAST_DUE,
        unpaid_reason=Subscription.UnpaidReason.PAYMENT_FAILED,
        unpaid_since=soft_since,
        unpaid_invoice_url="https://invoice.stripe.com/i/e2e-billing-norte",
    )
    invoice(norte, "norte", days_ago=2, open_url="https://invoice.stripe.com/i/e2e-billing-norte")
    PaymentFailure.objects.create(
        hub=norte,
        stripe_invoice_id=f"{STRIPE_PREFIX}norte",
        stripe_subscription_id="sub_e2e_billing_norte",
        stripe_customer_id="cus_e2e_billing",
        reason=PaymentFailure.Reason.PAYMENT_FAILED,
        decline_code="insufficient_funds",
        hosted_invoice_url="https://invoice.stripe.com/i/e2e-billing-norte",
        invoice_created_at=soft_since,
        failed_at=soft_since,
    )

    business("cafe", "Café Central", plan=free, paying=False)


def main(action: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("billing_seed.py only runs with DEBUG=True")
    with transaction.atomic():
        clear()
        if action == "seed":
            seed()
    print(f"{action}: billing e2e account, businesses, subscriptions and invoices")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: billing_seed.py seed|clear")
    main(sys.argv[1])
