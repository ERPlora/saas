"""Writes of billing in Stripe: a business handed over with a paid plan, the sweeps that apply the live subscription,
the payer of an account that deleted itself, and «Pay» on an invoice not collected. Buying, changing and cancelling,
Stripe's webhook, the VAT number of a payer, its VIES verdict, the tax of a sale, ERPlora's invoices and rectifying
invoices, their issue by the platform hub and the OSS notices live in their own modules of this package."""

import logging
import uuid
from collections import Counter
from functools import partial
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.errors import NotFound as NotFoundError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.models import Module
from base.navigation import BILLING, BUSINESSES
from billing import events, queries, stripe_service, vat
from billing.models import (
    CheckoutAttempt,
    Invoice,
    PaymentFailure,
)
from billing.schemas import (
    InvoicePayIn,
    InvoicePayOut,
    CheckoutStartOut,
    HubIn,
    ModuleIn,
    PortalOpenIn,
    PortalOpenOut,
    SubscriptionOut,
)
from billing.services import (
    checkout_webhooks,
    checkouts,
    discounts,
    downgrades,
    invoice_discounts,
    invoice_events,
    invoice_numbering,
    invoice_recording,
    invoice_sealing,
    invoice_webhooks,
    live_subscriptions,
    oss_notices,
    payer_vat_numbers,
    payment_gates,
    plan_changes,
    platform_invoices,
    price_checks,
    promo_codes,
    promo_holds,
    rectifying_invoices,
    sale_tax,
    staff_test_clocks,
    stripe_customers,
    stripe_sales,
    stripe_sync,
    subscription_webhooks,
    unpaid_notices,
    vat_clearance,
    webhook_dispatch,
    webhook_events,
    webhook_targets,
)
from billing.stripe_checkout import (
    EMBEDDED_UI_MODE,
    KIND_METADATA_KEY,
    CheckoutKind,
)
from billing.stripe_keys import StripeKeyMode
from billing.stripe_period import subscription_period
from hubs import emails as hub_emails
from hubs.queries import access_control, payers
from hubs.services import refusals, suspensions
from hubs.models import BillingProfile, Hub, HubMember, Subscription, SubscriptionItem

logger = logging.getLogger("billing.services")


# --- A business handed over with a paid plan ----------------------------------------------------------


def end_renewal_after_hand_over(hub: Hub, new_owner) -> datetime | None:
    """The business ``hub`` was just handed over to ``new_owner`` (``hubs.ownership.accept``, in its transaction):
    a plan still charged to the card of another account's payer stops renewing there (Stripe
    ``cancel_at_period_end``). The business keeps it until the end of the period already paid, the previous payer
    is never charged again, and the new owner keeps it with their own card (``billing.plan.take_over``) or it
    goes back to Free on that date. A plan the new owner already pays is left alone, and so is one already ending.
    Stripe not answering refuses the hand-over (503): nothing changes hands.

    The end of that paid period, which the mail of the hand-over tells the previous payer; ``None`` on Free or when
    the new owner already pays it."""
    subscription = Subscription.objects.filter(hub=hub).first()
    if not stripe_sales._paying(subscription) or payers.plans_charged_to(hub.id, new_owner.pk).exists():
        return None
    if subscription.cancel_at_period_end:
        return subscription.current_period_end
    payment_gates.require_stripe()
    # Free wins over a downgrade that waits (Stripe refuses to cancel a scheduled subscription).
    downgrades._release_pending(hub)
    with payment_gates.stripe_errors():
        updated = stripe_service.update_subscription(
            subscription.stripe_subscription_id, {"cancel_at_period_end": True}
        )
    live_subscriptions.apply_live(hub.id, updated)
    logger.info("[BILLING] Hub %s handed over: its plan stops renewing on its previous payer's card", hub.id)
    return Subscription.objects.get(hub=hub).current_period_end


def billed_to_another_account(subscription: Subscription | None, profile) -> bool:
    """Whether the live plan of a business is charged to a Stripe customer that is not its payer's (``profile``):
    the card of the payer before a hand-over."""
    if not stripe_sales._paying(subscription):
        return False
    return profile is None or subscription.stripe_customer_id != profile.stripe_customer_id


def _nothing_to_take_over() -> Conflict:
    return Conflict(
        _("This business's plan is already paid with your card, or it is on Free: there is nothing to keep."),
        code="billing.nothing_to_take_over",
    )


@operation(
    "billing.plan.take_over",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=CheckoutStartOut,
    ai=INTERNAL,  # stripe
)
def plan_take_over(ctx: OperationContext, data: HubIn) -> dict:
    """«Keep it with my card»: the new owner of a handed-over business keeps its plan and modules with
    their own payer. An Embedded Checkout of the same prices whose billing starts on the day the paid period ends
    (``billing_cycle_anchor``, no proration): nothing is charged today and nobody pays twice. Its completion
    (``checkout_completed``) moves the business to the new subscription and ends the previous one.

    Only its owner (404 without access, 403 for another role); their own payer first (409
    ``billing.payer_required``, the form of the dialog); a business on Free or already paid with this owner's
    card has nothing to keep (409 ``billing.nothing_to_take_over``); an unpaid invoice is paid first."""
    user = access_control.account_of(ctx)
    member = access_control.access(user, data.hub_id, HubMember.Role.OWNER, lock=True)
    if not access_control.is_writable(member.hub):
        raise refusals.business_deleted()
    hub = Hub.objects.select_related("billing_profile").get(pk=member.hub_id)
    subscription = Subscription.objects.select_related("plan").filter(hub=hub).first()
    if not stripe_sales._paying(subscription) or payers.plans_charged_to(hub.id, user.pk).exists():
        raise _nothing_to_take_over()
    profile = hub.billing_profile
    if profile is None or profile.owner_id != user.pk:
        raise Conflict(
            _("Say who pays for this business first: its billing details are another account's."),
            code="billing.payer_required",
        )
    stripe_sales._require_paid_up(hub, subscription)
    payment_gates.require_payments()
    live = stripe_sales._live(subscription)
    if (live.get("status") or "") in stripe_sales.ENDED_STATUSES:
        raise _nothing_to_take_over()
    _start, period_end = subscription_period(live)
    line_items = []
    for line in stripe_sales._live_items(live):
        sale = _item_sale(subscription, line)
        if sale is None:
            raise Conflict(
                _("This business pays something we no longer sell: contact support to keep it."),
                code="billing.unknown_price",
            )
        tax_rates = stripe_sales.price_sale(hub, sale, recurring_net=stripe_sales._recurring_net(subscription, sale.interval))
        line_items.append({"price": sale.price_id, "quantity": line.get("quantity") or 1, "tax_rates": tax_rates})
    carried = discounts.takeover_discounts(subscription.stripe_subscription_id, live)
    selection = f"takeover:{subscription.stripe_subscription_id}:" + ";".join(
        f"{line['price']}={','.join(line['tax_rates'])}" for line in line_items
    ) + "".join(f":{held['coupon']}" for held in carried)
    selection = selection[:255]
    attempt = (
        CheckoutAttempt.objects.filter(
            hub=hub,
            selection=selection,
            status=CheckoutAttempt.Status.OPEN,
            created_at__gt=timezone.now() - CheckoutAttempt.REUSE_FOR,
        )
        .exclude(client_secret="")
        .order_by("-created_at")
        .first()
    )
    if attempt is None:
        attempt = _open_takeover(ctx, hub, subscription, Takeover(line_items, period_end, selection, carried))
    return {
        "flow": "checkout",
        "session_id": attempt.stripe_session_id,
        "client_secret": attempt.client_secret,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "preview": None,
    }


class Takeover(NamedTuple):
    """The checkout of a new owner keeping the plan: its lines, the end of the paid period it bills from, its
    selection and what it carries of the business's discount."""

    line_items: list[dict]
    period_end: int
    selection: str
    discounts: list[dict]


def _open_takeover(ctx, hub: Hub, subscription: Subscription, takeover: Takeover):
    checkouts._expire_other_sessions(hub, takeover.selection)
    customer = stripe_customers.ensure_customer(hub)
    attempt = CheckoutAttempt.objects.create(
        hub=hub,
        owner=access_control.account_of(ctx),
        kind=CheckoutAttempt.Kind.TAKEOVER,
        plan_slug=subscription.plan.slug if subscription.plan else "",
        billing_interval=subscription.billing_interval,
        selection=takeover.selection,
    )
    base = hub_emails.base_url(ctx.request)
    params = {
        "ui_mode": EMBEDDED_UI_MODE,
        "mode": "subscription",
        "customer": customer,
        "customer_update": {"name": "auto", "address": "auto"},
        "line_items": takeover.line_items,
        "metadata": {
            KIND_METADATA_KEY: CheckoutKind.PLAN_TAKEOVER.value,
            "hub_id": str(hub.id),
            "replaces": subscription.stripe_subscription_id,
            "attempt": str(attempt.id),
        },
        "subscription_data": {
            "description": f"ERPlora — {hub.name}",
            "metadata": {"hub_id": str(hub.id)},
            # Billed from the day the paid period ends, nothing before it: the business uses what was paid.
            "billing_cycle_anchor": takeover.period_end,
            "proration_behavior": "none",
        },
        "redirect_on_completion": "if_required",
        "return_url": f"{base}{BUSINESSES}/{hub.id}/summary?checkout={{CHECKOUT_SESSION_ID}}",
        "locale": "auto",
        "billing_address_collection": "required",
        "tax_id_collection": {"enabled": False},
        "integration_identifier": checkouts.INTEGRATION_IDENTIFIER,
    }
    if takeover.discounts:
        params["discounts"] = takeover.discounts
    with payment_gates.stripe_errors():
        session = stripe_service.create_checkout_session(params, idempotency_key=f"checkout-{attempt.id}")
    attempt.stripe_session_id = session["id"]
    attempt.client_secret = session.get("client_secret") or ""
    attempt.save(update_fields=["stripe_session_id", "client_secret", "updated_at"])
    record_event(
        ctx,
        events.CHECKOUT_STARTED,
        {"hub_id": str(hub.id), "kind": "takeover", "attempt": str(attempt.id)},
    )
    return attempt


def _bought_item(subscription: Subscription | None, slug: str) -> SubscriptionItem:
    item = (
        SubscriptionItem.objects.filter(
            subscription=subscription, module_slug=slug
        ).first()
        if subscription is not None
        else None
    )
    if item is None:
        raise NotFoundError(_("This business has no such module."))
    if item.source == SubscriptionItem.Source.PLAN:
        raise Conflict(
            _("This module comes with the plan: change the plan to drop it."),
            code="billing.module_included",
        )
    return item


@operation(
    "billing.module.cancel",
    kind="command",
    permission="billing.pay",
    input=ModuleIn,
    output=SubscriptionOut,
    ai=INTERNAL,  # unused
)
def module_cancel(ctx: OperationContext, data: ModuleIn) -> dict:
    """Cancel a bought module: it leaves the subscription without proration and works until the end of the
    period (``valid_until`` in the snapshot). The last thing a subscription bills ends the
    subscription at the end of the period instead (Stripe keeps at least one item)."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    downgrades._require_no_pending_change(hub)
    item = _bought_item(subscription, data.module)
    if item.valid_until is not None:
        return live_subscriptions.subscription_out(hub.id)
    payment_gates.require_stripe()
    live = stripe_sales._live(subscription)
    others = [line for line in stripe_sales._live_items(live) if line["id"] != item.stripe_item_id]
    with payment_gates.stripe_errors():
        if others:
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id,
                {
                    "items": [{"id": item.stripe_item_id, "deleted": True}],
                    "proration_behavior": "none",
                },
            )
        else:
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": True}
            )
    live_subscriptions.apply_live(hub.id, updated)
    record_event(
        ctx, events.MODULE_CANCELLED, {"hub_id": str(hub.id), "module": data.module}
    )
    return live_subscriptions.subscription_out(hub.id)


@operation(
    "billing.module.keep",
    kind="command",
    permission="billing.pay",
    input=ModuleIn,
    output=SubscriptionOut,
    ai=INTERNAL,  # unused
)
def module_keep(ctx: OperationContext, data: ModuleIn) -> dict:
    """Undo the cancellation of a module before it ends: it is billed again from the next renewal (nothing
    is charged now: the period was paid). Not with an unpaid invoice, nor once it ended (buy it again),
    nor while the plan itself is cancelled (keep the plan first)."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    downgrades._require_no_pending_change(hub)
    item = _bought_item(subscription, data.module)
    if item.valid_until is None:
        return live_subscriptions.subscription_out(hub.id)
    if item.valid_until <= timezone.now():
        raise Conflict(
            _("This module has ended: buy it again in the store."),
            code="billing.module_ended",
        )
    if queries.module_on_sale(item.module_slug) is None:
        # It works until its cancellation ends, and is not sold again by undoing it.
        raise Conflict(
            _("This module is no longer sold: it works until its cancellation ends and cannot be kept."),
            code="billing.module_off_sale",
        )
    stripe_sales._require_paid_up(hub, subscription)
    payment_gates.require_stripe()
    live = stripe_sales._live(subscription)
    billed = {line["id"] for line in stripe_sales._live_items(live)}
    with payment_gates.stripe_errors():
        if item.stripe_item_id and item.stripe_item_id in billed:
            if stripe_sales._plan_item(live) is not None:
                raise Conflict(
                    _(
                        "The plan is cancelled, and its modules with it: keep the plan first."
                    ),
                    code="billing.plan_cancelled",
                )
            live = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": False}
            )
        else:
            stripe_sales._require_room(live)
            sale = stripe_sales.module_sale(
                item.module_slug,
                subscription.billing_interval,
                module=Module.objects.filter(slug=item.module_slug).first(),
            )
            tax_rates = stripe_sales.price_sale(
                hub,
                sale,
                recurring_net=stripe_sales._recurring_net(subscription, sale.interval, adding=sale),
            )
            stripe_service.create_subscription_item(
                {
                    "subscription": subscription.stripe_subscription_id,
                    "price": sale.price_id,
                    "quantity": 1,
                    "tax_rates": tax_rates,
                    "proration_behavior": "none",
                    "metadata": {"hub_id": str(hub.id), "module": sale.slug},
                },
                # Its own request: keeping again after cancelling again must not replay the first keep.
                idempotency_key=f"module-keep-{hub.id}-{sale.slug}-{uuid.uuid4().hex}",
            )
            live = stripe_service.retrieve_subscription(
                subscription.stripe_subscription_id
            )
            if not any(
                (
                    found := queries.module_for_price(
                        (line.get("price") or {}).get("id", "")
                    )
                )
                and found[0].slug == sale.slug
                for line in stripe_sales._live_items(live)
            ):
                logger.error(
                    "[BILLING] Hub %s kept %s but Stripe does not bill it back",
                    hub.id,
                    sale.slug,
                )
                raise OperationError(
                    _(
                        "The payment service did not confirm the change. Nothing was charged; try again."
                    ),
                    code="billing.not_confirmed",
                    status=502,
                )
    live_subscriptions.apply_live(hub.id, live)
    record_event(
        ctx, events.MODULE_KEPT, {"hub_id": str(hub.id), "module": data.module}
    )
    return live_subscriptions.subscription_out(hub.id)


@operation(
    "billing.portal.open",
    kind="command",
    permission="billing.pay",
    input=PortalOpenIn,
    output=PortalOpenOut,
    ai=INTERNAL,  # stripe
)
def portal_open(ctx: OperationContext, data: PortalOpenIn) -> dict:
    """Stripe's Customer Portal for the payer of the business: cards and Stripe's receipts (the panel opens
    it only on the web; the apps sell nothing)."""
    hub, _subscription = stripe_sales._owned(ctx, data.hub_id)
    payment_gates.require_stripe()
    if not settings.STRIPE_PORTAL_CONFIGURATION:
        logger.error(
            "[BILLING] STRIPE_PORTAL_CONFIGURATION is empty: the Customer Portal does not open"
        )
        raise OperationError(
            _("Payment details cannot be managed right now. Try again later."),
            code="billing.portal_unavailable",
            status=503,
        )
    customer = hub.billing_profile.stripe_customer_id if hub.billing_profile else ""
    if not customer:
        raise Conflict(
            _("The payment details appear here after the first payment."),
            code="billing.no_customer",
        )
    with payment_gates.stripe_errors():
        session = stripe_service.create_portal_session(
            customer,
            return_url=f"{hub_emails.base_url(ctx.request)}{BILLING}",
            configuration=settings.STRIPE_PORTAL_CONFIGURATION,
        )
    record_event(ctx, events.PORTAL_OPENED, {"hub_id": str(hub.id)})
    return {"url": session["url"]}


def expire_open_checkouts(hub_id) -> None:
    """After a hand-over's COMMIT (``hubs.ownership.accept``): the Checkout Sessions the business had open (its
    previous owner's) can no longer be paid (Stripe's ``expire``). One Stripe no longer lets expire (paid meanwhile)
    is left to the webhook, which refunds a payment of somebody who no longer owns it (``_end_not_owner``); Stripe
    away is logged as an error and changes nothing else: the hand-over is done either way."""
    for attempt in CheckoutAttempt.objects.filter(hub_id=hub_id, status=CheckoutAttempt.Status.OPEN).exclude(
        stripe_session_id=None
    ):
        try:
            stripe_service.expire_checkout_session(attempt.stripe_session_id)
        except stripe_service.StripeRefused as refused:
            logger.info(
                "[BILLING] Checkout %s of hub %s is not open any more (%s): the webhook decides",
                attempt.stripe_session_id,
                hub_id,
                refused.code,
            )
            continue
        except (stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured) as failed:
            logger.error(
                "[BILLING] Checkout %s of hub %s stays open after its hand-over: %s. A payment of it is refunded by "
                "the webhook",
                attempt.stripe_session_id,
                hub_id,
                failed,
                extra={"event": "billing.checkout_not_expired", "hub_id": str(hub_id)},
            )
            continue
        attempt.status = CheckoutAttempt.Status.EXPIRED
        attempt.save(update_fields=["status", "updated_at"])
        promo_holds.release(attempt=attempt)


# --- saas-cron: manage.py sync_subscriptions ----------------------------------------------------------

#: The counts of a pass; ``missing`` and ``errors`` make the run fail after it (``task_failed``).
SYNC_COUNTS = ("checked", "in_sync", "fixed", "drifted", "pending", "missing", "errors")
#: What the log names when a subscription drifted (``hubs.subscription.apply`` decides what is written).
DRIFT_FIELDS = (
    "plan",
    "billing_interval",
    "status",
    "stripe_subscription_id",
    "current_period_start",
    "current_period_end",
    "cancel_at_period_end",
    "trial_start",
    "trial_end",
)


def _drift(subscription: Subscription, state: dict) -> list[str]:
    """The fields where what Stripe says (``state``) and what erplora.com holds differ, bought modules too."""
    held = {field: getattr(subscription, field) for field in DRIFT_FIELDS if field != "plan"}
    held["plan"] = subscription.plan.slug
    fields = [field for field in DRIFT_FIELDS if field in state and state[field] != held[field]]
    bought = {
        (item.module_slug, item.valid_until)
        for item in subscription.items.filter(source=SubscriptionItem.Source.PURCHASE)
    }
    if {(right.module_slug, right.valid_until) for right in state["modules"]} != bought:
        fields.append("modules")
    return fields


def sync_subscription(subscription: Subscription, *, apply: bool = True) -> str:
    """Read the business's subscription from Stripe and write what it says, as a lost
    ``customer.subscription.updated`` would have (``live_state``), under the business's lock.
    ``in_sync`` · ``fixed`` · ``drifted`` (``apply=False``: nothing written) · ``pending`` (its first payment is
    not done) · ``missing`` (Stripe does not know it: left as it is, for the team). Stripe not answering raises
    (``stripe_service.StripeUnavailable``)."""
    hub = subscription.hub
    with stripe_sync.holding(hub.id):
        # Read inside the lock, as the webhook does: nothing changes the business between reading and writing.
        try:
            live = stripe_service.retrieve_subscription(subscription.stripe_subscription_id)
        except stripe_service.StripeRefused as refused:
            if refused.code != "resource_missing":
                raise
            logger.error(
                "[BILLING] Stripe does not know subscription %s of hub %s",
                subscription.stripe_subscription_id,
                hub.id,
                extra={"event": "billing.subscription_missing", "hub_id": str(hub.id)},
            )
            return "missing"
        if live.get("status") in ("incomplete", ""):
            return "pending"
        held = Subscription.objects.select_related("plan").get(pk=subscription.pk)
        state = live_subscriptions.live_state(hub, live)
        fields = _drift(held, state)
        changed = live_subscriptions.apply_state(hub, state)
        if not apply:
            # Everything the reading wrote (a card noted as changed included) goes back.
            transaction.set_rollback(True)
        elif changed:
            downgrades._forget_applied_change(hub.id, live)
    if not changed:
        return "in_sync"
    logger.warning(
        "[BILLING] Subscription %s of hub %s drifted from Stripe: %s",
        subscription.stripe_subscription_id,
        hub.id,
        ", ".join(fields) or "its standing",
        extra={"event": "billing.subscription_drift", "hub_id": str(hub.id), "fields": fields},
    )
    return "fixed" if apply else "drifted"


def sync_subscriptions(*, apply: bool = True) -> Counter:
    """One pass of ``manage.py sync_subscriptions``: every subscription Stripe still bills (with its id), one at a
    time; one business never stops the others."""
    counts = Counter({key: 0 for key in SYNC_COUNTS})
    for subscription in (
        Subscription.objects.exclude(stripe_subscription_id="").select_related("hub").order_by("pk")
    ):
        counts["checked"] += 1
        try:
            counts[sync_subscription(subscription, apply=apply)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; the next one reads it again
            logger.exception(
                "[BILLING] Subscription %s could not be read from Stripe",
                subscription.stripe_subscription_id,
                extra={"event": "billing.sync_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts


# --- The rate of a live subscription ------------------------------------------------------------------

#: Stripe statuses whose next invoice is still going to be charged.
RETAX_STATUSES = ("active", "trialing", "past_due")
#: The counts of a daily pass; ``refused`` and ``errors`` make the run fail after its pass (``task_failed``).
RETAX_COUNTS = ("retaxed", "unchanged", "skipped", "refused", "errors")


def _item_sale(subscription: Subscription, line: dict) -> stripe_sales.Sale | None:
    """What an item of the live subscription sells (its plan or its module, at its interval), or ``None`` for
    a price no plan nor module has."""
    price_id = (line.get("price") or {}).get("id", "")
    found = queries.plan_for_price(price_id)
    if found is not None:
        plan, interval = found
        return stripe_sales.Sale(
            "plan",
            plan.slug,
            interval,
            price_id,
            Decimal((plan.price_annual if interval == "year" else plan.price_monthly) or 0),
            vat.SAAS_SUBSCRIPTION_CATEGORY,
            plan=plan,
        )
    found = queries.module_for_price(price_id)
    if found is not None:
        module, interval = found
        cents = module.price_annual_cents if interval == "year" else module.price_monthly_cents
        return stripe_sales.Sale(
            "module",
            module.slug,
            interval,
            price_id,
            Decimal(cents) / 100,
            vat.SOFTWARE_LICENSE_CATEGORY,
            module=module,
        )
    logger.warning(
        "[BILLING] Item %s of %s bills price %s, which no plan nor module has: its rate is left alone",
        line.get("id"),
        subscription.stripe_subscription_id,
        price_id,
    )
    return None


def retax_subscription(hub: Hub) -> str:
    """Hand Stripe the rates the payer's place calls for today on every item of the business's live
    subscription: the checkout fixes a rate per item and Stripe charges it on every renewal, so a payer who
    moves (Madrid → Las Palmas), proves a VAT number, or a year that crosses the OSS threshold would keep the
    old one. The same engine as the sale (``price_sale``); the next invoice takes the new rate,
    the paid period is not touched (no proration).

    ``retaxed`` · ``unchanged`` (Stripe already holds them: nothing sent) · ``skipped`` (no live Stripe
    subscription, or one still charged to another account's card: its tax is that payer's) ·
    ``refused`` (the place is not sold to now: an ERROR, and the old rates stay until the billing details are
    fixed). With a downgrade waiting in a schedule, its phases are retaxed instead (``_retax_schedule``). Stripe
    failing raises (``stripe_errors``)."""
    subscription = Subscription.objects.filter(hub=hub).select_related("plan").first()
    if (
        subscription is None
        or not subscription.stripe_subscription_id
        or subscription.status not in RETAX_STATUSES
    ):
        return "skipped"
    hub = Hub.objects.select_related("billing_profile").get(pk=hub.pk)
    if billed_to_another_account(subscription, hub.billing_profile):
        return "skipped"
    payment_gates.require_stripe()
    pending = downgrades.pending_change(hub)
    if pending is not None:
        return _retax_schedule(hub, subscription, pending.stripe_schedule_id)
    live = stripe_sales._live(subscription)
    changes = []
    for line in stripe_sales._live_items(live):
        sale = _item_sale(subscription, line)
        if sale is None:
            continue
        try:
            due = stripe_sales.price_sale(
                hub, sale, recurring_net=stripe_sales._recurring_net(subscription, sale.interval), renewing=True
            )
        except Conflict as refused:
            return _retax_refused(hub, sale.kind, refused)
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in line.get("tax_rates") or []]
        if sorted(held) != sorted(due):
            changes.append({"id": line["id"], "tax_rates": stripe_sync._rates_param(due)})
    if not changes:
        return "unchanged"
    with payment_gates.stripe_errors():
        stripe_service.update_subscription(
            subscription.stripe_subscription_id,
            {"items": changes, "proration_behavior": "none"},
        )
    logger.info("[BILLING] Hub %s retaxed: %s", hub.id, changes)
    return "retaxed"


def _retax_refused(hub: Hub, kind: str, refused: Conflict) -> str:
    logger.error(
        "[BILLING] %s of hub %s cannot be retaxed (%s): Stripe keeps charging its old rate",
        kind,
        hub.id,
        refused.code,
        extra={"event": "billing.retax_refused", "hub_id": str(hub.id), "code": refused.code},
    )
    return "refused"


def _retax_schedule(hub: Hub, subscription: Subscription, schedule_id: str) -> str:
    """A downgrade waiting in a Stripe schedule: the first invoice of the new plan is billed by its next phase,
    whose items carry the rates fixed when it was scheduled. Every phase still to run is re-stated with
    today's rates (a phase over is left out; the current one keeps its start) and its discounts. Phases are
    re-stated whole, so no rate is an empty list there, and changing the current phase changes the subscription
    at once (checked against Stripe's test API). A price no plan nor module has keeps its rates."""
    with payment_gates.stripe_errors():
        schedule = stripe_service.retrieve_schedule(schedule_id)
    now = int(timezone.now().timestamp())
    phases = []
    changed = False
    for phase in schedule.get("phases") or []:
        if phase.get("end_date") is not None and phase["end_date"] <= now:
            continue
        restated = _restated_items(hub, subscription, phase)
        if restated is None:
            return "refused"
        items, retaxed = restated
        changed = changed or retaxed
        phases.append(_restated_phase(phase, items))
    if not changed:
        return "unchanged"
    with payment_gates.stripe_errors():
        stripe_service.update_schedule(schedule_id, {"end_behavior": "release", "phases": phases})
    logger.info("[BILLING] Hub %s retaxed the phases of schedule %s", hub.id, schedule_id)
    return "retaxed"


def _restated_items(hub: Hub, subscription: Subscription, phase: dict) -> tuple[list[dict], bool] | None:
    """The items of a phase with today's rates, and whether any changed; ``None`` when one cannot be retaxed."""
    sales = []
    for item in phase.get("items") or []:
        price = item["price"] if isinstance(item["price"], str) else item["price"]["id"]
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in item.get("tax_rates") or []]
        sales.append((price, item.get("quantity") or 1, held, _item_sale(subscription, {"price": {"id": price}})))
    # What a renewal of that phase charges, net: the 400 € of the simplified invoice is on the whole of it.
    recurring = sum((sale.net for _price, _quantity, _held, sale in sales if sale is not None), Decimal("0"))
    items = []
    changed = False
    for price, quantity, held, sale in sales:
        due = held
        if sale is not None:
            try:
                due = stripe_sales.price_sale(hub, sale, recurring_net=recurring, renewing=True)
            except Conflict as refused:
                _retax_refused(hub, sale.kind, refused)
                return None
        changed = changed or sorted(held) != sorted(due)
        items.append({"price": price, "quantity": quantity, "tax_rates": due})
    return items, changed


def _restated_phase(phase: dict, items: list[dict]) -> dict:
    restated = {"items": items, "start_date": phase["start_date"], "proration_behavior": "none"}
    if phase.get("end_date") is not None:
        restated["end_date"] = phase["end_date"]
    if phase.get("trial_end"):
        restated["trial_end"] = phase["trial_end"]
    restated["discounts"] = discounts.held_discounts(phase)
    return restated


def retax_payer(profile_id) -> None:
    """After the owner saves the billing details (on commit): the payer's Stripe customer takes them
    and every business this payer pays is retaxed. A failure is logged and never
    stops the other: the next checkout brings the customer up to date (``ensure_customer``), the daily pass
    (``retax_subscriptions``) retaxes again."""
    paid = list(Hub.objects.filter(billing_profile_id=profile_id).order_by("pk"))
    try:
        stripe_customers.push_payer_to_stripe(profile_id)
    except Exception:  # noqa: BLE001 - the save stands; the next checkout updates the customer
        logger.exception(
            "[BILLING] The Stripe customer of payer %s did not take the new billing details",
            profile_id,
            extra={"event": "billing.customer_push_failed", "hub_id": str(paid[0].id) if paid else ""},
        )
    for hub in paid:
        try:
            retax_subscription(hub)
        except Exception:  # noqa: BLE001 - the save stands; the daily pass retaxes it
            logger.exception(
                "[BILLING] Hub %s could not be retaxed after its billing details changed",
                hub.id,
                extra={"event": "billing.retax_failed", "hub_id": str(hub.id)},
            )


def retax_live_subscriptions() -> Counter:
    """One daily pass: every live Stripe subscription takes the rates of today (an address change whose push
    failed, the OSS threshold crossed or a new year back to origin, a rate the table schedules). One business
    never stops the others."""
    counts = Counter({key: 0 for key in RETAX_COUNTS})
    live = (
        Subscription.objects.filter(status__in=RETAX_STATUSES)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in live:
        try:
            counts[retax_subscription(subscription.hub)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[BILLING] %s could not be retaxed",
                subscription.stripe_subscription_id,
                extra={"event": "billing.retax_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts


# --- saas-cron: manage.py sweep_unpaid ----------------------------------------------------------------

#: The counts a sweep reports; ``errors`` makes the run fail after its whole pass (``task_failed``).
SWEEP_COUNTS = (
    "checked",
    "suspended",
    "cancelled",
    "payers_forgotten",
    "notified",
    "mail_failed",
    "errors",
    # The clock of the suspended businesses (``hubs.services.suspensions.age_suspended``).
    "warned",
    "final_notice",
    "expired",
    "undated",
)
#: Businesses whose unpaid plan the sweep looks at: still running (a suspended one already is).
SWEPT_STATUSES = [Hub.Status.PREPARING, Hub.Status.ACTIVE, Hub.Status.PAST_DUE]


def sweep_unpaid() -> Counter:  # noqa: C901, PLR0912, PLR0915
    """One pass of ``sweep_unpaid``: every business in dunning still running is replayed with its
    OLDEST open invoice through ``invoice_payment_failed`` (the live subscription decides; ``unpaid`` at once,
    else past the grace; one suspension), and the Stripe subscription of every deleted business is
    cancelled now. One business never stops the others; Stripe missing or failing for one is an error."""
    counts = Counter({key: 0 for key in SWEEP_COUNTS})
    configured = stripe_service.key_mode() is not StripeKeyMode.UNKNOWN
    owed = (
        Subscription.objects.filter(
            status__in=stripe_sales.DUNNING_STATUSES, hub__status__in=SWEPT_STATUSES
        )
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in owed:
        counts["checked"] += 1
        if not configured:
            logger.error(
                "[UNPAID SWEEP] Stripe is not configured: %s is not swept",
                subscription.stripe_subscription_id,
            )
            counts["errors"] += 1
            continue
        try:
            invoices = stripe_service.open_invoices(subscription.stripe_subscription_id)
            if invoices:
                invoice_webhooks.invoice_payment_failed(
                    min(invoices, key=lambda invoice: invoice.get("created") or 0),
                    replay=True,
                )
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[UNPAID SWEEP] %s could not be swept",
                subscription.stripe_subscription_id,
            )
            counts["errors"] += 1
            continue
        if Hub.objects.filter(
            pk=subscription.hub_id, status=Hub.Status.SUSPENDED
        ).exists():
            counts["suspended"] += 1
    # The businesses suspended too long: the notices of day 30 and 150 and the deletion
    # on day 180, which the loop below ends in Stripe in this same pass.
    counts.update(suspensions.age_suspended())
    # Asked at deletion (``hubs.business.delete``), whatever the business is now: recovered on Free, too.
    deleted = (
        Subscription.objects.filter(cancel_requested_at__isnull=False)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in deleted:
        if not configured:
            logger.error(
                "[UNPAID SWEEP] Stripe is not configured: deleted hub %s still pays",
                subscription.hub_id,
            )
            counts["errors"] += 1
            continue
        try:
            _end_billing_of_deleted(subscription)
        except Exception:  # noqa: BLE001 - kept for the next run, which fails until it goes through
            logger.exception(
                "[UNPAID SWEEP] The billing of deleted hub %s could not be ended",
                subscription.hub_id,
            )
            counts["errors"] += 1
            continue
        counts["cancelled"] += 1
    # The payers of deleted accounts, once nothing more can be charged to them.
    departed = BillingProfile.objects.filter(forget_after__isnull=False).order_by("pk").values_list("pk", flat=True)
    for profile_id in list(departed):
        try:
            outcome = forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - one payer never stops the pass; it is retried on the next one
            logger.exception("[UNPAID SWEEP] The payer %s of a deleted account could not be forgotten", profile_id)
            counts["errors"] += 1
            continue
        if outcome == PAYER_FORGOTTEN:
            counts["payers_forgotten"] += 1
    # A mail of the unpaid episode that could not leave is sent again here.
    untold = (
        PaymentFailure.objects.filter(resolved_at__isnull=True)
        .filter(
            Q(hub__status=Hub.Status.PAST_DUE, notified_at__isnull=True)
            | Q(hub__status=Hub.Status.SUSPENDED, suspension_notified_at__isnull=True)
        )
        .values_list("hub_id", flat=True)
        .distinct()
    )
    for hub_id in sorted(set(untold)):
        try:
            outcome = unpaid_notices.notify_unpaid(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("[UNPAID SWEEP] The payer of hub %s could not be told", hub_id)
            outcome = unpaid_notices.MAIL_NOT_SENT
        if outcome == unpaid_notices.NOTIFIED:
            counts["notified"] += 1
        elif outcome == unpaid_notices.MAIL_NOT_SENT:
            counts["mail_failed"] += 1
    return counts


def _end_billing_of_deleted(subscription: Subscription) -> None:
    """A deleted business stops paying now (``test_hub_delete_cancels_billing``): a subscription Stripe no
    longer has counts as ended; any other failure keeps it for the next run."""
    try:
        stripe_service.cancel_subscription(subscription.stripe_subscription_id)
    except stripe_service.StripeRefused as refused:
        if refused.code != "resource_missing":
            raise
    logger.info(
        "[UNPAID SWEEP] Ended %s of deleted hub %s",
        subscription.stripe_subscription_id,
        subscription.hub_id,
    )
    with transaction.atomic():
        live_subscriptions.apply_state(subscription.hub, live_subscriptions.ended_state(subscription.hub))


# --- The payer of an account that deleted itself ------------------------------------------------------
#
# GDPR art. 17: the payer record (``hubs.BillingProfile``) and its Stripe customer go with the account; the
# invoices ERPlora issued keep their own copy of the payer (Commercial Code art. 30, General Tax Law art. 66),
# which is what the law asks to keep (art. 17(3)(b)). Only what can still be charged holds the payer, because
# the invoice issued at that payment must name it: a subscription Stripe still bills, or an invoice not paid
# yet, which waits at most ``PAYER_RETENTION`` and is then voided in Stripe, as Stripe advises for a deletion
# request (docs.stripe.com/privacy/deletion-requests).

#: How long the payer of a deleted account waits for an invoice still unpaid: the 90 days a deleted business
#: is kept (``Hub.RETENTION``). On that day (``forget_after``) what is unpaid is voided and the payer goes.
PAYER_RETENTION = Hub.RETENTION
PAYER_FORGOTTEN = "forgotten"
PAYER_HELD = "held"


def payer_leaving(sender, user_id, **kwargs) -> None:
    """``accounts.signals.account_deleting``: each payer of the account gets its purge date and goes after the
    COMMIT, unless something can still be charged to it (``forget_departed_payer``; ``sweep_unpaid`` finishes).

    A live subscription only holds it here in a business that was deleted, which ``sweep_unpaid`` cancels on its
    next pass. A business still alive never does: whoever still pays for it (``hubs.queries.payers.still_pays``) can
    neither delete its account (409 ``accounts.pays_businesses``) nor be taken out of it (409 ``hubs.member_pays``)."""
    profile_ids = list(BillingProfile.objects.filter(owner_id=user_id).values_list("pk", flat=True))
    if not profile_ids:
        return
    now = timezone.now()
    BillingProfile.objects.filter(pk__in=profile_ids).update(forget_after=now + PAYER_RETENTION, updated_at=now)
    transaction.on_commit(partial(_forget_payers_quietly, profile_ids), robust=True)


def _forget_payers_quietly(profile_ids) -> None:
    for profile_id in profile_ids:
        try:
            forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the deletion; sweep_unpaid retries
            logger.exception("[PAYER] The payer %s of a deleted account could not be forgotten yet", profile_id)


def forget_departed_payer(profile_id, now: datetime | None = None) -> str:
    """Forget the payer of a deleted account (``forget_after`` set) once nothing can be charged to it any more:
    no subscription Stripe still bills for its businesses, and no invoice of it unpaid (from its purge date,
    those are voided in Stripe first). Its Stripe customer is deleted, its businesses stop naming it and the
    record goes. ``PAYER_HELD`` while something holds it; a Stripe failure raises (the sweep counts it)."""
    now = now or timezone.now()
    profile = BillingProfile.objects.filter(pk=profile_id, forget_after__isnull=False).first()
    if profile is None:
        return PAYER_FORGOTTEN
    if Subscription.objects.filter(hub__billing_profile=profile).exclude(stripe_subscription_id="").exists():
        return PAYER_HELD
    unpaid = Invoice.objects.filter(
        Q(billing_profile=profile) | Q(hub__billing_profile=profile), payment_status=Invoice.PaymentStatus.OPEN
    )
    if unpaid.exists():
        if now < profile.forget_after:
            return PAYER_HELD
        for stripe_invoice_id in list(unpaid.values_list("stripe_invoice_id", flat=True)):
            invoice_recording.invoice_voided(stripe_service.void_invoice(stripe_invoice_id))
    if profile.stripe_customer_id:
        try:
            stripe_service.delete_customer(profile.stripe_customer_id)
        except stripe_service.StripeRefused as refused:
            if refused.code != "resource_missing":
                raise
    with transaction.atomic():
        Hub.objects.filter(billing_profile=profile).update(billing_profile=None, updated_at=now)
        profile.delete()
    logger.info("[PAYER] The payer %s of a deleted account is forgotten", profile_id)
    return PAYER_FORGOTTEN


# --- «Pay» an invoice not collected -----------------------------------------------------------------


@operation(
    "billing.invoice.pay",
    kind="command",
    permission="billing.pay",
    input=InvoicePayIn,
    output=InvoicePayOut,
    ai=INTERNAL,  # stripe
)
def invoice_pay(ctx: OperationContext, data: InvoicePayIn) -> dict:
    """Stripe's page to pay an invoice not collected (the panel opens it only on the web; the apps sell
    nothing). Only its payer pays it; with a card the bank declined, «Pay» waits until the
    card changes (409 ``billing.card_change_required``)."""
    user = access_control.account_of(ctx)
    invoice = queries.invoice_of(user, data.id)
    if invoice.payment_status == Invoice.PaymentStatus.PAID:
        raise Conflict(_("This invoice is paid already."), code="billing.invoice_paid")
    if invoice.payment_status == Invoice.PaymentStatus.VOID or not invoice.hosted_invoice_url:
        raise Conflict(_("This invoice was cancelled: there is nothing to pay."), code="billing.invoice_void")
    if not queries.pays_for(user, invoice):
        raise Conflict(
            _("Only the account that pays this business can pay its invoices."), code="billing.payer_required"
        )
    if queries.card_change_required(invoice):
        raise Conflict(
            _("The bank declined the card. Change the card first, then pay the invoice."),
            code="billing.card_change_required",
        )
    return {"url": invoice.hosted_invoice_url}

