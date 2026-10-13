"""``/robots.txt`` and ``/llms.txt`` of the public web (spec §8.2).

Ported from ERPlora/saas ``apps/public/landing/views.py`` (origin/develop c5ca8ca). Both are
machine-facing English files, not interface text: they are not translated.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe

from public import store
from public.crawlers import ANSWER_ENGINE_AGENTS, private_prefixes

#: Sections of llms.txt after the summary: ``(title, ((URL name, link text, note), …))``. Only
#: pages that exist; each batch of the port adds its own. An empty section is omitted. The apps
#: section (``## Apps``) goes before «Optional», built from the listed apps (``_apps_section``).
LLMS_SECTIONS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "Start here",
        (
            (
                "public:home",
                "What ERPlora is",
                "the product in one page — apps, pricing and the counter app.",
            ),
            (
                "public:pricing",
                "Pricing",
                "plans, what each includes, and the answers to the usual billing questions.",
            ),
            (
                "public:features",
                "Features",
                "what the platform does across ERP, POS and back office.",
            ),
            (
                "public:industries_index",
                "Industries",
                "how it is set up for restaurants, salons and shops.",
            ),
            (
                "public:security",
                "Security",
                "how customer data is isolated and protected.",
            ),
            (
                "public:app",
                "Counter app",
                "the installable app that drives printers and cash drawer.",
            ),
            ("public:about", "About", "who builds ERPlora."),
        ),
    ),
    (
        "Optional",
        (
            (
                "public:terms",
                "Terms",
                "the terms of use, with the trial, the exit package and the update policy.",
            ),
            (
                "public:privacy",
                "Privacy",
                "how ERPlora processes personal data under the GDPR.",
            ),
            ("public:contact", "Contact", "how to reach the team."),
        ),
    ),
)


@require_safe
def robots_txt(request: HttpRequest) -> HttpResponse:
    """The answer engines get the public web, and only the public web.

    Every agent of ``ANSWER_ENGINE_AGENTS`` gets a group of its own, and each repeats the private
    paths: a client obeys exactly one group, so a named group replaces ``*`` rather than adding to
    it. ``Disallow:`` goes before ``Allow: /`` on purpose: RFC 9309 picks the most specific rule,
    but ``urllib.robotparser`` (and the crawlers built on it) picks the first that matches, and with
    this order the file means the same under both readings.
    """
    lines: list[str] = []
    for agents in (("*",), *((agent,) for agent in ANSWER_ENGINE_AGENTS)):
        lines.extend(f"User-agent: {agent}" for agent in agents)
        lines.extend(f"Disallow: {prefix}" for prefix in private_prefixes())
        lines.append("Allow: /")
        lines.append("")
    lines.append(f"Sitemap: https://{request.get_host()}/sitemap.xml")
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_safe
def llms_txt(request: HttpRequest) -> HttpResponse:
    """``/llms.txt`` (llmstxt.org): what ERPlora is, then the pages that answer what buyers ask.

    The private half is absent by construction: nothing below names a URL that is not public.
    """
    base = f"https://{request.get_host()}"
    lines = [
        "# ERPlora",
        "",
        "> ERPlora is a modular cloud ERP and POS for small businesses — restaurants, "
        "hair and beauty salons, and retail. You turn on only the apps you need; they all "
        "share one database, one interface and one login, so there are no integrations to "
        "maintain. Spanish VeriFactu invoicing is built in, and a free desktop/mobile app "
        "drives the counter's receipt printer and cash drawer.",
        "",
        "Hosted in the EU. Free plan with no card; paid plans add capacity and premium apps. "
        "Each customer gets an isolated Hub with its own database.",
        "",
    ]
    apps_section = _apps_section(base)
    for title, pages in LLMS_SECTIONS:
        if title == "Optional":
            lines += apps_section
            apps_section = []
        if not pages:
            continue
        lines += [f"## {title}", ""]
        lines += [
            f"- [{text}]({base}{reverse(name)}): {note}" for name, text, note in pages
        ]
        lines.append("")
    lines += apps_section
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def _apps_section(base: str) -> list[str]:
    """``## Apps``: the listed apps of the catalog, read live (never a list that goes stale), each
    linked to its page in the store. Without a listed app the section is omitted (spec §5.3)."""
    apps = store.listed_apps()
    if not apps:
        return []
    return [
        "## Apps",
        "",
        f"The catalog below is the live one ({len(apps)} listed apps).",
        "",
        *(
            f"- [{app.name}]({base}{reverse('public:store_detail', args=[app.id])}): "
            f"{' '.join(app.summary.split())}"
            for app in apps
        ),
        "",
    ]
