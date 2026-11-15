"""The notices to the team's mailbox about the OSS threshold."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from billing.models.invoices import Invoice


class OssNotice(UUIDModel):
    """A notice to the team's mailbox about the OSS threshold: the charged sale that took the year past 80 % of
    the threshold (``near``: register in the OSS now, it takes days) and the one that crossed it, or the first
    charged sale of a year that starts in destination because the previous one closed above (``crossed``).

    Once per year and kind: the row is the dedupe, persistent on purpose (a cache would warn again). Not
    written under a voluntary OSS registration, and ``near`` not in a year already crossed. Read only in the
    admin; ``mailed_at`` empty = the mail has not left yet (the daily ``retax_subscriptions`` sends it again).
    """

    class Kind(models.TextChoices):
        NEAR = "near", _("80 % of the threshold")
        CROSSED = "crossed", _("Threshold crossed")

    class Reason(models.TextChoices):
        NONE = "", _("—")
        CURRENT_YEAR = "current_year", _("Crossed this year")
        PREVIOUS_YEAR = "previous_year", _("The previous year closed above")

    year = models.PositiveSmallIntegerField(_("year"))
    kind = models.CharField(_("notice"), max_length=8, choices=Kind.choices)
    reason = models.CharField(_("reason"), max_length=16, choices=Reason.choices, blank=True)
    effective_from = models.DateField(_("destination VAT from"), null=True, blank=True)
    accumulated_cents = models.BigIntegerField(
        _("accumulated (cents)"),
        help_text=_("Cross-border B2C tax base in cents: of the year with the sale, or of the previous year"),
    )
    threshold_cents = models.BigIntegerField(
        _("threshold (cents)"), help_text=_("OSS threshold in force when the notice was written, in cents")
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="oss_notices", verbose_name=_("invoice")
    )
    mailed_at = models.DateTimeField(_("mailed at"), null=True, blank=True)
    recorded_at = models.DateTimeField(_("recorded at"), auto_now_add=True)

    class Meta:
        ordering = ["-year", "kind"]
        constraints = [models.UniqueConstraint(fields=["year", "kind"], name="billing_oss_notice_once_a_year")]
        verbose_name = _("OSS notice")
        verbose_name_plural = _("OSS notices")

    def __str__(self):
        return f"OSS {self.year} {self.kind}"
