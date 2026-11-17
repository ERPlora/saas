"""The 0 € invoice of a discount of all of it is in every place an invoice is: the panel's list, its page, its PDF and
CSV, the admin (list and ZIP of PDFs), the run that posts what the platform hub still owes, the payer's mail and the
report for the accountant. Each test records it through Stripe's webhook, as Stripe sent it (``fixtures/discounts/``).
"""

import csv
import io
import zipfile

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from billing import queries, services
from billing.models import Invoice
from billing.queries.billing_report import quarter_of
from billing.schemas import InvoiceByIdIn, InvoiceFilterIn, InvoiceListIn
from billing.tests.conftest import ctx_for
from billing.tests.stripe_captured import paid
from billing.tests.stripe_double import subscription
from billing.tests.test_invoice_recording import deliver

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n% ERPlora test\n%%EOF\n"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    return stripe_double


@pytest.fixture
def zero(running) -> Invoice:
    """The invoice of the first month of Panadería López (Starter, ``sub_1``) with all of it discounted, recorded from
    Stripe's event."""
    assert deliver(paid("repeating_100/invoice_paid_1.json")) == "processed"
    return Invoice.objects.get(total_cents=0)


def accepted(invoice: Invoice) -> Invoice:
    """The platform hub issued it and the AEAT accepted it."""
    Invoice.objects.filter(pk=invoice.pk).update(fiscal_status="accepted", payer_email="pagos@example.com")
    return Invoice.objects.get(pk=invoice.pk)


def test_the_list_shows_it(zero, owner):
    rows = queries.invoice_list(ctx_for(owner), InvoiceListIn()).model_dump(mode="json")["rows"]

    assert [(row["number"], row["total_cents"]) for row in rows] == [(zero.number, 0)]


def test_its_page_shows_the_discount_of_each_line(zero, owner):
    detail = queries.invoice_get(ctx_for(owner), InvoiceByIdIn(id=zero.id)).model_dump(mode="json")

    assert [(line["discount_cents"], line["net_cents"], line["total_cents"]) for line in detail["lines"]] == [(2999, 0, 0)]


def test_its_pdf_is_the_platform_hubs(zero, owner, monkeypatch):
    from hubs import hub_client

    monkeypatch.setattr(hub_client, "get_platform_invoice_pdf", lambda invoice_id: PDF)

    document = queries.invoice_pdf(ctx_for(owner), InvoiceByIdIn(id=accepted(zero).id))

    assert document.content == PDF


def test_the_csv_lists_it_at_zero(zero, owner):
    text = queries.invoice_csv(ctx_for(owner), InvoiceFilterIn()).content.decode("utf-8-sig")

    [row] = [row for row in csv.reader(io.StringIO(text)) if zero.number in row]
    assert "0.00" in row


def test_the_admin_lists_it(zero, staff_client):
    assert zero.number in staff_client.get("/admin/billing/invoice/").content.decode()


def test_the_zip_of_pdfs_carries_it(zero, staff_client, hub_double):
    hub_double.answer("GET", rf"/{zero.pk}/pdf$", 200, {"pdf": "zero"})

    response = staff_client.post(
        "/admin/billing/invoice/", {"action": "download_pdfs", "_selected_action": [str(accepted(zero).pk)]}
    )

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [f"{zero.number}.pdf"]


def test_the_run_posts_it_while_the_platform_hub_owes_it(zero, hub_double):
    Invoice.objects.filter(pk=zero.pk).update(next_post_at=timezone.now() - timezone.timedelta(minutes=1))
    hub_double.answer("POST", r"^/internal/platform/invoices$", 200, {"status": "accepted", "qr": "https://example.com/qr"})

    out = io.StringIO()
    call_command("reconcile_platform_invoices", stdout=out)

    assert "posted=1" in out.getvalue()
    [post] = [call for call in hub_double.calls_to("POST") if call.path == "/internal/platform/invoices"]
    assert (post.body["number"], post.body["total_cents"]) == (zero.number, 0)


def test_the_payer_gets_its_mail(zero):
    assert services.send_invoice_mail(accepted(zero).id) == services.MAILED

    assert [message.to for message in mail.outbox] == [["pagos@example.com"]]
    assert zero.number in mail.outbox[0].body


def test_the_report_for_the_accountant_counts_it(zero):
    report = queries.billing_report(quarter_of(accepted(zero).issued_on))

    assert (report.invoices.invoices, report.invoices.total_cents) == (1, 0)
    assert zero.number in [invoice.number for invoice in queries.report_invoices(report.period)]
