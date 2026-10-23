"""Events of billing (``<app>.<entity>.<fact>``): recorded by services.py in the outbox.

billing reacts to no event of another app, so this module only names its own. What the panel shows of a
business's plan re-runs with ``hubs.subscription.changed``, which ``hubs.subscription.apply`` records in the
same transaction; billing's own lists (invoices, subscriptions) re-run with the events below (``live.py``).
"""

#: A VAT number was asked about in VIES and the answer logged (payload: ``vat_number``, ``status``).
VAT_CHECK_COMPLETED = "billing.vat_check.completed"

#: An Embedded Checkout was opened for a business (payload: ``hub_id``, ``kind``, ``attempt``).
CHECKOUT_STARTED = "billing.checkout.started"
#: A checkout paid by somebody who no longer owned the business was ended and refunded (payload: ``hub_id``,
#: ``attempt``, ``refunded`` in cents; review of saas#89).
CHECKOUT_REFUNDED = "billing.checkout.refunded"
#: A module was added to a paying business's subscription (payload: ``hub_id``, ``module``).
MODULE_ADDED = "billing.module.added"
#: A module was cancelled (it works until the end of the period) or kept after all.
MODULE_CANCELLED = "billing.module.cancelled"
MODULE_KEPT = "billing.module.kept"
#: The plan of a paying business changed (payload: ``hub_id``, ``plan``, ``interval``).
PLAN_CHANGED = "billing.plan.changed"
#: The plan was cancelled at the end of its period (back to Free then), or kept after all.
PLAN_CANCELLED = "billing.plan.cancelled"
#: A downgrade waits for the end of the period (payload: ``hub_id``, ``plan``, ``interval``; review of L3-C).
PLAN_CHANGE_SCHEDULED = "billing.plan.change_scheduled"
PLAN_KEPT = "billing.plan.kept"
#: The owner opened Stripe's Customer Portal (payload: ``hub_id``).
PORTAL_OPENED = "billing.portal.opened"

#: An invoice of ERPlora was listed (not collected yet), numbered once paid, or voided (payload: ``id``,
#: ``hub_id``, ``payment_status``).
INVOICE_RECORDED = "billing.invoice.recorded"
INVOICE_VOIDED = "billing.invoice.voided"
#: The platform hub answered about an invoice: issued, accepted or rejected (payload: ``id``, ``status``).
INVOICE_FISCAL_STATUS_CHANGED = "billing.invoice.fiscal_status_changed"
#: A credit note rectified an invoice (payload: ``id``, ``rectifies``).
CREDIT_NOTE_RECORDED = "billing.credit_note.recorded"
#: The invoices and credit notes: what re-runs ``billing.invoice.list``.
INVOICES = [INVOICE_RECORDED, INVOICE_VOIDED, INVOICE_FISCAL_STATUS_CHANGED, CREDIT_NOTE_RECORDED]

ALL = [
    VAT_CHECK_COMPLETED,
    CHECKOUT_STARTED,
    CHECKOUT_REFUNDED,
    MODULE_ADDED,
    MODULE_CANCELLED,
    MODULE_KEPT,
    PLAN_CHANGED,
    PLAN_CANCELLED,
    PLAN_KEPT,
    PLAN_CHANGE_SCHEDULED,
    PORTAL_OPENED,
    *INVOICES,
]
