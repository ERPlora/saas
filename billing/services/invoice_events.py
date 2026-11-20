"""The events of an invoice, told to every account that sees it, and the platform acting on an invoice."""

from functools import partial

from django.db import transaction
from live.context import OperationContext, Scope, system_context
from live.outbox import notify, record_event

from billing.models import Invoice
from hubs.queries import membership
from hubs.services import hub_callbacks


def _record_invoice_event(ctx: OperationContext, invoice: Invoice, name: str, payload: dict) -> None:
    """Record an event of an invoice in the command's channel and tell, after the COMMIT, the other account that
    sees it too (its payer and its business's owner): both their Billing lists re-run."""
    record_event(ctx, name, payload)
    owner = membership.owner_id(invoice.hub_id) if invoice.hub_id else None
    viewers = {str(account) for account in (invoice.payer_account_id, owner) if account}
    for key in sorted(viewers - {ctx.scope.key}):
        transaction.on_commit(partial(notify, Scope("user", key), [name]), robust=True)


def _invoice_ctx(invoice: Invoice) -> OperationContext:
    """The platform acting on an invoice, in its payer's channel (its Billing lists re-run)."""
    if invoice.payer_account_id:
        return system_context(Scope("user", str(invoice.payer_account_id)))
    if invoice.hub_id:
        return hub_callbacks.system_ctx_for(invoice.hub_id)
    return system_context(Scope("user", "system"))
