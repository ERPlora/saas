"""The way back from a business to erplora.com: ``/hub-pass/?pass=<pass>`` (ACCOUNTS-F29, the Hub's BASE-F11;
saas#190).

The jump the other way round (``handoff.hub_login``) mints a one-time code on the SaaS. This one cannot: the Hub never
asks the SaaS anything per request (PLAN-SAAS §2), so it signs the pass itself, with the secret of ``/internal``
(``accounts.signing``), and the SaaS only checks it. The pass is what the Hub's «Upgrade plan» and «erplora.com» open
in the browser (in the installed app, the device's own): it lands on the plan or on the business already signed in.

The contract, what the Hub signs (``django.core.signing``, the scheme of Django's own signed cookies)::

    django.core.signing.dumps(
        {"user": "<the account's id on the SaaS>", "hub": "<slug>", "next": "plan" | "business", "nonce": "<nonce>"},
        key=INTERNAL_SHARED_SECRET,
        salt="erplora.hub-pass.v1",
    )

``user`` is the UUID the Hub got from ``/internal/auth/redeem`` (``HubIdentity.user_id``); ``nonce`` 16 to 128 of
``[A-Za-z0-9_-]`` (the Hub mints ``secrets.token_urlsafe(32)``), fresh for every pass. It is checked with every live
secret (``signing.live_secrets``: the previous one too during a rotation, never ``SECRET_KEY``) and opens for
``HUB_PASS_MAX_AGE_SECONDS`` (a minute), once, and only for an active account that is a member of that business and no
staff of the platform. Then the session of erplora.com is that account's, and the browser lands on
``/dashboard/store/plans?business=<id>`` (``plan``) or ``/dashboard/businesses/<id>`` (``business``).

Anything else opens nothing and lands on the Vue page ``/login/error?code=…``: ``invalid_pass`` (not signed as the Hub
signs it, or not saying what it must), ``not_a_member&hub=<slug>`` and ``pass_expired&next=<where it was going>`` (past
its minute, or already used: the page offers to sign in and go on there). An account already signed in in this browser
goes on where the pass was going, whatever its age: there is nothing to open. A session opened by a pass passed no
sign-in of allauth (no password, code or second factor on record) and accepts no terms: whatever asks for one asks
again.
"""

import logging
import re
import uuid
import zlib
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.core import signing
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts import services
from accounts.handoff import login_error_url
from accounts.signing import live_secrets
from base.navigation import BUSINESSES, STORE

logger = logging.getLogger(__name__)

#: What the Hub salts the pass with: a value signed for anything else with the same secret is no pass.
SALT = "erplora.hub-pass.v1"
#: The audience of the row that spends a pass (``AuthExchangeCode``): no jump to a hub redeems it.
AUDIENCE = services.HUB_PASS_AUDIENCE
#: Where a pass may lead: the plan of the business in the Store, or the business in the panel.
NEXT_PLAN = "plan"
NEXT_BUSINESS = "business"
NEXTS = (NEXT_PLAN, NEXT_BUSINESS)
#: A nonce of the Hub: 16 to 128 URL-safe characters.
_NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}")
#: The session a pass opens names this backend: the account signed in by no password nor allauth's flows.
_BACKEND = "django.contrib.auth.backends.ModelBackend"


class InvalidPass(Exception):
    """Not signed as the Hub signs a pass, or not saying what a pass must say."""


@dataclass(frozen=True)
class HubPass:
    """What a pass says, once its signature is proven. ``expired``: past ``HUB_PASS_MAX_AGE_SECONDS``."""

    user_id: str
    hub_slug: str
    next: str
    nonce: str
    expired: bool


def lifetime() -> timedelta:
    """How long a pass opens after the Hub signed it."""
    return timedelta(seconds=settings.HUB_PASS_MAX_AGE_SECONDS)


def read(token: str) -> HubPass:
    """The pass ``token``, checked against every live secret; ``InvalidPass`` if it is none.

    Without a shared secret nothing is a pass: Django's signer would fall back on ``SECRET_KEY``.
    """
    keys = live_secrets()
    if not token or not keys:
        raise InvalidPass
    signer = signing.TimestampSigner(key=keys[0], salt=SALT, fallback_keys=list(keys[1:]))
    expired = False
    try:
        try:
            payload = signer.unsign_object(token, max_age=settings.HUB_PASS_MAX_AGE_SECONDS)
        except signing.SignatureExpired:
            # The signature holds, only its minute is gone: read it to know where it was going.
            payload, expired = signer.unsign_object(token), True
    except (signing.BadSignature, ValueError, zlib.error) as error:
        # A signed value that is no JSON, no base64 or no zlib is no pass either.
        raise InvalidPass from error
    return _parse(payload, expired=expired)


def _parse(payload, *, expired: bool) -> HubPass:
    if not isinstance(payload, dict):
        raise InvalidPass
    user_id, hub_slug, next_, nonce = (payload.get(field) for field in ("user", "hub", "next", "nonce"))
    if not isinstance(user_id, str):
        raise InvalidPass
    try:
        user_id = str(uuid.UUID(user_id))
    except ValueError as error:
        raise InvalidPass from error
    if not (isinstance(hub_slug, str) and services.is_hub_slug(hub_slug)):
        raise InvalidPass
    if not (isinstance(next_, str) and next_ in NEXTS):
        raise InvalidPass
    if not (isinstance(nonce, str) and _NONCE.fullmatch(nonce)):
        raise InvalidPass
    return HubPass(user_id=user_id, hub_slug=hub_slug, next=next_, nonce=nonce, expired=expired)


def destination(next_: str, hub_id) -> str:
    """Where a pass leads in the panel: the business's plan in the Store, or the business."""
    if next_ == NEXT_PLAN:
        return f"{STORE}/plans?{urlencode({'business': str(hub_id)})}"
    return f"{BUSINESSES}/{hub_id}"


def _answer(location: str) -> HttpResponse:
    response = HttpResponseRedirect(location)
    # The pass sits in this address: the page it lands on never hands it to anybody.
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_GET
@never_cache
def follow(request: HttpRequest) -> HttpResponse:
    try:
        hub_pass = read(request.GET.get("pass", ""))
    except InvalidPass:
        # Nothing of it is echoed back: it is not the Hub's.
        logger.warning("hub_pass.invalid")
        return _answer(login_error_url("invalid_pass"))
    member = services.hub_pass_member(hub_pass.user_id, hub_pass.hub_slug)
    if member is None:
        logger.info("hub_pass.not_a_member hub=%s", hub_pass.hub_slug)
        return _answer(login_error_url("not_a_member", hub=hub_pass.hub_slug))
    user, hub_id = member
    going_to = destination(hub_pass.next, hub_id)
    spent = not hub_pass.expired and services.spend_hub_pass(user, hub_pass.hub_slug, hub_pass.nonce, lifetime())
    if request.user.is_authenticated and request.user.pk == user.pk:
        # Its session is open here already (a reload, the back button): nothing to open, it goes on.
        return _answer(going_to)
    if not spent:
        logger.info("hub_pass.expired_or_used hub=%s user=%s", hub_pass.hub_slug, user.pk)
        return _answer(login_error_url("pass_expired", next=going_to))
    # ``services.accept_legal_texts`` reads it: nobody saw the terms on the way.
    request.hub_pass = hub_pass
    login(request, user, backend=_BACKEND)
    logger.info("hub_pass.signed_in hub=%s user=%s", hub_pass.hub_slug, user.pk)
    return _answer(going_to)
