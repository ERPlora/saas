"""erplora.com's calls to the Hub's WhatsApp doors 1 and 2 (``hub/apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con
el SaaS»): ``POST /internal/whatsapp/inbound`` (a message Meta reported) and ``POST /internal/whatsapp/status`` (the
delivery status of a message the Hub sent).

Plain HTTP, no ORM: ``gateway.deliver`` hands in the bodies and records the answers. Signed as every call of the
SaaS to the Hub (``hubs.hub_client.signed_headers``: v1 over the body, v2 over method, path and body), to
``HUB_INTERNAL_URL``. Any answer is returned (``Answer``): the caller decides that a 200 is delivered, a 422 is not
worth retrying and anything else is retried; no answer at all raises ``Unreachable``. 5 s at most: it runs after the
COMMIT of Meta's webhook, which waits for it.
"""

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from hubs.hub_client import signed_headers

INBOUND_PATH = "/internal/whatsapp/inbound"
STATUS_PATH = "/internal/whatsapp/status"
TIMEOUT = httpx.Timeout(5.0)


class Unreachable(Exception):
    """The Hub did not answer (no connection, a timeout)."""


@dataclass(frozen=True)
class Answer:
    status: int
    body: Any


def post_inbound(body: dict) -> Answer:
    return _post(INBOUND_PATH, body)


def post_status(body: dict) -> Answer:
    return _post(STATUS_PATH, body)


def _post(path: str, payload: dict) -> Answer:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    headers = signed_headers("POST", path, raw, int(time.time()))
    try:
        response = httpx.post(
            settings.HUB_INTERNAL_URL.rstrip("/") + path, content=raw, headers=headers, timeout=TIMEOUT
        )
    except httpx.HTTPError as error:
        raise Unreachable(f"POST {path}: {type(error).__name__}") from None
    try:
        body = response.json()
    except ValueError:
        body = {}
    return Answer(response.status_code, body)
