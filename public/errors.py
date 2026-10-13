"""The site's 404 and 500 pages (``handler404``/``handler500`` in ``config/urls.py``).

Ported from ERPlora/saas ``apps/dashboard/core/views.py`` (origin/develop c5ca8ca). Each side keeps
its own look: a request of the public web (resolved to it, or an unknown path under one of its
first segments, ``public.urls.PUBLIC_PREFIXES``) gets its templates (``public/404.html``,
``public/500.html``); everything else (sign-in, the jump to a hub, the admin, static files, the
SPA's panel) Django's default pages, ``templates/404.html`` and ``templates/500.html`` with the
error layout of the sign-in pages. An API path that reaches the
500 handler answers the JSON envelope of ``live`` instead (saas#895); its 404 is already enveloped
by ``live.api_errors.ApiErrorEnvelopeMiddleware``.

Under ASGI (daphne) Django renders an error page with ``sync_to_async(response_for_exception,
thread_sensitive=False)``, in a pooled worker thread the request signals never reach. A connection
opened there (the templates read the signed-in person) was never released: with Django's pool, a
slot held forever, and once the server dropped it while idle the next error page on that thread
died with «connection already closed», a 500 where a 404 belonged (saas#2244). So each handler
releases a stale connection before rendering and its own afterwards.
"""

from __future__ import annotations

import functools
import logging
import time

from django.conf import settings
from django.db import connections
from django.http import HttpRequest, HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import render
from django.utils.html import format_html
from django.utils.translation import get_language, gettext
from django.views import defaults
from live.errors import OperationError

from public.csp import is_public
from public.urls import PUBLIC_PREFIXES

logger = logging.getLogger(__name__)

#: What a 500 answers when its own page fails to render: no template, no context, no database.
FALLBACK_500_HTML = (
    '<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8"><title>ERPlora</title></head>'
    "<body><h1>{title}</h1><p>{message}</p></body></html>"
)


def _is_public_web(request: HttpRequest) -> bool:
    """Whether the failed request belongs to the public web."""
    if getattr(request, "resolver_match", None) is not None:
        return is_public(request)
    return request.path.lstrip("/").split("/", 1)[0] in PUBLIC_PREFIXES


def _release_stale_connections() -> None:
    """Close every open connection of this thread that is past its age or has failed.

    The part of ``close_if_unusable_or_obsolete`` that matters here, without its probe (it would
    open a socket just to look at it). A connection inside a transaction is left alone: on the sync
    path the page renders in the request's own thread, and cutting its transaction would break the
    request. With Django's pool (``CONN_MAX_AGE = 0``) closing returns the connection to the pool.
    """
    for connection in connections.all(initialized_only=True):
        if connection.connection is None or connection.in_atomic_block:
            continue
        expired = (
            connection.close_at is not None and time.monotonic() >= connection.close_at
        )
        if expired or connection.errors_occurred:
            connection.close()
        else:
            # A persistent connection stays, but CONN_HEALTH_CHECKS re-checks it before reuse.
            connection.health_check_done = False


def _own_db_connection_lifecycle(handler):
    """Give an error page the connection lifecycle its thread does not have (saas#2244)."""

    @functools.wraps(handler)
    def wrapper(*args, **kwargs):
        _release_stale_connections()
        try:
            return handler(*args, **kwargs)
        finally:
            _release_stale_connections()

    return wrapper


@_own_db_connection_lifecycle
def page_not_found(
    request: HttpRequest, exception: Exception | None = None
) -> HttpResponse:
    if not _is_public_web(request):
        return defaults.page_not_found(request, exception)
    return render(request, "public/404.html", status=404)


@_own_db_connection_lifecycle
def server_error(request: HttpRequest) -> HttpResponse:
    if request.path.startswith("/api/"):
        envelope = OperationError(
            gettext("Internal error"), code="internal_error", status=500
        ).envelope()
        return JsonResponse(envelope, status=500)
    if not _is_public_web(request):
        return defaults.server_error(request)
    try:
        return render(request, "public/500.html", status=500)
    except Exception:
        # The page that reports a failure failed too: answer something, and say why in the log.
        logger.exception(
            "public.errors: the 500 page failed to render for %s", request.path
        )
        return HttpResponseServerError(
            format_html(
                FALLBACK_500_HTML,
                lang=get_language() or settings.LANGUAGE_CODE,
                title=gettext("Server error"),
                message=gettext("Something went wrong on our side. Please try again in a few minutes."),
            )
        )
