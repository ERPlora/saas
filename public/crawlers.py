"""Who may crawl what: one source of truth for robots.txt and the noindex header.

Ported from ERPlora/saas ``apps/public/crawlers.py`` (origin/develop c5ca8ca). The answer engines
are welcome on the public web and nowhere else (Ioan, 2026-08-26). Two mechanisms, because one of
them is only a polite request:

* ``robots.txt`` (``public.seo.robots_txt``) states the intent, agent by agent;
* ``NoIndexPrivatePathsMiddleware`` enforces it for the crawlers that do not ask.

The trap this module exists to make un-repeatable: a robots.txt client obeys exactly ONE group, the
most specific ``User-agent`` that matches it. A named group **replaces** the ``*`` group, it does not
extend it, so every named group repeats :func:`private_prefixes` (``public/tests/test_seo.py``
asserts it agent by agent).
"""

from __future__ import annotations

from django.http import HttpRequest

#: Agents that answer a user's question by citing a page, plus the training crawlers. Allowing
#: training is deliberate: it is the only path to a model knowing what ERPlora is without
#: searching first, and the public web is a sales page.
ANSWER_ENGINE_AGENTS = (
    "OAI-SearchBot",  # builds ChatGPT search's index, the one that gets us cited
    "ChatGPT-User",  # live fetch when a user asks ChatGPT about us
    "PerplexityBot",
    "Perplexity-User",
    "ClaudeBot",
    "Claude-User",
    "Google-Extended",  # grounding for Gemini and AI Overviews
    "Applebot-Extended",
    "GPTBot",
    "CCBot",
    "meta-externalagent",
    "Amazonbot",
    "Bytespider",
)

#: The header served on everything that is not the public web. ``noarchive`` so a cached copy of
#: a private page cannot outlive the page itself.
NOINDEX_HEADER = "noindex, nofollow, noarchive"

#: URL name of the SPA's catch-all (``config/urls.py``): every page of the account panel.
SPA_URL_NAME = "spa"


def private_prefixes() -> tuple[str, ...]:
    """Every path prefix that is not the public web.

    Django's own (admin, API, internal calls, allauth's pages and headless API, Google's redirect
    URIs, the jump to a hub, Stripe's webhook) and the sign-in pages of the SPA (``accounts/frontend/routes.ts`` and
    the pages allauth's mails link, ``HEADLESS_FRONTEND_URLS``). Without a trailing slash where the
    SPA serves the bare path (``/launch``, ``/login``…). Any other page of the SPA is private too:
    :func:`is_private` recognises its route.
    """
    return (
        "/admin/",
        "/api/",
        "/internal/",
        "/_allauth/",
        "/accounts/",
        "/auth/",
        "/hub-login/",
        "/webhooks/",
        "/launch",
        "/login",
        "/signup",
        "/password",
        "/verify-email",
        "/2fa",
        "/reauthenticate",
    )


def is_private(request: HttpRequest) -> bool:
    """Whether ``request`` is for the private half: a private prefix or any page of the SPA."""
    if request.path.startswith(private_prefixes()):
        return True
    match = getattr(request, "resolver_match", None)
    return match is not None and not match.namespace and match.url_name == SPA_URL_NAME


class NoIndexPrivatePathsMiddleware:
    """``X-Robots-Tag: noindex`` on every private response.

    robots.txt is advisory; this is not. It also covers what robots.txt cannot: a redirect to the
    login is still a URL a crawler can index, and it leaks the shape of the private site.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if is_private(request):
            response["X-Robots-Tag"] = NOINDEX_HEADER
        return response
