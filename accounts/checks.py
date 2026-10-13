"""System checks of accounts."""

from django.conf import settings
from django.core import checks


@checks.register()
def google_sign_in(app_configs, **kwargs):
    """Say why a development server shows no «Continue with Google» (production refuses to start)."""
    if settings.GOOGLE_OAUTH_ENABLED:
        return []
    return [
        checks.Info(
            "Google sign-in is off: GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are not set, "
            "so the login hides «Continue with Google».",
            hint="Set both in saas-next/.env (see saas-next/README.md, «Google»).",
            id="accounts.I001",
        )
    ]
