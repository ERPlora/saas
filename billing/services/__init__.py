"""Writes of billing in Stripe: buying, changing and cancelling a plan or a module, a business handed over with a paid
plan, Stripe's webhook, the sweeps that apply the live subscription and its rates, the payer of an account that deleted
itself, the VAT number of a payer and its VIES verdict, the tax of a sale, discounts and promotion codes, ERPlora's
invoices and rectifying invoices, their issue by the platform hub and the OSS notices.

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from billing.services.live_rates import retax_payer``).
"""

# Importing a module registers its operations.
from billing.services import (
    checkout_webhooks,
    checkouts,
    departed_payers,
    discounts,
    downgrades,
    hand_overs,
    invoice_discounts,
    invoice_events,
    invoice_numbering,
    invoice_recording,
    invoice_sealing,
    invoice_webhooks,
    live_rates,
    live_subscriptions,
    module_cancellations,
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
    stripe_pages,
    stripe_sales,
    stripe_sync,
    subscription_drift,
    subscription_webhooks,
    unpaid_notices,
    unpaid_sweep,
    vat_clearance,
    webhook_dispatch,
    webhook_events,
    webhook_targets,
)
