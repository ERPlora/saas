"""Django admin of hubs: the plans, the taxonomy of sectors and business types, and the account plane of
every business.

The plans and the taxonomy are ported from ERPlora/saas ``public/catalog/admin.py`` (origin/develop)
without modeltranslation's tabs: each language is its own column. The guards of the Spanish copy and of
duplicate names are the models' ``clean()``, which the admin form runs.

The account plane (``Hub``, ``HubMember``, ``HubOwnershipTransfer``, ``BillingProfile``, ``Subscription``,
``SubscriptionItem``, ``SessionRevocation``; L1-A2) is read-mostly: its writes are the operations of
``hubs.services`` (state version, the jump's mirror, the push to the Hub), so the admin adds, changes and
deletes nothing, not even for a superuser. Superusers get the platform's actions (``services.send_latest_state``,
``retry_owed``, ``deliver_revocations``); ``support`` only sees (data migration ``0007``).
"""

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from hubs import services
from hubs.models import (
    BillingProfile,
    BusinessType,
    Hub,
    HubMember,
    HubOwnershipTransfer,
    Plan,
    Sector,
    SessionRevocation,
    Subscription,
    SubscriptionItem,
)

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


# --- The account plane of a business (read-mostly) -------------------------------------------------


class ReadOnly:
    """Seen, never written here: the operations of ``hubs.services`` write these rows."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PlatformActions(ReadOnly, admin.ModelAdmin):
    def has_sync_permission(self, request):
        """The platform's actions on the Hub: superusers only (``support`` only sees)."""
        return request.user.is_active and request.user.is_superuser


class HubMemberInline(ReadOnly, admin.TabularInline):
    model = HubMember
    fk_name = "hub"
    extra = 0
    fields = ("user", "role", "invited_at", "accepted_at", "last_opened_at")


@admin.register(Hub)
class HubAdmin(PlatformActions):
    list_display = [
        "name",
        "slug",
        "status",
        "ready_at",
        "pending_hub_call",
        "state_version",
        "pushed_state_version",
        "last_hub_error",
    ]
    list_filter = ["status", "pending_hub_call"]
    search_fields = ["slug", "name"]
    inlines = [HubMemberInline]
    actions = ["send_latest_state", "retry_owed"]

    @admin.action(description=_("Send the latest state to the Hub"), permissions=["sync"])
    def send_latest_state(self, request, queryset):
        self._tell(request, services.send_latest_state(list(queryset.values_list("id", flat=True))))

    @admin.action(description=_("Retry what the Hub still owes"), permissions=["sync"])
    def retry_owed(self, request, queryset):
        self._tell(request, services.retry_owed(list(queryset.values_list("id", flat=True))))

    def _tell(self, request, counts):
        if counts["delivered"]:
            self.message_user(
                request, _("%(count)d business(es) up to date in the Hub.") % {"count": counts["delivered"]}
            )
        if counts["owed"]:
            self.message_user(
                request,
                _(
                    "%(count)d business(es) still owed: the Hub is away or refused it (see its last refusal); "
                    "reconcile_hub_states retries it."
                )
                % {"count": counts["owed"]},
                messages.WARNING,
            )


@admin.register(HubMember)
class HubMemberAdmin(PlatformActions):
    list_display = ["hub", "user", "role", "invited_at", "accepted_at", "last_opened_at"]
    list_filter = ["role"]
    list_select_related = ["hub", "user"]
    search_fields = ["hub__slug", "hub__name", "user__email"]


@admin.register(HubOwnershipTransfer)
class HubOwnershipTransferAdmin(PlatformActions):
    list_display = ["hub", "from_email", "to_email", "status", "created_at", "expires_at", "resolved_at"]
    list_filter = ["status"]
    list_select_related = ["hub"]
    search_fields = ["hub__slug", "from_email", "to_email"]


@admin.register(BillingProfile)
class BillingProfileAdmin(PlatformActions):
    list_display = ["__str__", "owner", "billing_email", "tax_id", "billing_country", "created_at"]
    list_select_related = ["owner"]
    search_fields = ["billing_name", "tax_id", "billing_email", "owner__email"]


@admin.register(Subscription)
class SubscriptionAdmin(PlatformActions):
    list_display = ["hub", "plan", "trial_plan", "status", "trial_end", "current_period_end", "cancel_at_period_end"]
    list_filter = ["status", "plan"]
    list_select_related = ["hub", "plan", "trial_plan"]
    search_fields = ["hub__slug", "hub__name", "stripe_subscription_id"]


@admin.register(SubscriptionItem)
class SubscriptionItemAdmin(PlatformActions):
    list_display = ["subscription", "module_slug", "source", "valid_until"]
    list_filter = ["source"]
    list_select_related = ["subscription__hub"]
    search_fields = ["module_slug", "subscription__hub__slug"]


@admin.register(SessionRevocation)
class SessionRevocationAdmin(PlatformActions):
    # ``user_id``, not ``user``: a revocation outlives the account it ends.
    list_display = ["user_id", "hub", "requested_at", "delivered_at", "attempts", "next_attempt_at", "last_error"]
    list_filter = [("delivered_at", admin.EmptyFieldListFilter)]
    list_select_related = ["hub"]
    search_fields = ["user_id", "hub__slug"]
    actions = ["deliver_now"]

    @admin.action(description=_("End the sessions in the Hub now"), permissions=["sync"])
    def deliver_now(self, request, queryset):
        counts = services.deliver_revocations(list(queryset.values_list("id", flat=True)))
        if counts["delivered"]:
            self.message_user(request, _("%(count)d session end(s) delivered.") % {"count": counts["delivered"]})
        if counts["pending"]:
            self.message_user(
                request,
                _("%(count)d session end(s) still pending: the Hub is away or refused it; reconcile_hub_states retries it.")
                % {"count": counts["pending"]},
                messages.WARNING,
            )
