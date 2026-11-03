"""The services the assistants use besides the turn (ASSISTANT-G54, G56, G57, F27): the fingerprints (embeddings) of
the Hub's index and of the panel's documentation (``index_docs``, ``assistant.docs.search``) and the transcription of a
dictation, by OpenAI's API; the reading aloud of an answer, by Azure AI Speech (PLAN-SAAS round 2026-11-03m).

The embeddings and the dictation go to the services' provider (``assistant.service.connection``:
``ASSISTANT_SERVICE_PROVIDER``, kept in the admin with its key, rotatable). The reading aloud goes to Azure's REST API
(``https://<region>.tts.speech.microsoft.com/cognitiveservices/v1``) with ``AZURE_SPEECH_KEY`` and
``AZURE_SPEECH_REGION`` of the environment: its DragonHD voices (``VOICES``, the catalogue ``@erplora/ui`` shows by the
same ids), SSML in, an mp3 out; without the key, ``SpeechUnavailable`` and the Hub reads with the device's voice.

Each call goes over ``httpx``, with no SDK, the same way as ``assistant.providers``. A failure is a ``MediaFailed``
with the provider's class (rejected, or worth trying again) and never the key nor the provider's words (they could
quote what was dictated or read); the log says the path and the status only. A server whose trusted certificates
cannot be loaded is a final failure, logged with the setting and its file by ``base.tls`` (caller
``assistant.media``). Nothing is written to disk: the audio goes from memory to the provider and back.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from xml.sax.saxutils import escape

import httpx
from django.conf import settings

from assistant.providers.base import is_retriable_status
from assistant.schemas import ServiceConnectionOut
from base import tls

logger = logging.getLogger(__name__)

#: The model of the fingerprints, always the same (the Hub's index compares vectors of one model), and its price.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_PRICE_PER_1M = Decimal("0.02")
TRANSCRIBE_MODEL = "whisper-1"
#: A few seconds of speech fit many times over.
MAX_AUDIO_BYTES = 2 * 1024 * 1024
#: What is read aloud in one call.
MAX_SPEECH_CHARS = 4096
#: The audio types a dictation comes in, and the extension the provider reads each by.
AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/flac": "flac",
}
TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)


@dataclass(frozen=True)
class Voice:
    """A voice of Azure AI Speech: its id, the language of its SSML (``xml:lang``) and whom it sounds like."""

    id: str
    locale: str
    gender: str

    @property
    def language(self) -> str:
        return self.locale.split("-")[0]


#: The voices that read aloud, the catalogue ``@erplora/ui`` shows by the same ids (a change here is a change there):
#: Azure's DragonHD voices of Spain and of the United States. The first of each language is its default.
VOICES = (
    Voice("es-ES-Ximena:DragonHDLatestNeural", "es-ES", "female"),
    Voice("es-ES-Tristan:DragonHDLatestNeural", "es-ES", "male"),
    Voice("en-US-Ava:DragonHDLatestNeural", "en-US", "female"),
    Voice("en-US-Andrew2:DragonHDLatestNeural", "en-US", "male"),
)
VOICE_IDS = frozenset(voice.id for voice in VOICES)
#: The languages there is a voice for, base code.
SPEECH_LANGUAGES = tuple(dict.fromkeys(voice.language for voice in VOICES))
#: Azure's endpoint of text to speech in a region, and its path.
SPEECH_ENDPOINT = "https://{region}.tts.speech.microsoft.com"
SPEECH_PATH = "/cognitiveservices/v1"
#: An mp3 a browser plays everywhere, of the quality the HD voices are made for.
SPEECH_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
#: Azure starts answering in under a second; four thousand characters take a few.
SPEECH_TIMEOUT = httpx.Timeout(20.0)
#: What XML 1.0 cannot carry (C0 controls but tab, newline and carriage return; surrogates; U+FFFE and U+FFFF):
#: one of them makes Azure refuse the whole SSML.
NOT_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


class MediaFailed(Exception):
    """A call to a provider (the services' one, or Azure) that failed: ``retriable`` if another attempt may
    succeed."""

    def __init__(self, retriable: bool, status: int | None = None):
        super().__init__("retriable" if retriable else "rejected")
        self.retriable, self.status = retriable, status

    @property
    def code(self) -> str:
        return "assistant.provider_unavailable" if self.retriable else "assistant.provider_rejected"


class UnknownVoice(ValueError):
    """A voice the catalogue does not have, or a language it has no voice for."""


class SpeechUnavailable(Exception):
    """No key of Azure AI Speech in this environment: nothing is read aloud by the server."""


async def _post(service: ServiceConnectionOut, path: str, *, timeout: httpx.Timeout = TIMEOUT, **request) -> httpx.Response:
    headers = {"Authorization": f"Bearer {service.api_key.get_secret_value()}"}
    return await _send(f"{service.base_url}{path}", path, headers=headers, timeout=timeout, **request)


async def _send(url: str, path: str, *, headers: dict, timeout: httpx.Timeout, **request) -> httpx.Response:
    """``POST url``; ``path`` is what the log names of it."""
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=tls.trusted_context("assistant.media")) as client:
            response = await client.post(url, headers=headers, **request)
    except tls.TrustStoreUnreadable:
        raise MediaFailed(retriable=False) from None
    except httpx.HTTPError as problem:
        logger.warning("assistant.media.unreachable path=%s kind=%s", path, type(problem).__name__)
        raise MediaFailed(retriable=True) from None
    if response.status_code >= 400:
        logger.warning("assistant.media.failed path=%s status=%s", path, response.status_code)
        raise MediaFailed(retriable=is_retriable_status(response.status_code), status=response.status_code)
    return response


async def embed(
    service: ServiceConnectionOut, texts: list[str], *, timeout: httpx.Timeout = TIMEOUT
) -> tuple[list[list[float]], int]:
    """A vector per text, in the order of ``texts``, and the tokens the provider counted; ``timeout`` bounds a call
    that waits inside a transaction (``assistant.docs.search``)."""
    response = await _post(service, "/embeddings", timeout=timeout, json={"model": EMBEDDING_MODEL, "input": texts})
    try:
        body = response.json()
        rows = sorted(body["data"], key=lambda row: row["index"])
        vectors = [[float(value) for value in row["embedding"]] for row in rows]
        tokens = int((body.get("usage") or {}).get("total_tokens") or 0)
    except (ValueError, KeyError, TypeError):
        logger.warning("assistant.media.unreadable path=/embeddings")
        raise MediaFailed(retriable=True) from None
    if len(vectors) != len(texts):
        logger.warning("assistant.media.unreadable path=/embeddings vectors=%s texts=%s", len(vectors), len(texts))
        raise MediaFailed(retriable=True)
    return vectors, tokens


def embedding_cost(tokens: int) -> Decimal:
    return EMBEDDING_PRICE_PER_1M * tokens / Decimal(1_000_000)


async def transcribe(service: ServiceConnectionOut, audio: bytes, mime_type: str, language: str) -> str:
    """The text of a dictation (``language`` empty: the model finds it)."""
    fields = {"model": TRANSCRIBE_MODEL, "response_format": "json"}
    if language:
        fields["language"] = language
    files = {"file": (f"dictation.{AUDIO_TYPES[mime_type]}", audio, mime_type)}
    response = await _post(service, "/audio/transcriptions", data=fields, files=files)
    try:
        return str(response.json().get("text") or "").strip()
    except (ValueError, AttributeError):
        logger.warning("assistant.media.unreadable path=/audio/transcriptions")
        raise MediaFailed(retriable=True) from None


def base_language(language: str) -> str:
    """``es-ES`` → ``es``: the provider takes the base code."""
    return language.strip().split("-")[0].split("_")[0].lower()


def speech_text(text: str) -> str:
    return text.strip()[:MAX_SPEECH_CHARS]


def voice_of(language: str, voice: str = "") -> Voice:
    """``voice`` if the catalogue has it (whatever ``language``: the voice says its own), else the default voice of
    ``language``; ``UnknownVoice`` for a voice the catalogue does not have or a language without voices."""
    if voice:
        for known in VOICES:
            if known.id == voice:
                return known
        raise UnknownVoice("not a voice of the catalogue")
    for known in VOICES:
        if known.language == language:
            return known
    raise UnknownVoice("no voice speaks this language")


def speech_url(region: str) -> str:
    return SPEECH_ENDPOINT.format(region=region) + SPEECH_PATH


def ssml(text: str, voice: Voice) -> str:
    """The SSML Azure reads: ``text`` escaped as XML (and without what XML cannot carry) in ``voice``."""
    spoken = escape(NOT_XML.sub("", text))
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{voice.locale}">'
        f'<voice name="{voice.id}">{spoken}</voice></speak>'
    )


async def synthesize(text: str, voice: Voice) -> bytes:
    """``text`` spoken with ``voice`` by Azure AI Speech, as an mp3; ``SpeechUnavailable`` without its key."""
    key, region = settings.AZURE_SPEECH_KEY, settings.AZURE_SPEECH_REGION
    if not key or not region:
        logger.warning("assistant.media.speech_not_configured")
        raise SpeechUnavailable
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": SPEECH_FORMAT,
        "User-Agent": "erplora",
    }
    body = ssml(text, voice).encode()
    response = await _send(speech_url(region), SPEECH_PATH, headers=headers, timeout=SPEECH_TIMEOUT, content=body)
    if not response.content:
        logger.warning("assistant.media.unreadable path=%s", SPEECH_PATH)
        raise MediaFailed(retriable=True)
    return response.content
