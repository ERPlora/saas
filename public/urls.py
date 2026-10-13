"""Routes of the public web (namespace ``public``), mounted at the root by ``config/urls.py`` before
the SPA's catch-all, and the first segments it owns (``PUBLIC_PREFIXES``, which the project keeps
out of the SPA). Each batch of the port adds its pages here (PLAN-SAAS §6, «Rutas con vistas»).

django-cookie-consent's routes (``/cookies/``) are mounted by ``config/urls.py`` itself: under
this namespace its names would become ``public:cookie_consent_*`` and break the ``{% url %}`` of the
package's own templates.
"""

from django.urls import path, re_path
from django.views.generic import RedirectView

from public import indexnow, language, seo, sitemaps
from public import declaracion, legal
from public import store
from public import industries
from public import appdist, company, product, resources
from public import help as help_center
from public import landing, pricing

app_name = "public"

#: First segments of the public web: the ones it serves, those a later batch of the port will
#: serve, and the retired ones that must answer 404, never the SPA's shell (`developers`, `bridge`,
#: `compliance`; spec §8.3). `help` is the public help (`/help/`): the panel has no help page of its
#: own (in-app help is out of scope, spec §12). An unknown path under one of them is a 404 of the
#: public web (public/errors.py).
PUBLIC_PREFIXES = (
    "set-language",
    "robots.txt",
    "llms.txt",
    "sitemap.xml",
    "cookies",
    "legal",
    "pricing",
    "industries",
    "apps",
    "app",
    "about",
    "company",
    "collaborate",
    "blog",
    "careers",
    "press",
    "features",
    "security",
    "updates",
    "documentation",
    "support",
    "help",
    "contact",
    "download",
    "marketplace",
    "solutions",
    "modules",
    "developers",
    "bridge",
    "compliance",
)

urlpatterns = [
    path("set-language/", language.set_language, name="set_language"),
    path("robots.txt", seo.robots_txt, name="robots_txt"),
    path("llms.txt", seo.llms_txt, name="llms_txt"),
    path("sitemap.xml", sitemaps.sitemap_xml, name="sitemap"),
    # IndexNow's key file (8 to 128 of [A-Za-z0-9-], its protocol), after robots.txt and llms.txt.
    re_path(
        r"^(?P<requested_key>[A-Za-z0-9-]{8,128})\.txt$",
        indexnow.key_file,
        name="indexnow_key",
    ),
    # Pages without data (L3a): product, company, resources and help.
    path("features/", product.features, name="features"),
    path("security/", product.security, name="security"),
    path("updates/", product.updates, name="updates"),
    path("about/", company.about, name="about"),
    # No longer linked, but external and cached links still point there (issue #547).
    path(
        "company/",
        RedirectView.as_view(pattern_name="public:about", permanent=True),
        name="company",
    ),
    path("blog/", company.blog, name="blog"),
    path("careers/", company.careers, name="careers"),
    path("press/", company.press, name="press"),
    # It reads Plan and the taxonomy (L7).
    path("collaborate/", company.collaborate, name="collaborate"),
    path("documentation/", resources.documentation, name="documentation"),
    path("support/", resources.support, name="support"),
    path("help/", help_center.help_center, name="help"),
    # The installable app (L3a): its page, its only download door and the ways to try ERPlora.
    path("app/", appdist.index, name="app"),
    path("app/download/<str:platform>/", appdist.download, name="app_download"),
    path("download/", appdist.ways_to_try, name="downloads"),
    # Legal pages (L3b; the terms, which read Plan, L7).
    path("legal/privacy/", legal.privacy, name="privacy"),
    path("legal/terms/", legal.terms, name="terms"),
    path("legal/cookies/", legal.cookies, name="cookies"),
    path("legal/legal-notice/", legal.legal_notice, name="legal_notice"),
    # Art. 13.2/13.3 RRSIF: the declaración responsable and the archive of every version. The route
    # carries the Spanish legal term on purpose: it is what the customer, the reseller or the AEAT
    # look up.
    path(
        "legal/declaracion-responsable/",
        declaracion.declaracion_responsable,
        name="declaracion_responsable",
    ),
    path(
        "legal/declaracion-responsable/<str:version>/",
        declaracion.declaracion_responsable,
        name="declaracion_responsable_version",
    ),
    # The SIGNED copy, byte for byte: inline by default, `?download=1` to save it.
    path(
        "legal/declaracion-responsable/<str:version>/pdf/",
        declaracion.declaracion_responsable_pdf,
        name="declaracion_responsable_pdf",
    ),
    # The app store (L6, decision 19): each tab is its own URL. An app id is its label in the Hub.
    path("apps/", store.store, name="store"),
    path("apps/<slug:app_id>/", store.store_detail, name="store_detail"),
    path("apps/<slug:app_id>/docs/", store.store_docs, name="store_docs"),
    # Its old addresses, already indexed: 301 (the marketplace's keep their query).
    path("marketplace/", store.marketplace, name="marketplace"),
    path("marketplace/<slug:app_id>/", store.marketplace, name="marketplace_detail"),
    path("solutions/", store.to_store, name="solutions"),
    path("solutions/<slug:slug>/", store.to_store, name="solutions_detail"),
    path("modules/", store.to_store, name="modules"),
    # The business types (L4): their list and one page each, by code (a retired code answers 301).
    path("industries/", industries.index, name="industries_index"),
    path("industries/<slug:slug>/", industries.detail, name="industries_detail"),
    # The pages that read Plan (L7): the home (`/`, no longer a redirect to the launcher), the
    # contact page and its form, the plans on sale and one page per plan.
    path("", landing.home, name="home"),
    path("contact/", landing.contact, name="contact"),
    path("contact/submit/", landing.contact_submit, name="contact_submit"),
    path("pricing/", pricing.index, name="pricing"),
    path("pricing/<slug:slug>/", pricing.detail, name="pricing_detail"),
]
