"""Transcribe a dictation, and read an answer aloud.

The Hub sends the audio of the person's dictation (``POST /internal/speech/transcribe``: base64, its type and,
optionally, its language) and gets the text, which it leaves in the assistant's box for the person to check. It goes to
the services' provider (OpenAI's API), with its key kept in the admin and rotatable. The door is signed by the Hub, not
a person's session, so whoever entered the Hub with a PIN can dictate too.

No engine reads an answer aloud: ``POST /internal/speech/synthesize`` answers 503
``assistant.speech_unavailable`` and the caller reads with the device's voice. What the door keeps for an engine (the
text and its voice to an mp3, the cut, the count, the failures) is held here with a stand-in. Neither door spends
messages; each has its own budget per business, spent after the signature, and what is dictated or read
never reaches a log. OpenAI is the local fake.
"""

import base64
import logging

import pytest
from django.conf import settings as django_settings
from django.test import Client

from assistant import media
from assistant.models import AssistantUsage
from assistant.tests.conftest import API_KEY, FakeSpeechEngine
from assistant.tests.doors import door, error_code
from config.tests.test_settings import PRODUCTION_ENV, _settings_in_a_fresh_process

TRANSCRIBE = "/internal/speech/transcribe"
SYNTHESIZE = "/internal/speech/synthesize"
AUDIO = b"\x1aE\xdf\xa3 a few seconds of webm"
MP3 = FakeSpeechEngine.MP3
#: A voice of the catalogue that left: a caller that still names it hears what any other does.
GONE = "es-ES-Ximena:DragonHDLatestNeural"


pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


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


def test_nothing_of_azure_is_left_to_configure():
    """The settings and the example of the environment name none of it: a key left in a secret is read by nothing."""
    names = ("ASSISTANT_SPEECH_PROVIDER", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
    expression = f"[hasattr(s, name) for name in {names!r}]"

    left = _settings_in_a_fresh_process({**PRODUCTION_ENV, "AZURE_SPEECH_KEY": "left-in-a-secret"}, expression)

    assert left.returncode == 0, left.stderr
    assert left.stdout.strip() == str([False, False, False])
    example = (django_settings.BASE_DIR / ".env.example").read_text(encoding="utf-8")
    assert not [name for name in names if name in example]


def reading(business, text: str = "Tienes dos citas hoy.", **extra) -> dict:
    return {"hub": business.slug, "text": text, "language": "es", **extra}


class TestWithoutAnEngine:
    """erplora.com as it is: nothing reads aloud, and the caller reads with the device's voice."""

    @pytest.mark.parametrize("voice", ["", GONE, "nova"])
    def test_it_is_a_503_so_the_hub_reads_with_the_devices_voice(self, client, internal, business, caplog, voice):
        response = door(client, SYNTHESIZE, reading(business, voice=voice))

        assert (response.status_code, error_code(response)) == (503, "assistant.speech_unavailable")
        assert response.json()["error"]["retriable"] is False
        assert not AssistantUsage.objects.filter(hub=business).exists()
        assert "assistant.media.no_speech_provider" in caplog.text

    def test_what_it_was_asked_to_read_never_reaches_a_log(self, client, internal, business, caplog):
        caplog.set_level(logging.DEBUG)

        door(client, SYNTHESIZE, reading(business, text="Rosalía Quintanar debe 400 euros"))

        assert "Rosalía" not in "\n".join(record.getMessage() for record in caplog.records)

    def test_a_provider_named_as_the_old_voice_reads_nothing(self, client, internal, business, fake_provider):
        """Only an engine reads aloud: no provider of the admin does, whatever its identifier and with its key."""
        from assistant.models import AIProvider, AIProviderCredential

        named = AIProvider.objects.create(slug="azure-speech", name="Azure", kind="openai", base_url=fake_provider.url)
        AIProviderCredential.objects.create(provider=named, label="default", api_key=API_KEY, key_hint="wxyz")

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (503, "assistant.speech_unavailable")
        assert fake_provider.requests == []

    @pytest.mark.parametrize(
        ("change", "field"),
        [({"language": "fr"}, "language"), ({"language": ""}, "language"), ({"language": None}, "language"), ({"text": "   "}, "text")],
    )
    def test_what_is_no_reading_is_still_a_422_naming_its_field(self, client, internal, business, change, field):
        body = {key: value for key, value in {**reading(business), **change}.items() if value is not None}

        response = door(client, SYNTHESIZE, body)

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert field in response.json()["error"]["fields"]


class TestTheContractOfTheDoor:
    """What an engine finds when it comes: the stand-in in its place."""

    def test_the_text_comes_back_spoken_as_an_mp3(self, client, internal, business, speech_engine):
        response = door(client, SYNTHESIZE, reading(business))

        assert response.status_code == 200
        assert response["Content-Type"] == "audio/mpeg"
        assert response.content == MP3
        assert speech_engine.calls == [("Tienes dos citas hoy.", "es", "")]

    @pytest.mark.parametrize(("language", "voice"), [("es", ""), ("en", ""), ("es", "a-voice"), ("en", "another")])
    def test_it_reads_in_the_language_and_the_voice_asked(self, client, internal, business, speech_engine, language, voice):
        assert door(client, SYNTHESIZE, reading(business, language=language, voice=voice)).status_code == 200
        assert speech_engine.calls == [("Tienes dos citas hoy.", language, voice)]

    def test_a_long_text_is_cut_to_what_is_read(self, client, internal, business, speech_engine):
        door(client, SYNTHESIZE, reading(business, text="a" * (media.MAX_SPEECH_CHARS + 100)))

        assert speech_engine.calls[0][0] == "a" * media.MAX_SPEECH_CHARS

    def test_at_most_the_first_4096_characters_are_read(self, client, internal, business, speech_engine):
        """The number the manual gives: the test above follows the constant, this one pins it."""
        door(client, SYNTHESIZE, reading(business, text="a" * 5000))

        assert len(speech_engine.calls[0][0]) == 4096

    def test_the_characters_read_are_counted_and_spend_no_message(self, client, internal, business, speech_engine):
        door(client, SYNTHESIZE, reading(business, text="Hola"))

        row = AssistantUsage.objects.get(hub=business)
        assert (row.messages, row.speech_characters) == (0, 4)

    def test_what_is_counted_is_what_was_read_not_what_was_sent(self, client, internal, business, speech_engine):
        door(client, SYNTHESIZE, reading(business, text="a" * 5000))

        assert AssistantUsage.objects.get(hub=business).speech_characters == media.MAX_SPEECH_CHARS

    @pytest.mark.parametrize("text", ["   ", "\n\t "])
    def test_an_empty_text_is_refused_and_the_engine_hears_nothing(self, client, internal, business, speech_engine, text):
        response = door(client, SYNTHESIZE, reading(business, text=text))

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert "text" in response.json()["error"]["fields"]
        assert speech_engine.calls == []

    def test_it_needs_no_services_provider_of_openai(self, client, internal, business, speech_engine, settings):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"

        assert door(client, SYNTHESIZE, reading(business)).status_code == 200

    @pytest.mark.parametrize(
        ("retriable", "code"), [(False, "assistant.provider_rejected"), (True, "assistant.provider_unavailable")]
    )
    def test_a_failure_is_a_502_with_its_code_that_counts_nothing(self, client, internal, business, speech_engine, retriable, code):
        speech_engine.failure = media.MediaFailed(retriable=retriable)

        response = door(client, SYNTHESIZE, reading(business))

        assert (response.status_code, error_code(response)) == (502, code)
        assert response.json()["error"]["retriable"] is retriable
        assert not AssistantUsage.objects.filter(hub=business).exists()

    def test_what_is_read_never_reaches_a_log(self, client, internal, business, speech_engine, caplog):
        caplog.set_level(logging.DEBUG)
        door(client, SYNTHESIZE, reading(business, text="Rosalía Quintanar debe 400 euros"))
        speech_engine.failure = media.MediaFailed(retriable=True)
        door(client, SYNTHESIZE, reading(business, text="Rosalía Quintanar debe 400 euros"))

        assert "Rosalía" not in "\n".join(record.getMessage() for record in caplog.records)


def test_saas_2531_each_voice_door_has_its_own_budget_spent_after_the_signature(client, internal, business, answering, fake_provider, speech_engine, settings):
    settings.ASSISTANT_TRANSCRIBE_RATELIMIT = "1/h"
    settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
    fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "Hola"}, always=True)
    for _ in range(3):
        door(client, TRANSCRIBE, dictation(business), signed=False)
        door(client, SYNTHESIZE, reading(business, text="Hola"), signed=False)

    assert door(client, TRANSCRIBE, dictation(business)).status_code == 200
    assert error_code(door(client, TRANSCRIBE, dictation(business))) == "rate_limited"
    assert door(client, SYNTHESIZE, reading(business, text="Hola")).status_code == 200
    assert error_code(door(client, SYNTHESIZE, reading(business, text="Hola"))) == "rate_limited"
    assert len(speech_engine.calls) == 1


def test_without_an_engine_the_budget_of_the_door_still_brakes(client, internal, business, settings):
    settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"

    assert error_code(door(client, SYNTHESIZE, reading(business))) == "assistant.speech_unavailable"
    assert error_code(door(client, SYNTHESIZE, reading(business))) == "rate_limited"
