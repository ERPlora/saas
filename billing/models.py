"""Models of billing's EU VAT engine (lot L2-A): what is sold at which rate, the issuer's policy and
identity, and the log of VIES queries.

Ported from ERPlora/saas ``apps/dashboard/fiscal/models.py`` (origin/develop): ``TaxCategory``,
``TaxRule``, ``FiscalPolicy``, ``CompanyConfig`` and ``VatCheck``, with UUIDv7 keys. The two singletons
stop forcing ``pk=1`` (a UUID key) and keep a single row by a unique column that is always true. Their
reads (the rule in force, the policy, the latest verdict) live in ``billing.queries``: only
``services.py`` and ``queries.py`` touch the ORM. Without ``CompanyConfig.logo`` (the invoice PDF is the
Hub's, plan §4 L3-C) nor the VeriFactu models, which are the Hub's (PLAN-HUB, fiscal).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
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
        help_text=_("The year the «this year» amount belongs to. Empty = nothing carried: the total is unknown"),
    )
    oss_carried_current_cents = models.PositiveBigIntegerField(
        _("cross-border B2C carried for that year (cents)"),
        default=0,
        help_text=_("Tax base of the intra-EU B2C sales without a verified VAT number invoiced by the old SaaS that year, in cents"),
    )
    oss_carried_previous_cents = models.PositiveBigIntegerField(
        _("cross-border B2C carried for the year before (cents)"),
        default=0,
        help_text=_("The same, for the year before: above the threshold, the whole year is destination VAT"),
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
