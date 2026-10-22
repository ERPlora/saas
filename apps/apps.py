"""The app catalog of the SaaS (round 16, PLAN §21.1 point 10, spec decision 18).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to
``base/``, without module fields (no requires, category, premium or menu of its own). It owns the
``shared`` schema of the ``saas`` database, where the Hub registers its apps (``App`` and
``AppDoc``, read-only here), and ``Module``, what the SaaS sells of a paid app. Not a folder of
modules: the SaaS turns nothing on or off.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class AppsConfig(LiveAppConfig):
    name = "apps"
    label = "apps"
    kind = "platform"
    verbose_name = _("Apps")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps import auditlog
        from apps import checks  # noqa: F401  (registers the system checks)

        # The audit trail of the paid apps' prices (ACCOUNTS-F36, PLAN-SAAS §1.1).
        auditlog.register()
