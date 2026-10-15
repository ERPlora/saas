"""The site's 404 and 500 pages (``handler404``/``handler500``).

Ported from ERPlora/saas ``apps/dashboard/core/views.py`` (``custom_404_handler``,
``custom_500_handler``) and ``apps/dashboard/core/tests/test_error_page_db_connection.py``
(origin/develop c5ca8ca). Each half keeps its own look: the public web answers its templates
(``public/404.html``, ``public/500.html``) and the private half (sign-in, the jump to a hub, the
panel, the API) Django's default pages (``templates/404.html``, ``templates/500.html``, with the
error layout of the sign-in pages; ``base/tests/test_error_pages.py``). These tests stand in a
minimal set of templates so they fix the views, not the markup.
"""

import json
import threading
from unittest.mock import patch

import pytest
from django.db import connections, transaction
from django.template import TemplateSyntaxError

from config import urls as project_urls
from public import errors

HOST = "localhost:8001"
# A template that reads the database, as the navbar does for the signed-in person.
TEMPLATES = {
    "public/404.html": "{% if perms.accounts %}{% endif %}not-found:{{ request.path }}",
    "public/500.html": "{% if perms.accounts %}{% endif %}server-error",
    "404.html": "private-not-found",
    "500.html": "private-server-error",
}


@pytest.fixture
def error_templates(settings):
    """The real loaders behind a locmem one holding the two pages."""
    engine = dict(settings.TEMPLATES[0])
    options = dict(engine["OPTIONS"])
    options["loaders"] = [
        ("django.template.loaders.locmem.Loader", TEMPLATES),
        "django.template.loaders.filesystem.Loader",
        "django.template.loaders.app_directories.Loader",
    ]
    engine.update(APP_DIRS=False, OPTIONS=options)
    settings.TEMPLATES = [engine]


def test_the_project_uses_the_public_error_pages():
    assert project_urls.handler404 == "public.errors.page_not_found"
    assert project_urls.handler500 == "public.errors.server_error"


@pytest.mark.django_db
@pytest.mark.usefixtures("error_templates")
def test_an_unknown_page_answers_the_public_404(client, settings):
    settings.DEBUG = False

    response = client.get("/pricing/nope/", HTTP_HOST=HOST)

    assert response.status_code == 404
    assert response.content.decode() == "not-found:/pricing/nope/"


@pytest.mark.django_db
@pytest.mark.usefixtures("error_templates")
@pytest.mark.parametrize(
    "path", ["/accounts/nope/", "/hub-login/nope", "/auth/nope", "/static/nope.js", "/csp-report/x", "/internal/nope"]
)
def test_an_unknown_page_outside_the_public_web_answers_djangos_404(client, settings, path):
    """Django's own prefixes (sign-in, the jump to a hub, static files, CSP reports…)."""
    settings.DEBUG = False

    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 404
    assert response.content.decode() == "private-not-found"


@pytest.mark.django_db
@pytest.mark.usefixtures("error_templates")
@pytest.mark.parametrize("path", ["/launch", "/admin/", "/hub-login/"])
def test_a_server_error_of_the_private_half_answers_djangos_500(rf, path):
    response = errors.server_error(rf.get(path))

    assert response.status_code == 500
    assert response.content.decode() == "private-server-error"


@pytest.mark.django_db
@pytest.mark.usefixtures("error_templates")
def test_a_server_error_of_a_spa_page_answers_djangos_500(rf):
    """A page of the SPA (any path its catch-all resolves) is the panel: the private half."""
    from django.urls import resolve

    request = rf.get("/a-panel-page")
    request.resolver_match = resolve("/a-panel-page")

    assert errors.server_error(request).content.decode() == "private-server-error"


@pytest.mark.django_db
@pytest.mark.usefixtures("error_templates")
def test_a_server_error_answers_the_public_500(rf, ana):
    request = rf.get("/pricing/")
    request.user = ana

    response = errors.server_error(request)

    assert response.status_code == 500
    assert response.content.decode() == "server-error"


@pytest.mark.django_db
def test_an_api_server_error_answers_the_json_envelope(rf):
    request = rf.get("/api/me")

    response = errors.server_error(request)

    assert response.status_code == 500
    assert json.loads(response.content) == {
        "error": {"code": "internal_error", "message": "Internal error"}
    }


@pytest.mark.django_db
def test_a_500_page_that_fails_to_render_still_answers_and_says_why(rf, caplog):
    """A broken 500 page must not turn into the server's bare error: a minimal page, and the
    failure in the log."""
    request = rf.get("/pricing/")

    with patch.object(errors, "render", side_effect=TemplateSyntaxError("broken")):
        response = errors.server_error(request)

    assert response.status_code == 500
    assert "<html" in response.content.decode()
    assert any(
        "broken" in (record.exc_text or "") or record.exc_info
        for record in caplog.records
    )


@pytest.mark.django_db
def test_the_minimal_500_speaks_the_visitors_language(rf):
    from django.utils import translation

    with translation.override("es"), patch.object(errors, "render", side_effect=TemplateSyntaxError("broken")):
        html = errors.server_error(rf.get("/pricing/")).content.decode()

    assert '<html lang="es">' in html
    assert "Algo ha fallado por nuestra parte" in html


# An error page rendered off the request thread must not reuse nor leak a database connection
# (saas#2244). Under ASGI (daphne) Django renders it with `sync_to_async(response_for_exception,
# thread_sensitive=False)`, in a pooled worker thread the request signals never reach: a connection
# opened there was never closed (with Django's pool, a slot held forever) and, once the server
# dropped it while idle, the next error page on that thread died with «connection already closed».


def _in_a_worker_thread(scenario):
    """Run ``scenario`` in a fresh thread, like ``sync_to_async(..., thread_sensitive=False)``."""
    outcome = {}

    def run():
        connection = connections["default"]
        try:
            outcome["value"] = scenario(connection)
        except Exception as exc:  # reported by the assertion below, with its type
            outcome["error"] = exc
        finally:
            connection.close()

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    assert "error" not in outcome, f"the error page raised {outcome['error']!r}"
    return outcome["value"]


def _signed_in_request(rf, user, path):
    request = rf.get(path)
    request.user = user
    return request


def _kill(connection):
    """What an idle timeout does to the socket: the wrapper still believes it is open."""
    connection.ensure_connection()
    connection.connection.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("error_templates")
@pytest.mark.parametrize(
    ("handler", "status"),
    [
        (lambda request: errors.page_not_found(request, exception=None), 404),
        (errors.server_error, 500),
    ],
    ids=["404", "500"],
)
def test_the_error_page_survives_a_connection_that_died_while_idle(
    rf, ana, handler, status
):
    def scenario(connection):
        _kill(connection)
        return handler(_signed_in_request(rf, ana, "/pricing/nope/")).status_code

    assert _in_a_worker_thread(scenario) == status


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("error_templates")
def test_the_error_page_does_not_keep_its_connection(rf, ana):
    def scenario(connection):
        errors.page_not_found(
            _signed_in_request(rf, ana, "/pricing/nope/"), exception=None
        )
        return connection.connection is None

    assert _in_a_worker_thread(scenario), (
        "the worker thread kept its database connection"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("error_templates")
def test_the_error_page_does_query_the_database(rf, ana):
    """Without this, the test above would pass on a page that never opened a connection."""

    def scenario(connection):
        with patch.object(errors, "_release_stale_connections"):
            errors.page_not_found(
                _signed_in_request(rf, ana, "/pricing/nope/"), exception=None
            )
        return connection.connection is not None

    assert _in_a_worker_thread(scenario)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("error_templates")
def test_an_error_page_inside_a_transaction_keeps_its_connection(rf, ana):
    """The sync path renders in the request's own thread: its transaction must not be cut."""

    def scenario(connection):
        with transaction.atomic():
            response = errors.page_not_found(
                _signed_in_request(rf, ana, "/nope/"), exception=None
            )
            still_open = connection.connection is not None
        return response.status_code, still_open

    assert _in_a_worker_thread(scenario) == (404, True)
