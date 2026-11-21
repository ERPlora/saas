"""``billing.checkout.start``: a business that pays nothing yet buys in an Embedded Checkout; one that pays already
previews the change."""

import logging

from django.conf import settings
from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base.navigation import BUSINESSES
from billing import events, queries, stripe_service
from billing.models import CheckoutAttempt
from billing.schemas.checkout import CheckoutStartIn, CheckoutStartOut
from billing.services import payment_gates, plan_changes, promo_codes, promo_holds, stripe_customers, stripe_sales
from billing.stripe_checkout import EMBEDDED_UI_MODE, KIND_METADATA_KEY, CheckoutKind
from hubs import emails as hub_emails
from hubs.queries import access_control
from hubs.models import Hub

logger = logging.getLogger("billing.services")


# ONE Stripe subscription per business, whose items are its plan and its bought modules, at NET prices
# plus OUR tax rates (one ``TaxRate`` per item, ``billing.TaxRule``; never ``automatic_tax``). A business
# without one pays in an Embedded Checkout; one that has it previews the proration and confirms. Every
# change is read back from Stripe and written by ``hubs.subscription.apply`` (an app writes in another
# only through its operations), which pushes the snapshot to the Hub after the COMMIT.

#: Stripe's tag of this checkout flow (Dashboard → Checkout), fixed with its 8-letter suffix.
INTEGRATION_IDENTIFIER = "erplora_saas_billing_qmvhtkzd"


@operation(
    "billing.checkout.start",
    kind="command",
    permission="billing.pay",
    input=CheckoutStartIn,
    output=CheckoutStartOut,
    ai=INTERNAL,  # stripe
)
def checkout_start(ctx: OperationContext, data: CheckoutStartIn) -> dict:
    """The owner buys a plan or a module for a business. Without a Stripe subscription (Free): an Embedded
    Checkout (``flow = checkout`` and its ``client_secret``; the same selection reuses its open session).
    With one: the prorated charge of adding it (``flow = confirm`` and ``preview``), confirmed with
    ``billing.checkout.confirm`` (a module) or ``billing.plan.change`` (a plan). Nothing is charged here."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    if stripe_sales._paying(subscription):
        interval = data.interval if data.plan else subscription.billing_interval
    else:
        interval = data.interval
    if data.plan and not stripe_sales._paying(subscription):
        asked = queries.plan_on_sale(data.plan, hub)
        if asked is not None and asked.upgrade_only:
            raise stripe_sales._upgrade_only()
    sale = (
        stripe_sales.plan_sale(hub, data.plan, interval)
        if data.plan
        else stripe_sales.module_sale(data.module, interval)
    )
    payment_gates.require_payments()
    stripe_sales._require_paid_up(hub, subscription)
    if sale.kind == "module":
        stripe_sales._require_module_not_owned(subscription, sale.slug)
    if stripe_sales._paying(subscription):
        return plan_changes._preview(hub, subscription, sale, data.promo_code)
    tax_rates = stripe_sales.price_sale(hub, sale, recurring_net=sale.net)
    customer = hub.billing_profile.stripe_customer_id
    promo = promo_codes.checkout_promo(data.promo_code, hub=hub, customer=customer) if sale.kind == "plan" else None
    with payment_gates.stripe_errors():
        terms = promo_codes.checkout_terms(sale, subscription, promo, timezone.now())
    attempt = _checkout_attempt(ctx, hub, sale, tax_rates, terms)
    return {
        "flow": "checkout",
        "session_id": attempt.stripe_session_id,
        "client_secret": attempt.client_secret,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "preview": None,
    }


def _expire_other_sessions(hub: Hub, selection: str) -> None:
    """One open checkout per business: two open sessions could both be paid, and the business would end up
    with two subscriptions. One Stripe no longer lets expire (paid meanwhile) is left to the webhook."""
    others = CheckoutAttempt.objects.filter(
        hub=hub, status=CheckoutAttempt.Status.OPEN
    ).exclude(selection=selection)
    for attempt in others.exclude(stripe_session_id=None):
        try:
            with payment_gates.stripe_errors():
                stripe_service.expire_checkout_session(attempt.stripe_session_id)
        except Conflict:
            raise
        except OperationError as refused:
            if refused.code != "billing.stripe_refused":
                raise
            logger.info(
                "[BILLING] Checkout %s could not be expired: it is not open any more",
                attempt.stripe_session_id,
            )
            continue
        CheckoutAttempt.objects.filter(pk=attempt.pk).update(
            status=CheckoutAttempt.Status.EXPIRED, updated_at=timezone.now()
        )
        promo_holds.release(attempt=attempt)


def _checkout_attempt(ctx, hub, sale: stripe_sales.Sale, tax_rates, terms: promo_codes.CheckoutTerms) -> CheckoutAttempt:
    """The open checkout of this selection, reused for a while, or a new Checkout Session."""
    # The tax rates too: a payer whose place or VAT number changed is charged anew, never at the old rate.
    selection = f"{sale.kind}:{sale.slug}:{sale.interval}:{terms.code}:{','.join(tax_rates)}"[:255]
    reusable = CheckoutAttempt.objects.filter(
        hub=hub,
        selection=selection,
        status=CheckoutAttempt.Status.OPEN,
        created_at__gt=timezone.now() - CheckoutAttempt.REUSE_FOR,
    ).exclude(client_secret="")
    attempt = reusable.order_by("-created_at").first()
    if attempt is not None:
        return attempt
    _expire_other_sessions(hub, selection)
    customer = stripe_customers.ensure_customer(hub)
    attempt = CheckoutAttempt.objects.create(
        hub=hub,
        owner=access_control.account_of(ctx),
        kind=CheckoutAttempt.Kind.PLAN
        if sale.kind == "plan"
        else CheckoutAttempt.Kind.MODULE,
        plan_slug=sale.slug if sale.kind == "plan" else "",
        module_slug=sale.slug if sale.kind == "module" else "",
        billing_interval=sale.interval,
        promo_code=terms.code,
        selection=selection,
    )
    if terms.promo is not None:
        promo_holds.hold(terms.promo, attempt, customer=customer, coupon=terms.coupon)
    kind = (
        CheckoutKind.HUB_PLAN if sale.kind == "plan" else CheckoutKind.MODULE_PURCHASE
    )
    metadata = {
        KIND_METADATA_KEY: kind.value,
        "hub_id": str(hub.id),
        sale.kind: sale.slug,
        "billing_interval": sale.interval,
        "attempt": str(attempt.id),
    }
    if terms.code:
        metadata["promo_code"] = terms.code
    subscription_data = {
        "description": f"ERPlora — {hub.name}",
        "metadata": {"hub_id": str(hub.id)},
        **terms.subscription_data,
    }
    base = hub_emails.base_url(ctx.request)
    params = {
        "ui_mode": EMBEDDED_UI_MODE,
        "mode": "subscription",
        "customer": customer,
        # With a customer, what the buyer types in the checkout is saved on it.
        "customer_update": {"name": "auto", "address": "auto"},
        "line_items": [{"price": sale.price_id, "quantity": 1, "tax_rates": tax_rates}],
        "metadata": metadata,
        "subscription_data": subscription_data,
        "redirect_on_completion": "if_required",
        "return_url": f"{base}{BUSINESSES}/{hub.id}/summary?checkout={{CHECKOUT_SESSION_ID}}",
        "locale": "auto",
        # Without an address there is no country, and without it no tax jurisdiction.
        "billing_address_collection": "required",
        # Never: Stripe reverse charges by the FORMAT of a number. Ours is asked in our form and only a
        # proved one reaches the customer (``ensure_customer``).
        "tax_id_collection": {"enabled": False},
        "integration_identifier": INTEGRATION_IDENTIFIER,
        **terms.params,
    }
    with payment_gates.stripe_errors():
        session = stripe_service.create_checkout_session(
            params, idempotency_key=f"checkout-{attempt.id}"
        )
    attempt.stripe_session_id = session["id"]
    attempt.client_secret = session.get("client_secret") or ""
    attempt.save(update_fields=["stripe_session_id", "client_secret", "updated_at"])
    record_event(
        ctx,
        events.CHECKOUT_STARTED,
        {"hub_id": str(hub.id), "kind": sale.kind, "attempt": str(attempt.id)},
    )
    return attempt
