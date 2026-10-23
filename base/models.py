"""The site's switches: one row, edited by the staff in the admin («Site settings»; ACCOUNTS-G33, G64).

Ported from ERPlora/saas ``SiteSettings`` (``apps/dashboard/core/models.py``, origin/develop c5ca8cae8): the maintenance
mode and its message in English and Spanish (ACCOUNTS-G82, ``base.maintenance``). One row by a constraint, not by
forcing ``pk = 1``: every key is a UUIDv7 here. Its state is read through ``base.queries.maintenance_state``, kept a
minute in the shared cache and dropped from it once a change commits, so every task sees the switch at once.
"""

import uuid

from django.core.cache import cache
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

#: The cache key of the maintenance state (``base.queries.maintenance_state``).
MAINTENANCE_CACHE_KEY = "base.maintenance"


class SiteSettings(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    #: Always True and unique: a second row cannot exist.
    singleton = models.BooleanField(default=True, unique=True, editable=False)
    maintenance_mode = models.BooleanField(
        _("maintenance mode"),
        default=False,
        help_text=_(
            "Every visitor gets the maintenance page; only the ERPlora staff with a session uses erplora.com. "
            "The health checks, the admin, the Hub's calls and the webhooks keep working."
        ),
    )
    maintenance_message_en = models.TextField(
        _("message in English"),
        blank=True,
        help_text=_("What the page says instead of its own text, for example when you will be back. Plain text."),
    )
    maintenance_message_es = models.TextField(
        _("message in Spanish"),
        blank=True,
        help_text=_("For Spanish visitors; empty, they read the English one."),
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")
        constraints = [models.CheckConstraint(condition=models.Q(singleton=True), name="base_sitesettings_singleton")]

    def __str__(self):
        return str(_("Site settings"))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # After the COMMIT: a request between the save and the commit would put the old state back in the cache.
        transaction.on_commit(lambda: cache.delete(MAINTENANCE_CACHE_KEY))

    def message_for(self, language: str) -> str:
        """The staff's message for ``language``: the Spanish one for Spanish when written, else the English one."""
        if language == "es" and self.maintenance_message_es:
            return self.maintenance_message_es
        return self.maintenance_message_en
