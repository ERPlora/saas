"""The services the assistants use besides the turn (ASSISTANT-G54, G56, G57, F27): the fingerprints (embeddings) of
the Hub's index and of the panel's documentation (``index_docs``, ``assistant.docs.search``) and the transcription of a
dictation, by OpenAI's API, through the services' provider (``assistant.service.connection``:
``ASSISTANT_SERVICE_PROVIDER``), kept in the admin with its key, rotatable. The reading aloud of an answer has no engine
(``SPEECH_ENGINE``, PLAN-SAAS round 2026-11-04c).

Each call goes over ``httpx``, with no SDK, the same way as ``assistant.providers``. A failure is a ``MediaFailed``
with the provider's class (rejected, or worth trying again) and never the key nor the provider's words (they could
quote what was dictated); the log says the path and the status only. A server whose trusted certificates cannot be
loaded is a final failure, logged with the setting and its file by ``base.tls`` (caller ``assistant.media``). Nothing is
written to disk: the audio goes from memory to the provider and back.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

import httpx

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


#: The languages an answer is read aloud in, base code.
SPEECH_LANGUAGES = ("es", "en")
#: What reads an answer aloud: ``(text, language, voice)`` to an mp3, an empty voice being its own for the language. None
#: since the provider of Azure AI Speech left (PLAN-SAAS round 2026-11-04c): the door and the panel's route answer 503
#: ``assistant.speech_unavailable``, and the Hub and the panel read with the device's voice. A free engine, in our own
#: containers, takes this place in a round of its own (§35); ``MediaFailed`` is how it fails.
SPEECH_ENGINE: Callable[[str, str, str], Awaitable[bytes]] | None = None


class MediaFailed(Exception):
    """A call to a provider that failed: ``retriable`` if another attempt may succeed."""

    def __init__(self, retriable: bool, status: int | None = None):
        super().__init__("retriable" if retriable else "rejected")
        self.retriable, self.status = retriable, status

    @property
    def code(self) -> str:
        return "assistant.provider_unavailable" if self.retriable else "assistant.provider_rejected"


async def _post(service: ServiceConnectionOut, path: str, *, timeout: httpx.Timeout = TIMEOUT, **request) -> httpx.Response:
    headers = {"Authorization": f"Bearer {service.api_key.get_secret_value()}"}
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=tls.trusted_context("assistant.media")) as client:
            response = await client.post(f"{service.base_url}{path}", headers=headers, **request)
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
