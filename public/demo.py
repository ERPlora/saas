"""``/demo/``: the door to a demo hub (PLAN-SAAS §3.5, round 2026-10-17).

Plan ``docs/plans/2026-10-17-demo-hubs-fase-1.md`` §1.6 and §1.8. A demo is an empty hub of the Hub's own
(``demo-<8 hex>``, 60 minutes); the SaaS keeps no row of it, only the browser's session knows it
(``session["demo"] = {id, slug, expires_at, ready}``). Four routes:

* ``index`` (GET): the page, in one of its states, always 200. It never creates a demo: a crawler, a prefetch
  or a reload must not spend the Hub's cap of live demos;
* ``start`` (POST, CSRF): asks the Hub for a demo of this browser (``hubs.hub_client.create_demo``). The Hub answers
  202 «requested» and prepares its database afterwards (the asynchronous demo of the tenancy, 2026-10-30): the browser
  goes back to the door, which says «Preparing your demo…» while its page asks ``status`` every second (for 30 seconds,
  ``frontend/demo-wait.ts``). A demo already ready (the live one given back, or a Hub from before, which answers 201
  without ``status``) jumps at once to its ``/auth/login`` (``accounts.queries.hub_start_url``), the same jump with
  ``state`` as a business.
  New demos are limited per address (``DEMO_SPAWN_RATELIMIT``, as the contact form); a browser that already
  has a live one is not counted, and the Hub answers it the same demo. Then reCAPTCHA Enterprise
  (``recaptcha_token``, action ``demo_request``; ``live.recaptcha``; Ioan, 2026-10-22): only a person gets a demo,
  and a refused try never reaches the Hub (``?state=unverified``);
* ``status`` (GET, JSON): how the browser's demo is going, ``{state, url?}``; with a ``url`` the page goes there (the
  jump once the Hub has it ready, or the door with what happened: ``not_ready`` when the Hub could not prepare it,
  ``expired`` when it ended). Only a demo being prepared asks the Hub (``GET /internal/hubs/{id}``);
* ``enter`` (GET): where the demo's ``/auth/login`` sends the browser back with its ``state``. If this browser
  owns that demo, it asks the Hub for a one-time code (``create_demo_code``) and answers the auto-submitted
  form of ``accounts/hub_login_form.html``, which posts it to the demo's ``/auth/callback`` (the code never
  sits in a URL). Never indexed. A demo still being prepared is never entered: the code is asked only once it is ready.

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
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.csp import CSP
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django_ratelimit.decorators import ratelimit
from live import recaptcha
from live.slugs import is_demo_slug, validate_hub_slug

from accounts.handoff import STATE_MAX_LENGTH
from accounts.queries import hub_start_url, local_path
from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from public import landing
from public.csp import public_policy

logger = logging.getLogger(__name__)

#: The browser's demo in its session: ``{"id": "<UUID>", "slug": "demo-…", "expires_at": "<ISO 8601>", "ready": bool}``.
#: A session from before the asynchronous demo holds only ``slug`` and ``expires_at``: that demo was ready.
SESSION_DEMO = "demo"
#: The random token whose sha256 names this browser to the Hub (``session_key`` of ``/internal/demos``).
SESSION_OWNER = "demo_owner"
#: The outcomes ``start`` and ``enter`` send to the door as ``?state=``; nothing else of the address is read.
OUTCOMES = frozenset({"expired", "full", "throttled", "unverified", "unavailable", "failed", "not_ready"})
#: The field of reCAPTCHA's token and the action it is made for (frontend/recaptcha.ts, ``data-recaptcha-action``).
RECAPTCHA_FIELD = "recaptcha_token"
RECAPTCHA_ACTION = "demo_request"
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


def _hub_id(value: Any) -> str | None:
    """The hub's id as the Hub wrote it if it is a UUID, else ``None``."""
    try:
        return str(UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def _demo_of(body: Any) -> dict[str, Any] | None:
    """``{id, slug, expires_at, status}`` of an answer that names a demo hub with its end; ``None`` for anything else.

    The door only ever jumps into a ``demo-…`` hub: an answer naming a business is no demo, nor one whose ``id`` is not
    a UUID. ``id`` and ``status`` are ``None`` when the answer has none (a Hub from before the asynchronous demo).
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
    hub_id = _hub_id(body.get("id"))
    if body.get("id") is not None and hub_id is None:
        return None
    status = body.get("status")
    return {"id": hub_id, "slug": slug, "expires_at": expires_at, "status": status if isinstance(status, str) else None}


def _live_demo(request: HttpRequest) -> dict[str, Any] | None:
    """The browser's demo while it lasts (``{id, slug, expires_at, ready}``), else ``None``."""
    entry = request.session.get(SESSION_DEMO)
    demo = _demo_of(entry)
    if demo is None or demo["expires_at"] <= timezone.now():
        return None
    return {**demo, "ready": entry.get("ready") is not False}


def _remember(request: HttpRequest, demo: dict[str, Any], *, ready: bool) -> None:
    request.session[SESSION_DEMO] = {
        "id": demo["id"],
        "slug": demo["slug"],
        "expires_at": demo["expires_at"].isoformat(),
        "ready": ready,
    }


def _door(outcome: str | None = None) -> HttpResponseRedirect:
    door = reverse("public:demo")
    return HttpResponseRedirect(f"{door}?state={outcome}" if outcome else door)


def _to_a_hub(response: HttpResponse) -> HttpResponse:
    """``response`` under the public policy, save that its form may also go to a hub's origin.

    The door's «Try the demo» posts to ``start``, answered with a 302 to the demo's host, and Chrome holds that
    redirect to ``form-action`` too (with ``'self'`` alone the button does nothing); the entry's form posts to the
    demo's ``/auth/callback``. ``PublicCSPMiddleware`` keeps a policy the view set.
    """
    response._csp_config = {**public_policy(), "form-action": [CSP.SELF, settings.HUB_ORIGIN_PATTERN]}
    return response


def _spawn_rate(group, request: HttpRequest) -> str | None:
    """New demos per address; ``None`` (nothing counted) for a browser with a live demo, or with it off."""
    if not settings.DEMO_ENABLED or _live_demo(request) is not None:
        return None
    return settings.DEMO_SPAWN_RATELIMIT


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    """The door, always 200: ``off``, ``idle``, ``ready``, or an outcome of a try (``OUTCOMES``).

    ``?state=expired`` is also where the Hub's 410 page of a demo sends the visitor: a demo can end before its hour
    (``manage.py demo_expire``, «Expire now» in the Hub admin) and the session, which only knows ``expires_at``,
    would still offer it as live, so that address forgets it. The Hub is not asked on any visit: the door is a public
    page (crawlers, reloads) and a demo that ended is found out anyway on «Back to my demo» (``enter`` hears 410). A
    link that says ``expired`` by mistake costs nothing: the browser keeps its token, and «Try the demo» gets its
    demo back from the Hub while it lasts.
    """
    asked = request.GET.get("state")
    live = None if asked == "expired" else _live_demo(request)
    ended = live is None and SESSION_DEMO in request.session
    if ended:
        # Said once: the next visit is a fresh door.
        del request.session[SESSION_DEMO]
    if not settings.DEMO_ENABLED:
        state = "off"
    elif ended:
        state = "expired"
    elif asked in OUTCOMES:
        state = asked
    elif live is None:
        state = "idle"
    else:
        state = "ready" if live["ready"] else "preparing"
    context: dict[str, Any] = {"demo_state": state, "demo": None}
    if live is not None and state != "off":
        seconds = (live["expires_at"] - timezone.now()).total_seconds()
        context["demo"] = {
            "slug": live["slug"],
            "expires_at": live["expires_at"],
            "minutes_left": max(1, math.ceil(seconds / 60)),
            # Only a demo the Hub has ready is jumped into; one being prepared is waited for on this page.
            "url": hub_start_url(live["slug"]) if live["ready"] else None,
        }
    if state == "preparing":
        context["wait"] = {"status_url": reverse("public:demo_status"), "timeout_url": _door("not_ready")["Location"]}
    return _to_a_hub(render(request, "public/demo/index.html", context))


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
        recaptcha.verify_or_raise(request, request.POST.get(RECAPTCHA_FIELD), RECAPTCHA_ACTION)
    except recaptcha.RecaptchaFailed:
        logger.info("demo.start.unverified")
        return _door("unverified")
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
    # A Hub from before the asynchronous demo answers without ``status``: its demo is ready as it answers.
    ready = demo is not None and demo["status"] in (None, "ready")
    waiting = (
        demo is not None
        and demo["id"] is not None
        and (demo["status"] in hub_client.PREPARING_STATUSES or demo["status"] == hub_client.FAILED_STATUS)
    )
    if not (ready or waiting):
        logger.error("demo.start.bad_answer status=%s", answer.status)
        return _door("unavailable")
    _remember(request, demo, ready=ready)
    logger.info("demo.start hub=%s created=%s ready=%s", demo["slug"], answer.status in (201, 202), ready)
    return HttpResponseRedirect(hub_start_url(demo["slug"], "/") if ready else reverse("public:demo"))


def _status(state: str, url: str | None = None) -> JsonResponse:
    answer = JsonResponse({"state": state} if url is None else {"state": state, "url": url})
    answer["X-Robots-Tag"] = "noindex, nofollow"
    return answer


def _forget(request: HttpRequest) -> None:
    request.session.pop(SESSION_DEMO, None)


@require_safe
@never_cache
def status(request: HttpRequest) -> JsonResponse:
    """How the browser's demo is going, for the door's page while it waits: ``{state}`` while the Hub prepares it (or
    is away a moment), ``{state, url}`` when the page should go to ``url``: the jump once it is ready (remembered, so
    the Hub is asked no more), or the door with what happened.

    Only the session's demo, never one named in the address; only a demo being prepared costs a call to the Hub.
    """
    door = reverse("public:demo")
    if not settings.DEMO_ENABLED:
        return _status("off", door)
    live = _live_demo(request)
    if live is None:
        # None, or its hour passed: the door says which (and forgets an ended one, once).
        return _status("idle", door)
    slug = live["slug"]
    if live["ready"]:
        return _status("ready", hub_start_url(slug, "/"))
    try:
        answer = hub_client.get_hub(live["id"])
    except HubRefused as refused:
        if refused.status in (404, 410):
            _forget(request)
            logger.info("demo.status.ended hub=%s status=%s", slug, refused.status)
            return _status("expired", _door("expired")["Location"])
        logger.error("demo.status.bad_answer hub=%s status=%s code=%s", slug, refused.status, refused.code)
        return _status("unavailable", _door("unavailable")["Location"])
    except HubUnavailable as away:
        logger.warning("demo.status.hub_unavailable hub=%s %s", slug, away)
        return _status("preparing")
    hub_status = answer.body.get("status") if isinstance(answer.body, dict) else None
    if hub_status == "ready":
        _remember(request, live, ready=True)
        logger.info("demo.status.ready hub=%s", slug)
        return _status("ready", hub_start_url(slug, "/"))
    if hub_status in hub_client.PREPARING_STATUSES:
        return _status("preparing")
    if hub_status == hub_client.FAILED_STATUS:
        # The Hub retries it on its own: «Try again» waits for the same demo.
        logger.warning("demo.status.not_prepared hub=%s", slug)
        return _status("not_ready", _door("not_ready")["Location"])
    if hub_status in hub_client.ENDED_STATUSES:
        _forget(request)
        logger.info("demo.status.ended hub=%s status=%s", slug, hub_status)
        return _status("expired", _door("expired")["Location"])
    logger.error("demo.status.bad_answer hub=%s status=%s hub_status=%r", slug, answer.status, hub_status)
    return _status("unavailable", _door("unavailable")["Location"])


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
    if not live["ready"]:
        # Still being prepared: the door waits for it; the code is asked only for a demo the Hub has ready.
        logger.info("demo.enter.not_ready hub=%s", slug)
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
            "demo_jump": True,
        },
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return _to_a_hub(response)
