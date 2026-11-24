"""A business of an account, as the SaaS knows it."""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from live.slugs import hub_slug_validator
from django.utils.translation import gettext_lazy as _

from hubs.countries import COUNTRY_NAMES
from hubs.models.payers import BillingProfile
from hubs.models.taxonomy import BusinessType


class Hub(models.Model):
    """A business of an account: what the SaaS knows of it, and what it owes the Hub service.

    ``id`` is the UUIDv7 the SaaS generates and the Hub keys its registry and database with
    (``hub_<hex>``). ``state_version`` grows with every change of the snapshot the Hub keeps;
    ``pushed_state_version`` is the last one the Hub acknowledged. ``pending_hub_call`` is the
    lifecycle call the Hub still owes an answer to (``put`` the registry, ``delete``, ``restore``):
    set in the command's transaction, cleared when the Hub acknowledges it, retried by
    ``reconcile_hub_states`` meanwhile.
    """

    class Status(models.TextChoices):
        PREPARING = "preparing", _("Preparing")
        ACTIVE = "active", _("Active")
        PAST_DUE = "past_due", _("Payment pending")
        SUSPENDED = "suspended", _("Suspended")
        DELETING = "deleting", _("Deleted")
        DELETED = "deleted", _("Purged")

    class HubCall(models.TextChoices):
        NONE = "", _("Nothing")
        PUT = "put", _("Register")
        DELETE = "delete", _("Delete")
        RESTORE = "restore", _("Restore")

    #: How long a deleted business can be recovered before the Hub purges it.
    RETENTION = timedelta(days=90)

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slug = models.CharField(_("address"), max_length=63, unique=True, validators=[hub_slug_validator])
    #: The address the business had before its owner changed it (HUBS-F16): still its own, so no other business
    #: takes it and receives the old links and QR codes; released when the address changes again.
    previous_slug = models.CharField(_("previous address"), max_length=63, blank=True, default="", db_index=True)
    name = models.CharField(_("name"), max_length=120)
    country = models.CharField(_("country"), max_length=2, choices=COUNTRY_NAMES, help_text=_("ISO 3166-1 alpha-2, e.g. ES."))
    timezone = models.CharField(_("time zone"), max_length=64, default="Europe/Madrid")
    language = models.CharField(_("language"), max_length=8, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE)
    business_type = models.ForeignKey(
        BusinessType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hubs",
        verbose_name=_("business type"),
    )
    # PROTECT: the payer of a live hub is never deleted silently.
    billing_profile = models.ForeignKey(
        BillingProfile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="hubs",
        verbose_name=_("billing profile"),
    )
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.PREPARING, db_index=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    provision_requested_at = models.DateTimeField(_("provisioning asked at"), null=True, blank=True)
    #: The Hub's real platform-wide provisioning pause from its signed status poll; ``None`` when there is none.
    maintenance = models.JSONField(_("provisioning maintenance"), null=True, blank=True, default=None)
    #: When the Hub starts moving the business to another server, in its night (a few minutes of maintenance), from
    #: its signed status poll (``services.scheduled_moves``); ``None`` without one, once started or cancelled.
    move_scheduled_for = models.DateTimeField(_("maintenance scheduled for"), null=True, blank=True)
    deletion_requested_at = models.DateTimeField(_("deletion asked at"), null=True, blank=True)
    can_buy_internal_plans = models.BooleanField(
        _("internal plans"),
        default=False,
        # In the table too: the code of the previous deploy keeps creating businesses while this one rolls out.
        db_default=False,
        help_text=_("Its owner sees the internal plans in the Store and may buy them. Only for ERPlora's own businesses."),
    )
    #: The clock of a business suspended for an unpaid plan (HUBS-F20): set when it is suspended, cleared when it
    #: pays; the notices of day 30 and 150 go out once each, and on day 180 it is deleted (``services.suspensions.age_suspended``).
    suspended_at = models.DateTimeField(_("suspended at"), null=True, blank=True)
    suspension_warned_at = models.DateTimeField(_("first suspension notice"), null=True, blank=True)
    suspension_final_notice_at = models.DateTimeField(_("last suspension notice"), null=True, blank=True)
    #: When the owner of a deleted business was told the copy of its data made at that deletion is ready
    #: (``services.reconciliation.reconcile``, «We'll let you know» of its page); older than ``deletion_requested_at``: not yet told.
    data_copy_mailed_at = models.DateTimeField(_("copy of the data announced at"), null=True, blank=True)
    #: How many passes the mail of the copy could not leave since this deletion (a refused recipient): given up at
    #: ``services.reconciliation.DATA_COPY_MAIL_ATTEMPTS``; back to 0 when the business is deleted again.
    data_copy_mail_attempts = models.PositiveSmallIntegerField(_("tries of the copy's mail"), default=0, db_default=0)
    state_version = models.PositiveBigIntegerField(_("state version"), default=1)
    pushed_state_version = models.PositiveBigIntegerField(_("state version the Hub has"), default=0)
    #: Grows with every change of the registry (``PUT /internal/hubs/{id}``): an acknowledgement of an
    #: older one never clears a newer one still owed.
    registry_version = models.PositiveIntegerField(_("registry version"), default=1)
    #: The Hub's last refusal of a call about this business (its error code), until a call succeeds:
    #: the panel shows an error instead of preparing for ever. Empty while all is well.
    last_hub_error = models.CharField(_("last refusal of the Hub"), max_length=64, blank=True, default="")
    hub_error_at = models.DateTimeField(_("refused at"), null=True, blank=True)
    pending_hub_call = models.CharField(
        _("call the Hub owes an answer to"), max_length=8, choices=HubCall.choices, blank=True, default=""
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = _("business")
        verbose_name_plural = _("businesses")
        constraints = [
            models.CheckConstraint(
                condition=Q(pushed_state_version__lte=F("state_version")),
                name="hubs_hub_pushed_not_ahead_of_state",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    def save(self, *args, **kwargs):
        """Whatever path writes a business, its address is one the Hub and the jump accept."""
        hub_slug_validator(self.slug)
        super().save(*args, **kwargs)

    @property
    def purge_after(self) -> datetime | None:
        if self.deletion_requested_at is None:
            return None
        return self.deletion_requested_at + self.RETENTION
