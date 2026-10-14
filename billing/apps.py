"""What an account pays ERPlora, and the VAT on it (plan 2026-10-13 §3, the ``billing`` row).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to
``base/``, without module fields (no requires, category, premium or menu of its own; the «Billing»
entry of the menu is ``base/navigation.py``'s). Lot L2-A brings the EU VAT engine (rates, the VIES
check and the tax a sale carries); L2-B adds Stripe (checkout, the business's subscription and its items,
the webhook, unpaid plans), L3-C the invoices.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class BillingConfig(LiveAppConfig):
    name = "billing"
    label = "billing"
    kind = "platform"
    verbose_name = _("Billing")
    default_auto_field = "django.db.models.BigAutoField"
    # Every signed-in account (role "account", base.operations) previews the tax of a sale, checks a VAT
    # number in VIES and reaches the operations that pay (``billing.pay``, lot L2-B: buy, change, cancel,
    # the portal), each of which checks that the account owns the business. ``billing.manage`` is no
    # account's by default.
    permissions = ["billing.view", "billing.vat_check", "billing.pay", "billing.manage"]
    role_permissions = {"account": ["billing.view", "billing.vat_check", "billing.pay"]}

    def ready(self):
        super().ready()
        from billing import checks  # noqa: F401  (registers the deploy check of the Stripe key)
