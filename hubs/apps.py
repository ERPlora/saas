"""The businesses of the SaaS: plans and the taxonomy of sectors and business types (PLAN §21.4).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to
``base/``, without module fields (no requires, category, premium or menu of its own). Being a
LiveAppConfig is what lets the API mount its router (``live.ninja.mount_app_routers``).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class HubsConfig(LiveAppConfig):
    name = "hubs"
    label = "hubs"
    kind = "platform"
    verbose_name = _("Businesses")
    default_auto_field = "django.db.models.BigAutoField"
    # Every signed-in account (role "account", base.operations) reads and acts on its own businesses;
    # which business and what it may do there is checked in each operation by its HubMember role.
    permissions = ["hubs.view", "hubs.manage"]
    role_permissions = {"account": ["hubs.*"]}
