"""The SaaS's API (django-ninja), mounted at ``/api/``: the SPA's and, later, the integrations'.

Every route calls one operation (``ensure_api_parity`` keeps it so) and every failure answers with
the single envelope ``{"error": {...}}``. Authentication is Django's session, which ninja checks
together with the CSRF token on every unsafe method (the SDK sends ``X-CSRFToken``); a route open
to anonymous visitors says ``auth=None``. Sign-in itself is not here: it is allauth.headless's API
at ``/_allauth/``.

No Swagger page yet: ninja's own has scripts without the CSP nonce, a blank page under
'strict-dynamic'. ``/api/openapi.json`` is served.
"""

from live.ninja import install_error_handlers, mount_app_routers
from ninja import NinjaAPI
from ninja.security import django_auth


def build_api(*, urls_namespace: str = "api") -> NinjaAPI:
    """A NinjaAPI configured as the SaaS's: session auth with CSRF and the error envelope."""
    api = NinjaAPI(
        title="ERPlora Cloud API",
        version="1",
        openapi_url="/openapi.json",
        docs_url=None,
        auth=django_auth,
        urls_namespace=urls_namespace,
    )
    install_error_handlers(api)
    return api


api = build_api()
# The api.py router of every app of ours: the platform apps base and accounts (round 15, PLAN §20).
mount_app_routers(api)
