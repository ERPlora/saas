"""WhatsApp, erplora.com's side.

A LiveAppConfig of kind "platform": always on, at the project root next to ``base/``, without module fields. It holds
the business's WhatsApp Business account before Meta (Embedded Signup, its number, its token and the token's renewal),
Meta's webhook, the attachments, the delivery statuses, the templates and the doors of the Hub's contract. No screen
in the panel: the inbox and its settings live in the Hub.
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
