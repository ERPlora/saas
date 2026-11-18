"""The plan a business is on and the paid modules it has."""

import uuid
from datetime import datetime

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from hubs.models.businesses import Hub
from hubs.models.plan_catalog import Plan


#: The label of an app = its folder in the Hub = ``modules[].id`` of the snapshot.
MODULE_SLUG_VALIDATOR = RegexValidator(
    r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$", _("Enter the label of an app: lowercase letters, digits and underscores.")
)


class Subscription(models.Model):
    """The plan a hub is on (one per hub). Stripe fills its ids and dates through
    ``hubs.subscription.apply``, which billing calls with what the live Stripe subscription says.

    While ``trial_end`` is ahead, the hub gets the rights of ``trial_plan``. A paid plan carries its
    own trial in Stripe, so paying clears ``trial_plan``.

    ``unpaid_*`` say why a renewal is not paid, while it is not: with a declined card «Pay» waits
    until the card changes; ``unpaid_since`` is when the failed invoice was issued (the 7 days of
    grace count from it); ``unpaid_invoice_url`` is Stripe's page to pay it (its owner's only).
    """

    class UnpaidReason(models.TextChoices):
        NONE = "", _("Paid")
        CARD_DECLINED = "card_declined", _("Card declined")
        CARD_CHANGED = "card_changed", _("Card changed")
        AUTHENTICATION_REQUIRED = "authentication_required", _("Authentication required")
        PAYMENT_FAILED = "payment_failed", _("Payment failed")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        TRIALING = "trialing", _("Trial")
        PAST_DUE = "past_due", _("Payment pending")
        UNPAID = "unpaid", _("Unpaid")
        CANCELED = "canceled", _("Cancelled")
        INCOMPLETE = "incomplete", _("Incomplete")
        INCOMPLETE_EXPIRED = "incomplete_expired", _("Incomplete, expired")
        PAUSED = "paused", _("Paused")

    class Interval(models.TextChoices):
        MONTH = "month", _("Monthly")
        YEAR = "year", _("Annual")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.OneToOneField(Hub, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions", verbose_name=_("plan"))
    trial_plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("trial plan")
    )
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.ACTIVE)
    billing_interval = models.CharField(_("billing"), max_length=8, choices=Interval.choices, default=Interval.MONTH)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    unpaid_reason = models.CharField(
        _("why it is unpaid"), max_length=24, choices=UnpaidReason.choices, blank=True, default=""
    )
    unpaid_since = models.DateTimeField(_("unpaid since"), null=True, blank=True)
    unpaid_invoice_url = models.URLField(_("invoice to pay"), max_length=2048, blank=True, default="")
    #: The business was deleted while Stripe billed it: billing's ``sweep_unpaid`` ends that subscription and
    #: clears this. Durable, so recovering the business meanwhile does not leave it charging.
    cancel_requested_at = models.DateTimeField(_("end in Stripe asked at"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self):
        return f"{self.hub_id} - {self.plan_id} ({self.status})"

    def effective_plan(self, now: datetime) -> Plan:
        """The plan whose rights the hub has at ``now``: the trial's while it lasts, else its own."""
        if self.trial_plan_id is not None and self.trial_end is not None and now < self.trial_end:
            return self.trial_plan
        return self.plan


class SubscriptionItem(models.Model):
    """A paid module a hub has, included in its plan or bought: ``modules[]`` of the snapshot.
    ``module_slug`` is the app's label (a slug, no FK: the catalog is ``apps``'s)."""

    class Source(models.TextChoices):
        PLAN = "plan", _("Included in the plan")
        PURCHASE = "purchase", _("Bought")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="items")
    module_slug = models.CharField(_("module"), max_length=63, validators=[MODULE_SLUG_VALIDATOR])
    source = models.CharField(_("source"), max_length=8, choices=Source.choices, default=Source.PURCHASE)
    valid_until = models.DateTimeField(_("valid until"), null=True, blank=True)
    stripe_item_id = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["module_slug"]
        verbose_name = _("subscription item")
        verbose_name_plural = _("subscription items")
        constraints = [
            models.UniqueConstraint(fields=["subscription", "module_slug"], name="hubs_item_one_per_module"),
        ]

    def __str__(self):
        return f"{self.module_slug} ({self.source})"

    def is_live(self, now: datetime) -> bool:
        """Whether the right holds at ``now``: open-ended, or before its ``valid_until``."""
        return self.valid_until is None or now < self.valid_until
