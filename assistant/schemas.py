"""Inputs and outputs of the assistant's operations. A provider's key is a ``SecretStr``: no ``repr``, dump nor
JSON of a schema shows it (only ``get_secret_value`` does, where the key is used)."""

from datetime import datetime
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
