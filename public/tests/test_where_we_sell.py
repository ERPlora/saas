"""Where the public web says ERPlora sells its paid plans: exactly where the payment sells them.

The payment's rule is ``billing.vat.SOLD_TO_COUNTRIES`` (the payer's billing country) and
``billing.vat.BUSINESS_ONLY_REGIONS`` (the Spanish territories outside VAT, sold to businesses and professionals only),
enforced by ``billing.services.require_sold_to``. Two texts describe it to a visitor: the answer «Is VAT included in
these prices?» of ``/pricing/`` and the clause of the terms with ``id="where-we-sell"``. Both name every country the
payment sells to and no other; neither they nor the ex-VAT note under the prices describe a sale abroad (VIES, the
reverse charge, HMRC) while the payment refuses it. Adding a country to the list, or a country to the texts, fails here
until the other follows, with a new version of the terms.
"""

import re
from html import unescape

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation

from billing import vat
from hubs.countries import PAYER_COUNTRY_NAMES
from public import pricing

TERMS = "/legal/terms/"

#: How the texts call each region of ``vat.BUSINESS_ONLY_REGIONS``, per language.
REGION_NAMES = {
    "IC": {"en": "Canary Islands", "es": "Canarias"},
    "CE": {"en": "Ceuta", "es": "Ceuta"},
    "ML": {"en": "Melilla", "es": "Melilla"},
}

#: The words of selling to a payer abroad: to a business of another member state (VIES, the reverse charge, its
#: intra-EU VAT number) and to the UK (HMRC). A text may only use them while the payment sells there.
EU_ABROAD_WORDS = {
    "en": ("VIES", "reverse charge", "member state"),
    "es": ("VIES", "inversión del sujeto pasivo", "Estado miembro", "NIF-IVA"),
}
UK_WORDS = ("HMRC", "HM Revenue")

#: What the VAT of a sale is worked out from: the payer's billing address (its postal code tells the Canary Islands,
#: Ceuta and Melilla from the rest of Spain), not the tax ID.
BILLING_ADDRESS = {"en": "billing address", "es": "dirección de facturación"}

LANGUAGES = ("en", "es")


def plain(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def terms_clause(client, language: str) -> str:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    html = client.get(TERMS).content.decode()
    match = re.search(r'<section[^>]*id="where-we-sell"[^>]*>(.*?)</section>', html, re.S)
    assert match, "the terms have no clause on where ERPlora sells (id=where-we-sell)"
    return plain(match.group(1))


def vat_answer(language: str) -> str:
    with translation.override(language):
        (item,) = [item for item in pricing.faq_items() if item["key"] == "vat"]
        return str(item["answer"])


def vat_note(language: str) -> str:
    with translation.override(language):
        return plain(render_to_string("public/partials/_vat_note.html"))


def where_we_sell(client, language: str) -> dict[str, str]:
    """The texts that say where ERPlora sells."""
    return {"terms, where-we-sell": terms_clause(client, language), "pricing FAQ, vat": vat_answer(language)}


def countries_named(text: str, language: str) -> set[str]:
    """The billing countries a text names, by the name a payer reads in that language."""
    with translation.override(language):
        names = {code: str(name) for code, name in PAYER_COUNTRY_NAMES.items()}
    return {code for code, name in names.items() if re.search(rf"\b{re.escape(name)}\b", text)}


def abroad_words(text: str, language: str, sold_to: frozenset[str]) -> list[str]:
    """The words of a sale the payment refuses that a text still uses."""
    refused = []
    if not (sold_to & (set(vat.EU_VAT_RATES) - {"ES"})):
        refused += EU_ABROAD_WORDS[language]
    if "GB" not in sold_to:
        refused += UK_WORDS
    return [word for word in refused if word.lower() in text.lower()]


def test_the_checks_tell_a_text_that_sells_abroad():
    """Positive control of the checks below: a text of the old answer is caught by both."""
    old = (
        "A Spanish NIF/CIF/NIE pays 21%. A company in another EU member state with a VAT number we validate "
        "against VIES pays 0% under the reverse charge. In the United Kingdom we sell to businesses."
    )

    assert countries_named(old, "en") == {"GB"}
    assert abroad_words(old, "en", frozenset({"ES"})) == ["VIES", "reverse charge", "member state"]
    assert abroad_words(old, "en", frozenset(vat.BILLING_COUNTRIES)) == []


def test_the_region_names_cover_every_region_sold_to_businesses_only():
    assert set(REGION_NAMES) == vat.BUSINESS_ONLY_REGIONS


@pytest.mark.django_db
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_texts_name_every_country_the_payment_sells_to_and_no_other(client, language):
    for where, text in where_we_sell(client, language).items():
        assert countries_named(text, language) == set(vat.SOLD_TO_COUNTRIES), where


@pytest.mark.django_db
@pytest.mark.parametrize("language", LANGUAGES)
def test_no_text_describes_a_sale_the_payment_refuses(client, language):
    for where, text in {**where_we_sell(client, language), "ex-VAT note": vat_note(language)}.items():
        assert abroad_words(text, language, vat.SOLD_TO_COUNTRIES) == [], where


@pytest.mark.django_db
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_texts_sell_to_businesses_only_in_the_regions_without_vat(client, language):
    for where, text in where_we_sell(client, language).items():
        for region in sorted(vat.BUSINESS_ONLY_REGIONS):
            assert REGION_NAMES[region][language] in text, (where, region)


@pytest.mark.django_db
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_vat_is_worked_out_from_the_billing_address(language):
    for where, text in {"pricing FAQ, vat": vat_answer(language), "ex-VAT note": vat_note(language)}.items():
        assert BILLING_ADDRESS[language] in text, where


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "sells", "free", "modules"),
    [("en", "paid plans", "free plan", "module"), ("es", "planes de pago", "plan gratuito", "módulo")],
)
def test_the_clause_sells_paid_plans_and_leaves_the_free_plan_out(client, language, sells, free, modules):
    """Every plan includes all our apps, so no module is sold on its own; the free plan charges nothing."""
    clause = terms_clause(client, language)

    assert sells in clause
    assert free in clause
    assert modules not in clause.lower()


@pytest.mark.django_db
def test_the_clause_is_translated_into_spanish(client):
    english = terms_clause(client, "en")
    spanish = terms_clause(client, "es")

    assert "España" in spanish
    assert "Spain" not in spanish
    assert english != spanish
