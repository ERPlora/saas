"""Django admin of the sessions: ``allauth.usersessions'`` own page, read only, named in the staff's language."""

from django.contrib import admin, messages
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from allauth.usersessions.admin import UserSessionAdmin as AllauthUserSessionAdmin
from allauth.usersessions.models import UserSession

from accounts.services import active_sessions


# allauth's page of the sessions searches ``user__username``, which this account model has not.
admin.site.unregister(UserSession)


@admin.register(UserSession)
class UserSessionAdmin(AllauthUserSessionAdmin):
    """Who is signed in where (``allauth.usersessions``): read only. Deleting a row would only hide a session that
    still signs in; a superuser ends the picked ones with «Close the selected sessions», which also
    asks their businesses; ``support`` sees them. Every column and label is named here, in the staff's language."""

    list_display = ("account", "signed_in", "last_used", "ip_address", "browser")
    search_fields = ["user__email", "ip"]
    fields = ("account", "signed_in", "last_used", "ip_address", "browser", "session_key", "session_data")
    readonly_fields = fields
    actions = ("close_sessions",)

    @admin.display(description=_("Account"), ordering="user__email")
    def account(self, session):
        return session.user

    @admin.display(description=_("Signed in"), ordering="created_at")
    def signed_in(self, session):
        return session.created_at

    @admin.display(description=_("Last used"), ordering="last_seen_at")
    def last_used(self, session):
        return session.last_seen_at

    @admin.display(description=_("IP address"), ordering="ip")
    def ip_address(self, session):
        return session.ip

    @admin.display(description=_("Browser"))
    def browser(self, session):
        return session.user_agent

    @admin.display(description=_("Session data"))
    def session_data(self, session):
        return session.data

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_close_sessions_permission(self, request):
        return request.user.is_superuser

    @admin.action(description=_("Close the selected sessions"), permissions=["close_sessions"])
    def close_sessions(self, request, queryset):
        count = active_sessions.close_sessions(by=request.user, sessions=list(queryset))
        self.message_user(request, gettext("Sessions closed: %(count)s.") % {"count": count}, messages.SUCCESS)
