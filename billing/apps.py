"""What an account pays ERPlora, and the VAT on it (plan 2026-10-13 §3, the ``billing`` row).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to
``base/``, without module fields (no requires, category, premium or menu of its own; the «Billing»
entry of the menu is ``base/navigation.py``'s). Lot L2-A brings the EU VAT engine (rates, the VIES
check and the tax a sale carries); L2-B adds Stripe, L3-C the invoices.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class BillingConfig(LiveAppConfig):
    name = "billing"
    label = "billing"
    kind = "platform"
    verbose_name = _("Billing")
    default_auto_field = "django.db.models.BigAutoField"
    # Every signed-in account (role "account", base.operations) previews the tax of a sale and checks a
    # VAT number in VIES. ``billing.manage`` is no account's by default: the operations that act on a
    # business's billing (lot L2-B) decide who may by the account's role in that business.
    permissions = ["billing.view", "billing.vat_check", "billing.manage"]
    role_permissions = {"account": ["billing.view", "billing.vat_check"]}
