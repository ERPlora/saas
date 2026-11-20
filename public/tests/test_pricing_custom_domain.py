"""The custom domain of the business's public website on ``/pricing/`` and ``/pricing/<slug>/``."""

from __future__ import annotations

from html import unescape

import pytest

from hubs.models import Plan
from hubs.tests.test_plan_catalogue import APP_ON_A_CUSTOM_DOMAIN, CUSTOM_DOMAIN_WORDS
from public.tests.pricing_pages import INDEX, card_items, column_cells, get, html_of, make_plan, plan_table, table_head

pytestmark = [pytest.mark.django_db]


# --- The custom domain of the business's public website -----------------------------------------------------------
# A business can connect its own domain on the plans whose ``includes_custom_domain`` is true: their cards and the table
# say so, read from that row, and only for the public website (the app stays on erplora.com).

CUSTOM_DOMAIN_LINE = {
    "en": "Your own domain for your website (www.yourbusiness.com)",
    "es": "Dominio propio para tu web (www.tunegocio.com)",
}
CUSTOM_DOMAIN_HEADER = {"en": "Own domain", "es": "Dominio propio"}
CUSTOM_DOMAIN_CELL = {"en": "For your website", "es": "Para tu web"}
NOT_INCLUDED = {"en": "Not included", "es": "No incluido"}


def custom_domain_cells(table: str, language: str = "en") -> list[str]:
    """The «Own domain» cell of each plan row, in the table's order."""
    return column_cells(table, CUSTOM_DOMAIN_HEADER[language])


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_card_names_the_custom_domain_only_on_the_plans_that_include_it(client, seeded, language):
    """Standard and the plans above include it (hubs/0013); Free and Starter do not. The line goes after the messages
    a month, where the lines worked out of the plan's row are."""
    html = html_of(client, language=language)
    line = CUSTOM_DOMAIN_LINE[language]
    names = {plan.slug: plan.translated("name", language) for plan in Plan.objects.public()}

    for slug in ("free", "starter"):
        assert line not in card_items(html, names[slug]), slug
    for slug in ("standard", "pro", "enterprise", "max"):
        assert card_items(html, names[slug]).count(line) == 1, slug
    assert card_items(html, names["standard"])[-1] == line


def test_the_cards_follow_the_row_when_staff_change_the_custom_domain(client, seeded):
    Plan.objects.filter(slug="starter").update(includes_custom_domain=True)
    Plan.objects.filter(slug="standard").update(includes_custom_domain=False)
    html = html_of(client)

    assert CUSTOM_DOMAIN_LINE["en"] in card_items(html, "Starter")
    assert CUSTOM_DOMAIN_LINE["en"] not in card_items(html, "Standard")


def test_the_custom_domain_line_comes_before_the_trial(no_plans, client):
    make_plan("starter", trial_days=15, includes_custom_domain=True, whatsapp_messages_per_month=40)

    assert card_items(html_of(client), "Starter") == [
        "Unlimited users", "All the apps turned on at once", "WhatsApp: 40 messages a month", CUSTOM_DOMAIN_LINE["en"],
        "15-day free trial",
    ]  # fmt: skip


@pytest.mark.parametrize(("slug", "included"), [("standard", True), ("starter", False)])
def test_the_detail_names_the_custom_domain_only_if_the_plan_includes_it(client, seeded, slug, included):
    response = get(client, f"/pricing/{slug}/", "es")
    included_block = response.content.decode().split('<h2 class="text-2xl font-semibold mb-6">', 1)[1].split("</ion-card>", 1)[0]

    assert (CUSTOM_DOMAIN_LINE["es"] in included_block) is included
    assert (CUSTOM_DOMAIN_LINE["es"] in response.context["plan"]["own_features"]) is included


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_table_compares_the_custom_domain_of_each_plan(client, seeded, language):
    table = plan_table(html_of(client, language=language))
    head = table_head(table)
    yes, no = CUSTOM_DOMAIN_CELL[language], NOT_INCLUDED[language]

    assert CUSTOM_DOMAIN_HEADER[language] in head
    assert custom_domain_cells(table, language) == [no, no, yes, yes, yes, yes]


def test_the_table_reads_the_custom_domain_from_the_rows(client, seeded):
    Plan.objects.filter(slug="free").update(includes_custom_domain=True)
    Plan.objects.filter(slug="max").update(includes_custom_domain=False)

    cells = custom_domain_cells(plan_table(html_of(client)))

    assert (cells[0], cells[-1]) == ("For your website", "Not included")


@pytest.mark.parametrize("path", [INDEX, "/pricing/standard/"])
@pytest.mark.parametrize("language", ["en", "es"])
def test_without_a_plan_that_includes_it_the_page_names_no_custom_domain(client, seeded, path, language):
    """With no plan on sale that includes one, neither the cards, nor the descriptions, nor the table (no column
    whose every cell says the same) name a custom domain. The whole page, structured data included."""
    Plan.objects.update(includes_custom_domain=False)
    html = unescape(html_of(client, path, language))

    match = CUSTOM_DOMAIN_WORDS.search(html)
    assert match is None, f"{path} ({language}) sells a custom domain: {html[max(0, match.start() - 90) : match.end() + 90]!r}"


@pytest.mark.parametrize("path", [INDEX, "/pricing/standard/"])
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_pricing_page_never_puts_the_app_on_a_custom_domain(client, seeded, path, language):
    """Only the public website goes on the business's domain; the app stays on erplora.com."""
    html = unescape(html_of(client, path, language))

    assert CUSTOM_DOMAIN_WORDS.search(html), "control: the page names the custom domain of the plans that include it"
    assert APP_ON_A_CUSTOM_DOMAIN.search(html) is None
