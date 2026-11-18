"""The sessions of an account the Hub must end."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from hubs.models.businesses import Hub


class SessionRevocation(models.Model):
    """An account's sessions the Hub must end, as OIDC's back-channel logout does: in one business,
    or in every one (``hub`` empty).

    Queued in the transaction that took the access away (removing a member, changing a role, handing
    the ownership over), delivered after the COMMIT (``POST /internal/sessions/revoke``) and, while the
    Hub is away or refuses it, retried by ``reconcile_hub_states`` once ``next_attempt_at`` passes (the
    wait doubles with every failed ``attempts``). ``delivered_at`` marks it done, once.

    ``user`` has no database constraint and is never cascaded: a revocation outlives the account it
    ends (deleting an account ends its sessions everywhere).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
        verbose_name=_("account"),
    )
    hub = models.ForeignKey(
        Hub,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="session_revocations",
        verbose_name=_("business"),
        help_text=_("Empty: every business of the account."),
    )
    requested_at = models.DateTimeField(_("requested at"), default=timezone.now)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    attempts = models.PositiveIntegerField(_("attempts"), default=0)
    next_attempt_at = models.DateTimeField(_("next attempt at"), default=timezone.now)
    last_error = models.CharField(_("last error"), max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-requested_at", "id"]
        verbose_name = _("session revocation")
        verbose_name_plural = _("session revocations")
        indexes = [
            models.Index(
                fields=["next_attempt_at"], condition=Q(delivered_at__isnull=True), name="hubs_revocation_due"
            )
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.hub_id or '*'}"
