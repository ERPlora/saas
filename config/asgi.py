"""ASGI entry point of saas-next: the ``application`` that Daphne serves.

``ignore_root_path`` wraps it because Daphne trusts its client's own ``Daphne-Root-Path`` header:
it copies it into ``scope["root_path"]``, which Django takes as the script prefix, stripped from the
path it resolves and put in front of every URL it builds. The project is served at the root of its
host, so that prefix is always empty and a request is answered for its real path (ERPlora/saas#2).

``refuse_websockets`` wraps that: erplora.com serves no WebSocket (no channels, PLAN-SAAS §1.1; the Hub's
``/ws/print`` is the Hub's). Django's handler raises on a non-HTTP scope, an error in the log on every attempt; the
handshake is refused instead (``websocket.close``, which Daphne answers with 403), as the old SaaS's catch-all
``DenyConsumer`` did (ACCOUNTS-G72).

``BodiesInMemory`` is Django's handler with one change: the body of the assistant's doors of the Hub
(``/internal/assistant/*``, ``/internal/speech/*``) stays in memory. Django reads every body into a file that moves
to disk past ``FILE_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB), before any view; a turn with its attachments or a dictation is
larger, and those documents and that audio never touch the disk (ASSISTANT-F19, F21). Up to
``assistant.internal.TURN_BODY_BYTES``; what passes it, or a declared length over it, is received and dropped, never
kept, and the door answers 413. Those doors are not published on the ALB: only the Hub reaches them.

https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import contextvars
import io
import os

import django
from django.core.exceptions import RequestAborted
from django.core.handlers.asgi import ASGIHandler
from live.asgi import ignore_root_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

#: The paths whose body stays in memory (assistant.internal).
IN_MEMORY_PATHS = ("/internal/assistant/", "/internal/speech/")
#: The ceiling of the request in hand when its body stays in memory (``None``: Django's own reading).
_in_memory_ceiling: contextvars.ContextVar[int | None] = contextvars.ContextVar("in_memory_ceiling", default=None)


def body_ceiling(scope: dict) -> int | None:
    """How much of the body of ``scope`` stays in memory: ``None`` for Django's own reading (every other path), the
    turn's ceiling for the assistant's doors, and nothing when their declared length is already over it."""
    if not scope["path"].startswith(IN_MEMORY_PATHS):
        return None
    from assistant.internal import TURN_BODY_BYTES

    declared = dict(scope.get("headers") or []).get(b"content-length", b"")
    return 0 if declared.isdigit() and int(declared) > TURN_BODY_BYTES else TURN_BODY_BYTES


class BodiesInMemory(ASGIHandler):
    """Django's ASGI handler, keeping in memory the body of ``IN_MEMORY_PATHS``."""

    async def handle(self, scope, receive, send):
        token = _in_memory_ceiling.set(body_ceiling(scope))
        try:
            await super().handle(scope, receive, send)
        finally:
            _in_memory_ceiling.reset(token)

    async def read_body(self, receive):
        """The body in memory, at most one byte over its ceiling (so the door sees it is too big); the rest is
        received and dropped, as every message of the body must be read before the response."""
        ceiling = _in_memory_ceiling.get()
        if ceiling is None:
            return await super().read_body(receive)
        body = io.BytesIO()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise RequestAborted()
            room = ceiling + 1 - body.tell()
            if room > 0:
                body.write(message.get("body", b"")[:room])
            if not message.get("more_body", False):
                break
        body.seek(0)
        return body


def get_asgi_application() -> BodiesInMemory:
    """``django.core.asgi.get_asgi_application`` with ``BodiesInMemory``."""
    django.setup(set_prefix=False)
    return BodiesInMemory()


def refuse_websockets(app):
    """``app`` for HTTP; every WebSocket handshake refused (policy violation, 1008) without reaching Django."""

    async def application(scope, receive, send):
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        await app(scope, receive, send)

    return application


application = refuse_websockets(ignore_root_path(get_asgi_application()))
