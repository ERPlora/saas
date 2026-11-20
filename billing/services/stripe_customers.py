"""The payer of a business as its Stripe customer: created once, kept up to date with its billing details, and given
its VAT number only when it may travel to Stripe."""

import hashlib
import json

from django.conf import settings

from billing import stripe_service, stripe_tax_ids, vat
from billing.services import payment_gates, vat_clearance
from hubs.services import hub_callbacks, subscription_sync
from hubs.models import BillingProfile, Hub, HubMember
from hubs.schemas.subscriptions import SubscriptionApplyIn


def ensure_customer(hub: Hub, *, test_clock: str | None = None) -> str:
    """The payer of ``hub`` as a Stripe customer: created once (and remembered on the payer through
    ``hubs.subscription.apply``), brought up to date otherwise. Its VAT number travels only when VIES
    proved it, or it is national (Stripe reverse charges by the FORMAT of a number).
    ``test_clock`` attaches a new customer to a Stripe test clock (``billing.stripe_test_clocks``)."""
    profile = hub.billing_profile
    params = _customer_params(hub, profile)
    with payment_gates.stripe_errors():
        if profile.stripe_customer_id:
            customer = stripe_service.update_customer(
                profile.stripe_customer_id, params
            )["id"]
        else:
            # One that a failed checkout created (its id rolled back with it) is found, not created again.
            found = stripe_service.find_customer(str(profile.id))
            if found is not None:
                customer = stripe_service.update_customer(found["id"], params)["id"]
            else:
                if test_clock:
                    params["test_clock"] = test_clock
                # Keyed by the payer AND what is sent: Stripe refuses the same key with other details.
                digest = hashlib.sha256(
                    json.dumps(params, sort_keys=True).encode()
                ).hexdigest()[:16]
                customer = stripe_service.create_customer(
                    params, idempotency_key=f"customer-{profile.id}-{digest}"
                )["id"]
            subscription_sync.subscription_apply(
                hub_callbacks.system_ctx_for(hub.id),
                SubscriptionApplyIn(hub_id=hub.id, stripe_customer_id=customer),
            )
            profile.stripe_customer_id = customer
        _keep_only_cleared_tax_id(customer, profile)
    return customer


def _customer_params(hub: Hub, profile) -> dict:
    """What the payer's Stripe customer holds: the billing details, the language of its mails and the payer."""
    owner = profile.owner or _owner_of(hub)
    address = {
        key: value
        for key, value in (
            ("line1", profile.billing_address),
            ("city", profile.billing_city),
            ("postal_code", profile.billing_postal_code),
            ("country", profile.billing_country),
        )
        if value
    }
    return {
        "name": profile.billing_name or hub.name,
        "email": profile.billing_email or getattr(owner, "email", ""),
        "address": address,
        "preferred_locales": [getattr(owner, "language", "") or settings.LANGUAGE_CODE],
        "metadata": {"billing_profile_id": str(profile.id)},
    }


def push_payer_to_stripe(profile_id) -> str:
    """The billing details the owner saved, onto the payer's Stripe customer: what Stripe sends
    (the page to authenticate a renewal, its receipts) and the Customer Portal show them, not the old ones.
    ``updated`` · ``skipped`` (Stripe never saw this payer: the first checkout creates the customer with them,
    ``ensure_customer``). Stripe failing raises (``stripe_errors``)."""
    profile = BillingProfile.objects.select_related("owner").get(pk=profile_id)
    hub = Hub.objects.filter(billing_profile=profile).order_by("pk").first()
    if not profile.stripe_customer_id or hub is None:
        return "skipped"
    with payment_gates.stripe_errors():
        stripe_service.update_customer(profile.stripe_customer_id, _customer_params(hub, profile))
        _keep_only_cleared_tax_id(profile.stripe_customer_id, profile)
    return "updated"


def _owner_of(hub: Hub):
    member = (
        HubMember.objects.select_related("user")
        .filter(hub=hub, role=HubMember.Role.OWNER)
        .first()
    )
    return member.user if member else None


def _keep_only_cleared_tax_id(customer: str, profile) -> None:
    """The payer's tax id as the customer's only one, or none when it has none or it may not travel to Stripe."""
    number = ""
    if (profile.tax_id or "").strip():
        clearance = vat_clearance.clear_tax_id_for_stripe(
            profile.tax_id, customer_country=profile.billing_country
        )
        number = clearance.vat_number if clearance.may_travel_to_stripe else ""
    tax_type = vat.tax_id_type_for(profile.billing_country)
    stripe_tax_ids.keep_only(
        customer, tax_type=tax_type, number=number if tax_type else "", country=profile.billing_country
    )
