"""Django admin of the audit trail: auditlog's own page, read only, in the staff's language."""

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils import formats
from django.utils.text import capfirst
from django.utils.translation import ngettext
from django.utils.translation import gettext_lazy as _

from auditlog.admin import LogEntryAdmin as AuditlogLogEntryAdmin
from auditlog.filters import CIDFilter
from auditlog.filters import ResourceTypeFilter as AuditlogResourceTypeFilter
from auditlog.mixins import MAX as SUMMARY_MAX
from auditlog.models import LogEntry
from auditlog.render import get_field_verbose_name


# auditlog's page writes its summary («1 change: first_name») and its «Correlation ID» header in English whatever the
# language, and lists the resources by their models' code names (``usersession``).
admin.site.unregister(LogEntry)


class ResourceTypeFilter(AuditlogResourceTypeFilter):
    """«Resource Type» by each model's name in the staff's language («Clave de API»), not its code name («apikey»)."""

    def lookups(self, request, model_admin):
        named = []
        for type_id, code_name in super().lookups(request, model_admin):
            model = ContentType.objects.get_for_id(type_id).model_class()
            named.append((type_id, capfirst(model._meta.verbose_name) if model is not None else code_name))
        return sorted(named, key=lambda choice: str(choice[1]))


@admin.register(LogEntry)
class LogEntryAdmin(AuditlogLogEntryAdmin):
    """The audit trail, read only as auditlog's own page, with what it says in English said in the
    staff's language: the summary counts the changes and names each field, as Django's own history does."""

    list_filter = ["action", ResourceTypeFilter, CIDFilter]

    @admin.display(description=_("Created"))
    def created(self, obj):
        # A datetime is formatted on the list but printed raw on the entry's page (a read-only callable): formatted
        # here, the same on both.
        return formats.localize(super().created(obj))

    @admin.display(description=_("Changes"))
    def msg_short(self, obj):
        if obj.action in (LogEntry.Action.DELETE, LogEntry.Action.ACCESS):
            return ""
        changes = obj.changes_dict
        fields = ", ".join(str(get_field_verbose_name(obj, name)) for name in changes)
        if len(fields) > SUMMARY_MAX:
            fields = fields[: fields.rfind(" ", 0, SUMMARY_MAX)] + " .."
        return ngettext("%(count)d change: %(fields)s", "%(count)d changes: %(fields)s", len(changes)) % {
            "count": len(changes),
            "fields": fields,
        }

    @admin.display(description=_("Correlation ID"))
    def cid_url(self, obj):
        return super().cid_url(obj)
