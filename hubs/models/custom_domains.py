"""A business's own domain for its public website."""

import uuid

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from hubs.models.businesses import Hub


def new_certificate_token() -> str:
    """ACM's ``IdempotencyToken`` (32 at most, ``\\w``): the same one gives back the same certificate for an hour."""
    return uuid.uuid7().hex


class CustomDomain(models.Model):
    """A business's own domain for its public website (HUBS-F17): one for each business.

    It is nobody's until its CNAME reaches the name of THIS business (``proven_at``): asking for a stranger's domain keeps
    it from nobody, and only one business holds the proof of a name. A row goes last, once the Hub and the ALB have let
    go of the domain: that is what frees the name. ``attached_at`` is what counts for the listener's quota: AWS gives no
    list of its certificates to these roles (``aws`` README, «Dominio propio de un negocio»).
    """

    class State(models.TextChoices):
        #: On its way: its certificate, then the records of the customer, then the snapshot and the probe.
        PENDING = "pending", _("Waiting for your records")
        ACTIVE = "active", _("Connected")
        #: Not served and without a certificate; the reason says whether it comes back by itself.
        LAPSED = "lapsed", _("Not connected")
        #: Its owner took it out; the certificate is going, then the row.
        REMOVING = "removing", _("Being removed")

    class Reason(models.TextChoices):
        NONE = "", ""
        CERTIFICATE_PENDING = "certificate_pending", _("Create the validation record: the certificate is waiting for it.")
        CERTIFICATE_UNAVAILABLE = "certificate_unavailable", _("The certificate could not be asked for now. We will try again within the hour.")
        CERTIFICATE_FAILED = "certificate_failed", _("The certificate was refused for this domain. Check that its CAA records allow amazon.com, and ask for the domain again.")
        VALIDATION_TIMED_OUT = "validation_timed_out", _("The validation record did not appear in 72 hours. Create it and ask for the domain again.")
        QUOTA_FULL = "quota_full", _("There is no room for more domains right now. We will try again every hour.")
        CNAME_MISSING = "cname_missing", _("Create the record that points your domain at ERPlora.")
        DNS_UNAVAILABLE = "dns_unavailable", _("The records of your domain could not be read now. We will try again within the hour.")
        PROBE_FAILED = "probe_failed", _("Your domain points at ERPlora, but it is not being served yet. We will try again within the hour.")
        TAKEN = "taken", _("Another business is connected to this domain.")
        CHECKS_FAILED = "checks_failed", _("Your domain stopped pointing at ERPlora, so your website is no longer served on it. It comes back by itself when the record does.")
        NOT_IN_PLAN = "not_in_plan", _("Your plan does not include an own domain.")
        BUSINESS_GONE = "business_gone", _("This business was deleted.")

    #: Why it lapsed, when its CNAME alone brings it back. A certificate that was refused is not asked for again by itself:
    #: every hour, one CAA would spend ACM's certificates of the year.
    RETURNS_BY_ITSELF = frozenset({Reason.CHECKS_FAILED, Reason.CNAME_MISSING, Reason.NOT_IN_PLAN, Reason.BUSINESS_GONE})

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.OneToOneField(Hub, on_delete=models.CASCADE, related_name="custom_domain", verbose_name=_("business"))
    #: In the form the Hub and ACM are given (``hubs.domain_names``).
    hostname = models.CharField(_("domain"), max_length=64)
    state = models.CharField(_("state"), max_length=16, choices=State.choices, default=State.PENDING)
    #: Where it is stuck, in the customer's words: empty when nothing is missing.
    reason = models.CharField(_("reason"), max_length=32, choices=Reason.choices, blank=True, default=Reason.NONE)
    certificate_token = models.CharField(_("certificate token"), max_length=32, default=new_certificate_token, editable=False)
    certificate_arn = models.CharField(_("certificate"), max_length=255, blank=True, default="")
    attached_at = models.DateTimeField(_("on the listener since"), null=True, blank=True)
    validation_name = models.CharField(_("validation record"), max_length=255, blank=True, default="")
    validation_value = models.CharField(_("validation value"), max_length=255, blank=True, default="")
    proven_at = models.DateTimeField(_("proved at"), null=True, blank=True)
    activated_at = models.DateTimeField(_("connected at"), null=True, blank=True)
    #: Checks in a row that found it not pointing here or not served; a question that could not be answered does not count.
    failures = models.PositiveSmallIntegerField(_("failures in a row"), default=0)
    checked_at = models.DateTimeField(_("checked at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = _("own domain")
        verbose_name_plural = _("own domains")
        constraints = [
            models.UniqueConstraint(
                fields=["hostname"],
                condition=Q(proven_at__isnull=False),
                name="hubs_customdomain_one_proved_owner",
            )
        ]

    def __str__(self):
        return self.hostname

    @property
    def in_snapshot(self) -> bool:
        """Whether the Hub is told of it (``queries.hub_sync.hub_snapshot``, if the plan includes it too)."""
        return self.proven_at is not None and self.state in (self.State.PENDING, self.State.ACTIVE)
