"""Django admin of the promo codes: written here, as sales hands them out. A used code keeps its code and what it
gives (trial days or a discount), and is turned off rather than deleted."""

from django.contrib import admin

from billing.models import PromoCode


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "discount", "trial_days", "is_active", "expires_at", "redemption_count", "max_redemptions",
                    "note")
    list_filter = ("is_active",)
    list_select_related = ("discount",)
    search_fields = ("code", "note")
    readonly_fields = ("redemption_count", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        if is_used(obj):
            return (*self.readonly_fields, "code", "discount", "trial_days")
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not is_used(obj)


def is_used(promo: PromoCode | None) -> bool:
    """A code somebody used (or holds in an open checkout): turned off, never deleted."""
    return promo is not None and promo.pk is not None and promo.redemptions.exists()
