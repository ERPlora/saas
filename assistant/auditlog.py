"""The audit trail of the AI gateway (django-auditlog; ASSISTANT-F08, ACCOUNTS-F36, PLAN-SAAS §1.1). Registered from
``AssistantConfig.ready``.

Who added, changed, turned off or deleted a provider, a provider's key, a model or the model that answers, from
where and what changed. Never logged: a provider's key (``api_key``, neither in clear nor its encrypted token; its
rotation shows as its new ``key_hint`` and ``rotated_at``, saas#970 of the old product) nor ``updated_at``.
"""

from accounts.auditlog import audit
from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy


def register() -> None:
    audit(AIProvider, exclude=["updated_at"])
    audit(AIProviderCredential, exclude=["api_key", "updated_at"])
    audit(AIModel, exclude=["updated_at"])
    audit(AIRoutingPolicy, exclude=["updated_at"])
