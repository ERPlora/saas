"""Reads of billing: the rule in force, the policy, ERPlora's identity, the VIES log, the payer of a
business, and the operation ``billing.tax.preview``.

Only this package and ``billing.services`` touch the ORM: the VAT engine (``billing.vat``) reads the table and the
policy through its functions. Nothing here asks VIES nor writes: a query runs READ ONLY.

The Billing section: ``billing.invoice.{list,get,pdf,csv}`` (ERPlora's invoices; the PDF is asked
to the platform hub), ``billing.subscription.list`` and ``billing.payment_method.get`` (the card, asked to
Stripe and kept a few minutes). The admin's billing report (``billing_report``) sums what was invoiced in a month,
a quarter or a year, and its Excel shares the panel's CSV writer (``invoices_csv``), as does the admin's list of
paying customers (``paying_customers``).
"""

from billing.queries.tax import (
    CATEGORY_KEYS,
    cross_border_b2c_cents,
    destination_rate_applies,
    fiscal_policy,
    latest_vat_check,
    oss_total_is_known,
    payer_of,
    tax_preview,
    tax_rule,
    uses_destination_rate,
    vat_verdict_as_of,
    vies_requester,
)
from billing.queries.tax_audit import (
    NON_VAT_TERRITORIES,
    TAX_RULE_ADMIN_URL,
    TaxRuleAuditLine,
    TaxRuleAuditReport,
    tax_rule_audit,
)
from billing.queries.promo_codes import PROMO_CHECK_GROUP, promo_check, redeemable_promo
from billing.queries.invoices import (
    ACCOUNT_CSV_COLUMNS,
    CARD_CACHE_SECONDS,
    FORMULA_STARTS,
    ISSUED_STATUSES,
    REPORT_CSV_COLUMNS,
    card_change_required,
    invoice_csv,
    invoice_get,
    invoice_list,
    invoice_of,
    invoice_pdf,
    invoices_csv,
    invoices_of,
    pays_for,
    platform_invoice_pdf,
)
from billing.queries.billing_report import (
    CUSTOMER_KINDS,
    BillingReport,
    ReportCustomerRow,
    ReportPeriod,
    ReportTaxRow,
    ReportTotals,
    billing_report,
    billing_report_csv,
    customer_kind,
    quarter_of,
    report_invoices,
    report_period,
)
from billing.queries.subscriptions import (
    ENDED_SUBSCRIPTIONS,
    card_cache_key,
    payment_method_get,
    plan_cancel_preview,
    scheduled_change_of,
    subscription_list,
)
from billing.queries.catalog import (
    businesses_having_module,
    is_paying,
    module_for_price,
    module_on_sale,
    offered_plans,
    plan_for_price,
    plan_on_sale,
    store_catalog,
)
from billing.queries.paying_customers import (
    monthly_cents,
    paying_customer_country,
    paying_customer_kind,
    paying_customer_payer,
    paying_customer_values,
    paying_customers,
    paying_customers_csv,
)
