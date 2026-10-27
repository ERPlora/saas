"""Django admin of billing: the rate table, the fiscal policy, ERPlora's identity and the VIES log.

Ported from ERPlora/saas ``apps/dashboard/fiscal/admin.py`` (origin/develop), the VAT part. A new rate, a
country raising its VAT or a service with its own rate are solved here, without a deploy (saas#1063). The
two singletons open straight on their row; the VIES log is read-only, except the manual override (adding
a row by hand) and «Check now in VIES», which adds rows through the same door as the panel and spends the
same per-person budget.

Stripe (lot L2-B): promo codes are written here (sales hands them out); what Stripe did —the checkouts
opened, the webhook's events and the renewals that failed— is read-only: Stripe is the source, and the
webhook and the operations are its only writers.

ERPlora's invoices (lot L3-C) are read-only too: recorded from what Stripe charged and issued by the platform
hub, and a record sent to the AEAT is never modified (a credit note corrects it). Their one action, «Send
again to the platform hub», posts them through ``billing.services.post_platform_invoice`` (idempotent on the
Hub) and says what the Hub answered. Its page links the PDF the platform hub issued (BILLING-G12), asked when
the staff downloads it, as the account's «Download PDF».
"""

from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.errors import OperationError

from billing import queries, services
from billing.models import (
    CheckoutAttempt,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    CompanyConfig,
    FiscalPolicy,
    OssNotice,
    PaymentFailure,
    PlanChangeSchedule,
    PromoCode,
    PromoRedemption,
    TaxCategory,
    TaxRule,
    VatCheck,
    WebhookEvent,
)
from billing.money import from_cents
from billing.vies import is_uk_vat_number


class SingletonAdminMixin:
    """A singleton in the admin: the changelist and ``/add/`` open the one row (``/add/`` only while there
    is none), and it is never deleted."""

    def has_add_permission(self, request):
        """Only while there is no row, and only for whoever may add it."""
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def _url(self, action, *args):
        meta = self.model._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_{action}", args=args)

    def changelist_view(self, request, extra_context=None):
        row = self.model.objects.first()
        return redirect(
            self._url("change", row.pk) if row is not None else self._url("add")
        )

    def add_view(self, request, form_url="", extra_context=None):
        row = self.model.objects.first()
        if row is not None:
            return redirect(self._url("change", row.pk))
        return super().add_view(request, form_url=form_url, extra_context=extra_context)


@admin.register(CompanyConfig)
class CompanyConfigAdmin(SingletonAdminMixin, admin.ModelAdmin):
    fieldsets = (
        (
            gettext_lazy("Legal identity"),
            {"fields": ("legal_name", "trade_name", "tax_id")},
        ),
        (
            gettext_lazy("Address"),
            {"fields": ("street", "city", "postal_code", "province", "country")},
        ),
        (gettext_lazy("VAT and currency"), {"fields": ("vat_regime", "currency")}),
        (gettext_lazy("Contact"), {"fields": ("email", "phone", "website")}),
        (
            gettext_lazy("History"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(TaxCategory)
class TaxCategoryAdmin(admin.ModelAdmin):
    """What ERPlora sells, in fiscal terms."""

    list_display = ("key", "name", "rule_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("key", "name", "description")
    ordering = ("key",)

    @admin.display(description=gettext_lazy("Rules"))
    def rule_count(self, obj):
        return obj.rules.count()


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    """The % by country, region and category, with validity: a change of rate is scheduled here with a
    future ``valid_from``, and older sales keep resolving the rate they had."""

    list_display = (
        "country_code",
        "region_code",
        "category",
        "rate_display",
        "rate_pct",
        "valid_from",
        "valid_to",
        "is_active",
    )
    list_filter = ("country_code", "category", "is_subject", "is_active")
    search_fields = ("country_code", "region_code", "category__key")
    list_editable = ("rate_pct", "is_active")
    list_select_related = ("category",)
    ordering = ("country_code", "region_code", "-valid_from")
    autocomplete_fields = ("category",)
    fieldsets = (
        (None, {"fields": ("category", "country_code", "region_code")}),
        (
            gettext_lazy("Rate"),
            {
                "fields": ("rate_pct", "is_subject"),
                "description": gettext_lazy(
                    "Untick «Subject to VAT» for a territory outside the scope of the tax (Canary Islands, "
                    "Ceuta, Melilla, third countries). It is not a 0 % rate: the AEAT gets it as a sale not "
                    "subject to VAT."
                ),
            },
        ),
        (gettext_lazy("Validity"), {"fields": ("valid_from", "valid_to", "is_active")}),
    )

    @admin.display(description=gettext_lazy("Applies"))
    def rate_display(self, obj):
        if not obj.is_subject:
            return _("Not subject")
        return format_html("{}%", obj.rate_pct)


@admin.register(FiscalPolicy)
class FiscalPolicyAdmin(SingletonAdminMixin, admin.ModelAdmin):
    """The issuer and the One-Stop Shop: ``oss_progress`` shows how far the threshold is, because crossing
    it unnoticed is invoicing wrong."""

    readonly_fields = ("oss_progress",)
    fieldsets = (
        (gettext_lazy("Issuer"), {"fields": ("issuer_country", "issuer_region")}),
        (
            gettext_lazy("Intra-EU B2B (ROI / VIES)"),
            {
                "fields": ("intra_eu_reverse_charge",),
                "description": gettext_lazy(
                    "While unticked, Spanish VAT is charged to EVERY customer, EU businesses included. Even "
                    "when ticked, each sale also needs a current VIES verdict on the customer's VAT number "
                    "(see «VAT checks»); otherwise VAT is charged anyway."
                ),
            },
        ),
        (
            gettext_lazy("One-Stop Shop (OSS)"),
            {
                "fields": ("oss_registered", "oss_threshold", "oss_progress"),
                "description": gettext_lazy(
                    "Below the threshold the issuer's country VAT is charged. Above it —or with the OSS "
                    "registration ticked, which binds for two years— the customer's country rate applies."
                ),
            },
        ),
        (
            gettext_lazy("Carried from the old SaaS"),
            {
                "fields": ("oss_carried_year", "oss_carried_current_cents", "oss_carried_previous_cents"),
                "description": gettext_lazy(
                    "Until the invoices live here, the cross-border B2C sales of the year come from the old "
                    "SaaS: type them for the current year and the year before. Without them the total is "
                    "unknown and the threshold could be crossed without anybody noticing."
                ),
            },
        ),
    )

    @admin.display(description=gettext_lazy("Cross-border B2C this year"))
    def oss_progress(self, obj):
        year = timezone.localdate().year
        if not queries.oss_total_is_known(obj, year):
            return _("Unknown: carry this year's amounts from the old SaaS below (threshold %(threshold)s €)") % {
                "threshold": obj.oss_threshold
            }
        total = from_cents(queries.cross_border_b2c_cents(obj, year))
        applies = (
            _("destination rate")
            if queries.uses_destination_rate(obj)
            else _("issuer rate")
        )
        return format_html("{} / {} € → {}", total, obj.oss_threshold, applies)


@admin.register(VatCheck)
class VatCheckAdmin(admin.ModelAdmin):
    """The log of VIES queries — the proof, not a boolean. Read-only: rewriting a row forges the proof that
    defends an invoice issued without VAT. The only row written by hand is the override, with its author
    and reason (contract §7)."""

    list_display = (
        "vat_number",
        "status",
        "requested_at",
        "consultation_number",
        "is_current",
        "override_by",
    )
    list_filter = ("status", "requested_at")
    search_fields = ("vat_number", "consultation_number", "returned_name")
    date_hierarchy = "requested_at"
    ordering = ("-requested_at",)
    actions = ["recheck_in_vies"]
    fields = (
        "vat_number",
        "status",
        "requested_at",
        "consultation_number",
        "returned_name",
        "returned_address",
        "override_by",
        "override_reason",
        "override_at",
    )

    @admin.display(boolean=True, description=gettext_lazy("Current"))
    def is_current(self, obj):
        return obj.is_current

    def get_readonly_fields(self, request, obj=None):
        """To add one, the number and the reason are asked; the override fills the rest."""
        if obj is None:
            return tuple(
                field
                for field in self.fields
                if field not in ("vat_number", "override_reason")
            )
        return self.fields

    def get_form(self, request, obj=None, **kwargs):
        """The reason is NOT optional: without it there is no override."""
        form = super().get_form(request, obj, **kwargs)
        if obj is None and "override_reason" in form.base_fields:
            form.base_fields["override_reason"].required = True
        return form

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        """A query is not edited: rewriting it forges the proof."""
        return False

    @admin.action(description=gettext_lazy("Check now in VIES"), permissions=["add"])
    def recheck_in_vies(self, request, queryset):
        """Ask VIES again about the selected numbers, now: each answer is a NEW row (saas#1949). The lever
        for a number the Commission could not confirm at the sale, so the override stays the exception."""
        numbers = list(
            dict.fromkeys(
                queryset.order_by("vat_number").values_list("vat_number", flat=True)
            )
        )
        for position, number in enumerate(numbers):
            if is_uk_vat_number(number):
                messages.warning(
                    request,
                    _("%(vat)s: a UK number is HMRC's, not VIES': nothing was asked.")
                    % {"vat": number},
                )
                continue
            try:
                check = services.check_vat_number(number, spender=request.user)
            except services.VatCheckThrottled:
                messages.error(
                    request,
                    _(
                        "Too many VAT checks in the last minute. Not checked, try again shortly: %(numbers)s"
                    )
                    % {"numbers": ", ".join(numbers[position:])},
                )
                return
            except services.VatCheckNotRecorded:
                messages.error(
                    request,
                    _(
                        "%(vat)s: the answer could not be saved, so it proves nothing. Try again."
                    )
                    % {"vat": number},
                )
                continue
            if check.status == VatCheck.VERIFIED:
                messages.success(
                    request,
                    _("%(vat)s: confirmed in VIES (consultation %(consultation)s).")
                    % {
                        "vat": check.vat_number,
                        "consultation": check.consultation_number,
                    },
                )
            elif check.status == VatCheck.INVALID:
                messages.warning(
                    request,
                    _("%(vat)s: not registered in VIES. VAT is charged.")
                    % {"vat": check.vat_number},
                )
            else:
                messages.warning(
                    request,
                    _(
                        "%(vat)s: VIES could not answer. VAT is still charged; try again later."
                    )
                    % {"vat": check.vat_number},
                )

    def save_model(self, request, obj, form, change):
        """Adding by hand is exactly an override, written through the same door as the code
        (``services.record_manual_override``), so the rule —author and reason— is one."""
        check = services.record_manual_override(
            obj.vat_number,
            by=request.user.email or request.user.get_username(),
            reason=form.cleaned_data.get("override_reason", ""),
        )
        obj.pk = check.pk
        obj.refresh_from_db()
        messages.warning(
            request,
            _(
                "VAT number %(vat)s marked as valid BY HAND. Who did it and why is on the record: it is the only "
                "way to invoice without VAT when VIES does not confirm the number."
            )
            % {"vat": obj.vat_number},
        )


# --- Stripe (lot L2-B) -------------------------------------------------------------------------------


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "trial_days", "is_active", "expires_at", "redemption_count", "max_redemptions", "note")
    list_filter = ("is_active",)
    search_fields = ("code", "note")
    readonly_fields = ("redemption_count", "created_at", "updated_at")


class ReadOnlyAdmin(admin.ModelAdmin):
    """What Stripe did, as the webhook and the operations wrote it: nobody adds, edits or deletes it here."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckoutAttempt)
class CheckoutAttemptAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "hub", "kind", "plan_slug", "module_slug", "billing_interval", "promo_code", "status")
    list_filter = ("status", "kind")
    search_fields = ("hub__slug", "hub__name", "stripe_session_id")
    exclude = ("client_secret",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(ReadOnlyAdmin):
    list_display = ("received_at", "event_type", "event_id", "success", "outcome", "attempts")
    list_filter = ("success", "event_type")
    search_fields = ("event_id",)


@admin.register(PaymentFailure)
class PaymentFailureAdmin(ReadOnlyAdmin):
    list_display = ("failed_at", "hub", "reason", "decline_code", "invoice_created_at", "card_changed_at", "resolved_at")
    list_filter = ("reason",)
    search_fields = ("hub__slug", "hub__name", "stripe_invoice_id", "stripe_subscription_id")


@admin.register(OssNotice)
class OssNoticeAdmin(ReadOnlyAdmin):
    """The team's notices of the OSS threshold (BILLING-F06): read only, the row is what keeps a notice from
    being sent twice in a year."""

    list_display = ("year", "kind", "reason", "accumulated", "threshold", "invoice", "effective_from", "mailed_at")
    list_filter = ("kind",)
    list_select_related = ("invoice",)

    @admin.display(description=_("accumulated"), ordering="accumulated_cents")
    def accumulated(self, obj):
        return f"{from_cents(obj.accumulated_cents)} €"

    @admin.display(description=_("threshold"), ordering="threshold_cents")
    def threshold(self, obj):
        return f"{from_cents(obj.threshold_cents)} €"


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(ReadOnlyAdmin):
    """A promo code used by a business (once per business and per payer): written when its checkout is paid."""

    list_display = ("created_at", "promo", "hub", "stripe_customer_id")
    list_select_related = ("promo", "hub")
    search_fields = ("promo__code", "hub__slug", "hub__name", "stripe_customer_id")


@admin.register(InvoiceCounter)
class InvoiceCounterAdmin(ReadOnlyAdmin):
    """The last number of each series and year: only the invoice's numbering moves it (``services.issue_number``)."""

    list_display = ("series", "year", "last_number")


@admin.register(PlanChangeSchedule)
class PlanChangeScheduleAdmin(ReadOnlyAdmin):
    """A downgrade waiting for the end of the paid period, as Stripe's subscription schedule holds it."""

    list_display = ("starts_at", "hub", "plan_slug", "interval", "stripe_schedule_id")
    list_select_related = ("hub",)
    search_fields = ("hub__slug", "hub__name", "stripe_schedule_id")


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    can_delete = False
    fields = ("position", "description", "item_kind", "item_slug", "proration", "tax_category", "tax_treatment",
              "tax_rate", "net_cents", "tax_cents", "total_cents")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ("number", "stripe_number", "kind", "issued_on", "business_name", "payer_name", "total",
                    "payment_status", "fiscal_status", "post_attempts")
    list_filter = ("kind", "payment_status", "fiscal_status", "tax_treatment")
    list_select_related = ("hub", "payer_account")
    search_fields = ("number", "stripe_number", "payer_name", "payer_tax_id", "business_name", "stripe_invoice_id",
                     "stripe_source_id")
    date_hierarchy = "issued_on"
    ordering = ("-issued_on", "-created_at")
    inlines = [InvoiceLineInline]
    actions = ["send_to_platform", "send_mail_again"]
    readonly_fields = ("pdf",)

    @admin.display(description=gettext_lazy("PDF"))
    def pdf(self, obj):
        """The platform hub's PDF, once it issued the invoice (BILLING-G12): asked when it is downloaded."""
        if obj is None or obj.payment_status != Invoice.PaymentStatus.PAID or obj.fiscal_status not in queries.ISSUED_STATUSES:
            return _("Not issued yet: its PDF is ready once the platform hub issues it.")
        return format_html(
            '<a href="{}">{}</a>', reverse("admin:billing_invoice_pdf", args=[obj.pk]), _("Download the PDF")
        )

    def get_urls(self):
        own = [path("<path:object_id>/pdf/", self.admin_site.admin_view(self.pdf_view), name="billing_invoice_pdf")]
        return own + super().get_urls()

    def pdf_view(self, request, object_id):
        """The PDF of any invoice for whoever may read invoices (``view_invoice``): the platform hub's file, or back to
        the invoice's page saying why there is none (not issued yet, the Hub away). An address with no invoice behind
        it (a stale link, an id that is no UUID) gets Django's own «does not exist» answer, never a crash."""
        invoice = self.get_object(request, unquote(object_id))
        if invoice is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        if not self.has_view_permission(request, invoice):
            raise PermissionDenied
        try:
            content = queries.platform_invoice_pdf(invoice)
        except OperationError as refused:
            messages.error(request, refused.message)
            return redirect("admin:billing_invoice_change", invoice.pk)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.number}.pdf"'
        return response

    @admin.display(description=gettext_lazy("Total"), ordering="total_cents")
    def total(self, obj):
        return f"{from_cents(obj.total_cents)} {obj.currency}"

    def has_send_permission(self, request):
        """Posting or mailing again writes: it needs the change permission (review of L3-C), although nothing
        of the invoice itself is edited here."""
        return request.user.has_perm("billing.change_invoice")

    @admin.action(description=gettext_lazy("Send again to the platform hub"), permissions=["send"])
    def send_to_platform(self, request, queryset):
        """Post the selected invoices to ERPlora's platform hub now and say what it answered: the lever for one
        «issuing» for too long or rejected and corrected in the Hub."""
        for invoice in queryset.order_by("series", "sequence"):
            outcome = services.post_platform_invoice(invoice.pk)
            invoice.refresh_from_db()
            label = invoice.number or invoice.stripe_invoice_id
            if outcome == services.POSTED:
                messages.success(
                    request,
                    _("%(invoice)s: the platform hub says «%(status)s».")
                    % {"invoice": label, "status": invoice.get_fiscal_status_display()},
                )
            elif outcome == services.NOTHING_TO_POST:
                messages.warning(request, _("%(invoice)s: not paid, so there is nothing to issue.") % {"invoice": label})
            elif outcome == services.REFUSED:
                messages.error(
                    request,
                    _("%(invoice)s: the platform hub refused it (%(code)s). It stays «issuing».")
                    % {"invoice": label, "code": invoice.fiscal_error_code or invoice.last_post_error},
                )
            else:
                messages.error(
                    request,
                    _("%(invoice)s: the platform hub did not answer. It stays «issuing» and is retried.")
                    % {"invoice": label},
                )

    @admin.action(description=gettext_lazy("Send the invoice mail again"), permissions=["send"])
    def send_mail_again(self, request, queryset):
        """Send the payer the mail of the selected invoices again (it says where to download them): only of
        the ones the platform hub issued."""
        for invoice in queryset.order_by("series", "sequence"):
            label = invoice.number or invoice.stripe_invoice_id
            if invoice.fiscal_status not in services.ISSUED_STATUSES:
                messages.warning(request, _("%(invoice)s: not issued yet, so it has no mail.") % {"invoice": label})
                continue
            outcome = services.send_invoice_mail(invoice.pk)
            if outcome == services.MAILED:
                messages.success(request, _("%(invoice)s: the mail was sent.") % {"invoice": label})
            elif outcome == services.MAIL_SKIPPED:
                messages.warning(request, _("%(invoice)s: it has nobody to send it to.") % {"invoice": label})
            else:
                messages.error(request, _("%(invoice)s: the mail could not leave; it is sent again later.")
                               % {"invoice": label})

