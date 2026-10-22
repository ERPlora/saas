"""The audit trail of what ERPlora sells of a paid app (django-auditlog; ACCOUNTS-F36, PLAN-SAAS §1.1). Registered
from ``AppsConfig.ready``.

A ``Module`` is a price the staff keep in the admin; ``updated_at`` is not logged. The catalog the Hub writes (``App``,
``AppDoc``) is not money: not registered.
"""

from accounts.auditlog import audit
from apps.models import Module


def register() -> None:
    audit(Module, exclude=["updated_at"])
