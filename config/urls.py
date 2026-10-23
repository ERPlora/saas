"""URLconf of saas-next: Django's own prefixes first, then the SPA for every other path.

Django keeps the sign-in's API (allauth.headless at ``/_allauth/``, headless only: allauth serves no
page; Google comes back to the redirect URI registered with it), the old addresses of the sign-in, the
jump to a hub and its redeem, the API, the live stream, the admin, the CSP reports and ``/readyz``.
``/healthz`` is answered by ``base.health.HealthCheckMiddleware`` before the Host is validated, so it has
no route here.
``/webhooks/stripe/`` is Stripe's single webhook (``billing.webhooks``, lot L2-B); anything else under
``/webhooks/`` is a 404 of Django's, never the SPA. Every other path is the Ionic Vue SPA (``base.spa``):
the launcher with its sign-in (``/launch``) and the sign-in's errors (``/login/error``) among them.
"""

from django.contrib import admin
from django.urls import include, path, re_path
from django.utils.translation import gettext_lazy
from django.views.generic import RedirectView
from live.live_view import live_stream
from live.spa import BASE_NON_SPA_PREFIXES, spa_path_pattern

from accounts import admin as accounts_admin
from accounts import doors, google, handoff, internal
from accounts.adapters import SPA_LOGIN
from base.csp_report import csp_report
from base.health import readyz
from base.spa import spa
from billing import webhooks as billing_webhooks
from config.api import api
from fiscal import internal as fiscal_internal
from fiscal_gateway import internal as fiscal_gateway_internal
from hubs import internal as hubs_internal
from hubs import shell as hubs_shell
from public import landing
from whatsapp import internal as whatsapp_internal
from whatsapp import media as whatsapp_media
from whatsapp import signup_return as whatsapp_signup_return
from whatsapp import webhooks as whatsapp_webhooks
from public.urls import PUBLIC_PREFIXES

# Prefixes of saas-next on top of the shared ones: allauth.headless's API, the old addresses of the
# sign-in (`/accounts/`), Google's redirect URI, the jump to a hub and Stripe's webhook
# (`/webhooks/stripe/`, PLAN-SAAS §4). Not `launch`: `/launch` is the SPA's launcher, and only the
# exact `/launch/` (its old address) is a Django route, matched before the SPA's catch-all.
NON_SPA_PREFIXES = (
    *BASE_NON_SPA_PREFIXES,
    "_allauth",
    "accounts",
    "auth",
    "hub-login",
    "webhooks",
    # The public web's own first segments (public/urls.py).
    *PUBLIC_PREFIXES,
)

#: The launcher's «Create account» tab (`SignInForm.vue`; «Sign in», the default, is `SPA_LOGIN` alone).
SPA_SIGN_UP = f"{SPA_LOGIN}?tab=signup"


class SignUpRedirect(RedirectView):
    """The old address of the sign-up, for good, to the launcher's «Create account» tab in one hop, keeping
    `next` and the rest of the query (a `tab` of its own never wins over the sign-up's)."""

    permanent = True

    def get_redirect_url(self, *args, **kwargs) -> str:
        query = self.request.GET.copy()
        query.pop("tab", None)
        rest = query.urlencode(safe="/")
        return f"{SPA_SIGN_UP}&{rest}" if rest else SPA_SIGN_UP


# The admin's login is the SaaS's sign-in (it asks for the mailed code and the authenticator app).
# Assigned before `admin.site.urls` is read below: `AdminSite.get_urls` binds `self.login` then.
admin.site.login = accounts_admin.admin_login
# Who enters: active staff, and with ACCOUNTS_MFA_ENABLED only with an authenticator app (ACCOUNTS-F20).
admin.site.has_permission = accounts_admin.admin_has_permission
# ERPlora's name on every page of the admin, never «Django administration» (the old SaaS's ADMIN_SITE_*; ACCOUNTS-G30).
admin.site.site_header = "ERPlora Cloud"
admin.site.site_title = "ERPlora Admin"
admin.site.index_title = gettext_lazy("Administration")

urlpatterns = [
    # The old addresses of the sign-in and of the sign-up (allauth's template pages until headless only,
    # then the SPA's `/login` until the form moved into the launcher): bookmarks and pages of the public
    # web cached elsewhere land on the launcher for good, in one hop, keeping `next` and the rest of the
    # query: the sign-in's on its «Sign in» tab, the sign-up's on «Create account». `/login/error` stays a
    # page of the SPA; every other old page of allauth under /accounts/ is gone (404).
    path("accounts/login/", RedirectView.as_view(url=SPA_LOGIN, query_string=True, permanent=True)),
    path("accounts/signup/", SignUpRedirect.as_view()),
    path("login", RedirectView.as_view(url=SPA_LOGIN, query_string=True, permanent=True)),
    # The account's addresses change only through Cuenta's code, and an account without a password gets
    # one only through «Forgot your password?» (accounts/doors.py, plan 2026-10-13 L3-A).
    path("_allauth/browser/v1/account/email", doors.closed),
    path("_allauth/browser/v1/account/password/change", doors.password_change),
    # The sign-in's address folded as the sign-up's (ERPlora/saas#1018), and the sign-up's password checked
    # against its address (ERPlora/saas#2542): accounts/doors.py.
    path("_allauth/browser/v1/auth/login", doors.login, name="login"),
    path("_allauth/browser/v1/auth/signup", doors.signup, name="signup"),
    # «Continue with Google» on the launcher posts here; without Google's credentials it is not served.
    path("_allauth/browser/v1/auth/provider/redirect", google.provider_redirect, name="redirect_to_provider"),
    path("_allauth/", include("allauth.headless.urls")),
    # Google comes back to the redirect URI registered with it (/auth/google/callback/, PLAN-SAAS §6),
    # under allauth's name: allauth builds the redirect_uri of the authorization and of the token
    # exchange from `reverse("google_callback")`.
    path("auth/google/callback/", google.callback, name="google_callback"),
    path("launch/", handoff.launch, name="launch"),
    path("hub-login/", handoff.hub_login, name="hub_login"),
    # The installed app's «Open» (PLAN-SAAS bloque 3); its start, /shell/, is the SPA's launcher.
    path("shell/open/<uuid:hub_id>/", hubs_shell.open_business, name="shell_open"),
    # The old panel's addresses of the businesses, for good, to the new panel (PLAN-SAAS §1).
    path("", include("hubs.redirects")),
    path("", include("accounts.redirects")),
    # ReDoc for /api/docs without its one outside address (ACCOUNTS-F34), before ninja's /api/.
    path("", include("accounts.api_docs")),
    path("internal/auth/redeem", internal.redeem, name="internal_auth_redeem"),
    path(
        "internal/hubs/<uuid:hub_id>/ready",
        hubs_internal.ready,
        name="internal_hub_ready",
    ),
    path(
        "internal/hubs/<uuid:hub_id>/representation",
        fiscal_internal.representation,
        name="internal_hub_representation",
    ),
    path(
        "internal/representation/model",
        fiscal_internal.representation_model,
        name="internal_representation_model",
    ),
    # The fiscal gateway (PLAN-SAAS §4): the Hub's VeriFactu envelopes, presented to the AEAT.
    path(
        "internal/verifactu/submit",
        fiscal_gateway_internal.submit,
        name="internal_verifactu_submit",
    ),
    path(
        "internal/verifactu/query",
        fiscal_gateway_internal.query,
        name="internal_verifactu_query",
    ),
    path(
        "internal/verifactu/probe",
        fiscal_gateway_internal.probe,
        name="internal_verifactu_probe",
    ),
    # WhatsApp (whatsapp/internal.py): the doors erplora.com serves to the Hub (its WORKBOOK whatsapp_inbox, doors 5–9).
    path("internal/whatsapp/send", whatsapp_internal.send, name="internal_whatsapp_send"),
    path("internal/whatsapp/erase", whatsapp_internal.erase, name="internal_whatsapp_erase"),
    path("internal/whatsapp/templates", whatsapp_internal.templates, name="internal_whatsapp_templates"),
    path(
        "internal/whatsapp/templates/delete",
        whatsapp_internal.templates_delete,
        name="internal_whatsapp_templates_delete",
    ),
    # The proposed doors 10–12 of connecting a number (whatsapp/WORKBOOK.md «Contrato con el Hub»).
    path("internal/whatsapp/config", whatsapp_internal.config, name="internal_whatsapp_config"),
    path("internal/whatsapp/connect", whatsapp_internal.connect, name="internal_whatsapp_connect"),
    path("internal/whatsapp/disconnect", whatsapp_internal.disconnect, name="internal_whatsapp_disconnect"),
    # Stripe's single webhook (PLAN-SAAS §4): signed by Stripe, no session nor CSRF.
    path("webhooks/stripe/", billing_webhooks.stripe_webhook, name="stripe_webhook"),
    # Meta's single WhatsApp webhook (whatsapp/webhooks.py): its verification (GET) and its signed notices.
    path("webhooks/whatsapp/", whatsapp_webhooks.whatsapp_webhook, name="whatsapp_webhook"),
    # A customer's attachment opened from the Hub's inbox, with the person's session (whatsapp/media.py).
    path("whatsapp/media/<str:delivery_id>", whatsapp_media.media, name="whatsapp_media"),
    # Where Meta's window (Embedded Signup) brings its code back, handed to the Hub's page that opened it
    # (whatsapp/signup_return.py): public, its own Cross-Origin-Opener-Policy.
    path("whatsapp/return", whatsapp_signup_return.signup_return, name="whatsapp_signup_return"),
    # Before the API's prefix, which would otherwise answer it.
    path("api/live", live_stream, name="live-stream"),
    path("api/", api.urls),
    path("csp-report/", csp_report, name="csp-report"),
    path("readyz", readyz, name="readyz"),
    # The admin's «Hubs» page (ronda 13): before the admin's own URLs, whose catch-all would take it.
    path(
        "admin/accounts/hubs/",
        admin.site.admin_view(accounts_admin.hubs_view),
        name="accounts_hubs",
    ),
    path("admin/", admin.site.urls),
    # The public web (public/urls.py, namespace `public`) and its cookie consent, whose third-party
    # URL names have no namespace (its templates reverse them so).
    path("cookies/", include("cookie_consent.urls")),
    path("", include("public.urls")),
    # `home` is the project-wide name of `/` (the public web's navbar, footer and error pages): the landing,
    # `public:home`, answers `/` from the include above, so this line only names it (plan §3.c).
    path("", landing.home, name="home"),
    re_path(spa_path_pattern(NON_SPA_PREFIXES), spa, name="spa"),
]

# The site's error pages are the public web's (public/errors.py), with its CSP.
handler404 = "public.errors.page_not_found"
handler500 = "public.errors.server_error"
