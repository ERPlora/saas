"""Live queries of billing and the events that re-run them after the COMMIT (lot L3-C; plan 2026-10-13 §3).

The scope is the account (PLAN-SAAS §6): the webhook records an invoice in its payer's channel (or its
business owner's) and ``hubs.subscription.apply`` in the owner's, so the Billing section of that account
re-runs; anybody else sees a change at the 300 s safety re-run or on reload. The payment method is not live:
it asks Stripe, and is read when the tab opens.
"""

from live.live_registry import live

from billing import events
from hubs import events as hub_events

live("billing.invoice.list", on=[*events.INVOICES])
# The page of one invoice (BILLING-G05): «Issuing» turns into its number and QR while it is on screen.
live("billing.invoice.get", on=[*events.INVOICES])
live(
    "billing.subscription.list",
    on=[
        hub_events.SUBSCRIPTION_CHANGED,
        hub_events.BILLING_PROFILE_UPDATED,
        events.PLAN_CHANGED,
        events.PLAN_CANCELLED,
        events.PLAN_KEPT,
        events.PLAN_CHANGE_SCHEDULED,
        events.MODULE_ADDED,
        events.MODULE_CANCELLED,
        events.MODULE_KEPT,
        events.INVOICE_RECORDED,
        events.INVOICE_VOIDED,
    ],
)
