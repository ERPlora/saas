"""The AI gateway of erplora.com: every request of AI goes through the SaaS with the same provider key.

A LiveAppConfig of kind "platform": always on, at the project root next to ``base/``, without
module fields. The providers ERPlora pays (OpenAI, Anthropic, Gemini, DeepSeek), their keys kept encrypted, their
models, which model answers, the trial of a model before it answers, and the clients that speak each provider's API.
The staff configure it in the admin; the panel's own assistant (``base.assistant``) is every
account's, with its own monthly allowance.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class AssistantConfig(LiveAppConfig):
    name = "assistant"
    label = "assistant"
    kind = "platform"
    verbose_name = _("AI assistant")
    default_auto_field = "django.db.models.BigAutoField"
    # Only the platform (its commands, the Hub's doors) and ERPlora's staff (the admin, each change backed by a
    # model permission of Django) configure it: no account role gets ``assistant.manage``. Every signed-in account
    # asks the panel's assistant (``assistant.ask``: ``base.assistant.turn``, ``.usage`` and ``.report``).
    permissions = ["assistant.manage", "assistant.ask"]
    role_permissions = {"account": ["assistant.ask"]}

    def ready(self):
        super().ready()
        from assistant import auditlog

        # The audit trail of the providers, their keys, their models and the model that answers.
        auditlog.register()
