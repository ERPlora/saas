"""The audit trail of the billing models (django-auditlog; ACCOUNTS-F36, PLAN-SAAS §1.1). Registered from
``BillingConfig.ready``.

Who changed what ERPlora charges and how (the VAT rules and their categories, the fiscal policy, ERPlora's company data
on the invoices, the promo codes) and what Stripe did to a business's money (a checkout, a promo code used, an unpaid
renewal, an invoice, its lines and its VeriFactu state, a downgrade waiting). Never logged: an Embedded Checkout's
client secret (a Stripe credential), the links that open a Stripe invoice to whoever holds them, and the fields that
move by themselves (the OSS accumulators, a promo code's count, an invoice's sending queue, every ``updated_at``). Not
registered: the VIES log, the webhook queue, the invoice counter and the OSS notices, each a log, a queue or a counter
of its own (``billing/tests/test_auditlog.py`` says why). The trail only reads a fiscal record: it writes its own table.
"""

from accounts.auditlog import audit
from billing.models import (
    CheckoutAttempt,
    CompanyConfig,
    FiscalPolicy,
    Invoice,
    InvoiceLine,
    PaymentFailure,
    PlanChangeSchedule,
    PromoCode,
    PromoRedemption,
    TaxCategory,
    TaxRule,
)


def register() -> None:
    audit(TaxCategory, exclude=["updated_at"])
    audit(TaxRule, exclude=["updated_at"])
    audit(
        FiscalPolicy,
        exclude=["oss_carried_year", "oss_carried_current_cents", "oss_carried_previous_cents", "updated_at"],
    )
    audit(CompanyConfig, exclude=["updated_at"])
    audit(PromoCode, exclude=["redemption_count", "updated_at"])
    audit(PromoRedemption)
    audit(CheckoutAttempt, exclude=["client_secret", "updated_at"])
    audit(PaymentFailure, exclude=["hosted_invoice_url"])
    audit(Invoice, exclude=["hosted_invoice_url", "post_attempts", "next_post_at", "last_post_error", "updated_at"])
    audit(InvoiceLine)
    audit(PlanChangeSchedule)
