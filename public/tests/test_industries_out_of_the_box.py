"""``/industries/`` and ``/industries/<slug>/``: an app available for a business type is not turned on."""

from __future__ import annotations

import pytest

from apps.tests.factories import make_app
from public.tests.conftest import without_tokens
from public.tests.industry_pages import HOST, INDEX, _main, _page, make_business_type, make_sector

pytestmark = [pytest.mark.django_db]


# --- Available is not turned on -----------------------------------------------------------------
# Every business is born with every app off, a demo too: the apps of a vertical are the ones made for it, included in
# every plan, and the business turns them on with the template its Home suggests or one at a time. So no page says a
# business «comes with» them «out of the box» or «turned on from day one», nor that the point of sale, the catalogue,
# customers and invoicing «come with every hub».

OUT_OF_THE_BOX = (
    "comes with",
    "come with every hub",
    "out of the box",
    "turned on from day one",
    "same core",
    "de serie",
    "vienen con cada hub",
    "desde el primer día",
    "mismo núcleo",
)

HOW_APPS_TURN_ON = {
    "en": (
        "Your business starts with no app turned on: its Home suggests a template that turns on "
        "the apps of a business like yours, or you turn them on one at a time."
    ),
    "es": (
        "Tu negocio empieza sin ninguna app activada: su Inicio te propone una plantilla que "
        "activa las apps de un negocio como el tuyo, o las activas una a una."
    ),
}

LANGUAGES = pytest.mark.parametrize("language", ["en", "es"])


@pytest.fixture
def restaurant():
    """A business type whose vertical has two listed apps: the page lists them."""
    hospitality = make_sector("hospitality", name_en="Hospitality", name_es="Hostelería")
    make_business_type(
        "restaurant",
        name_en="Restaurant",
        name_es="Restaurante",
        sector=hospitality,
        vertical="restaurant",
    )
    make_app("kitchen", name_en="Kitchen Display", name_es="Pantalla de cocina", verticals=["restaurant"])
    make_app("tables", name_en="Tables", name_es="Mesas", verticals=["restaurant"])


def _promises(html: str) -> list[str]:
    return [phrase for phrase in OUT_OF_THE_BOX if phrase in html]


@LANGUAGES
def test_the_index_promises_no_app_out_of_the_box(client, sector, salon, language):
    """The hero, the meta description and the Open Graph description: none says «comes with»."""
    html = without_tokens(
        client.get(INDEX, HTTP_HOST=HOST, headers={"accept-language": language}).content.decode()
    )

    assert _promises(html) == []


@pytest.mark.parametrize(
    ("language", "hero", "meta", "og"),
    [
        (
            "en",
            "Find your business type and see the apps made for it: ERPlora is ready for 1 type of business.",
            "Discover how ERPlora adapts to your business, with the apps made for a restaurant, a salon, a shop or a clinic.",
            "Discover how ERPlora adapts to your business, with the apps made for every type of business.",
        ),
        (
            "es",
            "Encuentra tu tipo de negocio y mira las apps pensadas para él: ERPlora está listo para 1 tipo de negocio.",
            "Descubre cómo ERPlora se adapta a tu negocio, con las apps pensadas para un restaurante, una peluquería, una tienda o una clínica.",
            "Descubre cómo ERPlora se adapta a tu negocio, con las apps pensadas para cada tipo de negocio.",
        ),
    ],
)
def test_the_index_speaks_of_the_apps_made_for_each_business_type(
    client, sector, salon, language, hero, meta, og
):
    html = client.get(INDEX, HTTP_HOST=HOST, headers={"accept-language": language}).content.decode()

    assert hero in _main(html)
    assert f'<meta name="description" content="{meta}">' in html
    assert f'<meta property="og:description" content="{og}">' in html


@LANGUAGES
def test_the_detail_promises_no_app_out_of_the_box(client, restaurant, entry_plan, language):
    """Page, FAQ and FAQPage JSON-LD: the whole document, since the markup repeats the answers."""
    html = without_tokens(
        _page(client, "restaurant", headers={"accept-language": language}).content.decode()
    )

    assert _promises(html) == []


@pytest.mark.parametrize(
    ("language", "title"),
    [("en", "Apps made for your restaurant"), ("es", "Apps pensadas para tu restaurante")],
)
def test_the_apps_block_says_who_they_are_made_for_and_how_they_are_turned_on(
    client, restaurant, language, title
):
    main = _main(_page(client, "restaurant", headers={"accept-language": language}).content.decode())
    block = main[: main.index('id="faq"')]

    assert f'<h2 class="ep-section-title">{title}</h2>' in block
    assert f'<p class="ep-section-sub">{HOW_APPS_TURN_ON[language]}</p>' in block


@pytest.mark.parametrize(
    ("language", "fit"),
    [
        (
            "en",
            (
                "Yes. Our catalogue has 2 apps made for a restaurant — among them Kitchen Display, "
                "Tables — and they all work on the same data."
            ),
        ),
        (
            "es",
            (
                "Sí. Nuestro catálogo tiene 2 apps pensadas para tu restaurante —entre ellas "
                "Mesas, Pantalla de cocina— y todas trabajan sobre los mismos datos."
            ),
        ),
    ],
)
def test_with_apps_the_faq_names_the_apps_made_for_the_business_and_how_they_start(
    client, restaurant, language, fit
):
    answers = {
        item["key"]: str(item["answer"])
        for item in _page(client, "restaurant", headers={"accept-language": language}).context[
            "faq_items"
        ]
    }

    assert answers["fit"] == fit
    assert answers["start"].endswith(HOW_APPS_TURN_ON[language])
    # The catalogue sorts the apps by their name in the visitor's language.
    assert {"en": "Kitchen Display, Tables", "es": "Mesas, Pantalla de cocina"}[language] in answers["start"]


@LANGUAGES
def test_without_apps_the_faq_promises_no_core_that_comes_with_every_hub(
    client, salon, entry_plan, language
):
    """Without apps, the FAQ never says the point of sale, the catalogue, customers and invoicing «come with every
    hub» on «the same core»: they are apps too, off like every other."""
    response = _page(client, headers={"accept-language": language})
    answers = {item["key"]: str(item["answer"]) for item in response.context["faq_items"]}

    assert answers["start"].endswith(HOW_APPS_TURN_ON[language])
    assert _promises(answers["fit"] + answers["start"]) == []
    assert _promises(without_tokens(response.content.decode())) == []
