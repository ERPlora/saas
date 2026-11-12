"""What an account pays ERPlora, and the VAT on it.

A platform app: always on, at the project root next to ``base/``, without module fields (no requires,
category, premium or menu of its own; the «Billing» entry of the menu is ``base/navigation.py``'s). It holds
the EU VAT engine (rates, the VIES check and the tax a sale carries), Stripe (checkout, the business's
subscription and its items, the webhook, unpaid plans) and ERPlora's invoices.
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
    # number in VIES and reaches the operations that pay (``billing.pay``: buy, change, cancel,
    # the portal), each of which checks that the account owns the business. ``billing.manage`` is no
    # account's by default.
    permissions = ["billing.view", "billing.vat_check", "billing.pay", "billing.manage"]
    role_permissions = {"account": ["billing.view", "billing.vat_check", "billing.pay"]}

    def ready(self):
        super().ready()
        from accounts import signals as account_signals
        from billing import auditlog, services
        from billing import checks  # noqa: F401  (registers the deploy check of the Stripe key)

        auditlog.register()

        # The payers of a deleted account go once nothing can be charged to them.
        account_signals.account_deleting.connect(services.payer_leaving, dispatch_uid="billing.account_deleting")
