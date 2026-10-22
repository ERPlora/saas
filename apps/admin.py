"""Admin of apps (spec §5.5): the catalog read-only, ``Module`` with its validation.

``App`` and ``AppDoc`` are written by the Hub with each release (``register_apps``): the SaaS's admin
shows them and never adds, changes nor deletes a row. ``Module`` is written here, by hand, and its
form runs ``Module.clean()`` (the slug is a paid app of the catalog, spec §5.4) and checks in Stripe the prices
pasted on it (APPS-F04, the same checks as a plan's, BILLING-F28). A module some business still has is not deleted
(saas#2568): taking it off sale («active» off) is how it stops being sold.
"""

from django import forms
from django.contrib import admin, messages
from django.utils.translation import gettext as _

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


class ModuleForm(forms.ModelForm):
    """APPS-F04: a module is not saved with a Stripe price that would charge something else than the Store paints;
    checked in Stripe only when its prices or their ids change. Without Stripe (development) it is saved and the
    admin says it was not checked; with Stripe not answering nothing is saved and the admin asks to try again."""

    PRICE_FIELDS = (
        "stripe_price_id_monthly",
        "stripe_price_id_annual",
        "stripe_product_id",
        "price_monthly_cents",
        "price_annual_cents",
    )

    class Meta:
        model = Module
        fields = "__all__"

    def clean(self):
        from billing import services as billing_services

        cleaned = super().clean()
        self.unchecked = ""
        if self.errors or not set(self.PRICE_FIELDS) & set(self.changed_data):
            return cleaned
        try:
            problems = billing_services.module_price_problems(
                prices={field: cleaned.get(field) or "" for field in ("stripe_price_id_monthly", "stripe_price_id_annual")},
                amounts={field: cleaned.get(field) for field in ("price_monthly_cents", "price_annual_cents")},
                product=cleaned.get("stripe_product_id") or "",
            )
        except billing_services.PriceCheckSkipped as skipped:
            self.unchecked = str(skipped)
            return cleaned
        except billing_services.PriceCheckFailed as failed:
            raise forms.ValidationError(str(failed), code="price_check_failed") from failed
        for field, problem in problems.items():
            self.add_error(field, problem)
        return cleaned


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    form = ModuleForm
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if getattr(form, "unchecked", ""):
            self.message_user(request, form.unchecked, messages.WARNING)

    def get_deleted_objects(self, objs, request):
        """Django's own refusal of a protected relation, for the modules some business still has: Stripe would
        bill a price nobody sells, and the business would lose the module while paying it (saas#2568)."""
        from billing.queries import businesses_having_module

        deleted, counts, perms_needed, protected = super().get_deleted_objects(objs, request)
        for module in objs:
            for name in businesses_having_module(module.slug):
                protected.append(
                    _("%(business)s has the module %(module)s: take it off sale instead (untick «active»).")
                    % {"business": name, "module": module.slug}
                )
        return deleted, counts, perms_needed, protected
