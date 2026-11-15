"""The paying customers, as the admin lists them."""

from django.utils.translation import gettext_lazy as _

from hubs.models import Subscription


class PayingCustomer(Subscription):
    """The subscriptions Stripe charges today, as the admin's «Paying customers» lists them (BILLING-F41). A proxy:
    the rows are ``hubs.Subscription``; what the list adds (payer, monthly amount, customer since) is read by
    ``billing.queries.paying_customers``."""

    class Meta:
        proxy = True
        verbose_name = _("paying customer")
        verbose_name_plural = _("paying customers")
