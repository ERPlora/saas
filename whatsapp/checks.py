"""System checks of whatsapp: ``FERNET_KEY`` is a Fernet key (``whatsapp.E001``) and every setting WhatsApp needs
is there, ``WHATSAPP_REDIRECT_URI`` being this site's ``/whatsapp/return`` over https (``whatsapp.I001``).

A missing setting never stops the rest of the SaaS: the webhook answers 503 and the doors
``whatsapp.not_configured``, both visible. ``check`` says it as information (the deploy fails at WARNING and the
secrets come from the infrastructure's repo), as ``accounts.I001`` does for Google.
"""

from django.conf import settings
from django.core import checks

from whatsapp.crypto import key_problem
from whatsapp.meta import redirect_uri

#: What WhatsApp needs from the environment (Meta's app, its webhook and the key of the tokens).
REQUIRED = (
    "WHATSAPP_APP_ID",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_CONFIG_ID",
    "FERNET_KEY",
)


@checks.register(checks.Tags.security)
def check_fernet_key(app_configs=None, **kwargs):
    key = str(getattr(settings, "FERNET_KEY", "") or "")
    problem = key_problem(key) if key else None
    if problem is None:
        return []
    return [
        checks.Error(
            f"FERNET_KEY is not a Fernet key: {problem}.",
            hint='Generate one with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"',
            id="whatsapp.E001",
        )
    ]


@checks.register(checks.Tags.security)
def check_meta_settings(app_configs=None, **kwargs):
    missing = [name for name in REQUIRED if not str(getattr(settings, name, "") or "").strip()]
    if not redirect_uri():
        # Not this site's /whatsapp/return over https: Meta's window could not bring its code back.
        missing.append("WHATSAPP_REDIRECT_URI")
    if not missing:
        return []
    return [
        checks.Info(
            f"WhatsApp is off: {', '.join(missing)} not set or not valid. Meta's webhook answers 503 and the Hub's "
            "WhatsApp doors refuse with whatsapp.not_configured.",
            hint="Set them from Meta's app («ERPlora Inbox») and the secrets of the environment; WHATSAPP_REDIRECT_URI "
            "is this site's https address of /whatsapp/return, one of the app's «Valid OAuth Redirect URIs».",
            id="whatsapp.I001",
        )
    ]
