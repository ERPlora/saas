"""Promo codes: the trial days a checkout grants, and who used each code."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


#: The longest trial a promo code may grant.
MAX_PROMO_TRIAL_DAYS = 365


class PromoCode(UUIDModel):
    """A code that grants trial DAYS at checkout, replacing the plan's own.

    Deliberately not a Stripe coupon: a coupon's duration burns from the moment it is applied, trial
    included, so one shorter than the trial expires before the first invoice. And free time, never a lower
    price: a discount anchors a cheaper price and turns the renewal into a price hike.
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
        validators=[MinValueValidator(1), MaxValueValidator(MAX_PROMO_TRIAL_DAYS)],
        help_text=_(
            "Free trial days granted, replacing the plan's own trial (1 to 365)"
        ),
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
                condition=Q(trial_days__gte=1)
                & Q(trial_days__lte=MAX_PROMO_TRIAL_DAYS),
                name="billing_promocode_trial_days_in_range",
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.trial_days})"

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
        return self.is_active and not self.is_expired and not self.is_exhausted


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
