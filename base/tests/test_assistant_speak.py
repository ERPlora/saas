"""ASSISTANT-F22 · The panel of erplora.com reads an answer aloud: ``POST /api/assistant/speak`` (``base.assistant.speak``),
for the signed-in account.

No engine reads aloud (PLAN-SAAS round 2026-11-04c): the panel does not ask, and whoever asks all the same gets the 503
``assistant.speech_unavailable`` that sends the reading to the device. What the route keeps for an engine is held here
with a stand-in: the gateway in process, with no ``/internal`` and no signature, the same cut of the text, the budget of
readings aloud per hour per account (``ASSISTANT_SYNTHESIZE_RATELIMIT``), and the characters read counted in the
account's month without spending a message. A connection never waits inside a transaction, so the operation is the door
(the session, the permission, the budget and the language) and the wait goes after it, in the route, as the dictation's.
"""

import io
import json
import logging

import pytest
from django.core.management import call_command
from live.ninja import ensure_api_parity, operation_ids
from live.operations import current_operation

from assistant import media
from assistant import turn as gateway
from assistant.models import AssistantUsage
from assistant.schemas import Caller
from assistant.tests.conftest import FakeSpeechEngine, fernet_key, speech_engine  # noqa: F401 - the gateway's fixtures
from config.api import api
from hubs.tests.conftest import make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
ROUTE = "/api/assistant/speak"
MP3 = FakeSpeechEngine.MP3
#: A voice of the catalogue that left: whoever still names it hears what anyone else does.
GONE = "es-ES-Ximena:DragonHDLatestNeural"
SECRET_WORDS = "Rosalía Quintanar debe 400 euros"


def post(client, data: dict):
    return client.post(ROUTE, json.dumps(data), content_type="application/json", HTTP_HOST=HOST)


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def month_of(account) -> tuple[int, int]:
    """What the account's month counts: its messages and the characters read aloud (nothing yet, nothing counted)."""
    row = AssistantUsage.objects.filter(user=account).first()
    return (row.messages, row.speech_characters) if row else (0, 0)


@pytest.fixture
def account(make_user):  # noqa: F811
    return make_user("lena@example.com", first_name="Lena", language="en")


@pytest.fixture
def signed_in(client, account):
    client.force_login(account)
    return client


class TestTheRoute:
    def test_it_is_bound_to_its_operation_and_listed_in_the_openapi_as_audio(self, client):
        assert ensure_api_parity(api) == []
        assert "base.assistant.speak" in operation_ids(api)
        route = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"][ROUTE]["post"]
        assert route["operationId"] == "base.assistant.speak"
        assert route["responses"]["200"]["content"]["audio/mpeg"]["schema"] == {"type": "string", "format": "binary"}

    def test_without_a_session_it_is_a_401_and_nothing_is_read(self, client, speech_engine):  # noqa: F811
        assert error(post(client, {"text": "Hola"})) == (401, "unauthorized")
        assert speech_engine.calls == []

    def test_without_the_assistants_permission_it_is_a_403(self, signed_in, speech_engine, monkeypatch):  # noqa: F811
        from live.meta import all_live_app_configs, permissions_for_role

        from base import operations

        granted = permissions_for_role(all_live_app_configs(), operations.ACCOUNT_ROLE) - {"assistant.ask"}
        monkeypatch.setattr(operations, "_permissions", lambda actor: granted)

        assert error(post(signed_in, {"text": "Hola"})) == (403, "permission_denied")
        assert speech_engine.calls == []


class TestWithoutAnEngine:
    """erplora.com as it is: the panel does not ask (``spa-config`` ``assistantSpeech`` false), and whoever asks all the
    same gets the 503 that sends the reading to the device."""

    @pytest.mark.parametrize("change", [{}, {"language": "es"}, {"voice": GONE}, {"voice": "nova"}])
    def test_it_is_a_503_that_counts_nothing(self, signed_in, account, change):
        response = post(signed_in, {"text": "Hola", **change})

        assert error(response) == (503, "assistant.speech_unavailable")
        assert response.json()["error"]["message"] == "Reading aloud is not available right now."
        assert month_of(account) == (0, 0)

    def test_what_it_refuses_speaks_the_language_of_the_account(self, client, make_user):  # noqa: F811
        client.force_login(make_user("es@example.com", language="es"))

        unavailable = post(client, {"text": "Hola"})

        assert error(unavailable) == (503, "assistant.speech_unavailable")
        assert unavailable.json()["error"]["message"] == "La lectura en voz alta no está disponible en este momento."

    @pytest.mark.parametrize(("change", "field"), [({"language": "fr"}, "language"), ({"text": "  "}, "text")])
    def test_what_is_no_reading_is_a_422_naming_its_field_and_spends_nothing(self, signed_in, settings, change, field):
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"

        response = post(signed_in, {"text": "Hola", **change})

        assert error(response) == (422, "invalid_payload")
        assert field in response.json()["error"]["fields"]
        assert error(post(signed_in, {"text": "Hola"})) == (503, "assistant.speech_unavailable")

    def test_its_budget_still_brakes(self, signed_in, settings):
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"

        assert error(post(signed_in, {"text": "Hola"})) == (503, "assistant.speech_unavailable")
        assert error(post(signed_in, {"text": "Hola"})) == (429, "rate_limited")


class TestTheContractOfTheRoute:
    """What an engine finds when it comes (PLAN-SAAS §35): the stand-in in its place."""

    def test_the_answer_comes_back_as_an_mp3_in_the_accounts_language(self, signed_in, speech_engine):  # noqa: F811
        response = post(signed_in, {"text": "You have two bookings today."})

        assert response.status_code == 200
        assert response["Content-Type"] == "audio/mpeg"
        assert response.content == MP3
        assert speech_engine.calls == [("You have two bookings today.", "en", "")]

    @pytest.mark.parametrize(
        ("change", "language", "voice"), [({"language": "es"}, "es", ""), ({"language": "en", "voice": "a-voice"}, "en", "a-voice")]
    )
    def test_it_reads_in_the_language_or_the_voice_asked(self, signed_in, speech_engine, change, language, voice):  # noqa: F811
        assert post(signed_in, {"text": "Hola", **change}).status_code == 200
        assert speech_engine.calls == [("Hola", language, voice)]

    def test_a_language_without_voices_reads_in_english(self, client, make_user, speech_engine, settings):  # noqa: F811
        """A language the panel speaks with no voice yet (none today: the panel speaks ``en`` and ``es``, the two of
        ``assistant.media.SPEECH_LANGUAGES``)."""
        settings.LANGUAGES = [*settings.LANGUAGES, ("fr", "Français")]
        client.force_login(make_user("fr@example.com", language="fr"))

        assert post(client, {"text": "Bonjour"}).status_code == 200
        assert speech_engine.calls == [("Bonjour", "en", "")]

    def test_it_counts_the_characters_in_the_accounts_month_and_spends_no_message(self, signed_in, account, speech_engine):  # noqa: F811
        post(signed_in, {"text": "Hola"})

        assert month_of(account) == (0, 4)

    @pytest.mark.parametrize("retriable", [False, True])
    def test_a_failure_is_a_503_that_counts_nothing_and_names_no_provider(self, signed_in, account, speech_engine, retriable):  # noqa: F811
        speech_engine.failure = media.MediaFailed(retriable=retriable)

        response = post(signed_in, {"text": "Hola"})

        assert error(response) == (503, "base.assistant_speech_failed")
        assert response.json()["error"]["message"] == "The answer could not be read aloud: try again."
        assert month_of(account) == (0, 0)

    def test_a_failure_speaks_the_language_of_the_account(self, client, make_user, speech_engine):  # noqa: F811
        client.force_login(make_user("es@example.com", language="es"))
        speech_engine.failure = media.MediaFailed(retriable=True)

        failed = post(client, {"text": "Hola"})

        assert error(failed) == (503, "base.assistant_speech_failed")
        assert failed.json()["error"]["message"] == "No se ha podido leer la respuesta en voz alta: inténtalo de nuevo."


class TestTheBudget:
    def test_past_its_budget_an_account_waits_and_another_one_does_not(self, signed_in, make_user, speech_engine, settings):  # noqa: F811
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"

        assert post(signed_in, {"text": "Hola"}).status_code == 200
        refused = post(signed_in, {"text": "Hola"})
        assert error(refused) == (429, "rate_limited")
        assert refused.json()["error"]["message"] == "Too many readings aloud in a short time: wait a moment and try again."
        assert len(speech_engine.calls) == 1

        signed_in.force_login(make_user("otra@example.com", language="es"))
        assert post(signed_in, {"text": "Hola"}).status_code == 200

    def test_the_refusal_of_the_budget_speaks_the_language_of_the_account(self, client, make_user, speech_engine, settings):  # noqa: F811
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
        client.force_login(make_user("es@example.com", language="es"))
        post(client, {"text": "Hola"})

        refused = post(client, {"text": "Hola"})

        assert refused.json()["error"]["message"] == "Demasiadas lecturas en voz alta seguidas: espera un momento y vuelve a intentarlo."

    def test_it_spends_the_budget_of_the_readings_aloud_and_no_other_door(self, signed_in, account, speech_engine, settings):  # noqa: F811
        """The Hub's ``synthesize`` door's, per account: a reading aloud never eats what a dictation may spend."""
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"

        assert post(signed_in, {"text": "Hola"}).status_code == 200

        gateway.spend(None, "transcribe", "1/h", Caller(user_id=account.pk))
        with pytest.raises(gateway.Refused):
            gateway.spend(None, "synthesize", "1/h", Caller(user_id=account.pk))


class TestWhileItWaits:
    def test_no_transaction_is_open_while_it_is_read(self, signed_in, monkeypatch):
        seen = []

        async def spying(text, language, voice):
            seen.append(current_operation.get())
            return MP3

        monkeypatch.setattr(media, "SPEECH_ENGINE", spying)

        assert post(signed_in, {"text": "Hola"}).status_code == 200
        assert seen == [None]


class TestItForgets:
    def test_what_is_read_is_kept_in_no_table_and_no_log(self, signed_in, speech_engine, caplog):  # noqa: F811
        """ASSISTANT-F17: what the account hears is forgotten as what the Hub's does, whichever way it ends."""
        caplog.set_level(logging.DEBUG)

        assert post(signed_in, {"text": SECRET_WORDS}).status_code == 200
        speech_engine.failure = media.MediaFailed(retriable=True)
        assert post(signed_in, {"text": SECRET_WORDS}).status_code == 503

        kept = io.StringIO()
        call_command("dumpdata", stdout=kept)
        assert SECRET_WORDS not in kept.getvalue()
        assert SECRET_WORDS not in "\n".join(record.getMessage() for record in caplog.records)
