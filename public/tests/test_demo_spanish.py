"""The demo's door, its wait and its jump, in Spanish (public/demo.py)."""

import gettext
from pathlib import Path

import pytest
from django.conf import settings

from public.tests.demo_pages import DOOR, code_calls, demo_calls, enter, page, spanish, start

pytestmark = pytest.mark.usefixtures("demo_settings")


# --- Spanish ---------------------------------------------------------------------------------------------


SPANISH_CATALOG = Path(settings.BASE_DIR) / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "english", "spanish_text"),
    [
        ({}, "Try the demo", "Prueba la demo"),
        ({}, "The demo hub is yours for 60 minutes", "El hub de demostración es tuyo durante 60 minutos"),
        ({"state": "expired"}, "This demo has ended. Start another one.", "Esta demo ha terminado. Empieza otra."),
        ({"state": "full"}, "The demo is full right now.", "La demo está llena ahora mismo."),
        ({"state": "throttled"}, "Too many demos from your network.", "Demasiadas demos desde tu red."),
        ({"state": "unavailable"}, "The demo is not available right now.", "La demo no está disponible ahora mismo."),
        ({"state": "failed"}, "We could not open your demo.", "No hemos podido abrir tu demo."),
        (
            {"state": "not_ready"},
            "Your demo is not ready yet. Try again in a moment.",
            "Tu demo aún no está lista. Vuelve a intentarlo en un momento.",
        ),
    ],
)
def test_the_door_speaks_spanish(client, query, english, spanish_text):
    html = page(spanish(client).get(DOOR, query))

    assert spanish_text in html
    assert english not in html


@pytest.mark.django_db
def test_the_switched_off_door_speaks_spanish(client, settings):
    settings.DEMO_ENABLED = False

    html = page(spanish(client).get(DOOR))

    assert "La demo está cerrada por ahora." in html


@pytest.mark.django_db
def test_a_demo_being_prepared_is_told_in_spanish(client, hub_double):
    spanish(client)
    start(client, hub_double, ready=False)

    html = page(client.get(DOOR))

    assert "Preparando tu demo…" in html
    assert "Tarda unos segundos y se abre sola cuando está lista." in html
    assert "Preparing your demo" not in html


@pytest.mark.django_db
def test_trying_the_same_demo_again_is_told_in_spanish(client, hub_double):
    spanish(client)
    start(client, hub_double, ready=False)

    html = page(client.get(DOOR, {"state": "not_ready"}))

    assert "Volver a intentarlo" in html


@pytest.mark.django_db
def test_a_live_demo_is_told_in_spanish(client, hub_double):
    spanish(client)
    start(client, hub_double)

    html = page(client.get(DOOR))

    assert "Volver a mi demo" in html
    assert "Termina en 60 minutos." in html


@pytest.mark.django_db
def test_the_jump_into_a_demo_speaks_spanish(client, hub_double):
    spanish(client)
    slug = start(client, hub_double)

    html = page(enter(client, slug))

    assert "<p>Abriendo tu demo…</p>" in html
    assert "Opening your demo…" not in html


@pytest.mark.django_db
def test_the_visitors_language_goes_to_the_hub(client, hub_double):
    spanish(client)
    slug = start(client, hub_double)

    page(enter(client, slug))

    (demo_call,) = demo_calls(hub_double)
    (code_call,) = code_calls(hub_double)
    assert (demo_call.body["language"], code_call.body["language"]) == ("es", "es")


def test_the_one_minute_left_is_singular_in_both_languages():
    with SPANISH_CATALOG.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)

    assert catalog.ngettext("It ends in %(minutes)s minute.", "It ends in %(minutes)s minutes.", 1) == (
        "Termina en %(minutes)s minuto."
    )
    assert catalog.ngettext("It ends in %(minutes)s minute.", "It ends in %(minutes)s minutes.", 5) == (
        "Termina en %(minutes)s minutos."
    )
