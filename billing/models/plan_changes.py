"""A plan change waiting for the end of the period."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class PlanChangeSchedule(UUIDModel):
    """A plan change waiting for the end of the period (a downgrade: a cheaper plan, or annual → monthly).

    Stripe holds it as a subscription schedule (``stripe_schedule_id``): the current phase ends with the paid
    period and the next one bills the new items, without proration, so no negative invoice arises.
    Kept here so the panel says «Starter from 1 Nov»; gone once applied or undone.
    """

    hub = models.OneToOneField(
        "hubs.Hub", on_delete=models.CASCADE, related_name="plan_change_schedule", verbose_name=_("business")
    )
    stripe_schedule_id = models.CharField(_("Stripe schedule"), max_length=255)
    plan_slug = models.CharField(_("plan"), max_length=50)
    interval = models.CharField(_("billing"), max_length=8)
    starts_at = models.DateTimeField(_("starts at"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("scheduled plan change")
        verbose_name_plural = _("scheduled plan changes")

    def __str__(self):
        return f"{self.hub_id} → {self.plan_slug}/{self.interval} at {self.starts_at:%Y-%m-%d}"
