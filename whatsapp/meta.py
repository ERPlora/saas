"""erplora.com's client of Meta's Graph API (WHATSAPP-G06, WHATSAPP-G10).

Every call goes to ``https://graph.facebook.com/<WHATSAPP_GRAPH_VERSION>/…`` with the business token in the
``Authorization`` header (never in the address; only Meta's token exchange and ``debug_token`` carry the app's
credentials in it, as Meta documents them, and httpx's own request log is silenced in the settings). No call
follows a redirect. ``httpx`` (maintained since 2019, 100+ contributors): 5 s to connect, 15 s to read (30 s for
a send, the time Meta itself gives a message).

How a call ends:

- a JSON object: Meta's answer (``{}`` when a 2xx is not one: the caller decides what a missing field means);
- ``MetaRefused``: Meta answered 4xx; ``code``/``subcode``/``message``/``title``/``detail``/``user_message`` are
  Meta's error object, ``rate_limited`` whether it asks to slow down (HTTP 429 or its throttling codes);
- ``MetaUnreachable``: no usable answer. ``sent`` is whether the request may have reached Meta (a 5xx, a read
  timeout, a redirect) or certainly did not (no connection).

``upload_sample`` is Meta's Resumable Upload API, the only way a template's header with a photo, a video or a
document gets the ``header_handle`` its review needs: a session on OUR app (``POST /<WHATSAPP_APP_ID>/uploads`` with
the file's name, length and type, ``Bearer``), then the bytes to that session (``POST /<upload id>`` with
``Authorization: OAuth`` and ``file_offset: 0``), answered ``{"h": <handle>}``. The second address comes from Meta's
answer, so it is checked to name an upload session and nothing else of Graph before the token follows it.

No credential, no message text and no recipient is ever logged here.
"""

import contextlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.urls import reverse

TIMEOUT = httpx.Timeout(15.0, connect=5.0)
SEND_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
#: A header's sample, up to 25 MB, to Meta: with the session and the template, within the Hub's 90 s for door 8.
UPLOAD_TIMEOUT = httpx.Timeout(60.0, connect=5.0)
GRAPH_HOST = "graph.facebook.com"
#: The hosts Meta serves attachments from: its media links point there, nowhere else.
MEDIA_HOST_SUFFIXES = (".fbsbx.com", ".facebook.com", ".fbcdn.net", ".whatsapp.net")
#: Meta's codes for «slow down» (besides HTTP 429): app and account throttling (80008: the business-use-case limit of
#: the WhatsApp Business Management API, the templates'), and the number's throughput.
RATE_LIMIT_CODES = frozenset({4, 17, 32, 613, 80007, 80008, 130429, 131056})
#: How much of an attachment's refusal is read for Meta's error object (it is a few hundred bytes).
REFUSAL_LIMIT = 16 * 1024


class NotConfigured(Exception):
    """Meta's app (WHATSAPP_APP_ID / WHATSAPP_APP_SECRET) is not set: nothing can be asked of Meta."""


class MetaUnreachable(Exception):
    def __init__(self, message: str, *, sent: bool, status: int | None = None) -> None:
        super().__init__(message)
        self.sent = sent
        self.status = status


@dataclass
class MetaRefused(Exception):
    status: int
    code: int | None = None
    subcode: int | None = None
    message: str = ""
    title: str = ""
    detail: str = ""
    #: Meta's explanation for the person (``error_user_msg``): what a business is shown of a template it refused.
    user_message: str = ""

    def __post_init__(self) -> None:
        super().__init__(f"Meta refused ({self.status}, code {self.code}): {self.message}")

    @property
    def rate_limited(self) -> bool:
        return self.status == 429 or self.code in RATE_LIMIT_CODES


def graph_url(path: str) -> str:
    return f"https://{GRAPH_HOST}/{settings.WHATSAPP_GRAPH_VERSION}/{path.lstrip('/')}"


def app_credentials() -> tuple[str, str]:
    """The id and the secret of Meta's app, or ``NotConfigured``."""
    app_id = str(getattr(settings, "WHATSAPP_APP_ID", "") or "").strip()
    secret = str(getattr(settings, "WHATSAPP_APP_SECRET", "") or "").strip()
    if not app_id or not secret:
        raise NotConfigured("WHATSAPP_APP_ID and WHATSAPP_APP_SECRET are not set.")
    return app_id, secret


def app_id() -> str:
    """The id of Meta's app (``WHATSAPP_APP_ID``), ``""`` when it is not set."""
    return str(getattr(settings, "WHATSAPP_APP_ID", "") or "").strip()


def redirect_uri() -> str:
    """erplora.com's page Meta's window brings its one-time code back to (``WHATSAPP_REDIRECT_URI``): an absolute
    address of this site's ``/whatsapp/return``, https (plain http in development only), with no query nor
    fragment; ``""`` when the setting is not one. The window opens with it and the code is exchanged with it."""
    value = str(getattr(settings, "WHATSAPP_REDIRECT_URI", "") or "").strip()
    page = urlsplit(value)
    schemes = ("https", "http") if settings.DEBUG else ("https",)
    if page.scheme not in schemes or not page.netloc or "?" in value or "#" in value:
        return ""
    return value if page.path == reverse("whatsapp_signup_return") else ""


def get(path: str, *, token: str, params: dict | None = None) -> dict:
    return _request("GET", path, token=token, params=params)


def post(
    path: str,
    *,
    token: str,
    json: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    timeout: httpx.Timeout = TIMEOUT,
) -> dict:
    return _request("POST", path, token=token, json=json, data=data, files=files, timeout=timeout)


def delete(path: str, *, token: str, params: dict | None = None) -> dict:
    return _request("DELETE", path, token=token, params=params)


def upload_sample(token: str, *, name: str, mime_type: str, content: bytes) -> str:
    """The ``header_handle`` of ``content`` uploaded to Meta as a template's header sample (``NotConfigured`` without
    Meta's app; ``MetaRefused`` / ``MetaUnreachable`` as any call, the latter also when Meta answers without what its
    documentation says)."""
    app = app_id()
    if not app:
        raise NotConfigured("WHATSAPP_APP_ID is not set.")
    query = {"file_name": name, "file_length": len(content), "file_type": mime_type}
    session = _request("POST", f"{app}/uploads", token=token, params=query)
    upload = _upload_session(session.get("id"))
    if upload is None:
        raise MetaUnreachable("Meta's upload session is not the documented one.", sent=True)
    answer = _request(
        "POST",
        upload,
        token=token,
        scheme="OAuth",
        content=content,
        headers={"file_offset": "0", "Content-Type": "application/octet-stream"},
        timeout=UPLOAD_TIMEOUT,
    )
    handle = answer.get("h")
    if not isinstance(handle, str) or not handle.strip():
        raise MetaUnreachable("Meta took the sample without its handle.", sent=True)
    return handle.strip()


def _upload_session(upload_id) -> str | None:
    """The path of the upload's second hop, only if it names a session (``upload:…``, with Meta's own ``?sig=``) and
    cannot walk to another node of Graph with the business's token (``upload:x/../../me``) or break the request."""
    if not isinstance(upload_id, str) or not upload_id.startswith("upload:"):
        return None
    path = upload_id.split("?", 1)[0]
    if "/" in path or "\\" in path or "#" in upload_id or any(ch.isspace() for ch in upload_id):
        return None
    return upload_id


def exchange_token(token: str) -> dict:
    """Meta's long-lived exchange of a business token for a fresh one (``{"access_token", "expires_in"?}``)."""
    app_id, secret = app_credentials()
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": secret,
        "fb_exchange_token": token,
    }
    return _request("GET", "oauth/access_token", token=None, params=params)


def exchange_code(code: str) -> dict:
    """Meta's exchange of Embedded Signup's one-time ``code`` for the business's token (``{"access_token"}``), with
    the ``redirect_uri`` the window was opened with (Meta refuses another: error 100, subcode 36008)."""
    app_id, secret = app_credentials()
    params = {"client_id": app_id, "client_secret": secret, "code": code, "redirect_uri": redirect_uri()}
    return _request("GET", "oauth/access_token", token=None, params=params)


def token_expiry(token: str) -> datetime | None:
    """When ``token`` expires, as Meta's ``debug_token`` says it (``None``: it never does, Meta's ``0``)."""
    app_id, secret = app_credentials()
    params = {"input_token": token, "access_token": f"{app_id}|{secret}"}
    answer = _request("GET", "debug_token", token=None, params=params)
    data = answer.get("data") if isinstance(answer.get("data"), dict) else {}
    seconds = _int(data.get("expires_at"))
    return datetime.fromtimestamp(seconds, tz=UTC) if seconds and seconds > 0 else None


def _request(
    method: str,
    path: str,
    *,
    token: str | None,
    params: dict | None = None,
    json: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    content: bytes | None = None,
    headers: dict | None = None,
    scheme: str = "Bearer",
    timeout: httpx.Timeout = TIMEOUT,
) -> dict:
    sent = {**(headers or {}), **({"Authorization": f"{scheme} {token}"} if token else {})}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(
                method,
                graph_url(path),
                params=params,
                json=json,
                data=data,
                files=files,
                content=content,
                headers=sent,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        raise MetaUnreachable(f"Meta could not be reached: {type(error).__name__}.", sent=False) from None
    except httpx.HTTPError as error:
        raise MetaUnreachable(f"No answer from Meta: {type(error).__name__}.", sent=True) from None
    return _read(response)


def _read(response: httpx.Response) -> dict:
    status = response.status_code
    if status >= 500 or 300 <= status < 400:
        raise MetaUnreachable(f"Meta answered HTTP {status}.", sent=True, status=status)
    try:
        body = response.json()
    except ValueError:
        body = None
    if status >= 400:
        raise _refused(status, body)
    return body if isinstance(body, dict) else {}


def _refused(status: int, body) -> MetaRefused:
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return MetaRefused(status=status, message=f"HTTP {status}")
    details = error.get("error_data")
    return MetaRefused(
        status=status,
        code=_int(error.get("code")),
        subcode=_int(error.get("error_subcode")),
        message=str(error.get("message") or "")[:500],
        title=str(error.get("error_user_title") or "")[:200],
        user_message=str(error.get("error_user_msg") or "")[:500],
        detail=str(details.get("details") or "")[:500] if isinstance(details, dict) else "",
    )


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _meta_media_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host.endswith(suffix) for suffix in MEDIA_HOST_SUFFIXES)


@contextlib.contextmanager
def download(url: str, *, token: str) -> Iterator[httpx.Response]:
    """Stream an attachment from the link Meta gave for it: only Meta's hosts, over https, never redirected.

    The response is open inside the ``with``: its bytes are read as they arrive, never kept here. A 4xx is
    ``MetaRefused`` with Meta's error object (its 190: the permission expired); anything else but a 200,
    ``MetaUnreachable``.
    """
    if not _meta_media_url(url):
        raise MetaUnreachable("The attachment's link is not Meta's.", sent=False)
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
            with client.stream("GET", url, headers={"Authorization": f"Bearer {token}"}) as response:
                status = response.status_code
                if 400 <= status < 500:
                    raise _refused(status, _refusal_body(response))
                if status != 200:
                    raise MetaUnreachable(
                        f"Meta answered HTTP {status} for the attachment.", sent=True, status=status
                    )
                yield response
    except httpx.HTTPError as error:
        raise MetaUnreachable(f"The attachment could not be fetched: {type(error).__name__}.", sent=True) from None


def _refusal_body(response: httpx.Response):
    """The JSON of a streamed refusal, read up to ``REFUSAL_LIMIT`` (``None`` when it is not JSON)."""
    read = b""
    for chunk in response.iter_bytes():
        read += chunk
        if len(read) >= REFUSAL_LIMIT:
            return None
    try:
        return json.loads(read)
    except ValueError:
        return None
