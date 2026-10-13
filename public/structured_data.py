"""JSON-LD builders of the public web (spec §8.2).

Ported from ERPlora/saas ``apps/public/structured_data.py`` (origin/develop c5ca8ca), without the
marketplace's imports: every builder takes its data (prices from ``Plan``, apps from ``apps.*``
operations) and reads no model, so the pages that call them decide where the data comes from.

Schema.org blocks are what an answer engine parses to state what ERPlora is and what it costs, so
they are built from live data, never hand-written into a template. Serialisation goes through
:func:`json_ld`, not ``|safe`` on a ``json.dumps`` string: a value holding ``</script>`` would close
the tag and turn a data block into markup.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.utils.safestring import SafeString, mark_safe

# `<`, `>` and `&` escaped as unicode: valid JSON, inert inside <script> (as Django's json_script).
_SCRIPT_ESCAPES = {ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026"}


def json_ld(payload: dict) -> SafeString:
    """Serialise a schema.org block for ``<script type="application/ld+json">``."""
    return mark_safe(
        json.dumps(payload, ensure_ascii=False, default=str).translate(_SCRIPT_ESCAPES)
    )


def _offer(price: Decimal | str, url: str) -> dict:
    return {
        "@type": "Offer",
        "price": f"{price}",
        "priceCurrency": "EUR",
        "url": url,
        "availability": "https://schema.org/InStock",
    }


def organization(base: str, logo_url: str) -> dict:
    """Who ERPlora is: the block that answers «what company is this?»."""
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "ERPlora",
        "url": f"{base}/",
        "logo": logo_url,
        "description": (
            "ERPlora builds a modular cloud ERP and POS for small businesses — "
            "restaurants, salons and retail — with Spanish VeriFactu invoicing built in."
        ),
        "areaServed": "ES",
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "sales",
            "url": f"{base}/contact/",
            "availableLanguage": ["es", "en"],
        },
    }


def software_application(
    base: str, cheapest_price: Decimal | None, app_count: int
) -> dict:
    """What ERPlora sells, priced from the live ``Plan`` table.

    ``cheapest_price`` is ``None`` when no plan is listed: the offer is then dropped rather than
    defaulted to ``0``. Advertising a price we do not charge is worse than advertising none.
    """
    block = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "ERPlora",
        "applicationCategory": "BusinessApplication",
        "applicationSubCategory": "ERP, POS",
        "operatingSystem": "Web, Windows, macOS, Android, iOS",
        "url": f"{base}/",
        "description": (
            "Modular cloud ERP and POS for small businesses. Turn on only the apps "
            f"you need — {app_count} of them, sharing one database, one interface and "
            "one login, with no integrations to maintain. Includes point of sale, "
            "inventory, invoicing, appointments and Spanish VeriFactu compliance."
        ),
        "featureList": [
            "Point of sale (restaurant, salon, retail)",
            "Inventory and catalog",
            "Invoicing with Spanish VeriFactu compliance",
            "Appointments and table management",
            "Receipt printing and cash drawer from an installable app",
            "App catalogue: turn on only what you need",
        ],
        "inLanguage": ["es", "en"],
    }
    if cheapest_price is not None:
        block["offers"] = _offer(cheapest_price, f"{base}/pricing/")
    return block


def faq_page(items) -> dict:
    """``FAQPage`` from the same list the page renders visibly: Google treats markup that does not
    match the visible page as a violation, so it takes the rendered items, not a second copy."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": str(item["question"]),
                "acceptedAnswer": {"@type": "Answer", "text": str(item["answer"])},
            }
            for item in items
        ],
    }


def industry_software_application(
    base: str, *, name: str, url: str, description: str, cheapest_price: Decimal | None
) -> dict:
    """``SoftwareApplication`` for one ``/industries/<slug>/`` page.

    Not :func:`software_application` with another name: that one names Spanish VeriFactu, and the
    industry pages are pan-European. Without a listable plan, no offer.
    """
    block = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": name,
        "applicationCategory": "BusinessApplication",
        "applicationSubCategory": "ERP, POS",
        "operatingSystem": "Web, Windows, macOS, Android, iOS",
        "url": url,
        "description": description,
        "inLanguage": ["es", "en"],
    }
    if cheapest_price is not None:
        block["offers"] = _offer(cheapest_price, f"{base}/pricing/")
    return block


def app_software_application(
    base: str,
    *,
    name: str,
    description: str,
    url: str,
    premium: bool,
    cheapest_paid_price: Decimal | None,
) -> dict:
    """``SoftwareApplication`` for one app page (``/apps/<id>/``, spec §8.2).

    A free app is offered at ``0``. A ``premium`` one is included in the paid plans (decision 17):
    its offer is the monthly price of the cheapest paid plan, and none without a paid plan. No
    ``aggregateRating``: there are no reviews.
    """
    block = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": name,
        "description": description,
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web, Windows, macOS, Android, iOS",
        "url": url,
        "author": {"@type": "Organization", "name": "ERPlora"},
    }
    if not premium:
        block["offers"] = _offer("0", url)
    elif cheapest_paid_price is not None:
        block["offers"] = _offer(cheapest_paid_price, f"{base}/pricing/")
    return block
