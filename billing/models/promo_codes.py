"""Promo codes: the trial days or the discount a checkout grants, and who used each code."""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


#: The longest trial a promo code may grant.
MAX_PROMO_TRIAL_DAYS = 365


class PromoCode(UUIDModel):
    """A code that grants, at checkout, either trial DAYS (replacing the plan's own) or a ``Discount``.

    Trial days are no Stripe coupon: a coupon's duration burns from the moment it is applied, trial included. A
    discount is one (its mirror), on a new subscription and never with a trial: Stripe invoices every period with
    the discount taken off (0 € when it takes all), which is what the accountant files.
    """

    code = models.CharField(
        _("code"),
        max_length=64,
        unique=True,
        help_text=_(
            "What the customer types, case-insensitive (stored in lowercase), e.g. canary_2026"
        ),
    )
    trial_days = models.PositiveIntegerField(
        _("trial days"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_PROMO_TRIAL_DAYS)],
        help_text=_(
            "Free trial days granted, replacing the plan's own trial (1 to 365)"
        ),
    )
    discount = models.ForeignKey(
        "billing.Discount",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="codes",
        verbose_name=_("discount"),
        help_text=_("What it takes off; instead of trial days"),
    )
    is_active = models.BooleanField(_("active"), default=True)
    expires_at = models.DateTimeField(
        _("expires at"), null=True, blank=True, help_text=_("Empty = never expires")
    )
    max_redemptions = models.PositiveIntegerField(
        _("maximum redemptions"),
        null=True,
        blank=True,
        help_text=_("Empty = unlimited"),
    )
    redemption_count = models.PositiveIntegerField(
        _("redemptions"), default=0, help_text=_("Completed checkouts that used it")
    )
    note = models.CharField(
        _("note"),
        max_length=255,
        blank=True,
        help_text=_("Campaign or deal this code belongs to"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("promo code")
        verbose_name_plural = _("promo codes")
        constraints = [
            models.CheckConstraint(
                # A NULL comparison passes a CHECK: each side says which of the two is filled in.
                condition=Q(
                    trial_days__isnull=False,
                    trial_days__gte=1,
                    trial_days__lte=MAX_PROMO_TRIAL_DAYS,
                    discount__isnull=True,
                )
                | Q(discount__isnull=False, trial_days__isnull=True),
                name="billing_promocode_discount_xor_trial_days",
            ),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        super().clean()
        # The discount may be one being made on the same page, not saved yet.
        if (self.trial_days is None) == (self.discount is None):
            raise ValidationError(_("A promo code grants either trial days or a discount: fill in one of the two."))

    def save(self, *args, **kwargs):
        self.code = normalise_promo_code(self.code)
        super().save(*args, **kwargs)

    @property
    def is_exhausted(self) -> bool:
        return (
            self.max_redemptions is not None
            and self.redemption_count >= self.max_redemptions
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and timezone.now() >= self.expires_at

    @property
    def is_redeemable(self) -> bool:
        live = self.discount is None or self.discount.is_active
        return self.is_active and live and not self.is_expired and not self.is_exhausted


def normalise_promo_code(code: str | None) -> str:
    """A code as it is stored and looked up: trimmed, lowercase."""
    return (code or "").strip().lower()


class PromoRedemption(UUIDModel):
    """A promo code used by a business: once per business and once per payer, so one
    code does not give a year free to every business an account opens. Written when its checkout is paid
    (or its plan change confirmed); ``PromoCode.redemption_count`` counts these."""

    promo = models.ForeignKey(
        PromoCode,
        on_delete=models.CASCADE,
        related_name="redemptions",
        verbose_name=_("promo code"),
    )
    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        related_name="promo_redemptions",
        verbose_name=_("business"),
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    # ``db_default``: the release before it still records uses during a deploy, without this column.
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="", db_default="", db_index=True)
    discount_ends_at = models.DateTimeField(
        _("discount ends at"), null=True, blank=True, help_text=_("When the discount of the code ends; empty = never")
    )
    created_at = models.DateTimeField(_("used at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("promo code used")
        verbose_name_plural = _("promo codes used")
        constraints = [
            models.UniqueConstraint(
                fields=["promo", "hub"], name="billing_promo_once_per_business"
            )
        ]

    def __str__(self):
        return f"{self.promo_id} → {self.hub_id}"
