"""Meta's webhook, ``/webhooks/whatsapp/`` (WHATSAPP-G13, WHATSAPP-G07): Meta's only address for every business.

- ``GET``: Meta proves the address is ours (``hub.mode=subscribe``, ``hub.verify_token``, ``hub.challenge``) when it
  is set in Meta's app. The token is compared in constant time; without ``WHATSAPP_VERIFY_TOKEN`` the answer is 503
  ``whatsapp.not_configured`` (an empty token never matches, #971 of the old product); another token or mode, 403.
- ``POST``: a notice, signed by Meta with the app's secret (``X-Hub-Signature-256: sha256=<hex HMAC-SHA256 of the
  raw body>``). Without ``WHATSAPP_APP_SECRET``, 503 ``whatsapp.not_configured``; unsigned or badly signed, 403;
  signed but not JSON, 400; more than ``WHATSAPP_WEBHOOK_MAX_BYTES``, 413, decided by its declared length before
  it is read. A signed notice is parked and pushed to the Hub (``gateway.ingest``) and answered 200: Meta delivers
  at least once and out of order, and parking is idempotent. A database failure answers 500 and Meta sends it again.

No throttle counts anything before the signature (saas#2571, saas#2531): the old one spent a budget of 200 posts a
minute per address on forged posts too, and refused Meta's own at a busy hour. Server to server: no session nor
CSRF token.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from whatsapp import gateway

logger = logging.getLogger(__name__)
SIGNATURE_HEADER = "X-Hub-Signature-256"


def _error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _not_configured(what: str) -> JsonResponse:
    logger.error("whatsapp.webhook.not_configured missing=%s", what)
    return _error(503, "whatsapp.not_configured", f"WhatsApp is not configured here ({what} is not set).")


@csrf_exempt
@never_cache
def whatsapp_webhook(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _verify(request)
    if request.method != "POST":
        response = _error(405, "method_not_allowed", "Only GET and POST are allowed.")
        response["Allow"] = "GET, POST"
        return response
    return _notice(request)


def _verify(request: HttpRequest) -> HttpResponse:
    expected = str(settings.WHATSAPP_VERIFY_TOKEN or "")
    if not expected:
        return _not_configured("WHATSAPP_VERIFY_TOKEN")
    given = request.GET.get("hub.verify_token", "")
    if request.GET.get("hub.mode") != "subscribe" or not hmac.compare_digest(given.encode(), expected.encode()):
        logger.warning("whatsapp.webhook.verification_refused")
        return HttpResponse(status=403)
    return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain; charset=utf-8")


def _notice(request: HttpRequest) -> HttpResponse:
    secret = str(settings.WHATSAPP_APP_SECRET or "")
    if not secret:
        return _not_configured("WHATSAPP_APP_SECRET")
    limit = settings.WHATSAPP_WEBHOOK_MAX_BYTES
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > limit:
        return _error(413, "payload_too_large", f"The body exceeds {limit} bytes.")
    raw = request.read(limit + 1)
    if len(raw) > limit:
        return _error(413, "payload_too_large", f"The body exceeds {limit} bytes.")
    if not _signed_by_meta(raw, request.headers.get(SIGNATURE_HEADER, ""), secret):
        logger.warning("whatsapp.webhook.bad_signature")
        return HttpResponse(status=403)
    try:
        payload = json.loads(raw)
    except ValueError:
        return _error(400, "invalid_payload", "The body is not JSON.")
    out = gateway.ingest(payload)
    logger.info(
        "whatsapp.webhook parked=%s statuses=%s verdicts=%s discarded=%s",
        out.parked,
        out.statuses,
        out.verdicts,
        out.discarded,
    )
    return JsonResponse({"received": True})


def _signed_by_meta(raw: bytes, header: str, secret: str) -> bool:
    scheme, _, given = header.partition("=")
    if scheme != "sha256" or not given:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(given.strip().lower().encode(), expected.encode())
