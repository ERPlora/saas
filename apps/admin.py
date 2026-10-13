"""Admin of apps (spec §5.5): the catalog read-only, ``Module`` with its validation.

``App`` and ``AppDoc`` are written by the Hub with each release (``register_apps``): the SaaS's admin
shows them and never adds, changes nor deletes a row. ``Module`` is written here, by hand, and its
form runs ``Module.clean()`` (the slug is a paid app of the catalog, spec §5.4).
"""

from django.contrib import admin

from apps.models import App, AppDoc, Module


class ReadOnlyAdmin(admin.ModelAdmin):
    """View only, for everyone: the rows belong to the Hub."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(App)
class AppAdmin(ReadOnlyAdmin):
    list_display = [
        "id",
        "name_en",
        "category",
        "premium",
        "listed",
        "hub_version",
        "registered_at",
    ]
    list_filter = ["category", "premium", "listed"]
    search_fields = ["id", "name_en", "name_es"]


@admin.register(AppDoc)
class AppDocAdmin(ReadOnlyAdmin):
    list_display = ["app", "lang", "source_hash", "updated_at"]
    list_filter = ["lang"]
    search_fields = ["app__id"]


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = [
        "slug",
        "tier",
        "price_monthly_cents",
        "price_annual_cents",
        "is_active",
        "updated_at",
    ]
    list_filter = ["tier", "is_active"]
    search_fields = ["slug", "stripe_product_id"]
    readonly_fields = ["created_at", "updated_at"]
