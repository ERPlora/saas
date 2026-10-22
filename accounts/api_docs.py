"""``/api/docs``: the reference of the SaaS's API for signed-in accounts (ACCOUNTS-F34; PLAN-SAAS bloque 15).

django-ninja's ReDoc, read only: the old Swagger's «Try it out» changed real data without a word (SAAS_DASHBOARD-F197);
an integration tries the API with Postman, whose collection comes from the same schema. Its own template
(``accounts/api_docs.html``) loads ninja's static ReDoc with the response's nonce, nothing from a CDN.

The SPA's policy stays, but for two directives of this page alone (``docs_policy``): ReDoc writes HTML from strings, which
Trusted Types refuses, and runs its search in a ``blob:`` worker. Signed out, the sign-in (``LOGIN_URL``), which comes
back here; an API key opens nothing here (the page is a person's). The gate is the page's own (``render_page``), not
ninja's ``docs_decorator``, which would close ``/api/openapi.json`` too: the schema stays open (Postman, the suites).
"""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.utils.csp import CSP
from ninja.openapi.docs import Redoc


def docs_policy(policy: dict[str, list[str]]) -> dict[str, list[str]]:
    """``policy`` (a fresh copy) without Trusted Types and with a ``blob:`` worker, for this page only."""
    result = {name: list(sources) for name, sources in policy.items() if name != "require-trusted-types-for"}
    result["worker-src"] = [CSP.SELF, "blob:"]
    return result


class ApiReference(Redoc):
    """ninja's ReDoc in our template, with the nonce on every script, for signed-in accounts only."""

    template = "accounts/api_docs.html"

    def render_page(self, request, api, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        response = super().render_page(request, api, **kwargs)
        # What Django's `csp_override` sets: the middleware builds the header from it, with the nonce.
        response._csp_config = docs_policy(settings.SECURE_CSP)
        return response
