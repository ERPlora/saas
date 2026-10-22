"""The installable app ``com.erplora.app``: the latest version, its downloads, its page ``/app/`` and
the «ways to try ERPlora» page ``/download/``.

Port of ``apps/public/appdist/views.py`` and ``apps/public/landing/downloads_views.py``
(origin/develop c5ca8ca). Together they are the whole install and update channel of the fleet:

* ``published_release`` — which build we publish right now. The hub's release CI writes
  ``downloads/app/latest/latest.json`` next to the installers (an installer does not say which
  version it is), and this reads it. The query ``public.app.release`` serves it at
  ``GET /api/v1/app/release/`` (``public/queries.py``, ``public/api.py``). **If it cannot be read,
  the answer is ``None``, never an invented number**: the Hub turns anything that is not a version
  into «could not check», silence; a number too many would send a till to download something that
  does not exist.
* ``download`` — ``GET /app/download/<platform>/``: the store when its listing is live, the
  installer (always ``latest/``) otherwise. It is the only download door: the store-or-presigned
  rule lives once (``public.downloads.store_url_for``), and it is an address of ``erplora.com``,
  which the installed app may open (ADR-0255), where a presigned URL of the bucket is not.
* ``index`` — ``GET /app/``, the app's public page; ``ways_to_try`` — ``GET /download/``.

**Android has no fallback** (hub#984): its only channel is Google Play (ADR-0160). It is not in
``_APP_PLATFORM_FILES``, so without a store it gets a page of ours (saas#1719) while
``GOOGLE_PLAY_LISTING_LIVE`` is off, and never the APK. The listing is live since 2026-10-01 and the
switch defaults to on: the page only comes back if Google pulls the listing.
"""

import json
import logging
from functools import lru_cache

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe

from public import pricing
from public.downloads import _s3_client, presigned_download_url, store_url_for

logger = logging.getLogger(__name__)

#: What the hub's release writes next to the installers. A contract with
#: `.github/workflows/tauri-release.yml` (hub repo): one word changed here or there leaves the
#: channel mute, and mute cannot be told apart from «nothing new».
RELEASE_MANIFEST_KEY = "downloads/app/latest/latest.json"

#: How long one reading of the bucket is reused. Every till of the fleet asks every 6 h for
#: something that changes once per release: without this, one `get_object` per till and round.
RELEASE_CACHE_TTL = 600

#: The platforms served as a WEB DOWNLOAD, and the binary of each. No macOS (no Apple Developer ID
#: certificate, nothing is published) and, on purpose, no Android (hub#984): its only channel is
#: Google Play; the CI still uploads the APK, as an internal QA artefact without a public door.
_APP_PLATFORM_FILES = {
    "windows": "erplora-app-setup.exe",
    "linux": "erplora-app.AppImage",
}

#: The settings that pick the store, in one place: `download` decides the destination with them and
#: `index` names the button with the same, so the page cannot promise another channel than the one
#: the 302 serves (saas#1719).
_STORE_SETTINGS = {
    "ms_store_setting": "MICROSOFT_STORE_APP_ID",
    "play_setting": "GOOGLE_PLAY_APP_ID",
    "play_live_setting": "GOOGLE_PLAY_LISTING_LIVE",
}


@lru_cache(maxsize=2)
def published_release(_bucket: int) -> str | None:
    """The version ``latest/`` publishes, or ``None`` if it could not be read.

    The argument is the time bucket (``time() // RELEASE_CACHE_TTL``): it gives an ``lru_cache`` an
    expiry, which is what is needed — a new release must be seen without restarting the process,
    and one reading per request is too many.

    **Never raises.** A bucket down, a missing key or a manifest that is not JSON all get the same
    answer, «I do not know», which reaches the till as silence: right, where an exception would be
    a 500 on a screen the user did not even ask for. The cause goes to the log.
    """
    bucket = getattr(settings, "DOWNLOADS_BUCKET", "erplora-saas")
    try:
        obj = _s3_client().get_object(Bucket=bucket, Key=RELEASE_MANIFEST_KEY)
        manifest = json.loads(obj["Body"].read())
    except Exception:  # Every failure is «I do not know», none is the user's.
        logger.warning(
            "Could not read the app release manifest %s from %s",
            RELEASE_MANIFEST_KEY,
            bucket,
            exc_info=True,
        )
        return None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    # A number is not a version: the Hub compares text, and `140` would read as unreadable.
    return version if isinstance(version, str) and version.strip() else None


def _store_url(platform: str) -> str | None:
    return store_url_for(platform, **_STORE_SETTINGS)


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    """``/app/``: the installable app's public page.

    It only tells the template whether each store is live, so the button reads «Get it from…»
    instead of «Download»; the real destination is ``download``'s, never a second copy of the rule.
    """
    return render(
        request,
        "public/appdist/index.html",
        {
            "app_ms_store": _store_url("windows") is not None,
            "app_google_play": _store_url("android") is not None,
        },
    )


@require_safe
def download(request: HttpRequest, platform: str) -> HttpResponse:
    """``/app/download/<platform>/``: the store, Android's page, or the installer.

    The prefix is ``latest/``, never ``v{version}/``: a page that caches this link keeps
    delivering the latest build (hub#400, point 1). The store is asked BEFORE the binary, and that
    order is the fix of hub#984: Android has no binary entry, so without a store it falls on its
    page, never on the presigned APK.
    """
    store_url = _store_url(platform)
    if store_url:
        return HttpResponseRedirect(store_url)
    if platform == "android":
        return render(request, "public/appdist/android.html")
    filename = _APP_PLATFORM_FILES.get(platform)
    if not filename:
        raise Http404
    prefix = getattr(settings, "APP_DOWNLOAD_PREFIX", "downloads/app/latest")
    return HttpResponseRedirect(presigned_download_url(f"{prefix}/{filename}"))


@require_safe
def ways_to_try(request: HttpRequest) -> HttpResponse:
    """``/download/``: the two free ways to try ERPlora, both through the free sign-up.

    A: create a free cloud hub (primary). B: install the app on the device at the counter (its
    first launch also walks you through creating the free hub). The per-platform buttons go to
    ``download``, which picks store or installer. The demo is ``/demo/`` (``public/demo.py``), offered by
    the home and the navbar: it is no way to your own hub, so it is not one of these two. The free hub's
    devices and users are the Free plan's (PUBLIC-G28), and without one on sale the page states none.
    """
    free = pricing.free_plan(pricing.plans_on_sale(request))
    return render(request, "public/downloads.html", {"free_plan": free})
