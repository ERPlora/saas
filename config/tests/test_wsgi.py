"""ACCOUNTS-G72: ``config.wsgi`` builds Django's WSGI application (``WSGI_APPLICATION``); production serves ASGI
(Daphne, ``config.asgi``), and any WSGI server given this module answers the same project."""

import pytest
from django.core.handlers.wsgi import WSGIHandler

from config.wsgi import application


def test_it_is_djangos_wsgi_handler_for_this_project():
    assert isinstance(application, WSGIHandler)


@pytest.mark.django_db
def test_it_answers_the_health_check():
    sent = {}

    def start_response(status, headers):
        sent["status"] = status
        sent["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/healthz",
        "SERVER_NAME": "10.0.0.7",
        "SERVER_PORT": "8001",
        "wsgi.url_scheme": "http",
        "wsgi.input": __import__("io").BytesIO(b""),
        "wsgi.errors": __import__("sys").stderr,
    }
    body = b"".join(application(environ, start_response))

    assert sent["status"].startswith("200")
    assert b'"status": "ok"' in body
