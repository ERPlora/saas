"""The usage of a business, one day at a time, as the Hub measures it."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from hubs.models.businesses import Hub


class HubUsageDaily(models.Model):
    """One day of a business's usage, as the Hub measured it that night.

    ``s3_bytes`` is what its files take in S3 (the storage the customer sees, as a percentage of what the
    plan includes), ``db_bytes`` what its database takes (the admin's only), ``active_users_1d`` the people
    active that day and ``active_users_30d`` in the 30 days up to it. ``requests`` is what it served that day,
    ``peak_connections`` the most transactions at once against its database and ``busy_requests`` the times a
    request found no room: for the admin only, the panel never shows them, and ``None`` when the Hub did not
    measure them, never a 0. One row per business and day, written only by the system command
    ``hubs.usage.record`` (``manage.py collect_hub_usage``, nightly in ``saas-cron``): collecting a day
    again replaces its figures. That pass ends by forgetting the days past ``services.usage_collection.USAGE_RETENTION_DAYS``
    (``hubs.usage.prune``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="usage_days", verbose_name=_("business"))
    day = models.DateField(_("day"))
    s3_bytes = models.PositiveBigIntegerField(_("files (bytes)"))
    db_bytes = models.PositiveBigIntegerField(_("database (bytes)"))
    active_users_1d = models.PositiveIntegerField(_("active that day"))
    active_users_30d = models.PositiveIntegerField(_("active in the 30 days"))
    requests = models.PositiveBigIntegerField(_("requests"), null=True, blank=True)
    peak_connections = models.PositiveIntegerField(_("peak connections"), null=True, blank=True)
    busy_requests = models.PositiveBigIntegerField(_("requests with no room"), null=True, blank=True)
    collected_at = models.DateTimeField(_("collected at"), default=timezone.now)

    class Meta:
        ordering = ["-day", "hub_id"]
        verbose_name = _("daily usage")
        verbose_name_plural = _("daily usages")
        constraints = [
            # Also the index of a business's days, newest first (``hubs.usage.*``).
            models.UniqueConstraint(fields=["hub", "day"], name="hubs_usage_one_row_per_day"),
        ]

    def __str__(self):
        return f"{self.hub_id} @ {self.day}"
