"""What Stripe needs remembered: the checkouts opened, the webhook events processed and the renewals not
collected."""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class CheckoutAttempt(UUIDModel):
    """One Embedded Checkout opened for a business: what it sells and the Stripe session it got.

    The same selection opened again while its session is still open reuses it (a double click, a modal
    closed and reopened), so one intent never leaves two sessions that could both be paid. The webhook
    completes it exactly once (the promo code is counted then).
    """

    class Kind(models.TextChoices):
        PLAN = "plan", _("Plan")
        MODULE = "module", _("Module")
        #: The new owner of a handed-over business keeps its plan with their own card.
        TAKEOVER = "takeover", _("Plan kept by the new owner")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        COMPLETED = "completed", _("Completed")
        EXPIRED = "expired", _("Expired")
        FAILED = "failed", _("Payment failed")
        #: Paid by somebody who no longer owned the business (a hand-over meanwhile): ended and refunded.
        REFUNDED = "refunded", _("Refunded: no longer the owner")

    #: Stripe keeps a Checkout Session open 24 hours; reuse it a bit less, so it never expires in hand.
    REUSE_FOR = timedelta(hours=23)

    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        related_name="checkout_attempts",
        verbose_name=_("business"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_attempts",
        verbose_name=_("opened by"),
    )
    kind = models.CharField(_("sells"), max_length=8, choices=Kind.choices)
    plan_slug = models.CharField(_("plan"), max_length=50, blank=True)
    module_slug = models.CharField(_("module"), max_length=63, blank=True)
    billing_interval = models.CharField(_("billing"), max_length=8, default="month")
    promo_code = models.CharField(_("promo code"), max_length=64, blank=True)
    #: What was sold, as a key (kind, plan or module, interval, promo code, trial): the same selection
    #: reuses the open session; any other gets a new one.
    selection = models.CharField(_("selection"), max_length=255)
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.OPEN
    )
    stripe_session_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )
    client_secret = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(_("opened at"), auto_now_add=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("checkout")
        verbose_name_plural = _("checkouts")
        indexes = [models.Index(fields=["hub", "selection", "status"])]

    def __str__(self):
        return f"{self.hub_id} {self.kind} {self.plan_slug or self.module_slug} ({self.status})"


class WebhookEvent(UUIDModel):
    """Each Stripe event the webhook received, processed once.

    A delivery claims the event before processing it, so two deliveries at once never both process it; a
    claim left by a process that died expires after ``CLAIM_LEASE``. A failure stays claimable: Stripe's
    retry processes it again. One endpoint (``/webhooks/stripe/``), so the event id alone is
    the key.
    """

    #: How long a claim protects an event being processed; after it the next delivery takes it over.
    CLAIM_LEASE = timedelta(minutes=10)

    event_id = models.CharField(_("Stripe event"), max_length=255, unique=True)
    event_type = models.CharField(_("type"), max_length=100)
    received_at = models.DateTimeField(_("received at"), auto_now_add=True)
    processing_since = models.DateTimeField(
        _("processing since"), null=True, blank=True
    )
    processed_at = models.DateTimeField(_("processed at"), null=True, blank=True)
    success = models.BooleanField(_("processed"), default=False)
    #: What the processing came to (``completed``, ``ignored``, ``unknown``…).
    outcome = models.CharField(_("outcome"), max_length=32, blank=True)
    error_message = models.TextField(_("error"), blank=True)
    attempts = models.PositiveIntegerField(_("attempts"), default=0)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = _("Stripe event")
        verbose_name_plural = _("Stripe events")
        indexes = [models.Index(fields=["event_type", "received_at"])]

    def __str__(self):
        return f"{self.event_type} ({self.event_id})"


class PaymentFailure(UUIDModel):
    """A renewal Stripe could not collect, and why: what «Pay» and the panel need.

    One row per unpaid Stripe invoice. ``reason`` tells a declined card (the bank refused it: paying again
    with it fails, so «Pay» waits until the card changes, ``card_changed_at``) from an authentication the
    customer must complete or any other failure. ``invoice_created_at`` starts the 7 days of grace.
    ``resolved_at`` is set when the invoice is paid (or the subscription ends). ``notified_at`` and
    ``suspension_notified_at`` keep the unpaid mails to one each (``services.notify_unpaid``).
    """

    class Reason(models.TextChoices):
        CARD_DECLINED = "card_declined", _("Card declined")
        AUTHENTICATION_REQUIRED = (
            "authentication_required",
            _("Authentication required"),
        )
        PAYMENT_FAILED = "payment_failed", _("Payment failed")

    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        related_name="payment_failures",
        verbose_name=_("business"),
    )
    stripe_invoice_id = models.CharField(
        _("Stripe invoice"), max_length=255, unique=True
    )
    stripe_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    reason = models.CharField(_("reason"), max_length=24, choices=Reason.choices)
    failure_code = models.CharField(_("Stripe code"), max_length=64, blank=True)
    decline_code = models.CharField(_("decline code"), max_length=64, blank=True)
    payment_method_id = models.CharField(
        _("card that failed"), max_length=255, blank=True
    )
    hosted_invoice_url = models.URLField(
        _("invoice to pay"), max_length=2048, blank=True
    )
    invoice_created_at = models.DateTimeField(_("invoice issued at"))
    failed_at = models.DateTimeField(_("last failure"), default=timezone.now)
    attempts = models.PositiveIntegerField(_("failures"), default=1)
    card_changed_at = models.DateTimeField(_("card changed at"), null=True, blank=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    #: The payer was told this invoice could not be collected (or there was nobody to tell): once per invoice.
    notified_at = models.DateTimeField(_("payer told"), null=True, blank=True)
    #: The payer was told the business is suspended for this unpaid episode: once per suspension.
    suspension_notified_at = models.DateTimeField(_("suspension told"), null=True, blank=True)

    class Meta:
        ordering = ["-failed_at"]
        verbose_name = _("failed payment")
        verbose_name_plural = _("failed payments")
        indexes = [models.Index(fields=["hub", "resolved_at"])]

    def __str__(self):
        return f"{self.stripe_invoice_id} {self.reason}"
