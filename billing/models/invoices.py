"""ERPlora's invoices to its customers, their lines and the counter of each series."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import pgettext_lazy
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from billing.models.tax import FiscalPolicy, TaxCategory


# --- ERPlora's invoices to its customers --------------------------------------------------------------

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
    """The year and the last number of a series: ``fiscal_counter``.

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
    one.

    Recorded from Stripe: an unpaid renewal is listed (``open``, without a number: «Not collected», with
    «Pay»); once paid it gets its number (``InvoiceCounter``), the payer as it was that day (a snapshot of
    ``hubs.BillingProfile``: editing the profile later never rewrites an issued invoice) and its lines, all
    in the transaction of the webhook. The legal invoice is issued by ERPlora's platform hub
    (``POST /internal/platform/invoices``), which chains it in VeriFactu and answers its status and QR:
    ``fiscal_status`` mirrors it. The PDF is the platform hub's, asked on demand.

    Money in integer cents: ``net + tax == total``, and the header is the sum of its lines. A
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
    # The qualification of the OPERATION, sealed on issue: rates and the policy change, and an
    # issued invoice chained in VeriFactu cannot change meaning afterwards.
    tax_treatment = models.CharField(
        _("tax treatment"), max_length=20, choices=TAX_TREATMENTS, default="domestic"
    )
    tax_country = models.CharField(_("tax country"), max_length=2, blank=True)
    tax_rate = models.DecimalField(
        _("VAT rate"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    #: Stripe charged no tax on a subject sale: the quota came out of the amount charged.
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
            # payment) never invoice it twice.
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
        """Must the document explain that the VAT came out of what was charged?

        Only when it was reconciled, there is a VAT number without a VIES verdict to show, and that number
        is of ANOTHER member state (a Spanish one is never asked to VIES: nothing to prove;
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
    """A line of an invoice with its own fiscal snapshot: what is sold (``tax_category``), its
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
    # What a promo code took off the price, without VAT; ``net_cents`` is the base after it.
    discount_cents = models.BigIntegerField(_("discount (cents)"), default=0)
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
