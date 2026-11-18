"""The plans a business subscribes to, as the staff keep them in the admin."""

import uuid

from django.db import models
from django.utils.formats import number_format
from django.utils.translation import ngettext
from django.utils.translation import gettext_lazy as _

from hubs.models.translated_fields import TranslatedFields


class PlanQuerySet(models.QuerySet):
    def public(self):
        """Active plans not ``internal_only``: what a visitor may be shown.

        Every public door lists plans through here; door-specific cuts (``upgrade_only``…) go on
        top of this, never instead of it.
        """
        return self.filter(is_active=True, internal_only=False)

    def signup_trial_days(self):
        """Shortest and longest free trial a visitor gets by creating a hub on a public plan.

        ``{"trial_days_min": …, "trial_days_max": …}``, both ``None`` when no plan on sale has a
        trial. An upgrade grants no trial, so ``upgrade_only`` plans never count. Every public
        page that states the trial reads it here.
        """
        return (
            self.public()
            .filter(upgrade_only=False, trial_period_days__gt=0)
            .aggregate(trial_days_min=models.Min("trial_period_days"), trial_days_max=models.Max("trial_period_days"))
        )

    def offered_to(self, hub):
        """The plans ``hub`` may be sold: every active one, internal ones included, if ERPlora's staff marked it
        (``Hub.can_buy_internal_plans``); ``public()`` for any other business, or without one.

        The Store lists and sells plans through here. The staff never own a business, so the mark is how one of
        ERPlora's own businesses, owned by a customer account, buys an internal plan.
        """
        if hub is not None and hub.can_buy_internal_plans:
            return self.filter(is_active=True)
        return self.public()


class Plan(TranslatedFields):
    """A subscription plan of a hub. Prices are net, VAT excluded.

    One subscription buys one hub and everything inside it: every device and user (multi-location
    comes from Pro and is charged per location). Free is permanent, needs no card and is the way in;
    no plan on sale carries a trial (``trial_period_days`` stays, dormant, for staff to use). Pro,
    Enterprise and Max are upgrade-only; ``payment-test`` is internal. The plans live only in the
    database and staff keep them in the admin: migration ``hubs/0013`` seeds them, and no deploy writes
    them again.
    """

    class IncludedLevel(models.TextChoices):
        """One level name, the same across every ERPlora premium module."""

        FREE = "free", "Free"
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    class SupportLevel(models.TextChoices):
        """Channel and priority, never a clock we do not staff."""

        COMMUNITY = "community", "Community forum"
        EMAIL = "email", "Email"
        PRIORITY_EMAIL = "priority_email", "Priority email"
        CONTRACT = "contract", "Agreed in contract"

    # The choice labels above are the English source and stay out of the migration untranslated on
    # purpose; the customer reads Spanish, so pages read these.
    INCLUDED_LEVEL_LABELS = {
        IncludedLevel.FREE: _("Free"),
        IncludedLevel.BASIC: _("Basic"),
        IncludedLevel.PRO: _("Pro"),
        IncludedLevel.ENTERPRISE: _("Enterprise"),
    }
    SUPPORT_LEVEL_LABELS = {
        SupportLevel.COMMUNITY: _("Community forum"),
        SupportLevel.EMAIL: _("Email"),
        SupportLevel.PRIORITY_EMAIL: _("Priority email"),
        SupportLevel.CONTRACT: _("Agreed in contract"),
    }
    #: The full tier of resources, the one Starter has (``max_db_connections``). Each plan up doubles it:
    #: what the customer reads is the multiple, never the number.
    PAID_BASE_DB_CONNECTIONS = 3
    RESOURCES_LABELS = {
        0: _("Basic, for one device"),
        1: _("Full, for several devices"),
        2: _("Double"),
        3: _("Triple"),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slug = models.SlugField(
        _("identifier"), max_length=50, unique=True, help_text=_("Stable identifier of the plan (free, starter…).")
    )
    name_en = models.CharField(_("name (English)"), max_length=100)
    name_es = models.CharField(_("name (Spanish)"), max_length=100, blank=True)
    description_en = models.TextField(_("description (English)"), blank=True)
    description_es = models.TextField(_("description (Spanish)"), blank=True)
    price_monthly = models.DecimalField(
        _("monthly price"), max_digits=10, decimal_places=2, help_text=_("Monthly price in EUR, VAT excluded (net).")
    )
    price_annual = models.DecimalField(
        _("annual price"),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("Annual price in EUR, VAT excluded (0 = no annual option)."),
    )
    features_en = models.JSONField(_("features (English)"), default=list, blank=True)
    features_es = models.JSONField(_("features (Spanish)"), default=list, blank=True)
    featured_label_en = models.CharField(_("badge (English)"), max_length=32, blank=True, default="")
    featured_label_es = models.CharField(_("badge (Spanish)"), max_length=32, blank=True, default="")
    is_active = models.BooleanField(_("active"), default=True, help_text=_("Available for new subscriptions."))
    upgrade_only = models.BooleanField(
        _("only as an upgrade"), default=False, help_text=_("Only offered as an upgrade, never at sign-up.")
    )
    internal_only = models.BooleanField(
        _("internal"),
        default=False,
        help_text=_("Never offered to customers; only a business the staff mark in the admin may buy it."),
    )
    stripe_product_id = models.CharField(_("Stripe product"), max_length=255, blank=True)
    stripe_price_id = models.CharField(
        _("Stripe monthly price"), max_length=255, blank=True, help_text=_("Stripe price of the monthly option.")
    )
    stripe_price_id_annual = models.CharField(
        _("Stripe annual price"), max_length=255, blank=True, help_text=_("Stripe price of the annual option.")
    )
    trial_period_days = models.PositiveIntegerField(
        _("trial days"), default=0, help_text=_("Free trial days (0 = no trial).")
    )
    display_order = models.IntegerField(_("order"), default=0)
    max_hubs_per_org = models.PositiveIntegerField(
        _("businesses per customer"), default=1, help_text=_("Hubs a customer may run on this plan (0 = unlimited).")
    )
    max_devices = models.PositiveIntegerField(
        _("devices"), default=0, help_text=_("Devices per hub (0 = unlimited).")
    )
    max_users = models.PositiveIntegerField(_("people"), default=0, help_text=_("Active users per hub (0 = unlimited)."))
    max_db_connections = models.PositiveIntegerField(
        _("database transactions at a time"),
        default=1,
        help_text=_("Database transactions a hub runs at a time per process."),
    )
    statement_timeout_seconds = models.PositiveIntegerField(
        _("longest database statement (seconds)"),
        default=5,
        help_text=_("Longest database statement of a hub, in seconds."),
    )
    #: What the plan includes of the assistant and of WhatsApp each month: one request of the user to the
    #: assistant is one message. They travel in the hub's state snapshot and the Hub counts them (warns at
    #: 80 %, blocks at 100 %, restarts on the 1st, UTC). 0 = none, never «unlimited»; there is no pack nor
    #: overage: more messages, a plan up.
    assistant_messages_per_month = models.PositiveIntegerField(
        _("AI assistant messages a month"),
        default=0,
        help_text=_("Requests to the AI assistant a business may make each month (0 = none)."),
    )
    whatsapp_messages_per_month = models.PositiveIntegerField(
        _("WhatsApp messages a month"),
        default=0,
        help_text=_("WhatsApp messages a business may send each month (0 = none)."),
    )
    #: How many modules a business may choose to turn on: every module is on every plan, a plan caps only how
    #: many the business picks; the modules they require come along and do not count. It travels in the hub's
    #: state snapshot and the Hub checks it when a business turns a module on. 0 = no limit (the upgrade-only
    #: tiers).
    max_apps = models.PositiveIntegerField(
        _("modules turned on"),
        default=0,
        db_default=0,
        help_text=_("Modules a business may choose to turn on; the ones they require do not count (0 = unlimited)."),
    )
    included_level = models.CharField(
        _("level of modules"), max_length=16, choices=IncludedLevel.choices, default=IncludedLevel.FREE
    )
    support_level = models.CharField(
        _("support"), max_length=16, choices=SupportLevel.choices, default=SupportLevel.COMMUNITY
    )
    includes_custom_domain = models.BooleanField(_("own domain"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = PlanQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "price_monthly"]
        verbose_name = _("plan")
        verbose_name_plural = _("plans")

    def __str__(self):
        """Its name and monthly price in the active language (the staff's in the admin): «Starter · 29,99 €/mes»."""
        return _("%(name)s · %(price)s €/month") % {
            "name": self.translated("name"),
            "price": number_format(self.price_monthly, 2),
        }

    def has_trial(self) -> bool:
        return self.trial_period_days > 0

    @property
    def trial_label(self) -> str:
        """The plan's free trial as a card line, in the active language; ``""`` without one."""
        days = self.trial_period_days
        if days <= 0:
            return ""
        return ngettext("%(days)d-day free trial", "%(days)d-day free trial", days) % {"days": days}

    @property
    def included_level_label(self) -> str:
        """Translated name of the module tier this plan includes, or ``""`` if unset."""
        return str(self.INCLUDED_LEVEL_LABELS.get(self.included_level, ""))

    @property
    def support_level_label(self) -> str:
        """Translated support channel and priority, or ``""`` if unset."""
        return str(self.SUPPORT_LEVEL_LABELS.get(self.support_level, ""))

    @property
    def resources_label(self) -> str:
        """How much database throughput the plan has, in plain words, relative to the full tier.

        A single-device plan is «basic»; a paid plan has the full tier; from there the multiple of the
        full tier (double, triple…). Never a connection count: the page sells what the customer gets.
        """
        if self.max_devices == 1:
            return str(self.RESOURCES_LABELS[0])
        times = max(1, self.max_db_connections // self.PAID_BASE_DB_CONNECTIONS)
        label = self.RESOURCES_LABELS.get(times)
        if label is not None:
            return str(label)
        return _("%(times)d times the full tier") % {"times": times}
