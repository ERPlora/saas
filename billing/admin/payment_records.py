"""Django admin of billing's payment records.

What Stripe did —the checkouts opened, the webhook's events and the renewals that failed— is read-only: Stripe is
the source, and the webhook and the operations are its only writers. Promo codes are written in their own module.
"""

from django.contrib import admin
from django.utils.translation import gettext as _

from billing.models import (
    CheckoutAttempt,
    InvoiceCounter,
    OssNotice,
    PaymentFailure,
    PlanChangeSchedule,
    PromoRedemption,
    WebhookEvent,
)
from billing.money import from_cents


class ReadOnlyAdmin(admin.ModelAdmin):
    """What Stripe did, as the webhook and the operations wrote it: nobody adds, edits or deletes it here."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckoutAttempt)
class CheckoutAttemptAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "hub", "kind", "plan_slug", "module_slug", "billing_interval", "promo_code", "status")
    list_filter = ("status", "kind")
    search_fields = ("hub__slug", "hub__name", "stripe_session_id")
    exclude = ("client_secret",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(ReadOnlyAdmin):
    list_display = ("received_at", "event_type", "event_id", "success", "outcome", "attempts")
    list_filter = ("success", "event_type")
    search_fields = ("event_id",)


@admin.register(PaymentFailure)
class PaymentFailureAdmin(ReadOnlyAdmin):
    list_display = ("failed_at", "hub", "reason", "decline_code", "invoice_created_at", "card_changed_at", "resolved_at")
    list_filter = ("reason",)
    search_fields = ("hub__slug", "hub__name", "stripe_invoice_id", "stripe_subscription_id")


@admin.register(OssNotice)
class OssNoticeAdmin(ReadOnlyAdmin):
    """The team's notices of the OSS threshold: read only, the row is what keeps a notice from
    being sent twice in a year."""

    list_display = ("year", "kind", "reason", "accumulated", "threshold", "invoice", "effective_from", "mailed_at")
    list_filter = ("kind",)
    list_select_related = ("invoice",)

    @admin.display(description=_("accumulated"), ordering="accumulated_cents")
    def accumulated(self, obj):
        return f"{from_cents(obj.accumulated_cents)} €"

    @admin.display(description=_("threshold"), ordering="threshold_cents")
    def threshold(self, obj):
        return f"{from_cents(obj.threshold_cents)} €"


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(ReadOnlyAdmin):
    """A promo code used by a business (once per business and per payer): held while its checkout is open
    (``held_until``), a use once paid."""

    list_display = ("created_at", "promo", "hub", "stripe_customer_id", "held_until")
    list_select_related = ("promo", "hub")
    search_fields = ("promo__code", "hub__slug", "hub__name", "stripe_customer_id")


@admin.register(InvoiceCounter)
class InvoiceCounterAdmin(ReadOnlyAdmin):
    """The last number of each series and year: only the invoice's numbering moves it (``services.issue_number``)."""

    list_display = ("series", "year", "last_number")


@admin.register(PlanChangeSchedule)
class PlanChangeScheduleAdmin(ReadOnlyAdmin):
    """A downgrade waiting for the end of the paid period, as Stripe's subscription schedule holds it."""

    list_display = ("starts_at", "hub", "plan_slug", "interval", "stripe_schedule_id")
    list_select_related = ("hub",)
    search_fields = ("hub__slug", "hub__name", "stripe_schedule_id")
