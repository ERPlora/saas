"""«Site settings» in the admin of erplora.com: the switch of the maintenance mode (ACCOUNTS-G33, G82).

One row (``base.models.SiteSettings``): the list opens it, creating it the first time; nothing to add or delete. Saving
says what the switch now does. Only who holds its permissions (the superuser) sees it: the support group does not.
Ported from ERPlora/saas ``SiteSettingsAdmin`` (origin/develop c5ca8cae8).
"""

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _

from base.models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fields = ("maintenance_mode", "maintenance_message_en", "maintenance_message_es", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            return super().changelist_view(request, extra_context)
        site, _created = SiteSettings.objects.get_or_create(singleton=True)
        return HttpResponseRedirect(reverse("admin:base_sitesettings_change", args=[site.pk]))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.maintenance_mode:
            self.message_user(
                request,
                _("Maintenance mode is on: only the ERPlora staff with a session uses erplora.com."),
                messages.WARNING,
            )
        else:
            self.message_user(request, _("Maintenance mode is off: erplora.com is open to everyone."), messages.SUCCESS)
