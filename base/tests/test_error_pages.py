"""The error pages Django and allauth render by name are ours: ``templates/<code>.html``, each
extending ``errors/base.html``. Ported from ERPlora/saas (origin/develop) without OutfitKit: plain
HTML and our CSS, a way home and a way to support, in English and Spanish.

- ``400.html``: ``django.views.defaults.bad_request`` (a SuspiciousOperation).
- ``403.html``: ``django.views.defaults.permission_denied``: the admin for a signed-in account that
  is not staff, or its «Hubs» page without the permission (``accounts/admin.py``).
- ``403_csrf.html``: ``django.views.csrf.csrf_failure``: a form posted with an expired session.
- ``404.html`` and ``500.html``: ``django.views.defaults.page_not_found`` and ``server_error``, which
  the project's ``handler404``/``handler500`` (``public.errors``) call for every path outside the
  public web (sign-in, the jump to a hub, the admin, static files, the SPA's panel); the public web
  keeps its own ``public/404.html`` and ``public/500.html``.
- ``429.html``: allauth's rate limit of the sign-in (``allauth/core/internal/ratelimit.py``).

Django renders the 500 with an empty context (no request, no context processors) and must not
touch the database to do it: those tests have no ``django_db`` mark, so a query would fail them.
"""

import html as html_lib
import json

import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.template import loader
from django.test import Client, RequestFactory
from django.urls import path
from django.utils import translation
from django.views import defaults

from accounts.tests.test_templates import assert_no_outfitkit, assert_tokens_defined
from config import urls as project_urls
from public import errors
from public.templatetags.public_assets import PUBLIC_ENTRY

#: template → (status, English heading, Spanish heading).
PAGES = {
    "400.html": (400, "We couldn't read that request", "No hemos podido leer esa solicitud"),
    "403.html": (403, "You don't have access to this", "No tienes acceso a esto"),
    "403_csrf.html": (403, "Your session expired while you were away", "Tu sesión ha caducado mientras no estabas"),
    "404.html": (404, "We couldn't find this page", "No hemos podido encontrar esta página"),
    "429.html": (429, "Slow down for a moment", "Espera un momento"),
    "500.html": (500, "Something went wrong on our end", "Algo ha ido mal por nuestra parte"),
}


def boom(request):
    raise RuntimeError("a view of the private half that fails")


#: The project's URLconf plus a failing view under a Django prefix of the private half, for the
#: tests that go through the real 500 handler (``@pytest.mark.urls``).
urlpatterns = [path("accounts/boom/", boom), *project_urls.urlpatterns]
handler404 = project_urls.handler404
handler500 = project_urls.handler500


@pytest.fixture
def production(settings):
    """DEBUG off, as in production: Django shows the error templates instead of its debug pages."""
    settings.DEBUG = False


def text(response) -> str:
    return html_lib.unescape(response.content.decode())


def render(name: str, language: str = "en"):
    """The response of the handler that renders ``name``, as Django or allauth call it."""
    from allauth.core.internal.ratelimit import handler429
    from django.views.csrf import csrf_failure

    request = RequestFactory().get("/somewhere/")
    handlers = {
        "400.html": lambda: defaults.bad_request(request, SuspiciousOperation()),
        "403.html": lambda: defaults.permission_denied(request, PermissionDenied()),
        "403_csrf.html": lambda: csrf_failure(request, reason="CSRF cookie not set."),
        "404.html": lambda: defaults.page_not_found(request, Http404()),
        "429.html": lambda: handler429(request),
        "500.html": lambda: defaults.server_error(request),
    }
    with translation.override(language):
        return handlers[name]()


@pytest.mark.parametrize("name", PAGES)
def test_each_error_page_is_ours_and_extends_the_error_layout(name):
    status, heading, _ = PAGES[name]

    response = render(name)

    page = text(response)
    assert response.status_code == status
    assert '<main class="error-page">' in page
    assert f"<h1>{heading}</h1>" in page
    assert '<a href="/">Home</a>' in page
    assert f'<a href="mailto:{settings.SUPPORT_EMAIL}">Contact Support</a>' in page
    assert "ERPlora Cloud</title>" in page
    assert '<html lang="en"' in page


@pytest.mark.parametrize("name", PAGES)
def test_each_error_page_is_translated_to_spanish(name):
    _, _, heading = PAGES[name]

    page = text(render(name, "es"))

    assert f"<h1>{heading}</h1>" in page
    assert '<a href="/">Inicio</a>' in page
    assert '<html lang="es"' in page


@pytest.mark.parametrize("name", PAGES)
def test_each_error_page_paints_without_outfitkit(name):
    page = render(name).content.decode()

    assert_no_outfitkit(page)
    assert_tokens_defined(page)


def test_the_rate_limit_page_leads_back_to_the_sign_in():
    assert '<a href="/launch">Back to sign in</a>' in text(render("429.html"))


@pytest.mark.django_db
def test_a_form_posted_with_an_expired_session_shows_our_csrf_page(production):
    response = Client(enforce_csrf_checks=True).post("/set-language/", {"language": "es", "next": "/"})

    assert response.status_code == 403
    assert "<h1>Your session expired while you were away</h1>" in text(response)


@pytest.mark.django_db
def test_staff_without_the_permission_gets_our_403_on_the_hubs_page(client, django_user_model, production):
    staff = django_user_model.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    client.force_login(staff)

    response = client.get("/admin/accounts/hubs/", headers={"Accept-Language": "es"})

    assert response.status_code == 403
    assert "403.html" in [template.name for template in response.templates]
    assert "<h1>No tienes acceso a esto</h1>" in text(response)


#: Paths of the private half under Django's own prefixes that resolve to nothing.
PRIVATE_MISSES = ["/accounts/does-not-exist/", "/hub-login/nope", "/static/nope.js"]


@pytest.mark.django_db
@pytest.mark.parametrize("missing", PRIVATE_MISSES)
def test_an_unknown_page_of_the_private_half_shows_our_404(client, production, missing):
    response = client.get(missing)

    page = text(response)
    assert response.status_code == 404
    assert "404.html" in [template.name for template in response.templates]
    assert '<main class="error-page">' in page
    assert "<title>404 — Page Not Found · ERPlora Cloud</title>" in page
    assert "<h1>We couldn't find this page</h1>" in page


@pytest.mark.django_db
def test_our_404_speaks_spanish(client, production):
    page = text(client.get("/accounts/does-not-exist/", headers={"Accept-Language": "es"}))

    assert '<main class="error-page">' in page
    assert "<title>404 — Página no encontrada · ERPlora Cloud</title>" in page
    assert "<h1>No hemos podido encontrar esta página</h1>" in page
    assert '<a href="/">Inicio</a>' in page


@pytest.fixture
def public_manifest(settings, tmp_path):
    """A Vite manifest with the public entry, so the public pages render whether or not
    ``pnpm build`` ran (as ``public/tests/conftest.py`` does)."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({PUBLIC_ENTRY: {"file": "assets/public.js", "src": PUBLIC_ENTRY, "isEntry": True}}))
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "manifest": manifest}}


@pytest.mark.django_db
@pytest.mark.usefixtures("public_manifest")
def test_an_unknown_page_of_the_public_web_keeps_the_public_404(client, production):
    response = client.get("/pricing/does-not-exist/")

    names = [template.name for template in response.templates]
    assert response.status_code == 404
    assert "public/404.html" in names
    assert "404.html" not in names
    assert '<main class="error-page">' not in text(response)


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_500_page_renders_with_an_empty_context_and_no_database(language):
    """As ``django.views.defaults.server_error`` does: ``template.render()``, no request at all."""
    with translation.override(language):
        page = html_lib.unescape(loader.get_template("500.html").render())

    title, heading = {
        "en": ("500 — Server Error", "Something went wrong on our end"),
        "es": ("500 — Error del servidor", "Algo ha ido mal por nuestra parte"),
    }[language]
    assert '<main class="error-page">' in page
    assert f"<title>{title} · ERPlora Cloud</title>" in page
    assert f"<h1>{heading}</h1>" in page
    assert f'<html lang="{language}"' in page


@pytest.mark.parametrize("failing", ["/admin/", "/hub-login/", "/launch"])
def test_the_project_500_handler_shows_ours_outside_the_public_web(failing):
    response = errors.server_error(RequestFactory().get(failing))

    page = text(response)
    assert response.status_code == 500
    assert '<main class="error-page">' in page
    assert "<h1>Something went wrong on our end</h1>" in page


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_view_of_the_private_half_that_fails_shows_our_500(production):
    response = Client(raise_request_exception=False).get("/accounts/boom/")

    page = text(response)
    assert response.status_code == 500
    assert '<main class="error-page">' in page
    assert "<h1>Something went wrong on our end</h1>" in page


@pytest.mark.parametrize("name", PAGES)
def test_contact_support_writes_to_the_support_address_of_the_settings(name, settings):
    """PUBLIC-F18: the same mailbox as the public web\'s footer and contact page, never a second one typed here."""
    settings.SUPPORT_EMAIL = "help@erplora.test"

    page = text(render(name))

    assert '<a href="mailto:help@erplora.test">Contact Support</a>' in page
    assert "info@erplora.com" not in page
