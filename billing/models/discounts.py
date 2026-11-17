"""Discounts: what a promo code takes off, mirrored in Stripe as a coupon.

A percentage or a fixed amount in euros, once, for a number of months or forever, on the plans it names (none
named = every plan). ``applies_to`` says which kind of thing it discounts; plans are the only one sold today.
"""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

#: The longest a discount that repeats may last.
MAX_DISCOUNT_MONTHS = 36


class Discount(UUIDModel):
    """Its terms are fixed once a customer used one of its codes (``billing.admin.discounts``): Stripe's coupon,
    its mirror, cannot change either."""

    class Duration(models.TextChoices):
        ONCE = "once", _("Once")
        REPEATING = "repeating", _("For a number of months")
        FOREVER = "forever", _("Forever")

    class AppliesTo(models.TextChoices):
        PLANS = "plans", _("Plans")

    name = models.CharField(_("name"), max_length=80, help_text=_("Internal label, e.g. Testers 2026"))
    percent_off = models.PositiveSmallIntegerField(
        _("percent off"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    amount_off_cents = models.PositiveIntegerField(
        _("amount off (cents)"), null=True, blank=True, validators=[MinValueValidator(1)],
        help_text=_("Without VAT, taken off each payment it applies to; never more than its price"),
    )
    currency = models.CharField(_("currency"), max_length=3, default="eur", choices=[("eur", "EUR")])
    duration = models.CharField(_("duration"), max_length=10, choices=Duration.choices)
    duration_in_months = models.PositiveSmallIntegerField(
        _("months"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(MAX_DISCOUNT_MONTHS)],
        help_text=_("Only for a discount for a number of months (1 to 36): monthly billing only"),
    )
    applies_to = models.CharField(
        _("applies to"), max_length=10, choices=AppliesTo.choices, default=AppliesTo.PLANS
    )
    plans = models.ManyToManyField(
        "hubs.Plan", blank=True, related_name="discounts", verbose_name=_("plans"),
        help_text=_("Empty = every plan"),
    )
    is_active = models.BooleanField(_("active"), default=True, help_text=_("Inactive: its codes are not valid"))
    note = models.CharField(_("note"), max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("discount")
        verbose_name_plural = _("discounts")
        # A NULL comparison passes a CHECK: each side says which of the two is filled in.
        constraints = [
            models.CheckConstraint(
                condition=Q(percent_off__isnull=False, percent_off__gte=1, percent_off__lte=100,
                            amount_off_cents__isnull=True)
                | Q(amount_off_cents__isnull=False, amount_off_cents__gte=1, percent_off__isnull=True),
                name="billing_discount_percent_xor_amount",
            ),
            models.CheckConstraint(
                condition=Q(duration="repeating", duration_in_months__isnull=False, duration_in_months__gte=1,
                            duration_in_months__lte=MAX_DISCOUNT_MONTHS)
                | (Q(duration__in=["once", "forever"]) & Q(duration_in_months__isnull=True)),
                name="billing_discount_months_only_when_repeating",
            ),
            models.CheckConstraint(condition=Q(currency="eur"), name="billing_discount_currency_eur"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if (self.percent_off is None) == (self.amount_off_cents is None):
            raise ValidationError(_("A discount takes off a percentage or an amount: fill in one of the two."))
        if (self.duration == self.Duration.REPEATING) != (self.duration_in_months is not None):
            raise ValidationError(
                _("Say how many months for a discount for a number of months, and only for that one.")
            )
