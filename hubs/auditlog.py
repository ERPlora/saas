"""The audit trail of who enters a business, what it pays and who pays it (django-auditlog; ACCOUNTS-F36).
Registered from ``HubsConfig.ready``.

Its people, the plans' prices the staff keep, a business's payer details, its subscription and the paid apps it carries.
Never logged: the text of an invitation (the inviter's own words) and when a person last opened it, which moves on every
visit; the link that opens an unpaid Stripe invoice to whoever holds it, nor ``updated_at``.
"""

from accounts.auditlog import audit
from hubs.models import BillingProfile, HubMember, Plan, Subscription, SubscriptionItem


def register() -> None:
    audit(HubMember, exclude=["last_opened_at", "invitation_message"])
    audit(Plan, exclude=["updated_at"])
    audit(BillingProfile, exclude=["updated_at"])
    audit(Subscription, exclude=["unpaid_invoice_url", "updated_at"])
    audit(SubscriptionItem, exclude=["updated_at"])
