"""ASSISTANT-F22 · The panel of erplora.com reads an answer aloud: ``POST /api/assistant/speak`` (``base.assistant.speak``),
for the signed-in account.

The gateway is called in process, with no ``/internal`` and no signature: the same voices of Azure AI Speech
(``assistant.media.VOICES``), the same cut of the text, the budget of readings aloud per hour per account
(``ASSISTANT_SYNTHESIZE_RATELIMIT``), and the characters read are counted in the account's month without spending a
message. A connection never waits on the provider inside a transaction, so the operation is the door (the session, the
permission, the budget, the language and the voice) and the wait goes after it, in the route, as the dictation's.
Azure is the local fake.
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
from assistant.tests.conftest import fake_provider, fernet_key  # noqa: F401 - the gateway's fixtures
from config.api import api
from hubs.tests.conftest import make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
ROUTE = "/api/assistant/speak"
AZURE_KEY = "not-a-real-azure-speech-key"
AZURE_PATH = "/westeurope/cognitiveservices/v1"
MP3 = b"ID3\x04\x00 spoken words"
XIMENA = "es-ES-Ximena:DragonHDLatestNeural"
TRISTAN = "es-ES-Tristan:DragonHDLatestNeural"
AVA = "en-US-Ava:DragonHDLatestNeural"
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
def azure(fake_provider, settings, monkeypatch):  # noqa: F811 - the gateway's fixture, extended
    """Azure AI Speech on the local fake, with a key and a region."""
    settings.AZURE_SPEECH_KEY = AZURE_KEY
    settings.AZURE_SPEECH_REGION = "westeurope"
    monkeypatch.setattr(media, "SPEECH_ENDPOINT", f"{fake_provider.url}/{{region}}")
    return fake_provider


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

    def test_without_a_session_it_is_a_401_and_azure_hears_nothing(self, client, azure):
        assert error(post(client, {"text": "Hola"})) == (401, "unauthorized")
        assert azure.requests == []

    def test_without_the_assistants_permission_it_is_a_403(self, signed_in, azure, monkeypatch):
        from live.meta import all_live_app_configs, permissions_for_role

        from base import operations

        granted = permissions_for_role(all_live_app_configs(), operations.ACCOUNT_ROLE) - {"assistant.ask"}
        monkeypatch.setattr(operations, "_permissions", lambda actor: granted)

        assert error(post(signed_in, {"text": "Hola"})) == (403, "permission_denied")
        assert azure.requests == []


class TestReadingAloud:
    def test_the_answer_comes_back_as_an_mp3_in_the_voice_of_the_accounts_language(self, signed_in, azure):
        azure.reply("POST", AZURE_PATH, body=MP3)

        response = post(signed_in, {"text": "You have two bookings today."})

        assert response.status_code == 200
        assert response["Content-Type"] == "audio/mpeg"
        assert response.content == MP3
        [asked] = azure.requests
        assert asked.headers["ocp-apim-subscription-key"] == AZURE_KEY
        assert f'xml:lang="en-US"><voice name="{AVA}">You have two bookings today.</voice>' in asked.body

    @pytest.mark.parametrize(
        ("change", "name"), [({"language": "es"}, XIMENA), ({"language": "en", "voice": TRISTAN}, TRISTAN)]
    )
    def test_it_reads_in_the_language_or_the_voice_asked(self, signed_in, azure, change, name):
        azure.reply("POST", AZURE_PATH, body=MP3)

        assert post(signed_in, {"text": "Hola", **change}).status_code == 200
        assert f'<voice name="{name}">' in azure.requests[0].body

    def test_a_language_without_voices_reads_in_english(self, client, make_user, azure, settings):  # noqa: F811
        """A language the panel speaks with no voice in the catalogue yet (none today: the panel speaks ``en`` and
        ``es``, the two languages of ``assistant.media.VOICES``)."""
        settings.LANGUAGES = [*settings.LANGUAGES, ("fr", "Français")]
        client.force_login(make_user("fr@example.com", language="fr"))
        azure.reply("POST", AZURE_PATH, body=MP3)

        assert post(client, {"text": "Bonjour"}).status_code == 200
        assert f'<voice name="{AVA}">' in azure.requests[0].body

    @pytest.mark.parametrize(("change", "field"), [({"voice": "nova"}, "voice"), ({"language": "fr"}, "language"), ({"text": "  "}, "text")])
    def test_what_cannot_be_read_is_a_422_naming_its_field_and_spends_nothing(
        self, signed_in, account, azure, settings, change, field
    ):
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"

        response = post(signed_in, {"text": "Hola", **change})

        assert error(response) == (422, "invalid_payload")
        assert field in response.json()["error"]["fields"]
        assert azure.requests == []
        azure.reply("POST", AZURE_PATH, body=MP3)
        assert post(signed_in, {"text": "Hola"}).status_code == 200

    def test_it_counts_the_characters_in_the_accounts_month_and_spends_no_message(self, signed_in, account, azure):
        azure.reply("POST", AZURE_PATH, body=MP3)

        post(signed_in, {"text": "Hola"})

        assert month_of(account) == (0, 4)

    def test_without_azures_key_it_is_a_503_that_counts_nothing(self, signed_in, account, azure, settings):
        settings.AZURE_SPEECH_KEY = ""

        response = post(signed_in, {"text": "Hola"})

        assert error(response) == (503, "assistant.speech_unavailable")
        assert response.json()["error"]["message"] == "Reading aloud is not available right now."
        assert azure.requests == []
        assert month_of(account) == (0, 0)

    @pytest.mark.parametrize("status", [401, 500])
    def test_a_failure_of_azure_is_a_503_that_counts_nothing_and_hides_the_key(self, signed_in, account, azure, status):
        azure.reply("POST", AZURE_PATH, status=status, json={"error": {"message": f"key {AZURE_KEY}"}})

        response = post(signed_in, {"text": "Hola"})

        assert error(response) == (503, "base.assistant_speech_failed")
        assert response.json()["error"]["message"] == "The answer could not be read aloud: try again."
        assert AZURE_KEY not in response.content.decode()
        assert month_of(account) == (0, 0)

    def test_what_it_refuses_speaks_the_language_of_the_account(self, client, make_user, azure, settings):  # noqa: F811
        client.force_login(make_user("es@example.com", language="es"))
        azure.reply("POST", AZURE_PATH, status=500, json={"error": {"message": "busy"}})
        failed = post(client, {"text": "Hola"})
        settings.AZURE_SPEECH_KEY = ""
        unavailable = post(client, {"text": "Hola"})

        assert error(failed) == (503, "base.assistant_speech_failed")
        assert failed.json()["error"]["message"] == "No se ha podido leer la respuesta en voz alta: inténtalo de nuevo."
        assert error(unavailable) == (503, "assistant.speech_unavailable")
        assert unavailable.json()["error"]["message"] == "La lectura en voz alta no está disponible en este momento."


class TestTheBudget:
    def test_past_its_budget_an_account_waits_and_another_one_does_not(self, signed_in, make_user, azure, settings):  # noqa: F811
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
        azure.reply("POST", AZURE_PATH, always=True, body=MP3)

        assert post(signed_in, {"text": "Hola"}).status_code == 200
        refused = post(signed_in, {"text": "Hola"})
        assert error(refused) == (429, "rate_limited")
        assert refused.json()["error"]["message"] == "Too many readings aloud in a short time: wait a moment and try again."
        assert len(azure.requests) == 1

        signed_in.force_login(make_user("otra@example.com", language="es"))
        refused_in_spanish = post(signed_in, {"text": "Hola"})
        assert refused_in_spanish.status_code == 200

    def test_the_refusal_of_the_budget_speaks_the_language_of_the_account(self, client, make_user, azure, settings):  # noqa: F811
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
        azure.reply("POST", AZURE_PATH, always=True, body=MP3)
        client.force_login(make_user("es@example.com", language="es"))
        post(client, {"text": "Hola"})

        refused = post(client, {"text": "Hola"})

        assert refused.json()["error"]["message"] == "Demasiadas lecturas en voz alta seguidas: espera un momento y vuelve a intentarlo."

    def test_it_spends_the_budget_of_the_readings_aloud_and_no_other_door(self, signed_in, account, azure, settings):
        """The Hub's ``synthesize`` door's, per account: a reading aloud never eats what a dictation may spend."""
        settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
        azure.reply("POST", AZURE_PATH, body=MP3)

        assert post(signed_in, {"text": "Hola"}).status_code == 200

        gateway.spend(None, "transcribe", "1/h", Caller(user_id=account.pk))
        with pytest.raises(gateway.Refused):
            gateway.spend(None, "synthesize", "1/h", Caller(user_id=account.pk))


class TestWhileItWaits:
    def test_no_transaction_is_open_while_azure_answers(self, signed_in, azure, monkeypatch):
        seen = []

        async def spying(text, voice):
            seen.append(current_operation.get())
            return MP3

        monkeypatch.setattr(media, "synthesize", spying)

        assert post(signed_in, {"text": "Hola"}).status_code == 200
        assert seen == [None]


class TestItForgets:
    def test_what_is_read_is_kept_in_no_table_and_no_log(self, signed_in, azure, caplog):
        """ASSISTANT-F17: what the account hears is forgotten as what the Hub's does, whichever way it ends."""
        caplog.set_level(logging.DEBUG)
        azure.reply("POST", AZURE_PATH, body=MP3)
        azure.reply("POST", AZURE_PATH, status=500, json={"error": {"message": "busy"}})

        assert post(signed_in, {"text": SECRET_WORDS}).status_code == 200
        assert post(signed_in, {"text": SECRET_WORDS}).status_code == 503

        kept = io.StringIO()
        call_command("dumpdata", stdout=kept)
        assert SECRET_WORDS not in kept.getvalue()
        assert SECRET_WORDS not in "\n".join(record.getMessage() for record in caplog.records)
