"""ASSISTANT-F21 (ASSISTANT-G56, G12, G20) · Transcribe a dictation, and ASSISTANT-F22 (G57) · read an answer aloud.

The Hub sends the audio of the person's dictation (``POST /internal/speech/transcribe``: base64, its type and,
optionally, its language) and gets the text, which it leaves in the assistant's box for the person to check; it sends
an answer (``POST /internal/speech/synthesize``) and gets it spoken, as an mp3. Both through the Hub, signed: the old
product took the dictation only with the session of a person with an erplora.com account, so whoever entered with a
PIN could not dictate (SAAS_ASSISTANT-F19, «parcial»). With the key of the services' provider (of OpenAI's API) kept in
the admin and rotatable, never the old ``OPENAI_API_KEY`` of the environment. Neither spends messages; each door has
its own budget per business, spent after the signature (saas#2531), and what is dictated never reaches a log (the old
one kept its first 50 characters). Cases of the old ``speech/tests/test_synthesize.py``; OpenAI is the local fake.
"""

import base64
import logging

import pytest
from django.test import Client

from assistant import media
from assistant.models import AssistantUsage
from assistant.tests.conftest import API_KEY
from assistant.tests.doors import door, error_code

TRANSCRIBE = "/internal/speech/transcribe"
SYNTHESIZE = "/internal/speech/synthesize"
AUDIO = b"\x1aE\xdf\xa3 a few seconds of webm"
MP3 = b"ID3\x04\x00 spoken words"

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

    @pytest.mark.parametrize(("status", "code"), [(401, "assistant.provider_rejected"), (500, "assistant.provider_unavailable")])
    def test_a_failure_of_the_provider_is_a_502_with_its_code(self, client, internal, business, answering, fake_provider, status, code):
        fake_provider.reply("POST", "/v1/audio/transcriptions", status=status, json={"error": {"message": f"key {API_KEY}"}})

        response = door(client, TRANSCRIBE, dictation(business))

        assert (response.status_code, error_code(response)) == (502, code)
        assert API_KEY not in response.content.decode()

    def test_without_the_services_provider_it_is_503(self, client, internal, business, answering, settings):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"

        response = door(client, TRANSCRIBE, dictation(business))

        assert (response.status_code, error_code(response)) == (503, "assistant.provider_not_configured")


class TestReadingAloud:
    def test_the_text_comes_back_spoken_as_an_mp3(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/speech", body=MP3)

        response = door(client, SYNTHESIZE, {"hub": business.slug, "text": "Tienes dos citas hoy.", "voice": "nova"})

        assert response.status_code == 200
        assert response["Content-Type"] == "audio/mpeg"
        assert response.content == MP3
        [asked] = fake_provider.requests
        assert asked.body == {"model": media.SPEECH_MODEL, "voice": "nova", "input": "Tienes dos citas hoy.", "response_format": "mp3"}

    def test_an_unknown_voice_is_the_default_one(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/speech", body=MP3)

        door(client, SYNTHESIZE, {"hub": business.slug, "text": "Hola", "voice": "darth"})

        assert fake_provider.requests[0].body["voice"] == media.DEFAULT_VOICE

    def test_a_long_text_is_cut_to_what_the_provider_reads(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/speech", body=MP3)

        door(client, SYNTHESIZE, {"hub": business.slug, "text": "a" * (media.MAX_SPEECH_CHARS + 100)})

        assert len(fake_provider.requests[0].body["input"]) == media.MAX_SPEECH_CHARS

    def test_the_characters_read_are_counted(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/speech", body=MP3)

        door(client, SYNTHESIZE, {"hub": business.slug, "text": "Hola"})

        row = AssistantUsage.objects.get(hub=business)
        assert (row.messages, row.speech_characters) == (0, 4)

    def test_an_empty_text_is_refused(self, client, internal, business, answering, fake_provider):
        response = door(client, SYNTHESIZE, {"hub": business.slug, "text": "   "})

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert fake_provider.requests == []

    def test_a_failure_of_the_provider_is_a_502(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", "/v1/audio/speech", status=503, json={"error": {"message": "busy"}})

        response = door(client, SYNTHESIZE, {"hub": business.slug, "text": "Hola"})

        assert (response.status_code, error_code(response)) == (502, "assistant.provider_unavailable")


def test_saas_2531_each_voice_door_has_its_own_budget_spent_after_the_signature(client, internal, business, answering, fake_provider, settings):
    settings.ASSISTANT_TRANSCRIBE_RATELIMIT = "1/h"
    settings.ASSISTANT_SYNTHESIZE_RATELIMIT = "1/h"
    fake_provider.reply("POST", "/v1/audio/transcriptions", json={"text": "Hola"}, always=True)
    fake_provider.reply("POST", "/v1/audio/speech", body=MP3, always=True)
    for _ in range(3):
        door(client, TRANSCRIBE, dictation(business), signed=False)

    assert door(client, TRANSCRIBE, dictation(business)).status_code == 200
    assert error_code(door(client, TRANSCRIBE, dictation(business))) == "rate_limited"
    assert door(client, SYNTHESIZE, {"hub": business.slug, "text": "Hola"}).status_code == 200
    assert error_code(door(client, SYNTHESIZE, {"hub": business.slug, "text": "Hola"})) == "rate_limited"
