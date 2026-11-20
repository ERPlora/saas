"""What the tests of ``/pricing/`` and ``/pricing/<slug>/`` (public/pricing.py) share: the plans they create, the
page they read and the pieces of it they look at.

* ``public`` imports no model: the pages read ``hubs.plan.list``. The tests create the rows with the ORM of ``hubs``
  (``name_en``, ``features_en``…) and read the page or its context, whose plans are dicts matched by ``slug``.
* The cards are the ``ep-pricing-card`` partial, so the helper that reads a card's ✓ lines reads that partial's
  markup.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from django.conf import settings

from hubs.models import Plan

INDEX = "/pricing/"


def make_plan(slug: str, *, trial_days: int = 0, features=None, **fields) -> Plan:
    defaults = {
        "name_en": slug.replace("-", " ").title(),
        "description_en": f"{slug} plan",
        "price_monthly": Decimal("29.99"),
        "trial_period_days": trial_days,
        "features_en": ["Unlimited users"] if features is None else features,
        "is_active": True,
    }
    return Plan.objects.create(slug=slug, **{**defaults, **fields})


def get(client, path: str = INDEX, language: str | None = None):
    if language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response


def html_of(client, path: str = INDEX, language: str | None = None) -> str:
    return get(client, path, language).content.decode()


CARD_START = re.compile(r'<div class="ep-pricing-card(?: ep-pricing-card--featured)?">')
CARD_ITEM = re.compile(
    r'<li><span class="ep-pricing-card__check" aria-hidden="true">✓</span><span>(.*?)</span></li>',
    re.S,
)


def card_items(html: str, plan_name: str) -> list[str]:
    """The ✓ lines of one plan card, so the note under the cards cannot make a test pass."""
    cards = [
        chunk
        for chunk in CARD_START.split(html)[1:]
        if f'<div class="ep-pricing-card__name">{plan_name}</div>' in chunk
    ]
    assert cards, f"no pricing card for {plan_name}"
    card = cards[0].split("</ul>", 1)[0]
    return [" ".join(item.split()) for item in CARD_ITEM.findall(card)]


VAT_NOTE = re.compile(r"<p\b[^>]*>(?:(?!</p>).)*?All prices exclude VAT.*?</p>", re.S)


def vat_note(html: str) -> str:
    """The ex-VAT note under the prices, so the footer's own terms link cannot make a test pass."""
    notes = VAT_NOTE.findall(html)
    assert len(notes) == 1, f"expected one ex-VAT note, found {len(notes)}"
    return notes[0]


def json_ld_blocks(html: str) -> list[dict]:
    marker = '<script type="application/ld+json">'
    blocks, cursor = [], 0
    while (start := html.find(marker, cursor)) != -1:
        start += len(marker)
        end = html.index("</script>", start)
        blocks.append(json.loads(html[start:end]))
        cursor = end
    return blocks


def faq_page_of(html: str) -> dict:
    block = next(
        (block for block in json_ld_blocks(html) if block.get("@type") == "FAQPage"),
        None,
    )
    assert block, "no FAQPage JSON-LD on /pricing/"
    return block


UPGRADE_SECTION = '<section id="more-capacity"'


def upgrade_section(html: str) -> str:
    """The «More capacity» section: the upgrade-only plans."""
    assert UPGRADE_SECTION in html, "no «More capacity» section on /pricing/"
    return html.split(UPGRADE_SECTION, 1)[1].split("</section>", 1)[0]


def visible_markup(html: str) -> str:
    """The page with every ``<script>`` and hidden form field removed: what a reader actually sees (the
    footer's language forms carry Django's ``csrfmiddlewaretoken``, which no reader sees)."""
    html = re.sub(r'<input type="hidden"[^>]*>', "", html, flags=re.IGNORECASE)
    return re.sub(
        r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )


PRICE_400 = re.compile(r"(?<![\d.,])400(?![\d.,])")


def visible_text(html: str) -> str:
    """What a reader reads: :func:`visible_markup` without its tags (``data-reveal-delay="400"`` is no price)."""
    return re.sub(r"<[^>]+>", " ", visible_markup(html))


TABLE_RE = re.compile(r'<table[^>]*id="plan-compare".*?</table>', re.S)


#: The columns of the comparison table: plan, price, devices and users, apps turned on at once, database throughput, AI
#: assistant, WhatsApp, own domain (while a plan on sale includes one), support and access.
COLUMNS = 10


def plan_table(html: str) -> str:
    match = TABLE_RE.search(html)
    assert match, (
        "the plan comparison table lost its `plan-compare` id: this guard is blind"
    )
    return match.group(0)


def table_head(table: str) -> list[str]:
    return re.findall(r"<th\b[^>]*>(.*?)</th>", table.split("</thead>", 1)[0])


def plan_rows(table: str) -> list[str]:
    """The table's plan rows, in order (not the group rows nor the head)."""
    return [row for row in table.split("<tr")[1:] if "<strong>" in row]


def column_cells(table: str, title: str) -> list[str]:
    """The cell of the column ``title`` in each plan row, in the table's order."""
    cells = []
    for row in plan_rows(table):
        match = re.search(rf'<td data-title="{title}">(.*?)</td>', row, re.S)
        assert match, row[:200]
        cells.append(" ".join(match.group(1).split()))
    return cells


PAINTED_AMOUNT = re.compile(r'<span class="ep-pricing-card__amount">€([\d.,]+)</span>')


def painted_prices(html: str) -> dict[str, Decimal]:
    """Each card's name and the amount it paints."""
    names = re.findall(r'<div class="ep-pricing-card__name">(.*?)</div>', html)
    amounts = PAINTED_AMOUNT.findall(html)
    assert len(names) == len(amounts)
    return {name: Decimal(amount.replace(",", "")) for name, amount in zip(names, amounts)}
