"""Models of hubs: the businesses of an account, who belongs to them, who pays, what they have,
the plans and the taxonomy of businesses.

``Plan`` is ported from ERPlora/saas ``hubs/subscriptions/models.py`` (origin/develop) without the
container sizing PLAN-SAAS §1 drops (vCPU, memory, storage flavour and database size) nor the price
of a paused container and its Stripe price: there is no container per hub any more. It keeps
``max_db_connections`` and ``statement_timeout_seconds`` (round 9, PLAN §14.2) and, since 2026-10-15, the
assistant and WhatsApp messages a month (PLAN-SAAS §3.6), which travel in the hub's state snapshot
(PLAN-SAAS §2.2). No modeltranslation: each translatable field is one column
per language (``name_en``, ``name_es``…), English being the source.

``Sector`` and ``BusinessType`` are ported from ERPlora/saas ``public/catalog/models.py``
(origin/develop) and live here, not in ``public/`` (PLAN §21.4: ``Hub.business_type`` points at
them and ``public`` reads them through the operations of hubs). ``BusinessType`` gains ``vertical``.

The account plane of a business (plan 2026-10-13 §3, round 17) is ported from ERPlora/saas
``apps/dashboard/hubs/main/models.py`` and ``hubs/subscriptions/models.py`` (origin/develop), reduced to
what the SaaS still knows now that the Hub runs every business in one service (PLAN §14): ``Hub``
keeps about a dozen fields (no server, container, database, token, heartbeat nor metrics), ``HubMember``
the four ``hub_*`` roles of round 11 with the hierarchy in code (no ``Role`` table), ``Subscription``
and ``SubscriptionItem`` are thin (Stripe is billing's, lot L2).
"""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from live.slugs import hub_slug_validator
from django.utils import timezone
from django.utils.translation import get_language, ngettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from apps.queries import known_verticals
from hubs.spanish_copy import spanish_copy_complaint, untranslated_copy_complaint


class TranslatedFields(models.Model):
    """A row whose copy lives in one column per language: ``<field>_en`` (the source), ``<field>_es``."""

    class Meta:
        abstract = True

    def translated(self, field: str, language: str | None = None):
        """``field`` in ``language`` (the active one by default); English when blank or unknown."""
        code = (language or get_language() or settings.LANGUAGE_CODE).split("-")[0].lower()
        value = getattr(self, f"{field}_{code}", None) if code in dict(settings.LANGUAGES) else None
        return value or getattr(self, f"{field}_{settings.LANGUAGE_CODE}")


class PlanQuerySet(models.QuerySet):
    def public(self):
        """The plans a visitor may be shown: active and not ``internal_only`` (saas#1052).

        Every public door lists plans through here (saas#1950); door-specific cuts
        (``upgrade_only``…) go on top of this, never instead of it.
        """
        return self.filter(is_active=True, internal_only=False)

    def signup_trial_days(self):
        """Shortest and longest free trial a visitor gets by creating a hub on a public plan.

        ``{"trial_days_min": …, "trial_days_max": …}``, both ``None`` when no plan on sale has a
        trial. An upgrade grants none (#809), so ``upgrade_only`` plans never count. Every public
        page that states the trial reads it here (saas#2414).
        """
        return (
            self.public()
            .filter(upgrade_only=False, trial_period_days__gt=0)
            .aggregate(trial_days_min=models.Min("trial_period_days"), trial_days_max=models.Max("trial_period_days"))
        )

    def offered_to(self, user):
        """The plans ``user`` may pick: every active one for staff, ``public()`` for anyone else.

        Every logged-in door that lists or accepts a plan goes through here (saas#2388). No user (or
        an anonymous one) is treated as a customer.
        """
        if user is not None and getattr(user, "is_authenticated", False) and user.is_staff:
            return self.filter(is_active=True)
        return self.public()


class Plan(TranslatedFields):
    """A subscription plan of a hub. Prices are NET, VAT excluded (saas#1098).

    One subscription buys one hub and everything inside it: every location, device and user
    (saas#1760). Free is permanent and needs no card (ADR-0154) and is the way in: no plan carries a trial
    since 2026-10-15 (``trial_period_days`` stays, dormant, for staff to use); Pro, Enterprise and Max are
    upgrade-only; ``payment-test`` is internal. The plans live only in the database and staff keep them in the
    admin: migration ``hubs/0013`` seeds them, and no deploy writes them again.
    """

    class IncludedLevel(models.TextChoices):
        """ADR-0474: one level name, the same across every ERPlora premium module."""

        FREE = "free", "Free"
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    class SupportLevel(models.TextChoices):
        """ADR-0426: channel and priority, never a clock we do not staff."""

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
    #: The full tier of resources, the one Starter has (``max_db_connections``; PLAN §14.2). Each plan up
    #: doubles it (Ioan, 2026-10-15): what the customer reads is the multiple, never the number.
    PAID_BASE_DB_CONNECTIONS = 3
    RESOURCES_LABELS = {
        0: _("Basic, for one device"),
        1: _("Full, for several devices"),
        2: _("Double"),
        3: _("Triple"),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slug = models.SlugField(max_length=50, unique=True, help_text=_("Stable identifier of the plan (free, starter…)."))
    name_en = models.CharField(_("name (English)"), max_length=100)
    name_es = models.CharField(_("name (Spanish)"), max_length=100, blank=True)
    description_en = models.TextField(_("description (English)"), blank=True)
    description_es = models.TextField(_("description (Spanish)"), blank=True)
    price_monthly = models.DecimalField(
        max_digits=10, decimal_places=2, help_text=_("Monthly price in EUR, VAT excluded (net).")
    )
    price_annual = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text=_("Annual price in EUR, VAT excluded (0 = no annual option).")
    )
    features_en = models.JSONField(_("features (English)"), default=list, blank=True)
    features_es = models.JSONField(_("features (Spanish)"), default=list, blank=True)
    featured_label_en = models.CharField(_("badge (English)"), max_length=32, blank=True, default="")
    featured_label_es = models.CharField(_("badge (Spanish)"), max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True, help_text=_("Available for new subscriptions."))
    upgrade_only = models.BooleanField(default=False, help_text=_("Only offered as an upgrade, never at sign-up."))
    internal_only = models.BooleanField(
        default=False, help_text=_("Never offered to customers; only staff may buy it (saas#1052).")
    )
    stripe_product_id = models.CharField(max_length=255, blank=True)
    stripe_price_id = models.CharField(max_length=255, blank=True, help_text=_("Stripe price of the monthly option."))
    stripe_price_id_annual = models.CharField(
        max_length=255, blank=True, help_text=_("Stripe price of the annual option.")
    )
    trial_period_days = models.PositiveIntegerField(default=0, help_text=_("Free trial days (0 = no trial)."))
    display_order = models.IntegerField(default=0)
    max_hubs_per_org = models.PositiveIntegerField(
        default=1, help_text=_("Hubs a customer may run on this plan (0 = unlimited).")
    )
    max_devices = models.PositiveIntegerField(default=0, help_text=_("Devices per hub (0 = unlimited)."))
    max_users = models.PositiveIntegerField(default=0, help_text=_("Active users per hub (0 = unlimited)."))
    max_db_connections = models.PositiveIntegerField(
        default=1, help_text=_("Database transactions a hub runs at a time per process (PLAN §14.2).")
    )
    statement_timeout_seconds = models.PositiveIntegerField(
        default=5, help_text=_("Longest database statement of a hub, in seconds (PLAN §14.2).")
    )
    #: What the plan includes of the assistant and of WhatsApp each month (PLAN-SAAS §3.6, 2026-10-15): one request
    #: of the user to the assistant is one message. They travel in the hub's state snapshot and the Hub counts
    #: them (warns at 80 %, blocks at 100 %, restarts on the 1st, UTC). 0 = none, never «unlimited»; there is no
    #: pack nor overage (ADR-0474): more messages, a plan up.
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
    included_level = models.CharField(max_length=16, choices=IncludedLevel.choices, default=IncludedLevel.FREE)
    support_level = models.CharField(max_length=16, choices=SupportLevel.choices, default=SupportLevel.COMMUNITY)
    includes_custom_domain = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PlanQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "price_monthly"]
        verbose_name = _("plan")
        verbose_name_plural = _("plans")

    def __str__(self):
        return f"{self.name_en} - EUR {self.price_monthly}/month"

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
        """How much database throughput the plan has, in plain words, relative to the full tier (Ioan, 2026-10-15:
        the «resources» that grow from plan to plan are the database's input/output capacity, never named by engine).

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

    def is_available_to(self, user) -> bool:
        """Whether ``user`` may subscribe to this plan: an internal one only for staff (saas#1052)."""
        if not self.internal_only:
            return True
        return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_staff)


# --- Taxonomy -------------------------------------------------------------------------------------


class TaxonomyEntry(TranslatedFields):
    """A sector or business type: a stable ``code`` and its copy in English and Spanish.

    The Spanish columns are Spanish: accented (saas#2017) and translated (saas#2027). The seed is
    guarded by its tests; this ``clean()`` guards the other door, the Django admin. Only the ``_es``
    columns are measured: «Menu» and «Salon» are English words and belong in the ``_en`` ones.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name_en = models.CharField(_("name (English)"), max_length=200)
    name_es = models.CharField(_("name (Spanish)"), max_length=200, blank=True)
    description_en = models.TextField(_("description (English)"), blank=True)
    description_es = models.TextField(_("description (Spanish)"), blank=True)
    icon = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=20, blank=True, help_text=_("Hex colour, e.g. #ff6b35."))
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["display_order", "code"]

    def __str__(self):
        return self.name_en or self.code

    def name(self, language: str | None = None) -> str:
        return self.translated("name", language)

    def description(self, language: str | None = None) -> str:
        return self.translated("description", language)

    def clean(self):
        super().clean()
        complaints = {}
        for field in ("name_es", "description_es"):
            text = getattr(self, field)
            if complaint := spanish_copy_complaint(text) or untranslated_copy_complaint(text):
                complaints[field] = complaint
        if complaints:
            raise ValidationError(complaints)


class Sector(TaxonomyEntry):
    """A business sector (hospitality, retail, healthcare…); groups the business types."""

    code = models.SlugField(max_length=50, unique=True, help_text=_("Stable code used by the API. Never change it."))

    class Meta(TaxonomyEntry.Meta):
        verbose_name = _("sector")
        verbose_name_plural = _("sectors")


class BusinessType(TaxonomyEntry):
    """A business type (bar, restaurant, hair salon…), under its sector.

    ``vertical`` names the template a new hub of this type is cloned from (``hub_template_<vertical>``,
    PLAN §15.2); blank, the hub starts from ``hub_template``, only ``base``.
    """

    code = models.SlugField(max_length=80, unique=True, help_text=_("Stable code used by the API. Never change it."))
    sector = models.ForeignKey(
        Sector, on_delete=models.SET_NULL, null=True, blank=True, related_name="business_types"
    )
    vertical = models.CharField(
        max_length=40,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                r"^[a-z][a-z0-9_]*$",
                _("Enter a vertical made of lowercase letters, digits and underscores, starting with a letter."),
            )
        ],
        help_text=_("Template a new hub of this type starts from (hair_salon, restaurant…); blank for none."),
    )

    class Meta(TaxonomyEntry.Meta):
        verbose_name = _("business type")
        verbose_name_plural = _("business types")

    def clean(self):
        """Two business types may not share a visible name in the same language (saas#2099), and a
        ``vertical`` is one an app of the catalog builds (``apps.queries.known_verticals``, spec §5.4).

        The sign-up dropdown lists them by name, so two rows called «Peluquería» are two identical
        options. Blank columns are not compared: an untranslated name is empty on many rows.
        """
        complaints = {}
        try:
            super().clean()
        except ValidationError as refused:
            complaints = refused.update_error_dict(complaints)
        others = BusinessType.objects.exclude(pk=self.pk)
        for language, _name in settings.LANGUAGES:
            field = f"name_{language}"
            name = getattr(self, field).strip()
            # Folded in Python: the database's iexact does not fold «PELUQUERÍA» the same way everywhere.
            taken = {other.strip().casefold() for other in others.values_list(field, flat=True)}
            if name and name.casefold() in taken:
                complaints.setdefault(field, []).append(
                    ValidationError(
                        _("Another business type is already called «%(name)s»."),
                        code="duplicate_business_type_name",
                        params={"name": name},
                    )
                )
        if self.vertical and self.vertical not in known_verticals():
            complaints.setdefault("vertical", []).append(
                ValidationError(
                    _("No app of the catalog builds the vertical «%(vertical)s»."),
                    code="unknown_vertical",
                    params={"vertical": self.vertical},
                )
            )
        if complaints:
            raise ValidationError(complaints)


# --- The account plane of a business --------------------------------------------------------------

#: The label of an app = its folder in the Hub = ``modules[].id`` of the snapshot (PLAN §20.2).
MODULE_SLUG_VALIDATOR = RegexValidator(
    r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$", _("Enter the label of an app: lowercase letters, digits and underscores.")
)


class BillingProfile(models.Model):
    """Who pays ERPlora for one or many hubs (ADR-0201 decision 3): the identity on ERPlora's invoice.

    Not the business's own fiscal identity (the one on its receipts), which lives in the Hub
    (PLAN-SAAS §3.1, the two identities). ``same_as_business`` is the «use the business's data» box:
    saving with it on copies what the SaaS knows of the business (its name and country) into the
    payer; a copy, never a sync. Every field but the owner may wait for the first checkout.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    # SET_NULL: the invoices ERPlora issued stay resolvable after the account is gone.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_profiles",
        verbose_name=_("owner"),
    )
    billing_name = models.CharField(_("legal name"), max_length=255, blank=True)
    tax_id = models.CharField(_("tax ID"), max_length=50, blank=True)
    billing_address = models.TextField(_("address"), blank=True)
    billing_city = models.CharField(_("city"), max_length=100, blank=True)
    billing_postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    billing_country = models.CharField(_("country"), max_length=2, blank=True)
    billing_email = models.EmailField(_("billing email"), blank=True)
    same_as_business = models.BooleanField(_("same as the business"), default=False)
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    #: The account it belonged to deleted itself (ACCOUNTS-F27): it goes, with its Stripe customer, once nothing
    #: can still be charged to it, and on this day at the latest (``billing.services.forget_departed_payer``).
    forget_after = models.DateTimeField(_("erased by"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("billing profile")
        verbose_name_plural = _("billing profiles")

    def __str__(self):
        return self.billing_name or self.tax_id or str(self.id)


class Hub(models.Model):
    """A business of an account: what the SaaS knows of it, and what it owes the Hub service.

    ``id`` is the UUIDv7 the SaaS generates and the Hub keys its registry and database with
    (``hub_<hex>``, PLAN-SAAS §2). ``state_version`` grows with every change of the snapshot the Hub
    keeps (§2.2); ``pushed_state_version`` is the last one the Hub acknowledged. ``pending_hub_call``
    is the lifecycle call the Hub still owes an answer to (``put`` the registry, ``delete``,
    ``restore``): set in the command's transaction, cleared when the Hub acknowledges it, retried by
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

    #: How long a deleted business can be recovered before the Hub purges it (ADR-0273 §10).
    RETENTION = timedelta(days=90)

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slug = models.CharField(_("address"), max_length=63, unique=True, validators=[hub_slug_validator])
    name = models.CharField(_("name"), max_length=120)
    country = models.CharField(_("country"), max_length=2, help_text=_("ISO 3166-1 alpha-2, e.g. ES."))
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
    deletion_requested_at = models.DateTimeField(_("deletion asked at"), null=True, blank=True)
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
        """When the Hub purges a deleted business; until then it can be recovered."""
        if self.deletion_requested_at is None:
            return None
        return self.deletion_requested_at + self.RETENTION


class HubMember(models.Model):
    """Who belongs to a hub, with which of the four roles of round 11 (ADR-0201: access is per hub).

    An invitation is a member without an answer (``accepted_at`` empty, round 17 §2.8): it expires
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

    #: Authority: lower is more. Nobody acts on a peer or a superior, nor grants their own rank.
    RANK = {Role.OWNER: 10, Role.ADMIN: 20, Role.MANAGER: 30, Role.EMPLOYEE: 40}
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
            # Fail closed: a role outside the four (a retired key from a data migration, a typo in the
            # admin) would rank nowhere in the access checks; the database never stores one.
            models.CheckConstraint(
                condition=Q(role__in=["hub_owner", "hub_admin", "hub_manager", "hub_employee"]),
                name="hubs_member_role_known",
            ),
        ]
        indexes = [models.Index(fields=["user", "-last_opened_at"], name="hubs_member_user_opened")]

    def __str__(self):
        return f"{self.user_id} @ {self.hub_id} ({self.role})"

    @property
    def is_pending(self) -> bool:
        """Invited and not answered yet."""
        return self.accepted_at is None

    def is_expired(self, now: datetime) -> bool:
        """An unanswered invitation past its window: it can no longer be accepted."""
        return self.is_pending and self.invitation_expires_at is not None and self.invitation_expires_at <= now


class HubOwnershipTransfer(models.Model):
    """A pending or resolved hand-over of a hub's ownership (saas#1670).

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


class Subscription(models.Model):
    """The plan a hub is on (one per hub). Stripe fills its ids and dates (lot L2-B, through
    ``hubs.subscription.apply``, which billing calls with what the LIVE Stripe subscription says).

    The Free plan is born with ``trial_plan`` = Starter for its trial days (ADR-0474: Free is born
    with 15 days of Starter): while ``trial_end`` is ahead, the hub gets the trial plan's rights. A paid
    plan carries its own trial in Stripe, so paying clears ``trial_plan``.

    ``unpaid_*`` say why a renewal is not paid, while it is not (mockups README §6.18): with a declined
    card «Pay» waits until the card changes; ``unpaid_since`` is when the failed invoice was issued (the
    7 days of grace count from it); ``unpaid_invoice_url`` is Stripe's page to pay it (its owner's only).
    """

    class UnpaidReason(models.TextChoices):
        NONE = "", _("Paid")
        CARD_DECLINED = "card_declined", _("Card declined")
        CARD_CHANGED = "card_changed", _("Card changed")
        AUTHENTICATION_REQUIRED = "authentication_required", _("Authentication required")
        PAYMENT_FAILED = "payment_failed", _("Payment failed")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        TRIALING = "trialing", _("Trial")
        PAST_DUE = "past_due", _("Payment pending")
        UNPAID = "unpaid", _("Unpaid")
        CANCELED = "canceled", _("Cancelled")
        INCOMPLETE = "incomplete", _("Incomplete")
        INCOMPLETE_EXPIRED = "incomplete_expired", _("Incomplete, expired")
        PAUSED = "paused", _("Paused")

    class Interval(models.TextChoices):
        MONTH = "month", _("Monthly")
        YEAR = "year", _("Annual")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.OneToOneField(Hub, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions", verbose_name=_("plan"))
    trial_plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("trial plan")
    )
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.ACTIVE)
    billing_interval = models.CharField(_("billing"), max_length=8, choices=Interval.choices, default=Interval.MONTH)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    unpaid_reason = models.CharField(
        _("why it is unpaid"), max_length=24, choices=UnpaidReason.choices, blank=True, default=""
    )
    unpaid_since = models.DateTimeField(_("unpaid since"), null=True, blank=True)
    unpaid_invoice_url = models.URLField(_("invoice to pay"), max_length=2048, blank=True, default="")
    #: The business was deleted while Stripe billed it: billing's ``sweep_unpaid`` ends that subscription and
    #: clears this. Durable, so recovering the business meanwhile does not leave it charging.
    cancel_requested_at = models.DateTimeField(_("end in Stripe asked at"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self):
        return f"{self.hub_id} - {self.plan_id} ({self.status})"

    def effective_plan(self, now: datetime) -> Plan:
        """The plan whose rights the hub has at ``now``: the trial's while it lasts, else its own."""
        if self.trial_plan_id is not None and self.trial_end is not None and now < self.trial_end:
            return self.trial_plan
        return self.plan


class SubscriptionItem(models.Model):
    """A paid module a hub has, included in its plan or bought (PLAN-SAAS §2.6): ``modules[]`` of the
    snapshot. ``module_slug`` is the app's label (a slug, no FK: the catalog is ``apps``'s)."""

    class Source(models.TextChoices):
        PLAN = "plan", _("Included in the plan")
        PURCHASE = "purchase", _("Bought")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="items")
    module_slug = models.CharField(_("module"), max_length=63, validators=[MODULE_SLUG_VALIDATOR])
    source = models.CharField(_("source"), max_length=8, choices=Source.choices, default=Source.PURCHASE)
    valid_until = models.DateTimeField(_("valid until"), null=True, blank=True)
    stripe_item_id = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["module_slug"]
        verbose_name = _("subscription item")
        verbose_name_plural = _("subscription items")
        constraints = [
            models.UniqueConstraint(fields=["subscription", "module_slug"], name="hubs_item_one_per_module"),
        ]

    def __str__(self):
        return f"{self.module_slug} ({self.source})"

    def is_live(self, now: datetime) -> bool:
        """Whether the right holds at ``now``: open-ended, or before its ``valid_until``."""
        return self.valid_until is None or now < self.valid_until


class SessionRevocation(models.Model):
    """An account's sessions the Hub must end (PLAN-SAAS §2.1, OIDC's back-channel logout): in one
    business, or in every one (``hub`` empty).

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


class HubUsageDaily(models.Model):
    """One day of a business's usage, as the Hub measured it that night (PLAN-SAAS §5; lot L4-A).

    ``s3_bytes`` is what its files take in S3 (the storage the customer sees, as a percentage of what the
    plan includes), ``db_bytes`` what its database takes (the admin's only), ``active_users_1d`` the people
    active that day and ``active_users_30d`` in the 30 days up to it. One row per business and day, written
    only by the system command ``hubs.usage.record`` (``manage.py collect_hub_usage``, nightly in
    ``saas-cron``): collecting a day again replaces its figures.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="usage_days", verbose_name=_("business"))
    day = models.DateField(_("day"))
    s3_bytes = models.PositiveBigIntegerField(_("files (bytes)"))
    db_bytes = models.PositiveBigIntegerField(_("database (bytes)"))
    active_users_1d = models.PositiveIntegerField(_("active that day"))
    active_users_30d = models.PositiveIntegerField(_("active in the 30 days"))
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
