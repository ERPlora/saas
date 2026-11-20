"""Who pays ERPlora for one or many businesses."""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from hubs.countries import PAYER_COUNTRY_NAMES


class BillingProfile(models.Model):
    """Who pays ERPlora for one or many hubs: the identity on ERPlora's invoice.

    Not the business's own fiscal identity (the one on its receipts), which lives in the Hub.
    ``same_as_business`` is the «use the business's data» box: saving with it on copies what the SaaS
    knows of the business (its name and country) into the payer; a copy, never a sync. Every field but
    the owner may wait for the first checkout.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    # SET_NULL: the invoices ERPlora issued stay resolvable after the account is gone.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_profiles",
        verbose_name=_("owner"),
    )
    billing_name = models.CharField(_("legal name"), max_length=255, blank=True)
    tax_id = models.CharField(_("tax ID"), max_length=50, blank=True)
    billing_address = models.TextField(_("address"), blank=True)
    billing_city = models.CharField(_("city"), max_length=100, blank=True)
    billing_postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    billing_country = models.CharField(_("country"), max_length=2, blank=True, choices=PAYER_COUNTRY_NAMES)
    billing_email = models.EmailField(_("billing email"), blank=True)
    same_as_business = models.BooleanField(_("same as the business"), default=False)
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    #: The account it belonged to deleted itself (ACCOUNTS-F27): it goes, with its Stripe customer, once nothing
    #: can still be charged to it, and on this day at the latest
    #: (``billing.services.departed_payers.forget_departed_payer``).
    forget_after = models.DateTimeField(_("erased by"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("billing profile")
        verbose_name_plural = _("billing profiles")

    def __str__(self):
        return self.billing_name or self.tax_id or str(self.id)
