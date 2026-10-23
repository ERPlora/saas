"""Inputs and outputs of the assistant's operations. A provider's key is a ``SecretStr``: no ``repr``, dump nor
JSON of a schema shows it (only ``get_secret_value`` does, where the key is used)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field, SecretStr, field_validator


class CredentialIn(Schema):
    """A provider's key, new (no ``id``) or changed; without ``api_key`` a change keeps the one there was."""

    provider: UUID
    id: UUID | None = None
    label: str = Field(default="default", max_length=64)
    is_active: bool = True
    api_key: SecretStr | None = None

    @field_validator("label", mode="before")
    @classmethod
    def _trimmed_label(cls, value):
        value = (value or "").strip() if isinstance(value, str) or value is None else value
        return value or "default"

    @field_validator("api_key", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CredentialOut(Schema):
    id: UUID
    provider: UUID
    label: str
    is_active: bool
    masked_key: str
    rotated_at: datetime | None


class CredentialDeleteIn(Schema):
    id: UUID


class CredentialDeleteOut(Schema):
    deleted: bool


class ProviderRef(Schema):
    id: UUID


class ConnectionOut(Schema):
    """What a client needs to call a provider: its API, its address and its usable key (a secret)."""

    id: UUID
    name: str
    kind: str
    base_url: str
    api_key: SecretStr
    existing: list[str]


class ListedModel(Schema):
    """A chat model as the provider's API listed it."""

    model_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=128)
    context_window: int = Field(default=0, ge=0)


class ModelSelectIn(Schema):
    provider: UUID
    listed: list[ListedModel]
    #: The ``model_id``s ticked among ``listed``.
    selected: list[str]


class ModelSelectOut(Schema):
    created: int
    kept: int
    deleted: int
    protected: int


class NoInput(Schema):
    """An operation that takes nothing."""


class PolicyIn(Schema):
    active_model: UUID | None = None
    fallback_model: UUID | None = None


class PolicyOut(Schema):
    active_model: UUID | None
    fallback_model: UUID | None
    updated_at: datetime | None


class ModelChoice(Schema):
    id: UUID
    label: str


class PolicyShowOut(Schema):
    active_model: UUID | None
    fallback_model: UUID | None
    updated_at: datetime | None
    updated_by: str
    #: The models that can be chosen: available, of an enabled provider.
    choices: list[ModelChoice]


class RouteIn(Schema):
    """The route of a turn: the policy's (no ``model``), or one model alone (trying it)."""

    model: UUID | None = None


class RouteCandidate(Schema):
    """A model that can answer, with what its client needs (its key, a secret) and its prices (USD per 1M)."""

    model: UUID
    model_id: str
    display_name: str
    provider: str
    kind: str
    base_url: str
    api_key: SecretStr
    price_input_per_1m: Decimal
    price_output_per_1m: Decimal
    supports_tools: bool
    supports_vision: bool


class RouteOut(Schema):
    #: In order: the model that answers, then its fallback.
    candidates: list[RouteCandidate]


class ModelTryIn(Schema):
    """A try of a model from the admin: how long the message was and how many tools it offered, never the message."""

    model: UUID
    prompt_chars: int = Field(ge=0)
    tools: int = Field(ge=0)


class ModelTryOut(Schema):
    recorded: bool


class CredentialImportIn(Schema):
    """A provider's key the platform loads (from the environment): the provider is the one of its API (``kind``)."""

    kind: Literal["openai", "anthropic", "gemini", "deepseek"]
    api_key: SecretStr
    label: str = Field(default="default", min_length=1, max_length=64)
    #: Replace a key already kept with that label.
    force: bool = False
    #: Say what would happen, writing nothing.
    dry_run: bool = False


class CredentialImportOut(Schema):
    provider: str
    #: ``created``, ``rotated`` or ``kept`` (a key with that label was there and ``force`` was not given).
    action: Literal["created", "rotated", "kept"]
    label: str
    masked_key: str


class EncryptionRotateIn(Schema):
    #: Count what would be written again, writing nothing.
    dry_run: bool = False


class RotatedColumn(Schema):
    #: ``<app>.<Model>.<field>``.
    column: str
    rotated: int
    current: int
    #: The primary keys of the rows whose value no live key opens (never written).
    unreadable: list[str]


class EncryptionRotateOut(Schema):
    columns: list[RotatedColumn]
    rotated: int
    current: int
    unreadable: int


# --- The Hub's turn (part 2): who calls, the allowance and what it spent ------------------------------------------


class CallerIn(Schema):
    """A door's ``hub``: a business by its address or its id, or a demo by its ``demo-…`` address."""

    hub: str = Field(min_length=1, max_length=63)


class Caller(Schema):
    """Who a call of the Hub is for: a business (``hub_id``) or a demo (``demo``, its address); never both."""

    hub_id: UUID | None = None
    demo: str = ""
    slug: str


class UsageOut(Schema):
    """What the caller spent of its allowance: ``used`` of ``limit`` messages, back on ``resets_at`` (UTC; ``None``
    for a demo, whose messages never come back)."""

    used: int
    limit: int
    resets_at: datetime | None
    demo: bool


class ClaimOut(UsageOut):
    """A message taken from the allowance (``claimed``), or not because none is left; ``month`` is the window it was
    taken from (where a release gives it back)."""

    claimed: bool
    month: date


class MessageReleaseIn(Schema):
    """Give back a message taken in ``month``: the turn failed before answering anything."""

    caller: Caller
    month: date


class UsageRecordIn(Schema):
    """What a turn (or an embedding, a dictation, a reading aloud) spent, added to this month's row of the caller."""

    caller: Caller
    tokens_input: int = Field(default=0, ge=0)
    tokens_output: int = Field(default=0, ge=0)
    tokens_embedding: int = Field(default=0, ge=0)
    transcriptions: int = Field(default=0, ge=0)
    speech_characters: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


class TurnIn(CallerIn):
    """A turn of the Hub: the whole conversation (its browser owns it), the ``instructions`` that are its only system
    message, the tools it offers and, answering the tools it was asked for, the ``continuation`` it got with them."""

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    instructions: str = Field(default="", max_length=200_000)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=256)
    continuation: str | None = Field(default=None, max_length=4096)


class ServiceConnectionOut(Schema):
    """What the embeddings and the voice need of the services' provider (of OpenAI's API): its address and its key."""

    provider: str
    base_url: str
    api_key: SecretStr


class EmbeddingsIn(CallerIn):
    """The texts whose fingerprints (vectors) the Hub's index keeps, 1 to 256."""

    texts: list[str] = Field(min_length=1, max_length=256)

    @field_validator("texts")
    @classmethod
    def _no_empty_text(cls, texts):
        if any(not text.strip() for text in texts):
            raise ValueError("every text must have something written")
        return texts


class TranscribeIn(CallerIn):
    """A dictation: its audio in base64, its type (``audio/webm``, ``audio/ogg``, ``audio/wav``, ``audio/mp4``,
    ``audio/mpeg`` or ``audio/flac``) and, if the Hub knows it, its language (``es`` or ``es-ES``)."""

    audio: str = Field(min_length=1)
    mime_type: str
    language: str = Field(default="", max_length=16)

    @field_validator("mime_type")
    @classmethod
    def _an_audio_type(cls, value):
        from assistant.media import AUDIO_TYPES

        kind = value.split(";")[0].strip().lower()
        if kind not in AUDIO_TYPES:
            raise ValueError(f"one of {', '.join(sorted(AUDIO_TYPES))}")
        return kind


class SynthesizeIn(CallerIn):
    """A text to read aloud and, optionally, its voice (``alloy``, ``echo``, ``fable``, ``onyx``, ``nova`` or
    ``shimmer``; another one is ``alloy``)."""

    text: str = Field(max_length=100_000)
    voice: str = Field(default="", max_length=32)

    @field_validator("text")
    @classmethod
    def _something_to_read(cls, value):
        if not value.strip():
            raise ValueError("write the text to read aloud")
        return value.strip()
