"""``/demo/``: the door to a demo hub (PLAN-SAAS §3.5, round 2026-10-17).

Plan ``docs/plans/2026-10-17-demo-hubs-fase-1.md`` §1.6 and §1.8. A demo is an empty hub of the Hub's own
(``demo-<8 hex>``, 60 minutes); the SaaS keeps no row of it, only the browser's session knows it
(``session["demo"] = {slug, expires_at}``). Three routes:

* ``index`` (GET): the page, in one of its states, always 200. It never creates a demo: a crawler, a prefetch
  or a reload must not spend the Hub's cap of live demos;
* ``start`` (POST, CSRF): asks the Hub for a demo of this browser (``hubs.hub_client.create_demo``) and jumps
  to its ``/auth/login`` (``accounts.queries.hub_start_url``), the same jump with ``state`` as a business.
  New demos are limited per address (``DEMO_SPAWN_RATELIMIT``, as the contact form); a browser that already
  has a live one is not counted, and the Hub answers it the same demo;
* ``enter`` (GET): where the demo's ``/auth/login`` sends the browser back with its ``state``. If this browser
  owns that demo, it asks the Hub for a one-time code (``create_demo_code``) and answers the auto-submitted
  form of ``accounts/hub_login_form.html``, which posts it to the demo's ``/auth/callback`` (the code never
  sits in a URL). Never indexed.

The browser is named to the Hub by the sha256 of a random token of its session (``session["demo_owner"]``),
never by the session cookie: the token survives the session key's rotation when the visitor signs in to the
SaaS, so they keep their demo. No ORM here (``public/tests/test_lint.py``).
"""

from __future__ import annotations

import hashlib
import logging
import math
import secrets
from datetime import datetime
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.csp import CSP
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django_ratelimit.decorators import ratelimit
from live.slugs import is_demo_slug, validate_hub_slug

from accounts.handoff import STATE_MAX_LENGTH
from accounts.queries import hub_start_url, local_path
from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from public import landing
from public.csp import public_policy

logger = logging.getLogger(__name__)

#: The browser's demo in its session: ``{"slug": "demo-…", "expires_at": "<ISO 8601>"}``.
SESSION_DEMO = "demo"
#: The random token whose sha256 names this browser to the Hub (``session_key`` of ``/internal/demos``).
SESSION_OWNER = "demo_owner"
#: The outcomes ``start`` and ``enter`` send to the door as ``?state=``; nothing else of the address is read.
OUTCOMES = frozenset({"expired", "full", "throttled", "unavailable", "failed"})
#: The Hub's refusal when its cap of live demos is reached.
DEMO_FULL = "base.demo_full"


def _language() -> str:
    """The visitor's language (``en``/``es``), which the demo opens in."""
    return (translation.get_language() or settings.LANGUAGE_CODE).split("-")[0]


def _owner(request: HttpRequest) -> str:
    """The sha256 hex that names this browser to the Hub; its token is made the first time."""
    token = request.session.get(SESSION_OWNER)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_OWNER] = token
    return hashlib.sha256(token.encode()).hexdigest()


def _expiry(value: Any) -> datetime | None:
    """An aware datetime from the Hub's (or the session's) ISO 8601, else ``None``."""
    moment = parse_datetime(value) if isinstance(value, str) else None
    return moment if moment is not None and timezone.is_aware(moment) else None


def _demo_of(body: Any) -> dict[str, Any] | None:
    """``{slug, expires_at}`` of an answer that names a demo hub with its end; ``None`` for anything else.

    The door only ever jumps into a ``demo-…`` hub: an answer naming a business is no demo.
    """
    if not isinstance(body, dict):
        return None
    slug, expires_at = body.get("slug"), _expiry(body.get("expires_at"))
    if not isinstance(slug, str) or not is_demo_slug(slug) or expires_at is None:
        return None
    try:
        validate_hub_slug(slug, allow_demo=True)
    except ValueError:
        return None
    return {"slug": slug, "expires_at": expires_at}


def _live_demo(request: HttpRequest) -> dict[str, Any] | None:
    """The browser's demo while it lasts, else ``None``."""
    demo = _demo_of(request.session.get(SESSION_DEMO))
    return demo if demo is not None and demo["expires_at"] > timezone.now() else None


def _door(outcome: str | None = None) -> HttpResponseRedirect:
    door = reverse("public:demo")
    return HttpResponseRedirect(f"{door}?state={outcome}" if outcome else door)


def _spawn_rate(group, request: HttpRequest) -> str | None:
    """New demos per address; ``None`` (nothing counted) for a browser with a live demo, or with it off."""
    if not settings.DEMO_ENABLED or _live_demo(request) is not None:
        return None
    return settings.DEMO_SPAWN_RATELIMIT


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    """The door, always 200: ``off``, ``idle``, ``ready``, or an outcome of a try (``OUTCOMES``)."""
    live = _live_demo(request)
    ended = live is None and SESSION_DEMO in request.session
    if ended:
        # Said once: the next visit is a fresh door.
        del request.session[SESSION_DEMO]
    asked = request.GET.get("state")
    if not settings.DEMO_ENABLED:
        state = "off"
    elif ended:
        state = "expired"
    elif asked in OUTCOMES and not (asked == "expired" and live is not None):
        state = asked
    else:
        state = "ready" if live is not None else "idle"
    context: dict[str, Any] = {"demo_state": state, "demo": None}
    if live is not None and state != "off":
        seconds = (live["expires_at"] - timezone.now()).total_seconds()
        context["demo"] = {
            "slug": live["slug"],
            "expires_at": live["expires_at"],
            "minutes_left": max(1, math.ceil(seconds / 60)),
            "url": hub_start_url(live["slug"]),
        }
    return render(request, "public/demo/index.html", context)


@require_POST
@ratelimit(key=landing.visitor_address, rate=_spawn_rate, method="POST", block=False)
def start(request: HttpRequest) -> HttpResponse:
    """A demo of this browser (the same one while it lasts), then the jump into it."""
    if not settings.DEMO_ENABLED:
        return _door()
    if getattr(request, "limited", False):
        logger.info("demo.start.throttled")
        return _door("throttled")
    try:
        answer = hub_client.create_demo(_owner(request), vertical=None, language=_language())
    except HubRefused as refused:
        if refused.code == DEMO_FULL:
            logger.info("demo.start.full")
            return _door("full")
        logger.error("demo.start.hub_refused status=%s code=%s", refused.status, refused.code)
        return _door("unavailable")
    except HubUnavailable as away:
        logger.warning("demo.start.hub_unavailable %s", away)
        return _door("unavailable")
    demo = _demo_of(answer.body)
    if demo is None:
        logger.error("demo.start.bad_answer status=%s", answer.status)
        return _door("unavailable")
    request.session[SESSION_DEMO] = {"slug": demo["slug"], "expires_at": demo["expires_at"].isoformat()}
    logger.info("demo.start hub=%s created=%s", demo["slug"], answer.status == 201)
    return HttpResponseRedirect(hub_start_url(demo["slug"], "/"))


@require_safe
@never_cache
def enter(request: HttpRequest) -> HttpResponse:
    """``?hub&next&state`` from the demo's ``/auth/login``: its one-time code, posted to its callback."""
    if not settings.DEMO_ENABLED:
        return _door()
    live = _live_demo(request)
    slug = request.GET.get("hub", "")
    if live is None or live["slug"] != slug:
        # Not this browser's demo, or it ended: the door says which (nothing is echoed back).
        logger.info("demo.enter.not_this_browsers")
        return _door()
    next_path = local_path(request.GET.get("next", ""))
    state = request.GET.get("state", "")
    if not state:
        # Without the Hub's state the Hub would refuse the code: the jump starts at the demo.
        return HttpResponseRedirect(hub_start_url(slug, next_path))
    if len(state) > STATE_MAX_LENGTH:
        logger.warning("demo.enter.invalid_state hub=%s", slug)
        return _door("failed")
    try:
        answer = hub_client.create_demo_code(slug, _owner(request), language=_language())
    except HubRefused as refused:
        if refused.status in (404, 410):
            del request.session[SESSION_DEMO]
            logger.info("demo.enter.ended hub=%s status=%s", slug, refused.status)
            return _door("expired")
        if refused.status == 403:
            del request.session[SESSION_DEMO]
            logger.warning("demo.enter.not_owner hub=%s", slug)
            return _door()
        logger.error("demo.enter.hub_refused hub=%s status=%s code=%s", slug, refused.status, refused.code)
        return _door("unavailable")
    except HubUnavailable as away:
        logger.warning("demo.enter.hub_unavailable hub=%s %s", slug, away)
        return _door("unavailable")
    code = answer.body.get("code") if isinstance(answer.body, dict) else None
    if not isinstance(code, str) or not code:
        logger.error("demo.enter.bad_answer hub=%s status=%s", slug, answer.status)
        return _door("unavailable")
    response = render(
        request,
        "accounts/hub_login_form.html",
        {
            "callback_url": settings.HUB_CALLBACK_TEMPLATE.format(slug=slug),
            "code": code,
            "next": next_path,
            "state": state,
            "staff_jump": False,
        },
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    # The public policy, but this one form posts to the demo's origin (``PublicCSPMiddleware`` keeps it).
    response._csp_config = {**public_policy(), "form-action": [CSP.SELF, settings.HUB_ORIGIN_PATTERN]}
    return response
