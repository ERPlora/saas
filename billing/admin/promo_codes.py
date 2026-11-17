"""Django admin of the promo codes: written here, as sales hands them out."""

from django.contrib import admin

from billing.models import PromoCode


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "trial_days", "is_active", "expires_at", "redemption_count", "max_redemptions", "note")
    list_filter = ("is_active",)
    search_fields = ("code", "note")
    readonly_fields = ("redemption_count", "created_at", "updated_at")
