"""Models of billing: the EU VAT engine, what Stripe needs remembered and ERPlora's invoices to its customers.

The invoice PDF and the VeriFactu records are not here: ERPlora's platform hub issues the legal invoice.
"""

from billing.models.tax import (
    GENERIC_CATEGORY,
    CompanyConfig,
    FiscalPolicy,
    SingletonModel,
    TaxCategory,
    TaxRule,
    VatCheck,
    country_code_validator,
    region_code_validator,
)
from billing.models.discounts import MAX_DISCOUNT_MONTHS, Discount
from billing.models.promo_codes import MAX_PROMO_TRIAL_DAYS, PromoCode, PromoRedemption, normalise_promo_code
from billing.models.payments import CheckoutAttempt, PaymentFailure, WebhookEvent
from billing.models.invoices import TAX_TREATMENTS, Invoice, InvoiceCounter, InvoiceLine
from billing.models.plan_changes import PlanChangeSchedule
from billing.models.oss_notices import OssNotice
from billing.models.paying_customers import PayingCustomer
