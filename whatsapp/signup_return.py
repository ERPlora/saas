"""``GET /whatsapp/return``: the page Meta's window (Embedded Signup) is sent back to with its one-time code
(WHATSAPP-F01, WHATSAPP-F11; the Hub's WORKBOOK ``whatsapp_inbox``, «La ventana de Meta sin el SDK de Facebook»).

The Hub opens Meta's window without Facebook's SDK, with door 10's ``redirect_uri`` (this page) and a ``state`` of
its own, ``<slug>.<32 hex>``; Meta ends the window here with ``?code=…&state=…`` (or ``?error=…&error_description=…``).
The page posts ``{"type": "erplora.whatsapp.signup", "state", "code" | "error", "error_description"}`` to the window
that opened Meta's, only at the origin of the hub the ``state`` names (``accounts.queries.hub_origin``), never
``"*"``, and closes itself; the Hub takes it only with its attempt's ``state`` and connects the code through door 11.
A ``state`` that names no hub, or nothing to hand back, posts nothing: the page says the window can be closed, as it
does when nobody opened it.

Public and without a session (Meta's window brings no cookie of the Hub's), never cached, and it reads no database.
Its ``Cross-Origin-Opener-Policy`` is ``unsafe-none``, on this view only: Django's ``same-origin`` (every other page)
would cut the window from its opener, a page of another origin, and the message would never arrive (the Hub's pages
send ``same-origin-allow-popups``, hub#154; PLAN-HUB, round 2026-10-21). What came from Meta is data
(``json_script``) read by the page's one script, which carries the CSP's nonce.
"""

import re

from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from live.slugs import validate_hub_slug

from accounts.queries import hub_origin

#: The type of the message the Hub's page waits for (``RETURN_TYPE`` of its ``lib/metaSignup.ts``).
MESSAGE_TYPE = "erplora.whatsapp.signup"
#: The Hub's ``state``: the business's slug and the attempt's 16 random bytes in lowercase hex.
STATE = re.compile(r"(?P<slug>[^.]+)\.[0-9a-f]{32}")
#: The longest code door 11 takes (``schemas.ConnectIn.code``).
MAX_CODE = 2048
#: How much of Meta's reason is handed back: its code and the sentence the Hub shows.
MAX_ERROR = 200
MAX_ERROR_DESCRIPTION = 500
#: Django's policy (``same-origin``) cuts a window from an opener of another origin; this page must keep it.
OPENER_POLICY = "unsafe-none"


@never_cache
@require_safe
def signup_return(request: HttpRequest) -> HttpResponse:
    response = render(request, "whatsapp/signup_return.html", {"handed": _handed(request.GET)})
    # Set here, SecurityMiddleware keeps it (it only fills the header in when a view has not).
    response["Cross-Origin-Opener-Policy"] = OPENER_POLICY
    return response


def _handed(query: QueryDict) -> dict | None:
    """What the page posts (``message``) and to which origin (``target``), or ``None``: a ``state`` that names no
    hub that could have opened the window (reserved names and demos included), or neither a code nor a reason."""
    state = query.get("state", "")
    found = STATE.fullmatch(state)
    if not found:
        return None
    try:
        slug = validate_hub_slug(found["slug"])
    except ValueError:
        return None
    code = query.get("code", "").strip()
    error = query.get("error", "").strip()[:MAX_ERROR]
    reason = query.get("error_description", "").strip()[:MAX_ERROR_DESCRIPTION]
    if code:
        if len(code) > MAX_CODE:
            return None
        message = {"type": MESSAGE_TYPE, "state": state, "code": code}
    elif error or reason:
        message = {"type": MESSAGE_TYPE, "state": state, "error": error, "error_description": reason}
    else:
        return None
    return {"message": message, "target": hub_origin(slug)}
