"""The documentation a business sends so ERPlora can file its VeriFactu records, and its review by the staff
(plan 2026-10-15, «revisión de la documentación fiscal»; PLAN-SAAS §4, round 2026-10-15).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to ``hubs/``,
whose businesses it reads, without module fields. The Hub sends the signed authorisation (Anexo I of the
AEAT's agreement 017) through ``/internal`` (``fiscal.internal``); the staff approve, return or withdraw it
in the admin (``fiscal.admin``); the business's snapshot carries the outcome (``fiscal.queries.snapshot_block``).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class FiscalConfig(LiveAppConfig):
    name = "fiscal"
    label = "fiscal"
    kind = "platform"
    verbose_name = _("Fiscal documentation")
    default_auto_field = "django.db.models.BigAutoField"
    # Every signed-in account reads the state of its businesses' authorisation (``fiscal.view``; which
    # business, and with which role, is checked in the operation). ``fiscal.manage`` is no role's: only the
    # platform (the Hub's upload) and the staff (the review in the admin) run those commands.
    permissions = ["fiscal.view", "fiscal.manage"]
    role_permissions = {"account": ["fiscal.view"]}

    def ready(self):
        super().ready()
        from fiscal import checks  # noqa: F401  (registers the check of FISCAL_DOCUMENTS_KEY)
