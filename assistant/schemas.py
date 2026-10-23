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
