"""The platform app of saas-next (Odoo's ``base``, as in hub-next): session, the API root and the SPA.

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, never turned on or off, so it
declares no module fields (no requires, category, premium or menu of its own). Being a
LiveAppConfig is what lets the API mount its router (``live.ninja.mount_app_routers``) and the
live checks see it.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class BaseConfig(LiveAppConfig):
    name = "base"
    label = "base"
    kind = "platform"
    verbose_name = _("Base")
    default_auto_field = "django.db.models.BigAutoField"
