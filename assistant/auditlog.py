"""The audit trail of the AI gateway (django-auditlog). Registered from
``AssistantConfig.ready``.

Who added, changed, turned off or deleted a provider (also the variable of the environment it reads its key from), a
model or the model that answers, from where and what changed. A provider's key is never in a row, so never here; nor
is ``updated_at``.
"""

from accounts.auditlog import audit
from assistant.models import AIModel, AIProvider, AIRoutingPolicy


def register() -> None:
    audit(AIProvider, exclude=["updated_at"])
    audit(AIModel, exclude=["updated_at"])
    audit(AIRoutingPolicy, exclude=["updated_at"])
