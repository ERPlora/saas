"""``/industries/<slug>/``: the answer to the buyer's question, its price and FAQ, and which slug answers."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.conf import settings
from django.urls import reverse

from hubs.models import Plan
from public.tests.conftest import without_tokens
from public.tests.industry_pages import HOST, _main, _page, make_business_type

pytestmark = [pytest.mark.django_db]


def _blocks(html: str) -> list[dict]:
    """Every JSON-LD block on the page, PARSED: a block that does not parse is not markup."""
    marker = '<script type="application/ld+json">'
    blocks, cursor = [], 0
    while (start := html.find(marker, cursor)) != -1:
        start += len(marker)
        end = html.index("</script>", start)
        blocks.append(json.loads(html[start:end]))
        cursor = end
    return blocks


def _of_type(html: str, wanted: str) -> dict:
    for block in _blocks(html):
        if block.get("@type") == wanted:
            return block
    raise AssertionError(f"no {wanted} JSON-LD on the page")


# --- The detail: the answer to the buyer's question --------------------------------------------


def test_the_h1_asks_the_buyers_question_and_not_just_the_business_name(client, salon):
    html = _main(_page(client).content.decode())
    heading = html[html.index("<h1") : html.index("</h1>")]

    assert "Hair salon" in heading or "hair salon" in heading, (
        "the business type must still be named"
    )
    assert "POS" in heading and "ERP" in heading, (
        f"the H1 is still the bare catalogue label — nobody searches for it: {heading!r}"
    )


def test_the_heading_check_would_catch_the_bare_label(client, salon):
    """Control: prove the assertion above is not vacuous — a bare-label heading fails it."""
    bare = "<h1 class='ep-hero__title'>Hair salon</h1>"

    assert not ("POS" in bare and "ERP" in bare)


def test_the_lead_answers_before_any_marketing(client, salon, entry_plan):
    response = _page(client)
    lead = response.context["industry"]["lead"]

    assert lead, (
        "the taxonomy has no description for this type and the page said nothing"
    )
    assert "Hair salon" in lead or "hair salon" in lead
    assert lead in response.content.decode(), "the lead is computed but never rendered"


def test_the_lead_is_also_the_meta_description(client, salon, entry_plan):
    response = _page(client)
    html = response.content.decode()
    lead = response.context["industry"]["lead"]

    assert f'name="description" content="{lead}"' in html, (
        "meta description still comes from the (usually empty) taxonomy field"
    )


def test_the_offer_price_comes_from_the_plan_table(no_plans, client, salon, entry_plan):
    offer = _of_type(_page(client).content.decode(), "SoftwareApplication")["offers"]

    assert offer["price"] == "29.99", (
        f"the industry page advertises {offer['price']} and Plan says 29.99"
    )
    assert offer["priceCurrency"] == "EUR"


def test_a_second_price_in_the_plan_table_moves_the_page(no_plans, client, salon, entry_plan):
    """Positive control for the test above: if the page were still hardcoding a number, changing
    the cheapest plan would not move it."""
    Plan.objects.create(
        slug="cheaper-sentinel",
        name_en="Cheaper",
        price_monthly=Decimal("9.99"),
        display_order=-30,
    )

    offer = _of_type(_page(client).content.decode(), "SoftwareApplication")["offers"]

    assert offer["price"] == "9.99"


def test_with_no_listable_plan_the_page_advertises_no_price_at_all(no_plans, client, salon):
    """Advertising a price we do not charge is worse than none: never a ``"price": "0"`` by default."""
    block = _of_type(_page(client).content.decode(), "SoftwareApplication")

    assert "offers" not in block, (
        f"a price was invented with no Plan in the table: {block.get('offers')}"
    )


def test_internal_and_upgrade_only_plans_are_not_the_advertised_entry_price(
    no_plans, client, salon, entry_plan
):
    """The advertised price must be one a visitor can actually buy — the same door `/pricing/`
    lists through."""
    Plan.objects.create(
        slug="internal-sentinel",
        name_en="Internal",
        price_monthly=Decimal("0.01"),
        display_order=-99,
        internal_only=True,
    )
    Plan.objects.create(
        slug="upgrade-sentinel",
        name_en="Upgrade",
        price_monthly=Decimal("0.02"),
        display_order=-98,
        upgrade_only=True,
    )

    offer = _of_type(_page(client).content.decode(), "SoftwareApplication")["offers"]

    assert offer["price"] == "29.99"


def test_the_lead_and_the_faq_state_the_entry_price(no_plans, client, salon, entry_plan):
    response = _page(client)
    lead = response.context["industry"]["lead"]
    price_answers = [
        str(item["answer"])
        for item in response.context["faq_items"]
        if item["key"] == "price"
    ]

    assert "Plans start at €29.99 per month per hub, VAT excluded." in lead
    assert len(price_answers) == 1
    assert price_answers[0].startswith("Plans start at €29.99")


@pytest.mark.parametrize(
    ("language", "answer"),
    [
        (
            "en",
            "Plans start at €29.99 per month per hub, VAT excluded. One subscription covers the "
            "whole business — every device and every user in it — and every plan includes all the "
            "apps; you never pay per transaction.",
        ),
        (
            "es",
            "Los planes empiezan en 29.99 € al mes por hub, IVA no incluido. Una suscripción cubre "
            "todo el negocio —todos sus dispositivos y todos sus usuarios— y todos los planes "
            "incluyen todas las apps; nunca pagas por transacción.",
        ),
    ],
)
def test_the_price_answer_puts_every_app_on_every_plan(
    no_plans, client, salon, entry_plan, language, answer, tokens_spelling
):
    """Every plan includes every app: the answer never keeps the premium apps for the paid plans."""
    tokens_spelling("premium")
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = _page(client)
    (price,) = [
        str(item["answer"]) for item in response.context["faq_items"] if item["key"] == "price"
    ]

    assert price == answer
    assert "premium" not in without_tokens(response.content.decode()).lower()


def test_a_free_entry_plan_is_announced_as_free_and_permanent(no_plans, client, salon):
    Plan.objects.create(
        slug="free", name_en="Free", price_monthly=Decimal("0"), display_order=0
    )

    response = _page(client)

    assert (
        "The Free plan is free and permanent, with no card."
        in response.context["industry"]["lead"]
    )
    offer = _of_type(response.content.decode(), "SoftwareApplication")["offers"]
    assert offer["price"] == "0.00"


def test_a_quote_in_the_business_name_does_not_break_the_markup(
    client, sector, entry_plan
):
    make_business_type(
        "quoted", name_en='Salon "Le Chic" & Co </script>', sector=sector
    )

    html = _page(client, "quoted").content.decode()

    block = _of_type(
        html, "SoftwareApplication"
    )  # _blocks raises if any block is invalid JSON
    assert 'Salon "Le Chic" & Co </script>' in block["name"], (
        f"the name reached the JSON-LD HTML-escaped instead of JSON-escaped: {block['name']!r}"
    )


def test_naive_interpolation_would_have_broken_it(client):
    """Control: the name above really is hostile — pasted into a JSON string it is invalid."""
    naive = '{"name": "Salon "Le Chic" & Co </script>"}'

    with pytest.raises(json.JSONDecodeError):
        json.loads(naive)


def test_every_faq_question_is_both_visible_and_marked_up(client, salon, entry_plan):
    response = _page(client)
    html = response.content.decode()
    items = response.context["faq_items"]

    assert len(items) >= 3, "an FAQ of one question is not an FAQ"

    marked_up = {q["name"] for q in _of_type(html, "FAQPage")["mainEntity"]}
    assert marked_up == {str(item["question"]) for item in items}, (
        "the markup and the page disagree"
    )
    for item in items:
        assert str(item["question"]) in html, (
            f"{item['question']!r} is marked up but not on the page"
        )
        assert str(item["answer"]) in html, (
            f"the answer to {item['question']!r} is markup-only"
        )


def test_the_faq_names_the_business_type_it_is_answering_about(
    client, salon, entry_plan
):
    questions = " ".join(
        str(item["question"]) for item in _page(client).context["faq_items"]
    )

    assert "hair salon" in questions.lower(), (
        "a generic FAQ answers nobody's actual question"
    )


@pytest.mark.parametrize("target", ["/pricing/", "/apps/", "/features/"])
def test_the_page_links_onward(client, salon, entry_plan, target):
    assert f'href="{target}' in _main(_page(client).content.decode()), (
        f"no internal link to {target} in the page's own content"
    )


@pytest.mark.parametrize("target", ["/pricing/", "/apps/", "/features/"])
def test_each_onward_link_is_a_real_link_and_not_a_slot_that_does_not_exist(
    client, salon, entry_plan, target
):
    """The card is the link itself: an `<a class="ep-feature-card">` around the tile, not an `<a slot="footer">` that
    a card without that slot never renders."""
    main = _main(_page(client).content.decode())

    assert f'<a class="ep-feature-card" href="{target}"' in main, (
        f"{target} is not the href of a feature card"
    )
    assert 'slot="footer"' not in main


def test_the_link_check_ignores_the_footer(client, salon, entry_plan):
    """Control: the footer links to /industries/ on every public page, so the assertions above
    would pass on an untouched template if they read the whole document."""
    html = _page(client).content.decode()

    assert 'href="/industries/"' in html[html.index("</main>") :], (
        "the footer stopped linking to /industries/"
    )
    assert 'href="/industries/"' not in _main(html)


def test_the_new_copy_stays_pan_european(client, salon, entry_plan):
    """Same contract as `TestTheyStayPanEuropean`, restated where the new copy is written so it
    cannot be reintroduced by an FAQ answer or a link label."""
    assert "verifactu" not in _page(client).content.decode().lower()


def test_the_new_copy_is_translated_to_spanish(client, salon, entry_plan):
    """English is the source string, Spanish a shipped translation: the H1 and the FAQ come out
    different from their English source. `LocaleMiddleware` picks the language per request, so the
    page is asked for in Spanish the way a Spanish reader's browser asks for it."""
    english = _page(client).context["industry"]["headline"]

    spanish_response = _page(client, headers={"accept-language": "es"})
    spanish = spanish_response.context["industry"]["headline"]
    faq_es = [str(item["question"]) for item in spanish_response.context["faq_items"]]

    assert spanish != english, f"the H1 is untranslated: {spanish!r}"
    assert "Software TPV" in spanish
    assert "peluquería" in spanish, "the business type is named in Spanish"
    assert any("¿" in question for question in faq_es), (
        f"the FAQ is untranslated: {faq_es}"
    )


def test_the_translation_check_is_looking_at_a_string_that_can_change(
    client, salon, entry_plan
):
    """Control: the assertion above compares two renders, so prove the English one is what we
    think it is — otherwise `spanish != english` could be true for the wrong reason."""
    assert (
        _page(client).context["industry"]["headline"].startswith("POS and ERP software")
    )


# --- The detail: which slug answers -------------------------------------------------------------


def test_a_retired_code_is_sent_on_for_good_to_its_replacement(client, salon):
    """``peluqueria`` was folded into ``hair_salon``: an indexed URL keeps working."""
    response = client.get("/industries/peluqueria/", HTTP_HOST=HOST)

    assert response.status_code == 301
    assert response["Location"] == "/industries/hair_salon/"


def test_a_code_in_another_case_is_sent_to_the_canonical_url(client, salon):
    response = client.get("/industries/Hair_Salon/", HTTP_HOST=HOST)

    assert response.status_code == 301
    assert response["Location"] == "/industries/hair_salon/"


def test_an_unknown_or_inactive_business_type_is_a_404(client, sector):
    make_business_type("closed", sector=sector, is_active=False)

    assert client.get("/industries/closed/", HTTP_HOST=HOST).status_code == 404
    assert client.get("/industries/nope/", HTTP_HOST=HOST).status_code == 404


def test_the_url_names_resolve():
    assert reverse("public:industries_index") == "/industries/"
    assert (
        reverse("public:industries_detail", kwargs={"slug": "hair_salon"})
        == "/industries/hair_salon/"
    )
