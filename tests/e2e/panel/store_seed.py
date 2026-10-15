"""The account, businesses, apps and modules the Store's spec opens (store.spec.ts).

``uv run python tests/e2e/panel/store_seed.py seed|clear`` from saas-next/, against the local database of
``.env`` (development only: a known password, refused without ``DEBUG``). ``seed`` starts from ``clear``.
Rows are written with the ORM (nothing is pushed to the Hub, nothing reaches Stripe): the spec plays
Stripe's part at the browser's boundary (the Embedded Checkout's ``Stripe`` global and the answers of the
operations that call Stripe).

- ``e2e-store`` (password ``e2e-panel``) owns three businesses:
  - Panadería López: pays Starter monthly; E2E Loyalty bought and cancelled (works until its renewal);
  - Café Central: on Free, its payer already on file (so the checkout goes straight to paying);
  - Bar La Plaza: Starter with an unpaid invoice, the card declined.
- Apps of the catalog (as the Hub's ``register_apps`` writes them): E2E Bookings and E2E Loyalty
  (premium, on sale as modules) and E2E Free App (not premium: never sold).
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
# The QA user of the root .env (README «Usuarios QA»), with its value there as the default.
EMAIL = os.environ.get("QA_STORE_EMAIL", "e2e-store@example.com")
PASSWORD = os.environ.get("QA_STORE_PASSWORD", "e2e-panel")
SLUG_PREFIX = "e2e-store-"
APPS = {
    "e2e_bookings": ("E2E Bookings", "E2E Reservas", True, 900),
    "e2e_loyalty": ("E2E Loyalty", "E2E Fidelización", True, 600),
    "e2e_free_app": ("E2E Free App", "E2E App gratuita", False, 0),
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
    from hubs.models import BillingProfile, Hub

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
    from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription, SubscriptionItem

    now = timezone.now()
    renewal = now + timedelta(days=18)
    user = get_user_model().objects.create_user(email=EMAIL, password=PASSWORD)
    user.first_name, user.last_name, user.language = "Laura", "Martín", "en"
    user.save(update_fields=["first_name", "last_name", "language"])
    # Proven address: every account proves it before its first session (the code a sign-up mails).
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    free = Plan.objects.get(slug="free")
    starter = Plan.objects.get(slug="starter")

    for app_id, (name_en, name_es, premium, cents) in APPS.items():
        make_app(app_id, name_en=name_en, name_es=name_es, category="sales", premium=premium)
        if premium:
            Module.objects.create(
                slug=app_id,
                tier=Module.Tier.BASIC,
                price_monthly_cents=cents,
                price_annual_cents=cents * 10,
                stripe_price_id_monthly=f"price_{app_id}_month",
                stripe_price_id_annual=f"price_{app_id}_year",
            )

    def business(slug, name, *, plan, hub_status=Hub.Status.ACTIVE, paying=False, **subscription):
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
            status=hub_status,
            ready_at=now - timedelta(days=200),
        )
        made = Subscription.objects.create(
            hub=hub,
            plan=plan,
            current_period_start=now - timedelta(days=12),
            current_period_end=renewal if paying else None,
            stripe_customer_id=f"cus_{slug}" if paying else "",
            stripe_subscription_id=f"sub_{slug}" if paying else "",
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
        return made

    bakery = business("panaderia", "Panadería López", plan=starter, paying=True)
    SubscriptionItem.objects.create(
        subscription=bakery,
        module_slug="e2e_loyalty",
        source=SubscriptionItem.Source.PURCHASE,
        valid_until=renewal,
        stripe_item_id="si_e2e_loyalty",
    )
    business("cafe", "Café Central", plan=free)
    business(
        "bar",
        "Bar La Plaza",
        plan=starter,
        paying=True,
        hub_status=Hub.Status.PAST_DUE,
        status=Subscription.Status.PAST_DUE,
        unpaid_reason=Subscription.UnpaidReason.CARD_DECLINED,
        unpaid_since=now - timedelta(days=4),
    )


def main(action: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("store_seed.py only runs with DEBUG=True")
    with transaction.atomic():
        clear()
        if action == "seed":
            seed()
    print(f"{action}: store e2e account, businesses and modules")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: store_seed.py seed|clear")
    main(sys.argv[1])
