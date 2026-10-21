"""Django admin of whatsapp (``erplora.com/admin``): what ERPlora's staff sees of the businesses' WhatsApp
(WHATSAPP-G08, WHATSAPP-G18).

Each business's number, the mirror of its templates at Meta, what waits for its Hub, its sends and its month's count:
seen, never written by hand, not even by a superuser (only Meta's window connects a number; the operations of
``whatsapp.services`` write the rest). The permission and the PIN of a number are never shown, only whether the
permission is stored, expired or missing; nobody reads here what a customer wrote nor their number.

Superusers get the platform's actions (each one the gateway's, so Meta and the Hub are called as everywhere else):
disconnect a number, push to the Hub now what waits for it, read Meta's templates again. ``support`` only sees
(data migration ``0002``).
"""

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from whatsapp import gateway, services
from whatsapp.models import Delivery, PhoneNumber, Send, Template, Usage
from whatsapp.schemas import DisconnectIn, DueNowIn


class ReadOnly:
    """Seen, never written here."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PlatformActions(ReadOnly, admin.ModelAdmin):
    def has_platform_permission(self, request):
        """The platform's actions: superusers only (``support`` only sees)."""
        return request.user.is_active and request.user.is_superuser


@admin.register(PhoneNumber)
class PhoneNumberAdmin(PlatformActions):
    list_display = (
        "display_phone",
        "hub",
        "phone_number_id",
        "waba_id",
        "is_active",
        "is_on_biz_app",
        "token_state",
        "token_expires_at",
        "needs_reconnect",
        "connected_at",
    )
    list_filter = ("is_active", "is_on_biz_app", "needs_reconnect")
    search_fields = ("display_phone", "phone_number_id", "waba_id", "hub__slug", "hub__name")
    list_select_related = ("hub",)
    ordering = ("-connected_at",)
    fields = (
        "hub",
        "display_phone",
        "display_name",
        "phone_number_id",
        "waba_id",
        "business_id",
        "is_on_biz_app",
        "token_state",
        "token_expires_at",
        "is_active",
        "needs_reconnect",
        "reconnect_alerted_at",
        "connected_by",
        "connected_at",
        "disconnected_at",
        "updated_at",
    )
    readonly_fields = fields
    actions = ("disconnect", "read_templates_again")

    @admin.display(description=gettext_lazy("Meta's permission"))
    def token_state(self, number: PhoneNumber) -> str:
        if not number.access_token:
            return _("Missing: the business has to connect the number again.")
        if number.token_expires_at is not None and number.token_expires_at <= timezone.now():
            return _("Expired: the business has to connect the number again.")
        return _("Stored: this number can send and receive.")

    @admin.action(description=gettext_lazy("Disconnect the number"), permissions=["platform"])
    def disconnect(self, request, queryset):
        done = 0
        for slug in sorted(set(queryset.filter(is_active=True).values_list("hub__slug", flat=True))):
            status, body = gateway.disconnect(DisconnectIn(hub=slug))
            done += int(status == 200 and body.get("disconnected") is True)
        self.message_user(
            request, ngettext("%(count)d number disconnected.", "%(count)d numbers disconnected.", done) % {"count": done}
        )

    @admin.action(description=gettext_lazy("Read Meta's templates again"), permissions=["platform"])
    def read_templates_again(self, request, queryset):
        for hub_id in sorted(set(queryset.filter(is_active=True).values_list("hub_id", flat=True)), key=str):
            if gateway.sync_templates(hub_id):
                self.message_user(request, _("Templates read again from Meta."))
            else:
                self.message_user(
                    request, _("Meta could not be read now: the templates stay as they were."), messages.WARNING
                )


@admin.register(Template)
class TemplateAdmin(ReadOnly, admin.ModelAdmin):
    list_display = ("name", "language", "hub", "category", "status", "rejected_reason", "updated_at")
    list_filter = ("status", "category")
    search_fields = ("name", "meta_id", "hub__slug", "hub__name")
    list_select_related = ("hub",)


@admin.register(Delivery)
class DeliveryAdmin(PlatformActions):
    """What waits for the Hub and what it took: a row without «taken by the Hub» long after «received» is a Hub that
    stopped taking. Never the content: it is what a customer wrote."""

    list_display = (
        "wa_message_id",
        "kind",
        "hub",
        "received_at",
        "delivered_at",
        "attempts",
        "next_attempt_at",
        "last_error",
    )
    list_filter = ("kind", ("delivered_at", admin.EmptyFieldListFilter))
    search_fields = ("wa_message_id", "hub__slug", "hub__name")
    list_select_related = ("hub",)
    fields = (
        "hub",
        "kind",
        "wa_message_id",
        "received_at",
        "delivered_at",
        "attempts",
        "next_attempt_at",
        "last_error",
    )
    readonly_fields = fields
    actions = ("push_now",)

    def get_queryset(self, request):
        return super().get_queryset(request).defer("body", "contact")

    @admin.action(description=gettext_lazy("Push to the Hub now"), permissions=["platform"])
    def push_now(self, request, queryset):
        due = services.delivery_due_now(services.platform_context(), DueNowIn(ids=list(queryset.values_list("id", flat=True))))
        if not due.count:
            self.message_user(request, _("Nothing selected waits for the Hub."), messages.WARNING)
            return
        counts = gateway.deliver(due.hub_ids)
        self.message_user(
            request,
            _("%(delivered)d taken by the Hub, %(retried)d still waiting, %(refused)d refused by the Hub.")
            % counts,
        )


@admin.register(Send)
class SendAdmin(ReadOnly, admin.ModelAdmin):
    list_display = ("idempotency_key", "hub", "state", "month", "wa_message_id", "created_at")
    list_filter = ("state", "month")
    search_fields = ("idempotency_key", "wa_message_id", "hub__slug")
    list_select_related = ("hub",)


@admin.register(Usage)
class UsageAdmin(ReadOnly, admin.ModelAdmin):
    list_display = ("hub", "month", "used", "updated_at")
    list_filter = ("month",)
    search_fields = ("hub__slug", "hub__name")
    list_select_related = ("hub",)
