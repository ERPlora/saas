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

``HubUsageDaily`` (L4-A) is what the Hub measured of each business every night (``collect_hub_usage``): read only,
for superusers, with its sizes readable and the database's, which the customer never sees (PLAN-SAAS §5).
"""

import functools

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.options import ActionLocation
from django.db.models import F
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from hubs import queries, services
from hubs.models import (
    BillingProfile,
    BusinessType,
    Hub,
    HubMember,
    HubOwnershipTransfer,
    HubUsageDaily,
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


class PlanForm(forms.ModelForm):
    """BILLING-F28: a plan is not saved with a Stripe price that would charge something else; checked in Stripe
    only when its prices or their ids change. Without Stripe it is saved and the admin says it was not checked; with
    Stripe not answering nothing is saved and the admin asks to try again."""

    PRICE_FIELDS = ("stripe_price_id", "stripe_price_id_annual", "stripe_product_id", "price_monthly", "price_annual")

    class Meta:
        model = Plan
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The choices' own labels are the untranslated English source (kept out of the migrations); the staff pick
        # from the names the customer reads, in their language (HUBS-F05). The stored values do not change.
        for field, labels in (
            ("included_level", Plan.INCLUDED_LEVEL_LABELS),
            ("support_level", Plan.SUPPORT_LEVEL_LABELS),
        ):
            self.fields[field].choices = [(value, labels.get(value, label)) for value, label in self.fields[field].choices]

    def clean(self):
        from billing import services as billing_services

        cleaned = super().clean()
        self.unchecked = ""
        if self.errors or not set(self.PRICE_FIELDS) & set(self.changed_data):
            return cleaned
        try:
            problems = billing_services.plan_price_problems(
                prices={field: cleaned.get(field) or "" for field in ("stripe_price_id", "stripe_price_id_annual")},
                amounts={field: cleaned.get(field) for field in ("price_monthly", "price_annual")},
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


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    form = PlanForm
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
            {"fields": ("included_level", "support_level", "includes_custom_domain", "max_hubs_per_org", "max_devices", "max_users", "max_apps")},
        ),
        (_("Database limits per hub"), {"fields": ("max_db_connections", "statement_timeout_seconds")}),
        (_("AI assistant and WhatsApp per month"), {"fields": ("assistant_messages_per_month", "whatsapp_messages_per_month")}),
        (_("Stripe"), {"fields": ("stripe_product_id", "stripe_price_id", "stripe_price_id_annual")}),
        (_("History"), {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if getattr(form, "unchecked", ""):
            self.message_user(request, form.unchecked, messages.WARNING)
        # HUBS-F31: what the plan gives reaches its businesses within 15 minutes, not at night.
        if change and set(queries.SNAPSHOT_PLAN_FIELDS) & set(form.changed_data):
            owed = services.owe_plan_rights(obj)
            if owed:
                self.message_user(
                    request,
                    ngettext(
                        "%(count)d business on this plan gets the change within 15 minutes.",
                        "%(count)d businesses on this plan get the change within 15 minutes.",
                        owed,
                    )
                    % {"count": owed},
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


def traced(action):
    """An action of the platform leaves, on each row it ran on, who ran it and which in the admin's history
    (HUBS-F23; ERPlora/saas SAAS_DASHBOARD-F41 lost that trace). Under ``@admin.action``, whose description it
    names: the line is written whatever the action reported, since the attempt is what the staff did."""

    @functools.wraps(action)
    def run(model_admin, request, queryset):
        rows = list(queryset)
        try:
            return action(model_admin, request, queryset)
        finally:
            message = _("Ran «%(action)s»") % {"action": run.short_description}
            for row in rows:
                model_admin.log_change(request, row, message)

    return run


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
    actions = ["send_latest_state", "retry_owed", "attach_test_clock", "advance_test_clock"]
    #: BILLING-F29: offered only with Stripe's test keys (PRE, development); production never sees them.
    TEST_CLOCK_ACTIONS = ("attach_test_clock", "advance_test_clock")

    def get_actions(self, request, action_location=ActionLocation.CHANGE_LIST):
        from billing.stripe_keys import StripeKeyMode
        from billing.stripe_service import key_mode

        actions = super().get_actions(request, action_location=action_location)
        if key_mode() is not StripeKeyMode.TEST:
            for name in self.TEST_CLOCK_ACTIONS:
                actions.pop(name, None)
        return actions

    @admin.action(description=_("Attach its payer to a Stripe test clock (test keys only)"), permissions=["sync"])
    @traced
    def attach_test_clock(self, request, queryset):
        from billing import services as billing_services

        for hub in queryset:
            try:
                clock = billing_services.attach_test_clock(hub.id)
            except billing_services.TestClockRefused as refused:
                self.message_user(request, f"{hub.slug}: {refused}", messages.ERROR)
                continue
            self.message_user(
                request, _("%(business)s: its payer is a new Stripe customer on clock %(clock)s.") % {"business": hub.slug, "clock": clock}
            )

    @admin.action(description=_("Advance its Stripe test clock a month (test keys only)"), permissions=["sync"])
    @traced
    def advance_test_clock(self, request, queryset):
        from billing import services as billing_services

        for hub in queryset:
            try:
                reached = billing_services.advance_test_clock_of(hub.id)
            except billing_services.TestClockRefused as refused:
                self.message_user(request, f"{hub.slug}: {refused}", messages.ERROR)
                continue
            self.message_user(
                request,
                _("%(business)s: its clock is advancing to %(date)s; Stripe tells what happens by its events.")
                % {"business": hub.slug, "date": reached.date().isoformat()},
            )

    @admin.action(description=_("Send the latest state to the Hub"), permissions=["sync"])
    @traced
    def send_latest_state(self, request, queryset):
        self._tell(request, services.send_latest_state(list(queryset.values_list("id", flat=True))))

    @admin.action(description=_("Retry what the Hub still owes"), permissions=["sync"])
    @traced
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
    # ``forget_after``: the account deleted itself; the payer goes once nothing can be charged to it (ACCOUNTS-F27).
    list_display = ["__str__", "owner", "billing_email", "tax_id", "billing_country", "created_at", "forget_after"]
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
    @traced
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


@admin.register(HubUsageDaily)
class HubUsageDailyAdmin(ReadOnly, admin.ModelAdmin):
    list_display = [
        "hub",
        "day",
        "files",
        "database",
        "active_users_1d",
        "active_users_30d",
        "served",
        "connections",
        "without_room",
        "collected_at",
    ]
    list_select_related = ["hub"]
    search_fields = ["hub__slug", "hub__name"]
    date_hierarchy = "day"
    #: What the Hub did not measure (``requests``, ``peak_connections``, ``busy_requests``): never read as a 0.
    empty_value_display = "—"

    @admin.display(description=_("Files"), ordering="s3_bytes")
    def files(self, obj):
        return filesizeformat(obj.s3_bytes)

    @admin.display(description=_("Database"), ordering="db_bytes")
    def database(self, obj):
        return filesizeformat(obj.db_bytes)

    # hub#603: their first click says who is highest, with what the Hub did not measure last, not on top.

    @admin.display(description=_("requests"), ordering=F("requests").desc(nulls_last=True))
    def served(self, obj):
        return obj.requests

    @admin.display(description=_("peak connections"), ordering=F("peak_connections").desc(nulls_last=True))
    def connections(self, obj):
        return obj.peak_connections

    @admin.display(description=_("requests with no room"), ordering=F("busy_requests").desc(nulls_last=True))
    def without_room(self, obj):
        return obj.busy_requests
