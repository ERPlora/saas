"""Django admin of the discounts: a discount is made with its codes on one page. Once a customer used one of its codes
its terms stay as they were (its Stripe coupon cannot change either) and it is not deleted."""

from django.contrib import admin

from billing.models import Discount, PromoCode, PromoRedemption

#: What a discount takes off and where: fixed once used.
TERMS = ("percent_off", "amount_off_cents", "currency", "duration", "duration_in_months", "applies_to", "plans")


def is_used(discount: Discount | None) -> bool:
    return discount is not None and PromoRedemption.objects.filter(promo__discount=discount).exists()


class PromoCodeInline(admin.TabularInline):
    model = PromoCode
    fields = ("code", "is_active", "expires_at", "max_redemptions", "redemption_count", "note")
    readonly_fields = ("redemption_count",)
    extra = 1

    def get_readonly_fields(self, request, obj=None):
        return (*self.readonly_fields, "code") if is_used(obj) else self.readonly_fields


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("name", "percent_off", "amount_off_cents", "duration", "duration_in_months", "is_active")
    list_filter = ("is_active", "duration")
    search_fields = ("name", "note", "codes__code")
    filter_horizontal = ("plans",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (PromoCodeInline,)

    def get_readonly_fields(self, request, obj=None):
        return (*self.readonly_fields, *TERMS) if is_used(obj) else self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not is_used(obj)
