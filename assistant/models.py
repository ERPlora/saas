"""What the AI gateway keeps (README.md «Datos»): the providers ERPlora pays, their keys and their models, and which
model answers. Keys are UUIDv7.

- ``AIProvider`` (ASSISTANT-G25): one of the four APIs the gateway speaks (``kind``) at its address.
- ``AIProviderCredential`` (G26): a key of a provider, encrypted (``assistant.fields``), with its last four
  characters as hint. Only ``assistant.services`` writes it.

Nothing here holds a conversation: the turn passes through and is forgotten (part 2, ADR-0149 of the old product).
"""

import ipaddress
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from assistant.fields import EncryptedTextField

#: Where each kind's API answers when the provider names no address of its own.
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "deepseek": "https://api.deepseek.com",
}


def on_this_machine(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_base_url(value: str) -> None:
    """The key travels to this address: https, or plain http to this machine only (the tests, a local proxy)."""
    if not value:
        return
    parts = urlsplit(value)
    if parts.scheme == "https" and parts.hostname:
        return
    if parts.scheme == "http" and parts.hostname and on_this_machine(parts.hostname):
        return
    raise ValidationError(
        _("Use an https address: the provider's key travels to it."), code="assistant.insecure_base_url"
    )


class AIProvider(models.Model):
    """A provider of models ERPlora pays, spoken to with the client of its ``kind`` (``assistant.providers``)."""

    class Kind(models.TextChoices):
        OPENAI = "openai", "OpenAI"
        ANTHROPIC = "anthropic", "Anthropic"
        GEMINI = "gemini", "Google Gemini"
        DEEPSEEK = "deepseek", "DeepSeek"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slug = models.SlugField(
        _("identifier"),
        max_length=32,
        unique=True,
        help_text=_("Short name the commands use, e.g. «openai»."),
    )
    name = models.CharField(_("name"), max_length=64)
    kind = models.CharField(
        _("API"),
        max_length=16,
        choices=Kind.choices,
        help_text=_("The API the provider speaks. A provider compatible with OpenAI's is «OpenAI» with its address."),
    )
    base_url = models.CharField(
        _("address"),
        max_length=200,
        blank=True,
        default="",
        validators=[validate_base_url],
        help_text=_("Empty: the provider's own. Another one (a proxy, a compatible provider) over https."),
    )
    is_enabled = models.BooleanField(
        _("enabled"), default=True, help_text=_("Off: none of its models answers nor can be tried.")
    )
    notes = models.TextField(_("notes"), blank=True, default="")
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("AI provider")
        verbose_name_plural = _("AI providers")
        ordering = ["name"]

    def __str__(self):
        return self.name or self.slug

    @property
    def api_base(self) -> str:
        """The address the client calls: the provider's own, or its kind's."""
        return (self.base_url or DEFAULT_BASE_URLS.get(self.kind, "")).rstrip("/")


class AIProviderCredential(models.Model):
    """A key of a provider. The column holds its token; ``key_hint`` (its last four characters) is the only part
    ever shown. A key that no live key of the platform opens reads as empty: «Unreadable», type it again."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    provider = models.ForeignKey(
        AIProvider, on_delete=models.CASCADE, related_name="credentials", verbose_name=_("provider")
    )
    label = models.CharField(_("label"), max_length=64, default="default")
    api_key = EncryptedTextField(_("key"), blank=True, default="")
    key_hint = models.CharField(_("key ends in"), max_length=8, blank=True, default="", editable=False)
    is_active = models.BooleanField(_("active"), default=True)
    rotated_at = models.DateTimeField(_("key changed"), null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("added by"),
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("changed by"),
        editable=False,
    )
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("provider key")
        verbose_name_plural = _("provider keys")
        ordering = ["provider__name", "label"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "label"], name="assistant_credential_unique_label"),
        ]

    def __str__(self):
        return f"{self.provider.slug}:{self.label} ({self.masked_key})"

    @property
    def masked_key(self) -> str:
        return f"…{self.key_hint}" if self.key_hint else "…"

    @property
    def is_readable(self) -> bool:
        """Whether the key opens with a live key of the platform (an unreadable one reads as empty)."""
        return bool(self.api_key)
