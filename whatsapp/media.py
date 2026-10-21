"""``GET /whatsapp/media/<id>``: a customer's photo, voice note, video or document, opened from the Hub's inbox
(WHATSAPP-G07; door 1 carries this address in ``media.url``).

The browser opens it with the person's erplora.com session (``<slug>.erplora.com`` and ``erplora.com`` are one
site, so the session travels); ``whatsapp.media.locate`` lets only an accepted member of the business through. The
bytes stream from Meta as they arrive and are never kept here nor cached. Everything is decided before the first
byte: Meta's answer about the attachment and the opening of its download.

What is not a picture, a sound or a video (a PDF, an HTML page a customer sent, an SVG that could run a script) is
never shown on erplora.com's origin: it is downloaded, sandboxed, with ``nosniff``.

Answers: 200 the bytes; 401 ``unauthorized`` without a session; 404 ``whatsapp.media_not_found`` (not this
person's business, not an attachment, or Meta no longer has it); 405; 409 ``whatsapp.not_connected`` (no connected
number, or Meta refused its permission: the number is marked «needs reconnecting»); 502
``whatsapp.media_unavailable`` (Meta not reached, failing, or pointing somewhere that is not Meta).
"""

import logging
from contextlib import ExitStack
from uuid import UUID

from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from live.errors import OperationError

from whatsapp import meta, queries, services
from whatsapp.schemas import MediaIn, ReconnectIn

logger = logging.getLogger(__name__)

#: Shown in the browser; anything else is downloaded. SVG is a picture that can run a script: downloaded.
INLINE_PREFIXES = ("image/", "audio/", "video/")
NEVER_INLINE = frozenset({"image/svg+xml"})
#: Kept as Meta names them; anything else travels as bytes with no meaning.
DOWNLOADED = frozenset({"application/pdf"})
CHUNK = 64 * 1024
#: Meta's error code of an expired or withdrawn permission.
EXPIRED_PERMISSION = 190


def _error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _unavailable() -> JsonResponse:
    return _error(502, "whatsapp.media_unavailable", "Meta could not hand over this attachment now. Try again later.")


class _Stream:
    """The download's bytes, and closing it when the response is closed (also if it was never read)."""

    def __init__(self, stack: ExitStack, upstream) -> None:
        self.stack, self.upstream = stack, upstream

    def __iter__(self):
        return self.upstream.iter_bytes(CHUNK)

    def close(self) -> None:
        self.stack.close()


def _content_type(mime: str) -> tuple[str, bool]:
    """The type served and whether it is shown in the browser."""
    clean = mime.split(";")[0].strip().lower()
    if clean.startswith(INLINE_PREFIXES) and clean not in NEVER_INLINE and "/" in clean and " " not in clean:
        return clean, True
    if clean in DOWNLOADED:
        return clean, False
    return "application/octet-stream", False


def _filename(name: str) -> str:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "._- ").strip()[:100]
    return safe or "attachment"


@never_cache
@require_GET
def media(request: HttpRequest, delivery_id: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return _error(401, "unauthorized", "Sign in to erplora.com to open this attachment.")
    try:
        key = UUID(delivery_id)
    except ValueError:
        return _error(404, "whatsapp.media_not_found", "This attachment is not available.")
    ctx = services.platform_context()
    try:
        found = queries.media_locate(ctx, MediaIn(delivery_id=key, user_id=request.user.pk))
    except OperationError as refused:
        return JsonResponse(refused.envelope(), status=refused.status)
    token = found.token.get_secret_value()
    try:
        info = meta.get(found.media_id, token=token)
    except meta.MetaRefused as refused:
        if refused.code == EXPIRED_PERMISSION:
            services.number_reconnect_needed(ctx, ReconnectIn(hub_id=found.hub_id))
            return _error(409, "whatsapp.not_connected", "WhatsApp needs connecting again to open attachments.")
        logger.info("whatsapp.media.refused meta_status=%s meta_code=%s", refused.status, refused.code)
        return _error(404, "whatsapp.media_not_found", "This attachment is not available.")
    except meta.MetaUnreachable:
        return _unavailable()
    stack = ExitStack()
    try:
        upstream = stack.enter_context(meta.download(str(info.get("url") or ""), token=token))
    except meta.MetaUnreachable as failure:
        stack.close()
        logger.warning("whatsapp.media.unavailable error=%s", failure)
        return _unavailable()
    served, inline = _content_type(str(info.get("mime_type") or found.mime_type))
    response = StreamingHttpResponse(_Stream(stack, upstream), content_type=served)
    size = info.get("file_size")
    if isinstance(size, int) and size >= 0:
        response["Content-Length"] = str(size)
    disposition = "inline" if inline else f'attachment; filename="{_filename(found.filename)}"'
    response["Content-Disposition"] = disposition
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response
