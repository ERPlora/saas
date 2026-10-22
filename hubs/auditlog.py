"""The audit trail of what a business pays and who pays it (django-auditlog; ACCOUNTS-F36, PLAN-SAAS §1.1).
Registered from ``HubsConfig.ready``.

The plans' prices the staff keep, a business's payer details, its subscription and the paid apps it carries. Never
logged: the link that opens an unpaid Stripe invoice to whoever holds it, nor ``updated_at``.
"""

from accounts.auditlog import audit
from hubs.models import BillingProfile, Plan, Subscription, SubscriptionItem


def register() -> None:
    audit(Plan, exclude=["updated_at"])
    audit(BillingProfile, exclude=["updated_at"])
    audit(Subscription, exclude=["unpaid_invoice_url", "updated_at"])
    audit(SubscriptionItem, exclude=["updated_at"])
