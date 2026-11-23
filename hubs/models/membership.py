"""Who belongs to a business, with which role, and the hand-over of its ownership."""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from hubs.models.businesses import Hub


class HubMember(models.Model):
    """Who belongs to a hub, with which of the five roles: access is per hub.

    An invitation is a member without an answer (``accepted_at`` empty): it expires
    ``INVITATION_WINDOW`` after it was sent (``invitation_expires_at``; «Resend» renews it) and
    «Decline» deletes the row. Only an answered membership enters the hub. The owner is born
    answered, with the business, and there is at most one per hub: ownership only moves by an
    accepted ``HubOwnershipTransfer``.
    """

    class Role(models.TextChoices):
        # A context of their own: the project's catalog already translates a bare «Manager».
        OWNER = "hub_owner", pgettext_lazy("hub role", "Owner")
        ADMIN = "hub_admin", pgettext_lazy("hub role", "Admin")
        MANAGER = "hub_manager", pgettext_lazy("hub role", "Manager")
        EMPLOYEE = "hub_employee", pgettext_lazy("hub role", "Employee")
        ACCOUNTANT = "hub_accountant", pgettext_lazy("hub role", "Accountant")

    #: Authority: lower is more. Nobody acts on a peer or a superior, nor grants their own rank.
    RANK = {Role.OWNER: 10, Role.ADMIN: 20, Role.MANAGER: 30, Role.EMPLOYEE: 40, Role.ACCOUNTANT: 40}
    #: The roles that take no seat of the plan: the accountancy firm only reads (the Hub does not count it either).
    FREE_ROLES = frozenset({Role.ACCOUNTANT})
    INVITATION_WINDOW = timedelta(days=7)

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="members", verbose_name=_("business"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hub_members", verbose_name=_("user")
    )
    # Least privilege by default: an invitation that forgets the role hands out the least.
    role = models.CharField(_("role"), max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("invited by"),
    )
    invitation_message = models.TextField(_("message"), blank=True, max_length=500)
    invited_at = models.DateTimeField(_("invited at"), null=True, blank=True)
    invitation_expires_at = models.DateTimeField(_("invitation expires at"), null=True, blank=True)
    joined_at = models.DateTimeField(_("joined at"), default=timezone.now)
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)
    last_opened_at = models.DateTimeField(_("last opened at"), null=True, blank=True)

    class Meta:
        ordering = ["joined_at", "id"]
        verbose_name = _("member")
        verbose_name_plural = _("members")
        constraints = [
            models.UniqueConstraint(fields=["hub", "user"], name="hubs_member_one_per_hub_and_user"),
            models.UniqueConstraint(fields=["hub"], condition=Q(role="hub_owner"), name="hubs_member_one_owner"),
            # Fail closed: a role outside the five (a retired key from a data migration, a typo in the
            # admin) would rank nowhere in the access checks; the database never stores one.
            models.CheckConstraint(
                condition=Q(role__in=["hub_owner", "hub_admin", "hub_manager", "hub_employee", "hub_accountant"]),
                name="hubs_member_role_known",
            ),
        ]
        indexes = [models.Index(fields=["user", "-last_opened_at"], name="hubs_member_user_opened")]

    def __str__(self):
        # What the staff read in the audit trail and on an account's page: who, on which business, as what.
        return f"{self.user} @ {self.hub.slug} ({self.get_role_display()})"

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None

    def is_expired(self, now: datetime) -> bool:
        """An unanswered invitation past its window: it can no longer be accepted."""
        return self.is_pending and self.invitation_expires_at is not None and self.invitation_expires_at <= now


class HubOwnershipTransfer(models.Model):
    """A pending or resolved hand-over of a hub's ownership.

    Only the owner offers it, only to somebody already on the hub, and the recipient answers within
    ``WINDOW``; the outgoing owner stays as admin and the payer does not move. ``from_user`` and
    ``to_user`` go NULL with their accounts; the two emails keep the trail.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    WINDOW = timedelta(days=7)

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="ownership_transfers")
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    from_email = models.EmailField(_("from"))
    to_email = models.EmailField(_("to"))
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expires at"))
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("ownership transfer")
        verbose_name_plural = _("ownership transfers")
        constraints = [
            # Two live offers could both be accepted, and the second would demote the first new owner.
            models.UniqueConstraint(fields=["hub"], condition=Q(status="pending"), name="hubs_transfer_one_pending"),
        ]
        indexes = [models.Index(fields=["to_user", "status"], name="hubs_transfer_to_status")]

    def __str__(self):
        return f"{self.from_email} → {self.to_email} ({self.status})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()
