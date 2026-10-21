"""What erplora.com keeps of a business's WhatsApp (README.md «Datos»).

A business's number and its Meta credentials (``PhoneNumber``, WHATSAPP-G04), the mirror of its templates at
Meta (``Template``), what the Hub asked to send, by its ``Idempotency-Key`` (``Send``), the month's counter
(``Usage``) and what waits to reach the Hub: a message of Meta's webhook or a delivery status (``Delivery``).
Neither the text of a sent message nor its recipient is kept; a received message lives here only until the Hub
took it and the retention passed (WHATSAPP-G14). Keys are UUIDv7.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from whatsapp.fields import EncryptedTextField


class PhoneNumber(models.Model):
    """A business's WhatsApp number at Meta: the business it belongs to, Meta's ids and the business token of
    Embedded Signup with the PIN it was registered with, both encrypted. A number has one owner in the whole
    platform; a business has one active number (the Hub's channel is one number)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        "hubs.Hub", on_delete=models.CASCADE, related_name="whatsapp_numbers", verbose_name=_("business")
    )
    phone_number_id = models.CharField(_("Meta number id"), max_length=50, unique=True)
    display_phone = models.CharField(_("number"), max_length=32)
    display_name = models.CharField(_("name on WhatsApp"), max_length=200, blank=True, default="")
    waba_id = models.CharField(_("WhatsApp Business account"), max_length=50)
    business_id = models.CharField(_("Meta business portfolio"), max_length=50, blank=True, default="")
    access_token = EncryptedTextField(_("business token"), blank=True, default="")
    registration_pin = EncryptedTextField(_("registration PIN"), blank=True, default="")
    is_on_biz_app = models.BooleanField(
        _("from the WhatsApp Business app"),
        default=False,
        help_text=_("Connected from the WhatsApp Business app (coexistence): never registered again."),
    )
    token_expires_at = models.DateTimeField(
        _("token expires"), null=True, blank=True, help_text=_("Empty: the token never expires.")
    )
    is_active = models.BooleanField(_("active"), default=True)
    needs_reconnect = models.BooleanField(
        _("needs reconnecting"),
        default=False,
        help_text=_("Meta's permission could not be renewed: only the business can fix it, by connecting again."),
    )
    reconnect_alerted_at = models.DateTimeField(_("owner warned"), null=True, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("connected by"),
    )
    connected_at = models.DateTimeField(_("connected"), default=timezone.now)
    disconnected_at = models.DateTimeField(_("disconnected"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("WhatsApp number")
        verbose_name_plural = _("WhatsApp numbers")
        ordering = ["-connected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["hub"], condition=Q(is_active=True), name="whatsapp_one_active_number_per_hub"
            )
        ]

    def __str__(self):
        return f"{self.display_phone} ({self.phone_number_id})"


class Template(models.Model):
    """A message template of a business as Meta has it: its id there, Meta's verdict and its content. Meta's key
    is the name and the language inside one account, so it is unique per business, never globally."""

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Under review")
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")
        PAUSED = "PAUSED", _("Paused by Meta")
        DISABLED = "DISABLED", _("Disabled by Meta")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        "hubs.Hub", on_delete=models.CASCADE, related_name="whatsapp_templates", verbose_name=_("business")
    )
    name = models.CharField(_("name"), max_length=512)
    language = models.CharField(_("language"), max_length=16)
    category = models.CharField(_("category"), max_length=20, default="UTILITY")
    status = models.CharField(_("Meta's verdict"), max_length=32, default=Status.PENDING)
    rejected_reason = models.CharField(_("Meta's reason"), max_length=500, blank=True, default="")
    meta_id = models.CharField(_("Meta template id"), max_length=64, blank=True, default="")
    header_format = models.CharField(_("header"), max_length=16, blank=True, default="")
    header = models.TextField(_("header text"), blank=True, default="")
    body = models.TextField(_("text"), blank=True, default="")
    body_examples = models.JSONField(_("examples"), default=list, blank=True)
    footer = models.TextField(_("footer"), blank=True, default="")
    buttons = models.JSONField(_("buttons"), default=list, blank=True)
    variables = models.PositiveSmallIntegerField(_("variables"), default=0)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("WhatsApp template")
        verbose_name_plural = _("WhatsApp templates")
        ordering = ["name", "language"]
        constraints = [
            models.UniqueConstraint(fields=["hub", "name", "language"], name="whatsapp_template_unique_per_hub")
        ]

    def __str__(self):
        return f"{self.name} [{self.language}] {self.status}"


class Send(models.Model):
    """One message the Hub asked to send, by its ``Idempotency-Key``: written before Meta is called, as a claim
    that reserves its place in the month's allowance. ``sent`` keeps Meta's id, so a retry gets it back without
    a second send; ``unknown`` is a call whose outcome Meta did not say. Neither the text nor the recipient."""

    class State(models.TextChoices):
        PENDING = "pending", _("Sending")
        SENT = "sent", _("Sent")
        UNKNOWN = "unknown", _("Unknown outcome")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        "hubs.Hub", on_delete=models.CASCADE, related_name="whatsapp_sends", verbose_name=_("business")
    )
    idempotency_key = models.CharField(_("key"), max_length=255)
    state = models.CharField(_("state"), max_length=8, choices=State.choices, default=State.PENDING)
    wa_message_id = models.CharField(_("WhatsApp message id"), max_length=255, blank=True, default="")
    month = models.CharField(_("month"), max_length=7, help_text=_("The month of the allowance it took, YYYY-MM."))
    created_at = models.DateTimeField(_("asked"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("WhatsApp send")
        verbose_name_plural = _("WhatsApp sends")
        constraints = [
            models.UniqueConstraint(fields=["hub", "idempotency_key"], name="whatsapp_send_key_unique_per_hub")
        ]
        indexes = [models.Index(fields=["hub", "wa_message_id"], name="whatsapp_send_message_idx")]

    def __str__(self):
        return f"{self.idempotency_key} → {self.wa_message_id or self.state}"


class Usage(models.Model):
    """The messages a business sent through erplora.com in a calendar month (UTC): what the plan's allowance
    is counted against, reserved one by one when a send is accepted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        "hubs.Hub", on_delete=models.CASCADE, related_name="whatsapp_usage", verbose_name=_("business")
    )
    month = models.CharField(_("month"), max_length=7)
    used = models.PositiveIntegerField(_("messages sent"), default=0)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("WhatsApp monthly usage")
        verbose_name_plural = _("WhatsApp monthly usage")
        constraints = [models.UniqueConstraint(fields=["hub", "month"], name="whatsapp_usage_unique_per_month")]

    def __str__(self):
        return f"{self.month}: {self.used}"


class Delivery(models.Model):
    """What waits to reach the Hub: a message Meta reported (door 1) or the furthest delivery status of a message
    the Hub sent (door 2). Pushed right after the COMMIT and, while the Hub does not take it, again with a growing
    wait. ``body`` is the door's body without ``hub``; ``media_id`` is Meta's id of its attachment, served at
    ``/whatsapp/media/<id>`` to the business's people."""

    class Kind(models.TextChoices):
        MESSAGE = "message", _("Message")
        STATUS = "status", _("Delivery status")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        "hubs.Hub", on_delete=models.CASCADE, related_name="whatsapp_deliveries", verbose_name=_("business")
    )
    kind = models.CharField(_("kind"), max_length=8, choices=Kind.choices)
    wa_message_id = models.CharField(_("WhatsApp message id"), max_length=255)
    contact = models.CharField(_("customer's number"), max_length=32, blank=True, default="")
    body = models.JSONField(_("content"), default=dict, blank=True)
    media_id = models.CharField(_("Meta attachment id"), max_length=64, blank=True, default="")
    #: Grows with every change of ``body`` (a status that moved on, a placeholder completed): a push of an older
    #: revision never marks a newer one as taken.
    revision = models.PositiveIntegerField(_("revision"), default=0)
    received_at = models.DateTimeField(_("received"), default=timezone.now)
    delivered_at = models.DateTimeField(_("taken by the Hub"), null=True, blank=True)
    attempts = models.PositiveIntegerField(_("attempts"), default=0)
    next_attempt_at = models.DateTimeField(
        _("next attempt"), null=True, blank=True, default=timezone.now,
        help_text=_("Empty: the Hub refused it as it is (422), it is not retried."),
    )
    last_error = models.CharField(_("last error"), max_length=300, blank=True, default="")

    class Meta:
        verbose_name = _("WhatsApp delivery to the Hub")
        verbose_name_plural = _("WhatsApp deliveries to the Hub")
        ordering = ["received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["hub", "kind", "wa_message_id"], name="whatsapp_delivery_unique_per_hub"
            )
        ]
        indexes = [
            models.Index(fields=["delivered_at", "next_attempt_at"], name="whatsapp_delivery_due_idx"),
            models.Index(fields=["hub", "contact"], name="whatsapp_delivery_contact_idx"),
        ]

    def __str__(self):
        return f"{self.kind} {self.wa_message_id}"
