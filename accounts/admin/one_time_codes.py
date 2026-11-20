"""Django admin of the one-time codes, read only: the codes of the jump to a hub and the changes of email waiting
for theirs."""

from django.contrib import admin

from accounts.models import AuthExchangeCode, EmailChangeRequest


@admin.register(AuthExchangeCode)
class AuthExchangeCodeAdmin(admin.ModelAdmin):
    """Audit only: a code is minted by /hub-login/ and spent by the hub, never by hand."""

    list_display = ("user", "hub_slug", "audience", "created_at", "expires_at", "used_at")
    list_filter = ("audience", "hub_slug")
    search_fields = ("user__email", "hub_slug")
    exclude = ("code_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailChangeRequest)
class EmailChangeRequestAdmin(admin.ModelAdmin):
    """Read only: a change of email waiting for its code (``accounts.email.change``); never the code's hash nor the
    session it is bound to."""

    list_display = ("user", "email", "attempts", "created_at")
    search_fields = ("user__email", "email")
    fields = ("user", "email", "attempts", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
