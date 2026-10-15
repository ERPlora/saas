"""System check of fiscal: ``FISCAL_DOCUMENTS_KEY`` is a Fernet key (``fiscal.E001``).

Without one the settings refuse to start in production (``config/settings.py``); a value that is no Fernet
key would only fail at the first upload, so ``check`` (``migrate`` and the deploy run it) says it first.
"""

from django.conf import settings
from django.core import checks

from fiscal.crypto import key_problem


@checks.register(checks.Tags.security)
def check_documents_key(app_configs=None, **kwargs):
    problem = key_problem(getattr(settings, "FISCAL_DOCUMENTS_KEY", "") or "")
    if problem is None:
        return []
    return [
        checks.Error(
            f"FISCAL_DOCUMENTS_KEY is not a Fernet key: {problem}.",
            hint='Generate one with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"',
            id="fiscal.E001",
        )
    ]
