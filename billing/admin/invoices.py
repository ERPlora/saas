"""Django admin of ERPlora's invoices and the billing report.

ERPlora's invoices are read-only: recorded from what Stripe charged and issued by the platform hub, and a
record sent to the AEAT is never modified (a credit note corrects it). Their one action, «Send again to the
platform hub», posts them through ``billing.services.platform_invoices.post_platform_invoice`` (idempotent on
the Hub) and says what the Hub answered. Its page links the PDF the platform hub issued, asked when the staff
downloads it, as the account's «Download PDF». From the list, «Billing report» shows what was invoiced in a
month, a quarter or a year for the accountant, and downloads it as an Excel; it is read for whoever may read
invoices.
"""

import io
import zipfile
from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone, translation
from django.utils.dates import MONTHS
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.errors import OperationError

from billing import queries
from billing.admin.payment_records import ReadOnlyAdmin
from billing.models import Invoice, InvoiceLine
from billing.money import from_cents
from billing.services import platform_invoices


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


class BillingReportForm(forms.Form):
    year = forms.IntegerField(label=gettext_lazy("Year"), min_value=2000, max_value=2100)
    period = forms.ChoiceField(
        label=gettext_lazy("Period"),
        choices=[
            ("year", gettext_lazy("Whole year")),
            ("q1", gettext_lazy("First quarter")),
            ("q2", gettext_lazy("Second quarter")),
            ("q3", gettext_lazy("Third quarter")),
            ("q4", gettext_lazy("Fourth quarter")),
            *((f"m{month}", name) for month, name in MONTHS.items()),
        ],
    )


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
    actions = ["send_to_platform", "send_mail_again", "download_pdfs"]
    readonly_fields = ("pdf",)

    @admin.display(description=gettext_lazy("PDF"))
    def pdf(self, obj):
        """The platform hub's PDF, once it issued the invoice: asked when it is downloaded."""
        if obj is None or obj.payment_status != Invoice.PaymentStatus.PAID or obj.fiscal_status not in queries.ISSUED_STATUSES:
            return _("Not issued yet: its PDF is ready once the platform hub issues it.")
        return format_html(
            '<a href="{}">{}</a>', reverse("admin:billing_invoice_pdf", args=[obj.pk]), _("Download the PDF")
        )

    def get_urls(self):
        own = [
            path("report/", self.admin_site.admin_view(self.report_view), name="billing_invoice_report"),
            path(
                "report/excel/",
                self.admin_site.admin_view(self.report_excel_view),
                name="billing_invoice_report_excel",
            ),
            path("<path:object_id>/pdf/", self.admin_site.admin_view(self.pdf_view), name="billing_invoice_pdf"),
        ]
        return own + super().get_urls()

    def _report_form(self, request) -> BillingReportForm:
        """The period asked for; without one, the current quarter. Whoever may read invoices may read the report."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        if request.GET:
            return BillingReportForm(request.GET)
        current = queries.quarter_of(timezone.localdate())
        return BillingReportForm({"year": current.year, "period": current.period})

    @staticmethod
    def _chosen_period(form: BillingReportForm):
        return queries.report_period(form.cleaned_data["year"], form.cleaned_data["period"])

    def report_view(self, request):
        """What ERPlora invoiced in the chosen month, quarter or year, with what the accountant asks for."""
        form = self._report_form(request)
        report = None
        excel_url = ""
        if form.is_valid():
            report = queries.billing_report(self._chosen_period(form))
            excel_url = "{}?{}".format(
                reverse("admin:billing_invoice_report_excel"),
                urlencode({"year": report.period.year, "period": report.period.period}),
            )
            if report.not_issued:
                messages.warning(
                    request,
                    _("Collected in this period but not issued yet, so not counted: %(invoices)s")
                    % {"invoices": ", ".join(report.not_issued)},
                )
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": _("Billing report"),
            "form": form,
            "report": report,
            "excel_url": excel_url,
        }
        return TemplateResponse(request, "admin/billing/invoice/report.html", context)

    def report_excel_view(self, request):
        """The report's «Download Excel»; a period it does not know goes back to the report, which says why."""
        form = self._report_form(request)
        if not form.is_valid():
            return redirect(f"{reverse('admin:billing_invoice_report')}?{request.GET.urlencode()}")
        document = queries.billing_report_csv(self._chosen_period(form), translation.get_language())
        response = HttpResponse(document["content"], content_type=document["content_type"])
        response["Content-Disposition"] = f'attachment; filename="{document["filename"]}"'
        return response

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

    @admin.action(description=gettext_lazy("Download the PDFs (ZIP)"), permissions=["view"])
    def download_pdfs(self, request, queryset):
        """The PDFs of the selected invoices in one ZIP, each asked of the platform hub as the single download is
        (``queries.platform_invoice_pdf``). One without its PDF (still being issued, or the Hub does not return it)
        is named, never dropped silently: in the admin's message and in ``not-included.txt`` inside the ZIP. With no
        PDF at all there is no empty ZIP: only the message, back on the list."""
        files, missing = [], []
        for invoice in queryset.order_by("series", "sequence", "issued_on"):
            label = invoice.number or invoice.stripe_invoice_id
            try:
                files.append((f"{label}.pdf", queries.platform_invoice_pdf(invoice)))
            except OperationError as refused:
                missing.append(f"{label}: {refused.message}")
        if not files:
            messages.error(
                request,
                _("None of the selected invoices has its PDF yet: %(invoices)s") % {"invoices": "; ".join(missing)},
            )
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files:
                archive.writestr(name, content)
            if missing:
                note = _("These invoices were left out of the ZIP:")
                archive.writestr("not-included.txt", "\n".join([note, *missing]) + "\n")
        if missing:
            messages.warning(
                request,
                _("These invoices were left out of the ZIP: %(invoices)s") % {"invoices": "; ".join(missing)},
            )
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="invoices-{timezone.localdate():%Y-%m-%d}.zip"'
        return response

    @admin.display(description=gettext_lazy("Total"), ordering="total_cents")
    def total(self, obj):
        return f"{from_cents(obj.total_cents)} {obj.currency}"

    def has_send_permission(self, request):
        """Posting or mailing again writes: it needs the change permission, although nothing
        of the invoice itself is edited here."""
        return request.user.has_perm("billing.change_invoice")

    @admin.action(description=gettext_lazy("Send again to the platform hub"), permissions=["send"])
    def send_to_platform(self, request, queryset):
        """Post the selected invoices to ERPlora's platform hub now and say what it answered: the lever for one
        «issuing» for too long or rejected and corrected in the Hub."""
        for invoice in queryset.order_by("series", "sequence"):
            outcome = platform_invoices.post_platform_invoice(invoice.pk)
            invoice.refresh_from_db()
            label = invoice.number or invoice.stripe_invoice_id
            if outcome == platform_invoices.POSTED:
                messages.success(
                    request,
                    _("%(invoice)s: the platform hub says «%(status)s».")
                    % {"invoice": label, "status": invoice.get_fiscal_status_display()},
                )
            elif outcome == platform_invoices.NOTHING_TO_POST:
                messages.warning(request, _("%(invoice)s: not paid, so there is nothing to issue.") % {"invoice": label})
            elif outcome == platform_invoices.REFUSED:
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
        """Send the payer the mail of the selected invoices again, each with its PDF attached: only of the ones
        the platform hub issued."""
        for invoice in queryset.order_by("series", "sequence"):
            label = invoice.number or invoice.stripe_invoice_id
            if invoice.fiscal_status not in platform_invoices.ISSUED_STATUSES:
                messages.warning(request, _("%(invoice)s: not issued yet, so it has no mail.") % {"invoice": label})
                continue
            outcome = platform_invoices.send_invoice_mail(invoice.pk)
            if outcome == platform_invoices.MAILED:
                messages.success(request, _("%(invoice)s: the mail was sent.") % {"invoice": label})
            elif outcome == platform_invoices.MAIL_SKIPPED:
                messages.warning(request, _("%(invoice)s: it has nobody to send it to.") % {"invoice": label})
            else:
                messages.error(request, _("%(invoice)s: the mail could not leave; it is sent again later.")
                               % {"invoice": label})

