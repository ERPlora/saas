"""The fiscal gateway: presents the Hub's VeriFactu envelopes to the AEAT (PLAN-SAAS §4; README.md).

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, at the project root next to
``base/``, without module fields, models or operations of its own: three signed ``/internal`` doors
(``internal.py``) for the Hub, and ERPlora's seal read from the settings (``seal.py``).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class FiscalGatewayConfig(LiveAppConfig):
    name = "fiscal_gateway"
    label = "fiscal_gateway"
    kind = "platform"
    verbose_name = _("Fiscal gateway")
    default_auto_field = "django.db.models.BigAutoField"
