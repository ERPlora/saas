"""IndexNow: push the public URLs to Bing the day they change (spec §8.2).

Ported from ERPlora/saas ``apps/public/landing/indexnow.py`` (origin/develop c5ca8ca). Being allowed
to crawl is not being crawled: a young domain waits weeks for a spontaneous recrawl, and IndexNow is
one HTTP call that gets the page fetched in hours. ChatGPT search leans on Bing's index, so this is
the shortest path from «we published a page» to «an assistant can cite it».

Two halves, both mandatory: the key file at ``/<key>.txt`` (proof we control the domain) and the
submission carrying the same key. With ``INDEXNOW_KEY`` empty the whole thing is inert on purpose.
The daily run is the ``indexnow_submit`` command in a scheduled ECS task (PLAN §16.5).
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.http import require_safe

from public.crawlers import private_prefixes
from public.sitemaps import SITEMAPS

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT_SECONDS = 15


def key() -> str:
    return (settings.INDEXNOW_KEY or "").strip()


def public_urls(host: str) -> list[str]:
    """Every public URL worth pushing, from the same sitemaps the crawlers read (two hand-kept
    lists drift), each built on ``host``: one off-host URL makes IndexNow reject the batch."""
    urls: list[str] = []
    for sitemap_class in SITEMAPS.values():
        sitemap = sitemap_class(host)
        for item in sitemap.items():
            location = sitemap.location(item)
            # The last gate before we actively announce a URL to a search engine.
            if location.startswith(private_prefixes()):
                logger.warning(
                    "indexnow: skipping a private path from the sitemap: %s", location
                )
                continue
            url = f"https://{host}{location}"
            if url not in urls:
                urls.append(url)
    return urls


def submit_sitemap_urls(host: str) -> int:
    """Submit the public URLs; how many were accepted, 0 on any failure (logged, never silent)."""
    api_key = key()
    if not api_key:
        logger.info("indexnow: INDEXNOW_KEY is not set, nothing submitted")
        return 0
    urls = public_urls(host)
    if not urls:
        logger.warning("indexnow: the sitemaps produced no URLs, nothing submitted")
        return 0
    payload = {
        "host": host,
        "key": api_key,
        "keyLocation": f"https://{host}/{api_key}.txt",
        "urlList": urls,
    }
    try:
        response = requests.post(
            ENDPOINT,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    except requests.RequestException as error:
        logger.error("indexnow: the submission did not reach %s (%s)", ENDPOINT, error)
        return 0
    if response.status_code not in (200, 202):
        logger.error(
            "indexnow: submission rejected with %s (%s)",
            response.status_code,
            (response.text or "")[:200],
        )
        return 0
    logger.info("indexnow: submitted %s URLs for %s", len(urls), host)
    return len(urls)


@require_safe
def key_file(request: HttpRequest, requested_key: str) -> HttpResponse:
    """``GET /<key>.txt``: the ownership proof, served only for OUR key (matching any key would
    hand anybody a verified key file for our domain)."""
    api_key = key()
    if not api_key or requested_key != api_key:
        raise Http404
    return HttpResponse(api_key, content_type="text/plain; charset=utf-8")
