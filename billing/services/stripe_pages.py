"""The payer's pages in Stripe: the Customer Portal, with its cards and Stripe's receipts, and the page that pays an
invoice not collected. The panel opens them only on the web; the apps sell nothing."""

import logging

from django.conf import settings
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base.navigation import BILLING
from billing import events, queries, stripe_service
from billing.models import Invoice
from billing.schemas.stripe_pages import InvoicePayIn, InvoicePayOut, PortalOpenIn, PortalOpenOut
from billing.services import payment_gates, stripe_sales
from hubs import emails as hub_emails
from hubs.queries import access_control

logger = logging.getLogger("billing.services")


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
