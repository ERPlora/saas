"""WhatsApp, erplora.com's side (PLAN-SAAS §1.1, round 2026-10-15b; README.md).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to ``base/``,
without module fields. The business's WhatsApp Business account before Meta (Embedded Signup, its number,
its token and the token's renewal), Meta's webhook, the attachments, the delivery statuses, the templates
and the doors of the Hub's contract (``hub/apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el SaaS»).
No screen in the panel: the inbox and its settings are the Hub's (PLAN-SAAS block 12).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class WhatsappConfig(LiveAppConfig):
    name = "whatsapp"
    label = "whatsapp"
    kind = "platform"
    verbose_name = _("WhatsApp")
    default_auto_field = "django.db.models.BigAutoField"
    # Only the platform acts here: the Hub through /internal, Meta through its webhook, the staff through
    # the admin. No account role gets it.
    permissions = ["whatsapp.manage"]

    def ready(self):
        super().ready()
        from whatsapp import checks  # noqa: F401  (registers the checks of Meta's settings and the key)
