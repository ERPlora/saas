"""ASGI entry point of saas-next: the ``application`` that Daphne serves.

``ignore_root_path`` wraps it because Daphne trusts its client's own ``Daphne-Root-Path`` header:
it copies it into ``scope["root_path"]``, which Django takes as the script prefix, stripped from the
path it resolves and put in front of every URL it builds. The project is served at the root of its
host, so that prefix is always empty and a request is answered for its real path (ERPlora/saas#2).

``refuse_websockets`` wraps that: erplora.com serves no WebSocket (no channels, PLAN-SAAS §1.1; the Hub's
``/ws/print`` is the Hub's). Django's handler raises on a non-HTTP scope, an error in the log on every attempt; the
handshake is refused instead (``websocket.close``, which Daphne answers with 403), as the old SaaS's catch-all
``DenyConsumer`` did (ACCOUNTS-G72).

https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from live.asgi import ignore_root_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


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
