"""Django admin of hubs: the plans and the taxonomy of sectors and business types.

Ported from ERPlora/saas ``public/catalog/admin.py`` (origin/develop) without modeltranslation's
tabs: each language is its own column. The guards of the Spanish copy and of duplicate names are
the models' ``clean()``, which the admin form runs.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from hubs.models import BusinessType, Plan, Sector

TAXONOMY_COPY = ("name_en", "name_es", "description_en", "description_es")


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ["code", "name_en", "name_es", "is_active", "display_order"]
    list_filter = ["is_active"]
    list_editable = ["is_active", "display_order"]
    search_fields = ["code", "name_en", "name_es"]
    fieldsets = (
        (None, {"fields": ("code", *TAXONOMY_COPY)}),
        (_("Display"), {"fields": ("icon", "color", "display_order", "is_active")}),
    )


@admin.register(BusinessType)
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ["code", "name_en", "name_es", "sector", "vertical", "is_active", "display_order"]
    list_filter = ["sector", "vertical", "is_active"]
    list_editable = ["is_active", "display_order"]
    list_select_related = ["sector"]
    search_fields = ["code", "name_en", "name_es"]
    autocomplete_fields = ["sector"]
    fieldsets = (
        (None, {"fields": ("code", *TAXONOMY_COPY, "sector", "vertical")}),
        (_("Display"), {"fields": ("icon", "color", "display_order", "is_active")}),
    )


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["slug", "name_en", "price_monthly", "trial_period_days", "is_active", "upgrade_only", "internal_only"]
    list_filter = ["is_active", "upgrade_only", "internal_only"]
    search_fields = ["slug", "name_en", "name_es"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("slug", "name_en", "name_es", "description_en", "description_es")}),
        (_("Card"), {"fields": ("features_en", "features_es", "featured_label_en", "featured_label_es", "display_order")}),
        (_("Price"), {"fields": ("price_monthly", "price_annual", "trial_period_days")}),
        (_("Availability"), {"fields": ("is_active", "upgrade_only", "internal_only")}),
        (
            _("What the plan includes"),
            {"fields": ("included_level", "support_level", "includes_custom_domain", "max_hubs_per_org", "max_devices", "max_users")},
        ),
        (_("Database limits per hub"), {"fields": ("max_db_connections", "statement_timeout_seconds")}),
        (_("Stripe"), {"fields": ("stripe_product_id", "stripe_price_id", "stripe_price_id_annual")}),
        (_("History"), {"fields": ("created_at", "updated_at")}),
    )
