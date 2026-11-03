"""ASSISTANT-F21 (ASSISTANT-G56, G12, G20) · Transcribe a dictation, and ASSISTANT-F22 (G57) · read an answer aloud.

The Hub sends the audio of the person's dictation (``POST /internal/speech/transcribe``: base64, its type and,
optionally, its language) and gets the text, which it leaves in the assistant's box for the person to check; it sends
an answer (``POST /internal/speech/synthesize``: the text, its language and, optionally, a voice of the catalogue) and
gets it spoken, as an mp3. Both through the Hub, signed: the old product took the dictation only with the session of a
person with an erplora.com account, so whoever entered with a PIN could not dictate (SAAS_ASSISTANT-F19, «parcial»).
The dictation goes to the services' provider (OpenAI's API); the reading aloud, to the provider of the voice (Azure AI
Speech and its DragonHD voices of Spain, PLAN-SAAS round 2026-11-03m, at its region's address): each one's key kept in
the admin and rotatable, never read from the environment by the door. Neither spends messages; each door has its own budget per business, spent after the signature
(saas#2531), and what is dictated or read never reaches a log (the old one kept its first 50 characters). Cases of the
old ``speech/tests/test_synthesize.py``; OpenAI and Azure are the local fake.
"""

import base64
import logging
import re

import httpx
import pytest
from django.test import Client

from assistant import media
from assistant.models import AIProvider, AIProviderCredential, AssistantUsage
from assistant.tests.conftest import API_KEY, OTHER_FERNET_KEY
from assistant.tests.conftest import FERNET_KEY as FERNET_KEY_OF_THE_TESTS
from assistant.tests.doors import door, error_code
from config.tests.test_production_settings import IGNORE_DOTENV
from config.tests.test_settings import PRODUCTION_ENV, _settings_in_a_fresh_process

TRANSCRIBE = "/internal/speech/transcribe"
SYNTHESIZE = "/internal/speech/synthesize"
AUDIO = b"\x1aE\xdf\xa3 a few seconds of webm"
MP3 = b"ID3\x04\x00 spoken words"
XIMENA = "es-ES-Ximena:DragonHDLatestNeural"
TRISTAN = "es-ES-Tristan:DragonHDLatestNeural"
AVA = "en-US-Ava:DragonHDLatestNeural"
ANDREW = "en-US-Andrew2:DragonHDLatestNeural"
#: A made-up key of Azure AI Speech, and the region the tests' address names (not the default, to see it in the path).
AZURE_KEY = "not-a-real-azure-speech-key"
AZURE_REGION = "westeurope"
AZURE_PATH = f"/{AZURE_REGION}/cognitiveservices/v1"


def speech_provider(fake_provider, *, key: str | None = AZURE_KEY, **fields) -> AIProvider:
    """Azure AI Speech in the admin, as ``import_ai_keys_from_env`` leaves it, at the fake's ``/<region>``."""
    provider = AIProvider.objects.create(
        slug="azure-speech",
        name="Azure AI Speech",
        kind=AIProvider.Kind.AZURE_SPEECH,
        base_url=f"{fake_provider.url}/{AZURE_REGION}",
        **fields,
    )
    if key is not None:
        credential = AIProviderCredential(provider=provider, label="default")
        credential.api_key = key
        credential.key_hint = key[-4:]
        credential.save()
    return provider

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def azure(fake_provider):
    """The provider of the voice (Azure AI Speech) on the local fake, with its key."""
    speech_provider(fake_provider)
    return fake_provider


def dictation(business, audio: bytes = AUDIO, **extra) -> dict:
    return {"hub": business.slug, "audio": base64.b64encode(audio).decode(), "mime_type": "audio/webm", **extra}


class TestTheDictation:
    def test_the_audio_comes_back_as_text(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "  Dos cafés y una tostada  "})

        response = door(client, TRANSCRIBE, dictation(business, language="es-ES"))

        assert response.status_code == 200
        assert response.json() == {"text": "Dos cafés y una tostada", "language": "es"}
        [asked] = fake_provider.requests
        assert asked.headers["authorization"] == f"Bearer {API_KEY}"
        assert asked.headers["content-type"].startswith("multipart/form-data")
        sent = asked.body
        assert media.TRANSCRIBE_MODEL in sent and 'name="language"' in sent and 'filename="dictation.webm"' in sent

    def test_without_a_language_the_model_finds_it(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "Hello"})

        response = door(client, TRANSCRIBE, dictation(business))

        assert response.json() == {"text": "Hello", "language": ""}
        assert 'name="language"' not in fake_provider.requests[0].body

    def test_each_dictation_is_counted_and_spends_no_message(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "Hola"})

        door(client, TRANSCRIBE, dictation(business))

        row = AssistantUsage.objects.get(hub=business)
        assert (row.messages, row.transcriptions) == (0, 1)

    def test_audio_over_two_megabytes_is_refused(self, client, internal, business, answering, fake_provider):
        response = door(client, TRANSCRIBE, dictation(business, audio=b"0" * (media.MAX_AUDIO_BYTES + 1)))

        assert (response.status_code, error_code(response)) == (413, "payload_too_large")
        assert fake_provider.requests == []

    @pytest.mark.parametrize(("change", "field"), [({"audio": "@@not base64@@"}, "audio"), ({"audio": ""}, "audio"), ({"mime_type": "video/mp4"}, "mime_type")])
    def test_what_is_not_audio_is_refused(self, client, internal, business, answering, fake_provider, change, field):
        response = door(client, TRANSCRIBE, {**dictation(business), **change})

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert field in response.json()["error"]["fields"]

    def test_what_is_dictated_never_reaches_a_log(self, client, internal, business, answering, fake_provider, caplog):
        caplog.set_level(logging.DEBUG)
        fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "Rosalía Quintanar debe 400 euros"})

        door(client, TRANSCRIBE, dictation(business))

        assert "Rosalía" not in "\n".join(record.getMessage() for record in caplog.records)

    @pytest.mark.parametrize(
        ("status", "code", "retriable"),
        [(401, "assistant.provider_rejected", False), (500, "assistant.provider_unavailable", True)],
    )
    def test_a_failure_of_the_provider_is_a_502_with_its_code(self, client, internal, business, answering, fake_provider, status, code, retriable):
        fake_provider.reply("POST", "/v1/audio/transcriptions", status=status, json={"error": {"message": f"key {API_KEY}"}})

        response = door(client, TRANSCRIBE, dictation(business))

        assert (response.status_code, error_code(response)) == (502, code)
        assert response.json()["error"]["retriable"] is retriable
        assert API_KEY not in response.content.decode()

    def test_without_the_services_provider_it_is_503(self, client, internal, business, answering, settings):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"

        response = door(client, TRANSCRIBE, dictation(business))

        assert (response.status_code, error_code(response)) == (503, "assistant.provider_not_configured")


class TestTheCatalogueOfVoices:
    """The voices of @erplora/ui's catalogue, by the same ids: a change on one side only breaks the other's."""

    def test_two_voices_per_language_a_woman_first_and_by_default(self):
        assert [(voice.id, voice.locale, voice.gender) for voice in media.VOICES] == [
            ("es-ES-Ximena:DragonHDLatestNeural", "es-ES", "female"),
            ("es-ES-Tristan:DragonHDLatestNeural", "es-ES", "male"),
            ("en-US-Ava:DragonHDLatestNeural", "en-US", "female"),
            ("en-US-Andrew2:DragonHDLatestNeural", "en-US", "male"),
        ]
        assert media.SPEECH_LANGUAGES == ("es", "en")

    @pytest.mark.parametrize(("language", "expected"), [("es", XIMENA), ("en", AVA)])
    def test_without_a_voice_it_is_the_default_of_the_language(self, language, expected):
        assert media.voice_of(language).id == expected
        assert media.voice_of(language, "").id == expected

    @pytest.mark.parametrize("voice", [TRISTAN, ANDREW, AVA])
    def test_a_voice_of_the_catalogue_is_that_one_whatever_the_language(self, voice):
        assert media.voice_of("es", voice).id == voice

    @pytest.mark.parametrize(("language", "voice"), [("es", "nova"), ("es", "alloy"), ("es", "es-ES-Elvira:DragonHDLatestNeural"), ("fr", ""), ("", "")])
    def test_an_unknown_voice_or_language_is_refused(self, language, voice):
        with pytest.raises(media.UnknownVoice):
            media.voice_of(language, voice)

    def test_an_unknown_voice_is_a_value_error_so_a_schema_names_its_field(self):
        assert issubclass(media.UnknownVoice, ValueError)


class TestTheRequestToAzure:
    def test_without_an_address_of_its_own_the_voice_speaks_from_sweden_central(self, db):
        provider = AIProvider(slug="azure-speech", name="Azure AI Speech", kind=AIProvider.Kind.AZURE_SPEECH)

        assert provider.api_base == "https://swedencentral.tts.speech.microsoft.com"

    def test_the_ssml_names_the_voice_and_its_language(self):
        assert media.ssml("Hola", media.voice_of("en", TRISTAN)) == (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-ES">'
            f'<voice name="{TRISTAN}">Hola</voice></speak>'
        )

    def test_the_text_is_escaped_as_xml(self):
        spoken = media.ssml('Tom & Jerry <3 </voice><voice name="x">', media.voice_of("es"))

        assert 'Tom &amp; Jerry &lt;3 &lt;/voice&gt;&lt;voice name="x"&gt;</voice></speak>' in spoken
        assert spoken.count("<voice ") == 1

    def test_characters_xml_cannot_carry_are_dropped(self):
        """A form feed or a NUL in an answer would make the whole SSML unreadable to Azure (a 400 for the person)."""
        spoken = media.ssml("Uno\x00 dos\x0c tres\x1f\tcuatro\ncinco\ufffe", media.voice_of("es"))

        assert ">Uno dos tres\tcuatro\ncinco</voice>" in spoken

    def test_the_provider_of_the_voice_is_azure_speech_unless_the_environment_names_another(self):
        """The key is the admin's (``import_ai_keys_from_env`` loads ``AZURE_SPEECH_KEY`` there); the region is the
        provider's address: no ``AZURE_SPEECH_REGION`` is read."""
        forget = "import os; [os.environ.pop(name, None) for name in ('ASSISTANT_SPEECH_PROVIDER', 'AZURE_SPEECH_KEY')]\n"
        expression = "(s.ASSISTANT_SPEECH_PROVIDER, s.AZURE_SPEECH_KEY, hasattr(s, 'AZURE_SPEECH_REGION'))"
        default = _settings_in_a_fresh_process(PRODUCTION_ENV, expression, forget + IGNORE_DOTENV)
        chosen = _settings_in_a_fresh_process({**PRODUCTION_ENV, "ASSISTANT_SPEECH_PROVIDER": "azure-eu"}, expression)

        assert default.returncode == 0, default.stderr
        assert default.stdout.strip() == str(("azure-speech", "", False))
        assert chosen.stdout.strip().startswith("('azure-eu',")


def read(ssml: str) -> str:
    """The text an SSML gives its voice to read."""
    return re.fullmatch(r'<speak [^>]+><voice name="[^"]+">(.*)</voice></speak>', ssml, re.DOTALL).group(1)


def reading(business, text: str = "Tienes dos citas hoy.", **extra) -> dict:
    return {"hub": business.slug, "text": text, "language": "es", **extra}


class TestReadingAloud:
    def test_the_text_comes_back_spoken_as_an_mp3_of_azure(self, client, internal, business, azure):
        azure.reply("POST", AZURE_PATH, body=MP3, headers={"Content-Type": "audio/mpeg"})

        response = door(client, SYNTHESIZE, reading(business))

        assert response.status_code == 200
        assert response["Content-Type"] == "audio/mpeg"
        assert response.content == MP3
        [asked] = azure.requests
        assert asked.path == AZURE_PATH
        assert asked.headers["ocp-apim-subscription-key"] == AZURE_KEY
        assert asked.headers["content-type"] == "application/ssml+xml"
        assert asked.headers["x-microsoft-outputformat"] == "audio-24khz-48kbitrate-mono-mp3"
        assert asked.headers["user-agent"] == "erplora"
        assert "authorization" not in asked.headers
        assert asked.body == (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-ES">'
            f'<voice name="{XIMENA}">Tienes dos citas hoy.</voice></speak>'
        )

    @pytest.mark.parametrize(
        ("language", "voice", "name", "locale"),
        [("es", "", XIMENA, "es-ES"), ("en", "", AVA, "en-US"), ("es", TRISTAN, TRISTAN, "es-ES"), ("en", ANDREW, ANDREW, "en-US")],
    )
    def test_it_reads_with_the_voice_asked_or_the_default_of_the_language(
        self, client, internal, business, azure, language, voice, name, locale
    ):
        azure.reply("POST", AZURE_PATH, body=MP3)

        response = door(client, SYNTHESIZE, reading(business, language=language, voice=voice))

        assert response.status_code == 200
        assert f'xml:lang="{locale}"><voice name="{name}">' in azure.requests[0].body

    @pytest.mark.parametrize("voice", ["nova", "alloy", "es-ES-Elvira:DragonHDLatestNeural"])
    def test_an_unknown_voice_is_a_422_naming_it_and_azure_hears_nothing(self, client, internal, business, azure, voice):
        response = door(client, SYNTHESIZE, reading(business, voice=voice))

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert list(response.json()["error"]["fields"]) == ["voice"]
        assert azure.requests == []

    @pytest.mark.parametrize("change", [{"language": "fr"}, {"language": ""}, {"language": None}])
    def test_a_language_without_voices_is_a_422(self, client, internal, business, azure, change):
        body = {key: value for key, value in {**reading(business), **change}.items() if value is not None}

        response = door(client, SYNTHESIZE, body)

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert "language" in response.json()["error"]["fields"]
        assert azure.requests == []

    def test_what_the_text_holds_reaches_azure_escaped(self, client, internal, business, azure):
        azure.reply("POST", AZURE_PATH, body=MP3)

        door(client, SYNTHESIZE, reading(business, text="Café & tostada < 3 €"))

        assert ">Café &amp; tostada &lt; 3 €</voice>" in azure.requests[0].body

    def test_a_long_text_is_cut_to_what_azure_reads(self, client, internal, business, azure):
        azure.reply("POST", AZURE_PATH, body=MP3)

        door(client, SYNTHESIZE, reading(business, text="a" * (media.MAX_SPEECH_CHARS + 100)))

        assert read(azure.requests[0].body) == "a" * media.MAX_SPEECH_CHARS

    def test_at_most_the_first_4096_characters_are_read(self, client, internal, business, azure):
        """The number the manual gives (ASSISTANT-F22, step 2): the test above follows the constant, this one pins it."""
        azure.reply("POST", AZURE_PATH, body=MP3)

        door(client, SYNTHESIZE, reading(business, text="a" * 5000))

        assert len(read(azure.requests[0].body)) == 4096

    def test_the_characters_read_are_counted_and_spend_no_message(self, client, internal, business, azure):
        azure.reply("POST", AZURE_PATH, body=MP3)

        door(client, SYNTHESIZE, reading(business, text="Hola"))

        row = AssistantUsage.objects.get(hub=business)
        assert (row.messages, row.speech_characters) == (0, 4)

    @pytest.mark.parametrize("text", ["   ", "\x00", "\x00\x0c \x1f", "\ufffe"])
    def test_an_empty_text_is_refused(self, client, internal, business, azure, text):
        """Nothing XML can carry is nothing to read: a 422 naming ``text``, never an empty ``<voice>`` sent to Azure."""
        response = door(client, SYNTHESIZE, reading(business, text=text))

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert "text" in response.json()["error"]["fields"]
        assert azure.requests == []

    def test_a_long_reading_has_a_minute_to_arrive(self):
        """Four thousand characters may take Azure longer than 20 s to read: a minute to answer, as the other services."""
        assert (media.SPEECH_TIMEOUT.connect, media.SPEECH_TIMEOUT.read) == (10.0, 60.0)

    def test_it_needs_no_services_provider_of_openai(self, client, internal, business, azure, settings):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"
        azure.reply("POST", AZURE_PATH, body=MP3)

        assert door(client, SYNTHESIZE, reading(business)).status_code == 200

    @pytest.mark.parametrize(
        "without",
        ["provider", "key", "active key", "readable key", "enabled provider", "provider of its API", "provider named"],
    )
    def test_without_the_provider_of_the_voice_and_its_key_it_is_a_503_so_the_hub_reads_with_the_devices_voice(
        self, client, internal, business, fake_provider, settings, caplog, without
    ):
        if without == "key":
            speech_provider(fake_provider, key=None)
        elif without == "active key":
            speech_provider(fake_provider)
            AIProviderCredential.objects.update(is_active=False)
        elif without == "readable key":
            settings.FERNET_KEY = OTHER_FERNET_KEY
            speech_provider(fake_provider)
            settings.FERNET_KEY = FERNET_KEY_OF_THE_TESTS
        elif without == "enabled provider":
            speech_provider(fake_provider, is_enabled=False)
        elif without == "provider of its API":
            AIProvider.objects.filter(pk=speech_provider(fake_provider).pk).update(kind=AIProvider.Kind.OPENAI)
        elif without == "provider named":
            speech_provider(fake_provider)
            settings.ASSISTANT_SPEECH_PROVIDER = "nobody"

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (503, "assistant.speech_unavailable")
        assert response.json()["error"]["retriable"] is False
        assert fake_provider.requests == []
        assert not AssistantUsage.objects.filter(hub=business).exists()
        assert "assistant.media.no_speech_provider" in caplog.text

    def test_the_key_of_the_environment_is_not_read(self, client, internal, business, fake_provider, settings):
        """``AZURE_SPEECH_KEY`` only feeds ``import_ai_keys_from_env``: until the admin keeps it, no voice."""
        settings.AZURE_SPEECH_KEY = AZURE_KEY

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (503, "assistant.speech_unavailable")

    @pytest.mark.parametrize(
        ("status", "code", "retriable"),
        [
            (400, "assistant.provider_rejected", False),
            (401, "assistant.provider_rejected", False),
            (429, "assistant.provider_unavailable", True),
            (500, "assistant.provider_unavailable", True),
            (503, "assistant.provider_unavailable", True),
        ],
    )
    def test_a_failure_of_azure_is_a_502_with_its_code_logged_with_its_status(
        self, client, internal, business, azure, caplog, status, code, retriable
    ):
        azure.reply("POST", AZURE_PATH, status=status, json={"error": {"message": f"key {AZURE_KEY}"}})

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (502, code)
        assert response.json()["error"]["retriable"] is retriable
        assert AZURE_KEY not in response.content.decode()
        assert f"assistant.media.failed path=/cognitiveservices/v1 status={status}" in caplog.text
        assert AZURE_KEY not in caplog.text
        assert not AssistantUsage.objects.filter(hub=business).exists()

    def test_azure_too_slow_is_a_502_worth_trying_again(self, client, internal, business, azure, monkeypatch, caplog):
        monkeypatch.setattr(media, "SPEECH_TIMEOUT", httpx.Timeout(0.2))
        azure.reply("POST", AZURE_PATH, sse=["ID3", "late"], delay=1.0)

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (502, "assistant.provider_unavailable")
        assert response.json()["error"]["retriable"] is True
        assert "assistant.media.unreachable path=/cognitiveservices/v1 kind=ReadTimeout" in caplog.text

    def test_an_answer_without_audio_is_a_502_worth_trying_again(self, client, internal, business, azure):
        azure.reply("POST", AZURE_PATH, body=b"")

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (502, "assistant.provider_unavailable")

    def test_what_is_read_never_reaches_a_log(self, client, internal, business, azure, caplog):
        caplog.set_level(logging.DEBUG)
        azure.reply("POST", AZURE_PATH, status=500, json={"error": {"message": "busy"}})

        door(client, SYNTHESIZE, reading(business, text="Rosalía Quintanar debe 400 euros"))

        assert "Rosalía" not in "\n".join(record.getMessage() for record in caplog.records)


def test_saas_2531_each_voice_door_has_its_own_budget_spent_after_the_signature(client, internal, business, answering, fake_provider, azure, settings):
    settings.ASSISTANT_TRANSCRIBE_RATELIMIT = "1/h"
    settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
    fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "Hola"}, always=True)
    fake_provider.reply("POST", AZURE_PATH, body=MP3, always=True)
    for _ in range(3):
        door(client, TRANSCRIBE, dictation(business), signed=False)
        door(client, SYNTHESIZE, reading(business, text="Hola"), signed=False)

    assert door(client, TRANSCRIBE, dictation(business)).status_code == 200
    assert error_code(door(client, TRANSCRIBE, dictation(business))) == "rate_limited"
    assert door(client, SYNTHESIZE, reading(business, text="Hola")).status_code == 200
    assert error_code(door(client, SYNTHESIZE, reading(business, text="Hola"))) == "rate_limited"
    assert len([seen for seen in fake_provider.requests if seen.path == AZURE_PATH]) == 1
