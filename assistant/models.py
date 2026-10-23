"""What the AI gateway keeps (README.md «Datos»): the providers ERPlora pays, their keys and their models, and which
model answers. Keys are UUIDv7.

- ``AIProvider`` (ASSISTANT-G25): one of the four APIs the gateway speaks (``kind``) at its address.
- ``AIProviderCredential`` (G26): a key of a provider, encrypted (``assistant.fields``), with its last four
  characters as hint. Only ``assistant.services`` writes it.
- ``AIModel`` (G24): a model of a provider the staff chose, with its prices (USD per million tokens, typed by hand:
  the APIs do not give them) and what it supports.
- ``AIRoutingPolicy`` (G27): one row, the model that answers and the fallback one; a model it uses is never deleted.
- ``AssistantUsage`` (G29, G51, G52): what a business (or a demo) spent through the gateway, a row per calendar month
  (UTC; a demo, one row for its whole life): its messages, the tokens of its turns and of its embeddings, its voice
  and what it cost. Numbers only: never a conversation, a person nor a text.

Nothing here holds a conversation: the turn passes through and is forgotten (ADR-0149 of the old product).
"""

import ipaddress
import uuid
from decimal import Decimal
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
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


def estimate_cost(price_input_per_1m: Decimal, price_output_per_1m: Decimal, tokens_in: int, tokens_out: int) -> Decimal:
    """USD of a turn with these tokens at these prices (USD per million tokens), exact (money is never a float)."""
    return (price_input_per_1m * tokens_in + price_output_per_1m * tokens_out) / Decimal(1_000_000)


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


class AIModel(models.Model):
    """A model of a provider that the staff keep: it can be tried and chosen to answer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    provider = models.ForeignKey(AIProvider, on_delete=models.CASCADE, related_name="models", verbose_name=_("provider"))
    model_id = models.CharField(_("model"), max_length=128, help_text=_("The name the provider's API gives it."))
    display_name = models.CharField(_("name"), max_length=128)
    context_window = models.PositiveIntegerField(
        _("context"), default=0, help_text=_("Tokens of input it accepts (0: unknown).")
    )
    price_input_per_1m = models.DecimalField(
        _("input price"), max_digits=10, decimal_places=4, default=Decimal("0"), help_text=_("USD per million input tokens.")
    )
    price_output_per_1m = models.DecimalField(
        _("output price"), max_digits=10, decimal_places=4, default=Decimal("0"), help_text=_("USD per million output tokens.")
    )
    supports_tools = models.BooleanField(_("tools"), default=True)
    supports_vision = models.BooleanField(_("images"), default=False)
    is_available = models.BooleanField(
        _("available"), default=True, help_text=_("Off: it can neither be tried nor answer.")
    )
    notes = models.TextField(_("notes"), blank=True, default="")
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("AI model")
        verbose_name_plural = _("AI models")
        ordering = ["provider__name", "display_name"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id"], name="assistant_model_unique_per_provider"),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.provider.slug})"

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> Decimal:
        """USD of a turn with these tokens, exact (money is never a float)."""
        return estimate_cost(self.price_input_per_1m, self.price_output_per_1m, tokens_in, tokens_out)


class AIRoutingPolicy(models.Model):
    """Which model answers and which one if its provider fails. One row (``slot``); ``solo`` gives it."""

    SLOT = "default"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slot = models.CharField(max_length=16, default=SLOT, unique=True, editable=False)
    active_model = models.ForeignKey(
        AIModel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("model that answers"),
    )
    fallback_model = models.ForeignKey(
        AIModel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("fallback model"),
        help_text=_("Answers when the provider of the first one fails or cannot be used."),
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
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("model that answers")
        verbose_name_plural = _("model that answers")

    def __str__(self):
        if self.active_model_id is None:
            return "—"
        if self.fallback_model_id is None:
            return str(self.active_model)
        return f"{self.active_model} → {self.fallback_model}"

    @classmethod
    def solo(cls) -> "AIRoutingPolicy":
        return cls.objects.get_or_create(slot=cls.SLOT)[0]


class AssistantUsage(models.Model):
    """What a business spent through the gateway in a calendar month (UTC), or a demo in its whole life.

    ``messages`` is what the plan's monthly allowance (``Plan.assistant_messages_per_month``) is counted against, one
    per request of a person, reserved before the model is called (``assistant.message.claim``); the tokens and the
    cost (USD, with the prices of the model that answered) are added when the turn ends. A demo has no row in the
    SaaS (its Hub keeps it): it is named by its ``demo-…`` address and has one row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assistant_usage",
        verbose_name=_("business"),
    )
    demo = models.CharField(_("demo"), max_length=63, blank=True, default="")
    month = models.DateField(_("month"), help_text=_("The first day of the month (UTC)."))
    messages = models.PositiveIntegerField(_("messages"), default=0)
    tokens_input = models.PositiveBigIntegerField(_("input tokens"), default=0)
    tokens_output = models.PositiveBigIntegerField(_("output tokens"), default=0)
    tokens_embedding = models.PositiveBigIntegerField(_("embedding tokens"), default=0)
    transcriptions = models.PositiveIntegerField(_("dictations"), default=0)
    speech_characters = models.PositiveBigIntegerField(_("characters read aloud"), default=0)
    cost_usd = models.DecimalField(_("cost (USD)"), max_digits=14, decimal_places=6, default=Decimal("0"))
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("assistant usage record")
        verbose_name_plural = _("assistant usage records")
        ordering = ["-month", "hub__name", "demo"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(hub__isnull=False) & Q(demo="")) | (Q(hub__isnull=True) & ~Q(demo="")),
                name="assistant_usage_business_or_demo",
            ),
            models.UniqueConstraint(
                fields=["hub", "month"], condition=Q(hub__isnull=False), name="assistant_usage_one_per_month"
            ),
            models.UniqueConstraint(fields=["demo"], condition=~Q(demo=""), name="assistant_usage_one_per_demo"),
        ]

    def __str__(self):
        who = self.demo or (self.hub.name if self.hub_id else "—")
        return f"{who} · {self.month:%Y-%m}"
