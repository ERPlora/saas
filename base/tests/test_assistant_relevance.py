"""The tools a turn of the panel's assistant offers for what an account asks (``live.assistant.relevant`` over the
SaaS's real catalogue).

Block A of the QA battery of the assistant with the real model (2026-10-31, docs/plans/2026-10-31-qa-asistente.md of
erplora-next), in order: each question with the operations its turn must offer. A1 asks how something is done (the
documentation search); A2 asks to do it (the operation that does it). The Hub's twin is block B
(``base/tests/test_assistant_relevance.py`` of ERPlora/hub).
"""

import pytest

from base import assistant
from hubs.tests.conftest import ctx_for, make_user, plans  # noqa: F401 - shared fixtures

DOCS = "assistant.docs.search"

BLOCK_A = [
    ("¿Cómo creo un negocio?", {DOCS}),
    ("¿Qué diferencia hay entre el plan Gratis y el Starter?", {DOCS}),
    ("¿Cuánto cuesta el plan Standard y cuántos dispositivos incluye?", {DOCS}),
    ("¿Cómo invito a un empleado a mi negocio?", {DOCS}),
    ("¿Cómo cambio la dirección de mi negocio?", {DOCS}),
    ("¿Cómo descargo una factura de ERPlora?", {DOCS}),
    ("¿Qué pasa con mis datos si borro mi negocio?", {DOCS}),
    ("¿Cómo conecto WhatsApp a mi negocio?", {DOCS}),
    ("¿Qué es VeriFactu y lo tengo incluido?", {DOCS}),
    ("¿Cómo activo el pago con criptomonedas?", {DOCS}),
    ("¿Qué negocios tengo?", {"hubs.business.list"}),
    ("Crea un negocio llamado «QA Asistente 31» en España", {"hubs.business.create"}),
    ("¿Qué plan tiene «QA Asistente 31»?", {"hubs.business.get", "billing.subscription.list"}),
    ("¿Cuánto pago al mes en total?", {"billing.subscription.list"}),
    ("Enséñame mis últimas facturas", {"billing.invoice.list"}),
    ("¿Qué sesiones tengo abiertas?", {"accounts.session.list"}),
    ("Cambia el nombre de «QA Asistente 31» a «QA Asistente 31b»", {"hubs.business.update"}),
    ("Borra el negocio «QA Asistente 31b»", {"hubs.business.delete"}),
    # Not a tool (it hands a secret out): the assistant links to Account, with the documentation.
    ("Crea una clave de API", {DOCS}),
    # Of a business, not of the panel: the assistant sends the person to open it.
    ("¿Cuántas ventas hice ayer en mi negocio?", {"hubs.business.list", DOCS}),
]
#: What the panel's words name (``base.assistant.SYNONYMS``), right after what is always offered: a «tienda» that is
#: the person's, another, new or old is one of their businesses; «la tienda» alone is the panel's Store.
PANEL_WORDS = [
    ("borra mi tienda de pruebas", "hubs.business.delete"),
    ("quiero abrir otra tienda", "hubs.business.create"),
    ("cambia el nombre de mi tienda", "hubs.business.update"),
    ("¿qué vende la tienda?", "billing.store.catalog"),
    ("¿qué módulos hay en la tienda?", "apps.app.list"),
]
#: How-to questions that name what other tools do (the team, the language, the plan): they reach the documentation
#: search as how-to questions (``base.assistant.HOWTO``), not only because it is always offered.
HOW_TO = [
    ("es", "¿cómo añado a alguien a mi equipo?"),
    ("es", "¿cómo cambio el idioma del panel?"),
    ("en", "how do I add someone to my team?"),
    ("en", "tell me how to change my plan"),
]


@pytest.fixture
def account(make_user, plans):  # noqa: F811
    return make_user("lena@example.com", first_name="Lena", language="es")


def offered(ctx, *asked: str) -> list[str]:
    return [op.name for op in assistant.relevant(assistant.catalog(ctx), list(asked), ctx.language)]


@pytest.mark.parametrize(("index", "asked", "expected"), [(i, q, e) for i, (q, e) in enumerate(BLOCK_A)])
def test_each_question_of_the_qa_battery_is_offered_its_tools(account, index, asked, expected):
    ctx = ctx_for(account, "es")
    assert expected <= set(assistant.catalog(ctx))  # the account holds them: only the selection can leave one out
    # A turn ranks by the last two questions of the person (``base.assistant.turn``): the battery asks them in order.
    before = BLOCK_A[index - 1][0] if index else None
    for texts in ([asked], [before, asked] if before else [asked]):
        missing = expected - set(offered(ctx, *texts))
        assert not missing, (texts, missing)


def test_no_tool_hands_an_api_key_out(account):
    assert "accounts.apikey.create" not in assistant.catalog(ctx_for(account, "es"))


@pytest.mark.parametrize(("asked", "expected"), PANEL_WORDS)
def test_the_panels_words_name_what_they_mean_there(account, asked, expected):
    assert offered(ctx_for(account, "es"), asked)[len(assistant.ALWAYS)] == expected


@pytest.mark.parametrize(("language", "asked"), HOW_TO)
def test_a_how_to_question_reaches_the_documentation_search_on_its_own(account, monkeypatch, language, asked):
    monkeypatch.setattr(assistant, "ALWAYS", ())

    assert offered(ctx_for(account, language), asked)[0] == DOCS
