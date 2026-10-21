"""Models of billing's EU VAT engine (lot L2-A): what is sold at which rate, the issuer's policy and
identity, and the log of VIES queries.

Ported from ERPlora/saas ``apps/dashboard/fiscal/models.py`` (origin/develop): ``TaxCategory``,
``TaxRule``, ``FiscalPolicy``, ``CompanyConfig`` and ``VatCheck``, with UUIDv7 keys. The two singletons
stop forcing ``pk=1`` (a UUID key) and keep a single row by a unique column that is always true. Their
reads (the rule in force, the policy, the latest verdict) live in ``billing.queries``: only
``services.py`` and ``queries.py`` touch the ORM. Without ``CompanyConfig.logo`` (the invoice PDF is the
Hub's, plan §4 L3-C) nor the VeriFactu models, which are the Hub's (PLAN-HUB, fiscal).

Lot L2-B adds what Stripe needs remembered: ``PromoCode`` (trial days, ADR-0107), ``CheckoutAttempt`` (one
Embedded Checkout per intent), ``WebhookEvent`` (each Stripe event processed once) and ``PaymentFailure``
(why a renewal is unpaid). Lot L3-C adds ERPlora's invoices to its customers: ``Invoice`` (and its credit
notes), ``InvoiceLine`` and ``InvoiceCounter`` (the correlative number of each series and year).
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

#: The default category: what is sold when nobody says more. The net of every rule.
GENERIC_CATEGORY = "service.generic"

country_code_validator = RegexValidator(
    r"^[A-Z]{2}$", _("Two capital letters (ISO 3166-1 alpha-2), e.g. ES.")
)
region_code_validator = RegexValidator(
    r"^[A-Z]{0,8}$", _("Capital letters only, e.g. IC.")
)


class SingletonModel(UUIDModel):
    """A model with one row at most: saving a new instance overwrites the row on file, and the database
    refuses a second one whatever the path (``singleton`` is unique and always true)."""

    singleton = models.BooleanField(default=True, editable=False)

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="%(app_label)s_%(class)s_one_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True),
                name="%(app_label)s_%(class)s_singleton_true",
            ),
        ]

    def save(self, *args, **kwargs):
        stamped = [
            field.attname
            for field in self._meta.concrete_fields
            if getattr(field, "auto_now_add", False)
        ]
        on_file = type(self).objects.exclude(pk=self.pk).values("pk", *stamped).first()
        if on_file is not None:
            # An UPDATE of the row on file: it keeps its key and its creation stamp
            # (``auto_now_add`` is only filled on an INSERT, and the column is NOT NULL).
            self.pk = on_file["pk"]
            for attname in stamped:
                setattr(self, attname, on_file[attname])
            self._state.adding = False
        super().save(*args, **kwargs)


class TaxCategory(UUIDModel):
    """What is sold, in fiscal terms (saas#1063): a stable canonical key, never a loose percentage.

    The % lives in ``TaxRule`` and may change over time without touching what was sold. Mirror of the
    Hub's ``tax`` categories (ADR-0085).
    """

    key = models.CharField(
        _("key"),
        max_length=64,
        unique=True,
        help_text=_("Stable canonical key, e.g. service.saas_subscription"),
    )
    name = models.CharField(_("name"), max_length=120)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = _("tax category")
        verbose_name_plural = _("tax categories")

    def __str__(self):
        return f"{self.name} ({self.key})"


class TaxRule(UUIDModel):
    """The rate of ``(country, region, category)`` on a date.

    The rates change (Estonia 22→24 in Jul-2025, Romania 19→21 in Aug-2025): with ``valid_from`` /
    ``valid_to`` a change is scheduled and older sales keep resolving the rate they had.
    ``is_subject=False`` describes the territories of a member state OUTSIDE the scope of VAT (Canary
    Islands, Ceuta, Melilla) and third countries: not a 0 % rate, a sale not subject to VAT, which the
    VeriFactu record declares differently (N2, without rate nor quota).
    """

    category = models.ForeignKey(
        TaxCategory,
        to_field="key",
        db_column="tax_category_key",
        on_delete=models.PROTECT,
        related_name="rules",
        verbose_name=_("category"),
    )
    country_code = models.CharField(
        _("country"),
        max_length=2,
        validators=[country_code_validator],
        help_text=_("ISO 3166-1 alpha-2 (ES, DE, FR…)"),
    )
    region_code = models.CharField(
        _("region"),
        max_length=8,
        blank=True,
        validators=[region_code_validator],
        help_text=_(
            "Empty = the whole country. IC = Canary Islands, CE = Ceuta, ML = Melilla"
        ),
    )
    rate_pct = models.DecimalField(
        _("rate %"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    is_subject = models.BooleanField(
        _("subject to VAT"),
        default=True,
        help_text=_(
            "Unchecked = territory outside the scope of VAT (not subject), not a 0 % rate"
        ),
    )
    valid_from = models.DateField(_("valid from"))
    valid_to = models.DateField(_("valid to"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_code", "region_code", "category_id", "-valid_from"]
        verbose_name = _("tax rule")
        verbose_name_plural = _("tax rules")
        indexes = [models.Index(fields=["country_code", "region_code"])]
        constraints = [
            # Two rules of the same kind starting the same day are an ambiguity, not data.
            models.UniqueConstraint(
                fields=["country_code", "region_code", "category", "valid_from"],
                name="billing_taxrule_one_per_start",
            ),
            models.CheckConstraint(
                condition=Q(rate_pct__gte=0) & Q(rate_pct__lte=100),
                name="billing_taxrule_rate_is_a_percentage",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="billing_taxrule_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        where = (
            f"{self.country_code}/{self.region_code}"
            if self.region_code
            else self.country_code
        )
        what = f"{self.rate_pct}%" if self.is_subject else gettext("not subject")
        return f"{where} · {self.category_id} · {what}"


class FiscalPolicy(SingletonModel):
    """The issuer's fiscal policy (saas#1063): where ERPlora invoices from, its ROI registration and the
    One-Stop Shop.

    The OSS threshold: while the B2C sales to other member states stay under €10,000 a year, the issuer's
    VAT is charged (21 % ES); above it —or with the voluntary OSS registration, binding for two years—
    the customer's country rate applies (``billing.queries.uses_destination_rate``).
    """

    issuer_country = models.CharField(
        _("issuer country"),
        max_length=2,
        default="ES",
        validators=[country_code_validator],
    )
    issuer_region = models.CharField(
        _("issuer region"),
        max_length=8,
        blank=True,
        validators=[region_code_validator],
        help_text=_(
            "IC = Canary Islands, CE = Ceuta, ML = Melilla. Empty = mainland Spain and the Balearic Islands"
        ),
    )
    # ERPlora is in the ROI since 08-08-2026 (ESB27593136), so the default is True (saas#1479).
    intra_eu_reverse_charge = models.BooleanField(
        _("registered in ROI / VIES"),
        default=True,
        help_text=_(
            "Registered in the Register of Intra-Community Operators (form 036). Unchecked, Spanish VAT is "
            "charged to EU businesses TOO: invoicing without VAT while not in the ROI ends in an assessment "
            "of the uncharged VAT, with interest. Checked, the reverse charge applies on its own — but only "
            "with the VAT number validated in VIES."
        ),
    )
    oss_registered = models.BooleanField(
        _("registered in OSS"),
        default=False,
        help_text=_(
            "Registered in the One-Stop Shop. Forces the customer's country rate even below the threshold"
        ),
    )
    oss_threshold = models.DecimalField(
        _("OSS threshold"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("10000.00"),
        help_text=_(
            "Yearly cross-border B2C sales (EU) from which the destination rate applies"
        ),
    )
    # The cross-border B2C base invoiced OUTSIDE this SaaS (the old one) until its invoices live here
    # (lot L3-C): without it the year's total is unknown, and the threshold could be crossed unseen.
    oss_carried_year = models.PositiveSmallIntegerField(
        _("year of the carried amounts"),
        null=True,
        blank=True,
        help_text=_(
            "The year the «this year» amount belongs to. Empty = nothing carried: the total is unknown"
        ),
    )
    oss_carried_current_cents = models.PositiveBigIntegerField(
        _("cross-border B2C carried for that year (cents)"),
        default=0,
        help_text=_(
            "Tax base of the intra-EU B2C sales without a verified VAT number invoiced by the old SaaS that year, in cents"
        ),
    )
    oss_carried_previous_cents = models.PositiveBigIntegerField(
        _("cross-border B2C carried for the year before (cents)"),
        default=0,
        help_text=_(
            "The same, for the year before: above the threshold, the whole year is destination VAT"
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SingletonModel.Meta):
        verbose_name = _("fiscal policy")
        verbose_name_plural = _("fiscal policy")

    def __str__(self):
        return gettext("Fiscal policy (%(country)s)") % {"country": self.issuer_country}


class CompanyConfig(SingletonModel):
    """ERPlora's own fiscal identity (the issuer of its invoices and the requester VIES must see).

    Seeded from the Modelo 036 (``billing.seed``) and edited in the admin. The registrations that change
    how a sale is taxed (the ROI and the OSS) are ``FiscalPolicy``'s.
    """

    class VatRegime(models.TextChoices):
        GENERAL = "general", _("General regime")
        SIMPLIFIED = "simplified", _("Simplified regime")
        EQUIVALENCE = "equivalence_surcharge", _("Equivalence surcharge")
        EXEMPT = "exempt", _("Exempt")

    legal_name = models.CharField(
        _("legal name"), max_length=200, help_text=_("e.g. ERPLORA CLOUD SL")
    )
    trade_name = models.CharField(_("trade name"), max_length=200, blank=True)
    tax_id = models.CharField(
        _("tax ID"), max_length=20, help_text=_("CIF/NIF, e.g. B12345678")
    )
    street = models.CharField(_("street"), max_length=300)
    city = models.CharField(_("city"), max_length=100)
    postal_code = models.CharField(_("postal code"), max_length=10)
    province = models.CharField(_("province"), max_length=100, blank=True)
    country = models.CharField(
        _("country"), max_length=2, default="ES", validators=[country_code_validator]
    )
    vat_regime = models.CharField(
        _("VAT regime"),
        max_length=50,
        choices=VatRegime.choices,
        default=VatRegime.GENERAL,
    )
    email = models.EmailField(_("email"), default="billing@erplora.com")
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    website = models.URLField(_("website"), default="https://erplora.com")
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SingletonModel.Meta):
        verbose_name = _("company configuration")
        verbose_name_plural = _("company configuration")

    def __str__(self):
        return self.legal_name or gettext("Company configuration")


class VatCheck(UUIDModel):
    """The log of VIES queries: the proof that a VAT number was valid on a date.

    Keyed by the VAT NUMBER, never by the customer (contract §5): a customer who changes their number
    must not inherit the verdict of the previous one. ``consultation_number`` is VIES' ``requestIdentifier``
    and the whole point of the table: it proves, with audit value, that on that date the Commission
    confirmed that number. VIES only returns it when the query identifies the requester. Rows are never
    edited nor deleted: every query is a new row.
    """

    VERIFIED = "verified"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    PENDING = "pending"

    STATUS_CHOICES = [
        (VERIFIED, _("Verified in VIES")),
        (INVALID, _("Not registered in VIES")),
        (UNAVAILABLE, _("VIES could not answer")),
        (PENDING, _("Awaiting an answer")),
    ]

    #: Days a verdict proves anything about (contract §8). Past it nothing blocks the sale, but the
    #: verdict no longer grants reverse charge and the next need asks VIES again.
    TTL_DAYS = 30

    vat_number = models.CharField(
        _("VAT number"),
        max_length=20,
        db_index=True,
        help_text=_(
            "Normalised: no spaces or dashes, uppercase, with the country prefix"
        ),
    )
    requested_at = models.DateTimeField(_("asked at"), default=timezone.now)
    status = models.CharField(
        _("status"), max_length=16, choices=STATUS_CHOICES, default=PENDING
    )
    consultation_number = models.CharField(
        _("consultation number"),
        max_length=64,
        blank=True,
        help_text=_("VIES requestIdentifier: the audit proof of this query"),
    )
    returned_name = models.CharField(_("name in VIES"), max_length=255, blank=True)
    returned_address = models.TextField(_("address in VIES"), blank=True)
    # Manual override (contract §7): a company incorporated days ago is not in VIES yet.
    override_by = models.CharField(_("overridden by"), max_length=254, blank=True)
    override_reason = models.TextField(_("reason of the override"), blank=True)
    override_at = models.DateTimeField(_("overridden at"), null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = _("VAT check")
        verbose_name_plural = _("VAT checks")
        indexes = [models.Index(fields=["vat_number", "-requested_at"])]

    def __str__(self):
        return f"{self.vat_number} — {self.status} ({self.requested_at:%Y-%m-%d})"

    @property
    def is_manual_override(self) -> bool:
        return bool(self.override_at)

    @property
    def is_current(self) -> bool:
        """Still within the window in which it proves something (§8)."""
        return self.requested_at >= timezone.now() - timedelta(days=self.TTL_DAYS)

    @property
    def grants_reverse_charge(self) -> bool:
        """``verified``, current AND with proof is the only combination that invoices at 0 %.

        The proof is VIES' consultation number or a manual override with its author and reason: a
        ``verified`` row with neither cannot be defended in front of the AEAT.
        """
        if self.status != self.VERIFIED or not self.is_current:
            return False
        return bool(self.consultation_number) or self.is_manual_override


# --- Stripe (lot L2-B) -------------------------------------------------------------------------------

#: The longest trial a promo code may grant.
MAX_PROMO_TRIAL_DAYS = 365


class PromoCode(UUIDModel):
    """A code that grants trial DAYS at checkout, replacing the plan's own (ADR-0107).

    Deliberately not a Stripe coupon: a coupon's duration burns from the moment it is applied, trial
    included, so one shorter than the trial expires before the first invoice. And free time, never a lower
    price: a discount anchors a cheaper price and turns the renewal into a price hike. Ported from
    ERPlora/saas ``hubs/subscriptions/models.py`` (origin/develop); reads in ``billing.queries``
    (``redeemable_promo``), the count in ``billing.services`` (``redeem_promo``).
    """

    code = models.CharField(
        _("code"),
        max_length=64,
        unique=True,
        help_text=_(
            "What the customer types, case-insensitive (stored in lowercase), e.g. canary_2026"
        ),
    )
    trial_days = models.PositiveIntegerField(
        _("trial days"),
        validators=[MinValueValidator(1), MaxValueValidator(MAX_PROMO_TRIAL_DAYS)],
        help_text=_(
            "Free trial days granted, replacing the plan's own trial (1 to 365)"
        ),
    )
    is_active = models.BooleanField(_("active"), default=True)
    expires_at = models.DateTimeField(
        _("expires at"), null=True, blank=True, help_text=_("Empty = never expires")
    )
    max_redemptions = models.PositiveIntegerField(
        _("maximum redemptions"),
        null=True,
        blank=True,
        help_text=_("Empty = unlimited"),
    )
    redemption_count = models.PositiveIntegerField(
        _("redemptions"), default=0, help_text=_("Completed checkouts that used it")
    )
    note = models.CharField(
        _("note"),
        max_length=255,
        blank=True,
        help_text=_("Campaign or deal this code belongs to"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("promo code")
        verbose_name_plural = _("promo codes")
        constraints = [
            models.CheckConstraint(
                condition=Q(trial_days__gte=1)
                & Q(trial_days__lte=MAX_PROMO_TRIAL_DAYS),
                name="billing_promocode_trial_days_in_range",
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.trial_days})"

    def save(self, *args, **kwargs):
        self.code = normalise_promo_code(self.code)
        super().save(*args, **kwargs)

    @property
    def is_exhausted(self) -> bool:
        return (
            self.max_redemptions is not None
            and self.redemption_count >= self.max_redemptions
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and timezone.now() >= self.expires_at

    @property
    def is_redeemable(self) -> bool:
        return self.is_active and not self.is_expired and not self.is_exhausted


def normalise_promo_code(code: str | None) -> str:
    """A code as it is stored and looked up: trimmed, lowercase."""
    return (code or "").strip().lower()


class PromoRedemption(UUIDModel):
    """A promo code used by a business: once per business and once per payer (review of L2-B), so one
    code does not give a year free to every business an account opens. Written when its checkout is paid
    (or its plan change confirmed); ``PromoCode.redemption_count`` counts these."""

    promo = models.ForeignKey(
        PromoCode,
        on_delete=models.CASCADE,
        related_name="redemptions",
        verbose_name=_("promo code"),
    )
    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        related_name="promo_redemptions",
        verbose_name=_("business"),
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(_("used at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("promo code used")
        verbose_name_plural = _("promo codes used")
        constraints = [
            models.UniqueConstraint(
                fields=["promo", "hub"], name="billing_promo_once_per_business"
            )
        ]

    def __str__(self):
        return f"{self.promo_id} → {self.hub_id}"


class CheckoutAttempt(UUIDModel):
    """One Embedded Checkout opened for a business: what it sells and the Stripe session it got.

    The same selection opened again while its session is still open reuses it (a double click, a modal
    closed and reopened), so one intent never leaves two sessions that could both be paid. The webhook
    completes it exactly once (the promo code is counted then).
    """

    class Kind(models.TextChoices):
        PLAN = "plan", _("Plan")
        MODULE = "module", _("Module")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        COMPLETED = "completed", _("Completed")
        EXPIRED = "expired", _("Expired")
        FAILED = "failed", _("Payment failed")

    #: Stripe keeps a Checkout Session open 24 hours; reuse it a bit less, so it never expires in hand.
    REUSE_FOR = timedelta(hours=23)

    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        related_name="checkout_attempts",
        verbose_name=_("business"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_attempts",
        verbose_name=_("opened by"),
    )
    kind = models.CharField(_("sells"), max_length=8, choices=Kind.choices)
    plan_slug = models.CharField(_("plan"), max_length=50, blank=True)
    module_slug = models.CharField(_("module"), max_length=63, blank=True)
    billing_interval = models.CharField(_("billing"), max_length=8, default="month")
    promo_code = models.CharField(_("promo code"), max_length=64, blank=True)
    #: What was sold, as a key (kind, plan or module, interval, promo code, trial): the same selection
    #: reuses the open session; any other gets a new one.
    selection = models.CharField(_("selection"), max_length=255)
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.OPEN
    )
    stripe_session_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )
    client_secret = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(_("opened at"), auto_now_add=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("checkout")
        verbose_name_plural = _("checkouts")
        indexes = [models.Index(fields=["hub", "selection", "status"])]

    def __str__(self):
        return f"{self.hub_id} {self.kind} {self.plan_slug or self.module_slug} ({self.status})"


class WebhookEvent(UUIDModel):
    """Each Stripe event the webhook received, processed once (saas#2530).

    A delivery claims the event before processing it, so two deliveries at once never both process it; a
    claim left by a process that died expires after ``CLAIM_LEASE``. A failure stays claimable: Stripe's
    retry processes it again. One endpoint (``/webhooks/stripe/``, PLAN-SAAS §4), so the event id alone is
    the key.
    """

    #: How long a claim protects an event being processed; after it the next delivery takes it over.
    CLAIM_LEASE = timedelta(minutes=10)

    event_id = models.CharField(_("Stripe event"), max_length=255, unique=True)
    event_type = models.CharField(_("type"), max_length=100)
    received_at = models.DateTimeField(_("received at"), auto_now_add=True)
    processing_since = models.DateTimeField(
        _("processing since"), null=True, blank=True
    )
    processed_at = models.DateTimeField(_("processed at"), null=True, blank=True)
    success = models.BooleanField(_("processed"), default=False)
    #: What the processing came to (``completed``, ``ignored``, ``unknown``…).
    outcome = models.CharField(_("outcome"), max_length=32, blank=True)
    error_message = models.TextField(_("error"), blank=True)
    attempts = models.PositiveIntegerField(_("attempts"), default=0)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = _("Stripe event")
        verbose_name_plural = _("Stripe events")
        indexes = [models.Index(fields=["event_type", "received_at"])]

    def __str__(self):
        return f"{self.event_type} ({self.event_id})"


class PaymentFailure(UUIDModel):
    """A renewal Stripe could not collect, and why: what «Pay» and the panel need (mockups README §6.18).

    One row per unpaid Stripe invoice. ``reason`` tells a declined card (the bank refused it: paying again
    with it fails, so «Pay» waits until the card changes, ``card_changed_at``) from an authentication the
    customer must complete or any other failure. ``invoice_created_at`` starts the 7 days of grace.
    ``resolved_at`` is set when the invoice is paid (or the subscription ends). ``notified_at`` and
    ``suspension_notified_at`` keep the mails of BILLING-F16 to one each (``services.notify_unpaid``).
    """

    class Reason(models.TextChoices):
        CARD_DECLINED = "card_declined", _("Card declined")
        AUTHENTICATION_REQUIRED = (
            "authentication_required",
            _("Authentication required"),
        )
        PAYMENT_FAILED = "payment_failed", _("Payment failed")

    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.CASCADE,
        related_name="payment_failures",
        verbose_name=_("business"),
    )
    stripe_invoice_id = models.CharField(
        _("Stripe invoice"), max_length=255, unique=True
    )
    stripe_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    reason = models.CharField(_("reason"), max_length=24, choices=Reason.choices)
    failure_code = models.CharField(_("Stripe code"), max_length=64, blank=True)
    decline_code = models.CharField(_("decline code"), max_length=64, blank=True)
    payment_method_id = models.CharField(
        _("card that failed"), max_length=255, blank=True
    )
    hosted_invoice_url = models.URLField(
        _("invoice to pay"), max_length=2048, blank=True
    )
    invoice_created_at = models.DateTimeField(_("invoice issued at"))
    failed_at = models.DateTimeField(_("last failure"), default=timezone.now)
    attempts = models.PositiveIntegerField(_("failures"), default=1)
    card_changed_at = models.DateTimeField(_("card changed at"), null=True, blank=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    #: The payer was told this invoice could not be collected (or there was nobody to tell): once per invoice.
    notified_at = models.DateTimeField(_("payer told"), null=True, blank=True)
    #: The payer was told the business is suspended for this unpaid episode: once per suspension.
    suspension_notified_at = models.DateTimeField(_("suspension told"), null=True, blank=True)

    class Meta:
        ordering = ["-failed_at"]
        verbose_name = _("failed payment")
        verbose_name_plural = _("failed payments")
        indexes = [models.Index(fields=["hub", "resolved_at"])]

    def __str__(self):
        return f"{self.stripe_invoice_id} {self.reason}"


# --- ERPlora's invoices to its customers (lot L3-C) --------------------------------------------------

#: The qualifications of a sale (``billing.vat``); a line may seal ``exempt`` on its own.
TAX_TREATMENTS = [
    ("domestic", _("Domestic")),
    ("oss", _("OSS (destination country)")),
    ("reverse_charge", _("Reverse charge")),
    ("not_subject", _("Not subject")),
    ("exempt", _("Exempt")),
]


def _euros(cents: int):
    """The euro view of integer cents (two decimals, exact)."""
    from billing.money import from_cents

    return from_cents(cents)


class InvoiceCounter(UUIDModel):
    """The year and the last number of a series: ``fiscal_counter`` (CLAUDE.md, «Fiscal»).

    ``billing.services.issue_number`` locks the series' row in the transaction that records the invoice, reads
    the issue date once it holds the lock (a later number never carries an earlier date) and moves it: a new
    year starts again at 1, a ROLLBACK gives the number back. No gap, no duplicate; never a Postgres sequence,
    which leaves holes.
    """

    series = models.CharField(_("series"), max_length=16, unique=True)
    year = models.PositiveSmallIntegerField(_("year"), default=0)
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("invoice counter")
        verbose_name_plural = _("invoice counters")

    def __str__(self):
        return f"{self.series}-{self.year}: {self.last_number}"


class Invoice(UUIDModel):
    """An invoice ERPlora issues to a customer for a business's subscription, or a credit note rectifying
    one (lot L3-C; PLAN-SAAS §4, ADR-0478).

    Recorded from Stripe: an unpaid renewal is listed (``open``, without a number: «Not collected», with
    «Pay»); once paid it gets its number (``InvoiceCounter``), the payer as it was that day (a snapshot of
    ``hubs.BillingProfile``: editing the profile later never rewrites an issued invoice) and its lines, all
    in the transaction of the webhook. The legal invoice is issued by ERPlora's platform hub in hub-next
    (``POST /internal/platform/invoices``), which chains it in VeriFactu and answers its status and QR:
    ``fiscal_status`` mirrors it. The PDF is the platform hub's, asked on demand.

    Money in integer cents (ADR-0123): ``net + tax == total``, and the header is the sum of its lines. A
    credit note carries negative amounts and points at the invoice it rectifies.
    """

    class Kind(models.TextChoices):
        INVOICE = "invoice", _("Invoice")
        CREDIT_NOTE = "credit_note", _("Credit note")

    # «invoice» context: in Spanish an invoice is feminine («Pagada», «Emitida»).
    class PaymentStatus(models.TextChoices):
        OPEN = "open", pgettext_lazy("invoice", "Not collected")
        PAID = "paid", pgettext_lazy("invoice", "Paid")
        VOID = "void", pgettext_lazy("invoice", "Void")

    class RectificationType(models.TextChoices):
        """VeriFactu's ``TipoFactura`` of a rectifying invoice (AEAT, «L3» list)."""

        NONE = "", _("Not a rectifying invoice")
        R1 = "R1", _("R1: error or art. 80.1, 80.2 and 80.6 LIVA (refunds, price changes)")
        R2 = "R2", _("R2: art. 80.3 LIVA (insolvency)")
        R3 = "R3", _("R3: art. 80.4 LIVA (uncollectible)")
        R4 = "R4", _("R4: other")

    class FiscalStatus(models.TextChoices):
        NONE = "", pgettext_lazy("invoice", "Not issued")
        ISSUING = "issuing", pgettext_lazy("invoice", "Issuing")
        ISSUED = "issued", pgettext_lazy("invoice", "Issued")
        ACCEPTED = "accepted", pgettext_lazy("invoice", "Accepted")
        ACCEPTED_WITH_ERRORS = "accepted_with_errors", pgettext_lazy("invoice", "Accepted with errors")
        REJECTED = "rejected", pgettext_lazy("invoice", "Rejected")

    kind = models.CharField(
        _("kind"), max_length=16, choices=Kind.choices, default=Kind.INVOICE
    )
    # SET_NULL: an invoice outlives the business, its payer and the account (Spanish law keeps it 4 years;
    # GDPR art. 17(3)); what it says of them is the snapshot below.
    hub = models.ForeignKey(
        "hubs.Hub",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("business"),
    )
    business_name = models.CharField(_("business name"), max_length=120, blank=True)
    billing_profile = models.ForeignKey(
        "hubs.BillingProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("billing profile"),
    )
    #: The account the payer belonged to on the issue date: it keeps seeing its invoices after a transfer.
    payer_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erplora_invoices",
        verbose_name=_("payer account"),
    )
    rectifies = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credit_notes",
        verbose_name=_("rectifies"),
    )
    series = models.CharField(_("series"), max_length=16, blank=True)
    sequence = models.PositiveIntegerField(_("sequence"), null=True, blank=True)
    number = models.CharField(_("number"), max_length=32, blank=True)
    #: The issue date (fecha de expedición): the day it was paid and numbered.
    issued_on = models.DateField(_("issued on"), null=True, blank=True)
    stripe_invoice_id = models.CharField(_("Stripe invoice"), max_length=255)
    #: What made a rectifying invoice: a Stripe credit note (``cn_…``), a refund without one (``re_…``) or a
    #: Stripe invoice of a negative total (``in_…``). Empty on an invoice.
    stripe_source_id = models.CharField(_("Stripe source"), max_length=255, blank=True)
    rectification_type = models.CharField(
        _("rectification type"), max_length=2, choices=RectificationType.choices, blank=True, default=""
    )
    #: Why it rectifies (Stripe's reason or memo), printed on the document.
    rectification_reason = models.CharField(_("rectification reason"), max_length=255, blank=True)
    #: Stripe's own number of the invoice (its receipt): the reference of one not numbered yet.
    stripe_number = models.CharField(_("Stripe number"), max_length=64, blank=True)
    hosted_invoice_url = models.URLField(
        _("Stripe's invoice page"), max_length=2048, blank=True
    )
    billed_at = models.DateTimeField(_("billed at"), null=True, blank=True)
    payment_status = models.CharField(
        _("payment"),
        max_length=8,
        choices=PaymentStatus.choices,
        default=PaymentStatus.OPEN,
    )
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    net_cents = models.BigIntegerField(_("tax base (cents)"), default=0)
    tax_cents = models.BigIntegerField(_("VAT (cents)"), default=0)
    total_cents = models.BigIntegerField(_("total (cents)"), default=0)
    # The qualification of the OPERATION, sealed on issue (saas#1063): rates and the policy change, and an
    # issued invoice chained in VeriFactu cannot change meaning afterwards.
    tax_treatment = models.CharField(
        _("tax treatment"), max_length=20, choices=TAX_TREATMENTS, default="domestic"
    )
    tax_country = models.CharField(_("tax country"), max_length=2, blank=True)
    tax_rate = models.DecimalField(
        _("VAT rate"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    #: Stripe charged no tax on a subject sale: the quota came out of the amount charged (saas#1479).
    vat_included_reconciled = models.BooleanField(
        _("VAT taken out of the amount charged"), default=False
    )
    # The payer as it was on the issue date.
    payer_name = models.CharField(_("payer"), max_length=255, blank=True)
    payer_tax_id = models.CharField(_("payer tax ID"), max_length=50, blank=True)
    payer_tax_id_type = models.CharField(
        _("payer tax ID type"), max_length=20, blank=True
    )
    payer_tax_id_verified = models.BooleanField(
        _("tax ID verified in VIES"), default=False
    )
    #: The VIES consultation number that backed the reverse charge: the proof travels with the document.
    vat_consultation_number = models.CharField(
        _("VIES consultation number"), max_length=64, blank=True
    )
    payer_address = models.TextField(_("payer address"), blank=True)
    payer_city = models.CharField(_("payer city"), max_length=100, blank=True)
    payer_postal_code = models.CharField(
        _("payer postal code"), max_length=20, blank=True
    )
    payer_country = models.CharField(_("payer country"), max_length=2, blank=True)
    payer_email = models.EmailField(_("payer email"), blank=True)
    #: The language the document is printed in (the payer account's).
    language = models.CharField(_("language"), max_length=8, default="es")
    # What the platform hub answered.
    fiscal_status = models.CharField(
        _("fiscal status"),
        max_length=24,
        choices=FiscalStatus.choices,
        blank=True,
        default=FiscalStatus.NONE,
    )
    fiscal_status_at = models.DateTimeField(
        _("fiscal status at"), null=True, blank=True
    )
    #: The content of the VeriFactu QR (the AEAT's verification URL).
    qr = models.TextField(_("QR"), blank=True)
    fiscal_error_code = models.CharField(
        _("fiscal error code"), max_length=64, blank=True
    )
    fiscal_error = models.TextField(_("fiscal error"), blank=True)
    post_attempts = models.PositiveIntegerField(
        _("posts to the platform hub"), default=0
    )
    next_post_at = models.DateTimeField(_("next post at"), null=True, blank=True)
    last_post_error = models.CharField(_("last post error"), max_length=255, blank=True)
    emailed_at = models.DateTimeField(_("emailed at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_on", "-created_at"]
        verbose_name = _("ERPlora invoice")
        verbose_name_plural = _("ERPlora invoices")
        indexes = [
            models.Index(fields=["stripe_invoice_id"]),
            models.Index(fields=["hub", "issued_on"]),
            models.Index(fields=["fiscal_status", "next_post_at"]),
        ]
        constraints = [
            # Two deliveries of one webhook (or ``invoice.paid`` and ``invoice.payment_succeeded`` of one
            # payment) never invoice it twice (saas#1067).
            models.UniqueConstraint(
                fields=["stripe_invoice_id"],
                condition=Q(kind="invoice"),
                name="billing_invoice_one_per_stripe_invoice",
            ),
            models.UniqueConstraint(
                fields=["stripe_source_id"],
                condition=Q(kind="credit_note") & ~Q(stripe_source_id=""),
                name="billing_invoice_one_rectification_per_source",
            ),
            models.UniqueConstraint(
                fields=["number"],
                condition=~Q(number=""),
                name="billing_invoice_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(total_cents=F("net_cents") + F("tax_cents")),
                name="billing_invoice_total_is_net_plus_tax",
            ),
            # Paid ⇔ numbered: a number is given at the payment, and only then.
            models.CheckConstraint(
                condition=(
                    Q(payment_status="paid")
                    & ~Q(number="")
                    & Q(issued_on__isnull=False)
                )
                | (~Q(payment_status="paid") & Q(number="")),
                name="billing_invoice_numbered_when_paid",
            ),
        ]

    def __str__(self):
        return self.number or self.stripe_number or self.stripe_invoice_id

    @property
    def net(self) -> Decimal:
        return _euros(self.net_cents)

    @property
    def tax(self) -> Decimal:
        return _euros(self.tax_cents)

    @property
    def total(self) -> Decimal:
        return _euros(self.total_cents)

    @property
    def is_reverse_charge(self) -> bool:
        """Read from the seal, never guessed from the tax id's type (a Spanish S.L. is ``eu_vat`` too)."""
        return self.tax_treatment == "reverse_charge"

    @property
    def vat_included_because_unverified(self) -> bool:
        """Must the document explain that the VAT came out of what was charged (saas#1479)?

        Only when it was reconciled, there is a VAT number without a VIES verdict to show, and that number
        is of ANOTHER member state (a Spanish one is never asked to VIES: nothing to prove; saas#1633 —
        under OSS the sealed jurisdiction is the customer's country, so it is not the test).
        """
        from billing.vies import is_domestic_vat_number

        if not self.vat_included_reconciled or self.payer_tax_id_verified:
            return False
        if not self.payer_tax_id or self.payer_tax_id_type != "eu_vat":
            return False
        issuer = FiscalPolicy.objects.values_list("issuer_country", flat=True).first() or "ES"
        return not is_domestic_vat_number(
            self.payer_tax_id, issuer_country=issuer, customer_country=self.payer_country
        )


class InvoiceLine(UUIDModel):
    """A line of an invoice with its own fiscal snapshot (saas#1063): what is sold (``tax_category``), its
    base, rate and quota, sealed on issue. ``net + tax == total``; negative on a proration credit or a
    credit note. ``item_kind`` and ``item_slug`` say which plan or module it bills, so the platform hub
    prints it in the payer's language; ``description`` is Stripe's text of the line."""

    class ItemKind(models.TextChoices):
        PLAN = "plan", _("Plan")
        MODULE = "module", _("Module")
        OTHER = "other", _("Other")

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("invoice"),
    )
    position = models.PositiveSmallIntegerField(_("position"))
    description = models.CharField(_("description"), max_length=255)
    item_kind = models.CharField(
        _("item"), max_length=8, choices=ItemKind.choices, default=ItemKind.OTHER
    )
    item_slug = models.CharField(_("plan or module"), max_length=63, blank=True)
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    proration = models.BooleanField(_("proration"), default=False)
    period_start = models.DateTimeField(_("from"), null=True, blank=True)
    period_end = models.DateTimeField(_("until"), null=True, blank=True)
    tax_category = models.ForeignKey(
        TaxCategory,
        to_field="key",
        db_column="tax_category_key",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_lines",
        verbose_name=_("tax category"),
    )
    #: Empty = the invoice's; sealed here only when what is sold changes it (exempt).
    tax_treatment = models.CharField(
        _("tax treatment"), max_length=20, choices=TAX_TREATMENTS, blank=True
    )
    tax_rate = models.DecimalField(
        _("VAT rate"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    net_cents = models.BigIntegerField(_("tax base (cents)"), default=0)
    tax_cents = models.BigIntegerField(_("VAT (cents)"), default=0)
    total_cents = models.BigIntegerField(_("total (cents)"), default=0)
    stripe_line_id = models.CharField(_("Stripe line"), max_length=255, blank=True)

    class Meta:
        ordering = ["invoice", "position"]
        verbose_name = _("invoice line")
        verbose_name_plural = _("invoice lines")
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "position"],
                name="billing_invoice_line_position_unique",
            ),
            models.CheckConstraint(
                condition=Q(total_cents=F("net_cents") + F("tax_cents")),
                name="billing_invoice_line_total_is_net_plus_tax",
            ),
        ]

    def __str__(self):
        return self.description

    @property
    def net(self) -> Decimal:
        return _euros(self.net_cents)

    @property
    def tax(self) -> Decimal:
        return _euros(self.tax_cents)

    @property
    def total(self) -> Decimal:
        return _euros(self.total_cents)


class PlanChangeSchedule(UUIDModel):
    """A plan change waiting for the end of the period (a downgrade: a cheaper plan, or annual → monthly).

    Stripe holds it as a subscription schedule (``stripe_schedule_id``): the current phase ends with the paid
    period and the next one bills the new items, without proration, so no negative invoice arises (review of
    L3-C). Kept here so the panel says «Starter from 1 Nov»; gone once applied or undone.
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



class OssNotice(UUIDModel):
    """A notice to the team's mailbox about the OSS threshold (BILLING-F06; old ``OssThresholdWarning`` and
    ``OssRegimeChange``, saas#2297, saas#2299): the charged sale that took the year past 80 % of the threshold
    (``near``: register in the OSS now, it takes days) and the one that crossed it, or the first charged sale
    of a year that starts in destination because the previous one closed above (``crossed``).

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
