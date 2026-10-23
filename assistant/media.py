"""The services of OpenAI's API the Hub's assistant uses besides the turn (ASSISTANT-G54, G56, G57): the fingerprints
(embeddings) of the Hub's index, the transcription of a dictation and the reading aloud of an answer.

Each call goes to the services' provider (``assistant.service.connection``: ``ASSISTANT_SERVICE_PROVIDER``, kept in
the admin with its key, rotatable) over ``httpx``, with no SDK, the same way as ``assistant.providers``. A failure is
a ``MediaFailed`` with the provider's class (rejected, or worth trying again) and never the key nor the provider's
words (they could quote what was dictated); the log says the status only. Nothing is written to disk: the audio goes
from memory to the provider.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx

from assistant.providers.base import is_retriable_status
from assistant.schemas import ServiceConnectionOut

logger = logging.getLogger(__name__)

#: The model of the fingerprints, always the same (the Hub's index compares vectors of one model), and its price.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_PRICE_PER_1M = Decimal("0.02")
TRANSCRIBE_MODEL = "whisper-1"
SPEECH_MODEL = "tts-1"
VOICES = frozenset({"alloy", "echo", "fable", "onyx", "nova", "shimmer"})
DEFAULT_VOICE = "alloy"
#: A few seconds of speech fit many times over.
MAX_AUDIO_BYTES = 2 * 1024 * 1024
#: What the provider reads aloud in one call.
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


class MediaFailed(Exception):
    """A call to the services' provider that failed: ``retriable`` if another attempt may succeed."""

    def __init__(self, retriable: bool, status: int | None = None):
        super().__init__("retriable" if retriable else "rejected")
        self.retriable, self.status = retriable, status

    @property
    def code(self) -> str:
        return "assistant.provider_unavailable" if self.retriable else "assistant.provider_rejected"


async def _post(service: ServiceConnectionOut, path: str, **request) -> httpx.Response:
    headers = {"Authorization": f"Bearer {service.api_key.get_secret_value()}"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(f"{service.base_url}{path}", headers=headers, **request)
    except httpx.HTTPError as problem:
        logger.warning("assistant.media.unreachable path=%s kind=%s", path, type(problem).__name__)
        raise MediaFailed(retriable=True) from None
    if response.status_code >= 400:
        logger.warning("assistant.media.failed path=%s status=%s", path, response.status_code)
        raise MediaFailed(retriable=is_retriable_status(response.status_code), status=response.status_code)
    return response


async def embed(service: ServiceConnectionOut, texts: list[str]) -> tuple[list[list[float]], int]:
    """A vector per text, in the order of ``texts``, and the tokens the provider counted."""
    response = await _post(service, "/embeddings", json={"model": EMBEDDING_MODEL, "input": texts})
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


def voice_of(voice: str) -> str:
    chosen = voice.strip().lower()
    return chosen if chosen in VOICES else DEFAULT_VOICE


async def synthesize(service: ServiceConnectionOut, text: str, voice: str) -> bytes:
    """``text`` spoken with ``voice``, as an mp3."""
    body = {"model": SPEECH_MODEL, "voice": voice, "input": text, "response_format": "mp3"}
    response = await _post(service, "/audio/speech", json=body)
    return response.content
