"""The billing report of the admin (BILLING-F40): what ERPlora invoiced in a month, a quarter or a year.

The team picks a period and reads what the accountant asks for: base, VAT and total per series (``ERP``
invoices, ``ERPR`` credit notes, which are negative) and the net of both; the VAT broken down by tax
treatment, customer's country and rate, as the lines were sent to VeriFactu (Spanish VAT for form 303,
reverse charge for 349, OSS for 369); and by kind of customer. Only invoices that were collected and
issued count: one still being issued is named, never added silently. «Download Excel» gives one row per
counted invoice, in the format of the panel's CSV. Whoever may read invoices in the admin sees it.
"""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from billing import queries
from billing.models import Invoice, InvoiceLine

pytestmark = pytest.mark.django_db

REPORT = "/admin/billing/invoice/report/"
EXCEL = "/admin/billing/invoice/report/excel/"
Q3 = {"year": "2026", "period": "q3"}

_sequences = {"ERP": 0, "ERPR": 0, "stripe": 0}


@pytest.fixture(autouse=True)
def _fresh_numbers():
    _sequences.update({"ERP": 0, "ERPR": 0, "stripe": 0})


def record(
    *,
    on=date(2026, 8, 10),
    kind="invoice",
    net=10000,
    tax=2100,
    treatment="domestic",
    rate="21.00",
    country="ES",
    tax_id="",
    verified=False,
    payment="paid",
    fiscal="accepted",
    payer="Panadería López SL",
    lines=None,
) -> Invoice:
    """An invoice (or a credit note, with negative amounts) as the webhook records it, with its lines. By
    default one line carrying the whole amount at the invoice's treatment and rate. One not collected has no
    number (the database refuses it), but its date may fall in the period."""
    paid = payment == "paid"
    series = ("ERPR" if kind == "credit_note" else "ERP") if paid else ""
    sequence = None
    if paid:
        _sequences[series] += 1
        sequence = _sequences[series]
    _sequences["stripe"] += 1
    invoice = Invoice.objects.create(
        kind=kind,
        stripe_invoice_id=f"in_{_sequences['stripe']}",
        stripe_source_id=f"cn_{_sequences['stripe']}" if kind == "credit_note" else "",
        business_name="Panadería López",
        series=series,
        sequence=sequence,
        number=f"{series}-{on.year}-{sequence:05d}" if paid else "",
        issued_on=on,
        payment_status=payment,
        net_cents=net,
        tax_cents=tax,
        total_cents=net + tax,
        tax_treatment=treatment,
        tax_rate=Decimal(rate),
        tax_country=country if treatment != "not_subject" else "",
        payer_name=payer,
        payer_tax_id=tax_id,
        payer_tax_id_verified=verified,
        payer_country=country,
        fiscal_status=fiscal,
    )
    for position, (line_net, line_tax, line_treatment, line_rate) in enumerate(
        lines or [(net, tax, "", rate)], start=1
    ):
        InvoiceLine.objects.create(
            invoice=invoice,
            position=position,
            description="1 × Starter",
            tax_treatment=line_treatment,
            tax_rate=Decimal(line_rate),
            net_cents=line_net,
            tax_cents=line_tax,
            total_cents=line_net + line_tax,
        )
    return invoice


def report(year=2026, period="q3"):
    return queries.billing_report(queries.report_period(year, period))


def totals(row):
    return (row.invoices, row.net_cents, row.tax_cents, row.total_cents)


class TestThePeriod:
    @pytest.mark.parametrize(
        ("period", "start", "end", "key"),
        [
            ("year", date(2026, 1, 1), date(2026, 12, 31), "2026"),
            ("q1", date(2026, 1, 1), date(2026, 3, 31), "2026-Q1"),
            ("q3", date(2026, 7, 1), date(2026, 9, 30), "2026-Q3"),
            ("q4", date(2026, 10, 1), date(2026, 12, 31), "2026-Q4"),
            ("m2", date(2026, 2, 1), date(2026, 2, 28), "2026-02"),
            ("m12", date(2026, 12, 1), date(2026, 12, 31), "2026-12"),
        ],
    )
    def test_a_month_a_quarter_or_a_year(self, period, start, end, key):
        chosen = queries.report_period(2026, period)

        assert (chosen.start, chosen.end, chosen.key) == (start, end, key)

    @pytest.mark.parametrize("period", ["", "q0", "q5", "m0", "m13", "week", "mx"])
    def test_anything_else_is_refused(self, period):
        with pytest.raises(ValueError):
            queries.report_period(2026, period)

    def test_its_first_and_last_day_count_and_the_next_one_does_not(self):
        record(on=date(2026, 6, 30))
        first = record(on=date(2026, 7, 1))
        last = record(on=date(2026, 9, 30))
        record(on=date(2026, 10, 1))

        counted = set(queries.report_invoices(queries.report_period(2026, "q3")).values_list("pk", flat=True))

        assert counted == {first.pk, last.pk}


class TestTheTotalsPerSeries:
    def test_invoices_credit_notes_and_their_net(self):
        record(net=10000, tax=2100)
        record(net=2999, tax=630)
        record(kind="credit_note", net=-2999, tax=-630)

        result = report()

        assert totals(result.invoices) == (2, 12999, 2730, 15729)
        assert totals(result.credit_notes) == (1, -2999, -630, -3629)
        assert totals(result.net) == (3, 10000, 2100, 12100)

    def test_a_period_without_invoices_is_all_zero(self):
        result = report()

        assert totals(result.invoices) == totals(result.credit_notes) == totals(result.net) == (0, 0, 0, 0)
        assert result.by_tax == [] and result.not_issued == []

    def test_one_not_collected_never_counts(self):
        record(net=10000, tax=2100)
        record(net=5000, tax=1050, payment="open", fiscal="")
        record(net=7000, tax=1470, payment="void", fiscal="")

        result = report()

        assert totals(result.net) == (1, 10000, 2100, 12100)
        assert result.not_issued == []

    @pytest.mark.parametrize("fiscal", ["issuing", "rejected", ""])
    def test_one_collected_but_not_issued_is_named_not_counted(self, fiscal):
        record(net=10000, tax=2100)
        pending = record(net=5000, tax=1050, fiscal=fiscal)

        result = report()

        assert totals(result.net) == (1, 10000, 2100, 12100)
        assert result.not_issued == [pending.number]

    @pytest.mark.parametrize("fiscal", ["issued", "accepted", "accepted_with_errors"])
    def test_every_issued_status_counts(self, fiscal):
        record(fiscal=fiscal)

        assert report().net.invoices == 1


class TestTheVatBreakdown:
    """By tax treatment, customer's country and rate, from the lines as the platform hub received them (a line
    without its own treatment carries the invoice's): domestic for form 303, reverse charge for 349, OSS for 369."""

    def rows(self, result):
        return [
            (row.treatment, row.country, row.rate, row.invoices, row.net_cents, row.tax_cents, row.total_cents)
            for row in result.by_tax
        ]

    def test_per_treatment_country_and_rate(self):
        record(net=10000, tax=2100)
        record(net=2999, tax=630)
        record(kind="credit_note", net=-2999, tax=-630)
        record(net=10000, tax=2000, treatment="oss", rate="20.00", country="FR")
        record(net=10000, tax=0, treatment="reverse_charge", rate="0.00", country="DE", tax_id="DE123456789",
               verified=True)
        record(net=10000, tax=0, treatment="not_subject", rate="0.00", country="US", tax_id="12-3456789")

        assert self.rows(report()) == [
            ("domestic", "ES", Decimal("21.00"), 3, 10000, 2100, 12100),
            ("oss", "FR", Decimal("20.00"), 1, 10000, 2000, 12000),
            ("reverse_charge", "DE", Decimal("0.00"), 1, 10000, 0, 10000),
            ("not_subject", "US", Decimal("0.00"), 1, 10000, 0, 10000),
        ]

    def test_a_line_with_its_own_treatment_goes_on_its_own_row(self):
        record(net=12000, tax=2100, lines=[(10000, 2100, "", "21.00"), (2000, 0, "exempt", "0.00")])

        assert self.rows(report()) == [
            ("domestic", "ES", Decimal("21.00"), 1, 10000, 2100, 12100),
            ("exempt", "ES", Decimal("0.00"), 1, 2000, 0, 2000),
        ]

    def test_it_adds_up_to_the_net(self):
        record(net=10000, tax=2100)
        record(kind="credit_note", net=-5000, tax=-1050)
        record(net=10000, tax=2000, treatment="oss", rate="20.00", country="FR")
        record(net=12000, tax=2100, lines=[(10000, 2100, "", "21.00"), (2000, 0, "exempt", "0.00")])
        record(net=999, tax=210, fiscal="issuing")
        record(net=999, tax=210, payment="open", fiscal="")

        result = report()

        summed = tuple(sum(getattr(row, field) for row in result.by_tax) for field in ("net_cents", "tax_cents",
                                                                                         "total_cents"))
        assert summed == totals(result.net)[1:]


class TestTheKindOfCustomer:
    """A company (a Spanish tax ID of a legal person, or a tax ID from abroad), a self-employed person or an
    individual with a Spanish tax ID of a natural person (also written as a VAT number, «ES» first), or an
    individual without a tax ID."""

    def rows(self, result):
        return {row.kind: (row.invoices, row.net_cents, row.tax_cents, row.total_cents) for row in result.by_customer}

    def test_each_invoice_counts_for_its_payer_kind(self):
        record(net=10000, tax=2100, tax_id="B12345678")
        record(net=10000, tax=0, treatment="reverse_charge", rate="0.00", country="DE", tax_id="DE123456789",
               verified=True)
        record(net=2000, tax=420, tax_id="12345678Z")
        record(net=3000, tax=630, tax_id="X1234567L")
        record(net=1000, tax=210, tax_id="ES-12345678Z")
        record(net=500, tax=105)
        record(kind="credit_note", net=-500, tax=-105)

        assert self.rows(report()) == {
            "company": (2, 20000, 2100, 22100),
            "self_employed": (3, 6000, 1260, 7260),
            "individual": (2, 0, 0, 0),
        }

    def test_every_kind_is_listed_even_without_invoices(self):
        assert self.rows(report()) == {
            "company": (0, 0, 0, 0),
            "self_employed": (0, 0, 0, 0),
            "individual": (0, 0, 0, 0),
        }


class TestTheExcel:
    """One row per counted invoice of the period, in the format of the panel's «Download Excel» (UTF-8 with its BOM,
    the separator and the decimals of the language), with what the accountant needs for 303, 349 and 369: the
    payer's tax ID, the country and the tax treatment."""

    def document(self, language="en", period="q3"):
        return queries.billing_report_csv(queries.report_period(2026, period), language)

    def rows(self, document, delimiter):
        return list(csv.reader(io.StringIO(document["content"].decode("utf-8-sig")), delimiter=delimiter))

    def test_one_row_per_counted_invoice_and_nothing_else(self):
        first = record(net=10000, tax=2100, tax_id="B12345678")
        credit = record(kind="credit_note", net=-2999, tax=-630)
        record(fiscal="issuing")
        record(payment="open", fiscal="")
        record(on=date(2026, 10, 1))

        document = self.document()
        header, *rows = self.rows(document, ",")

        assert document["content"].startswith("﻿".encode())
        assert document["content_type"] == "text/csv; charset=utf-8"
        assert document["filename"] == "erplora-invoices-2026-Q3.csv"
        assert header == ["Invoice", "Date", "Business", "Payer", "Tax ID", "Country", "Tax treatment", "VAT %",
                          "Tax base", "VAT", "Total", "Currency", "Payment", "Status"]
        assert rows == [
            [first.number, "2026-08-10", "Panadería López", "Panadería López SL", "B12345678", "ES", "Domestic",
             "21.00", "100.00", "21.00", "121.00", "EUR", "Paid", "Accepted"],
            [credit.number, "2026-08-10", "Panadería López", "Panadería López SL", "", "ES", "Domestic", "21.00",
             "-29.99", "-6.30", "-36.29", "EUR", "Paid", "Accepted"],
        ]

    def test_in_spanish_semicolons_and_a_decimal_comma(self):
        record(net=10000, tax=2100)

        header, row = self.rows(self.document("es"), ";")

        assert header[0] == "Factura"
        assert row[7:11] == ["21,00", "100,00", "21,00", "121,00"]

    def test_a_payer_that_looks_like_a_formula_is_text(self):
        record(payer='=HYPERLINK("http://evil.example","x")')

        _, row = self.rows(self.document(), ",")

        assert row[3] == "'=HYPERLINK(\"http://evil.example\",\"x\")"


@pytest.fixture
def staff_client(client):
    client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))
    return client


def staff_with(*codenames):
    user = get_user_model().objects.create_user(email=f"{'-'.join(codenames) or 'none'}@example.com", password="x",
                                                is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return user


class TestTheAdminPage:
    def test_the_list_of_invoices_links_it(self, staff_client):
        body = staff_client.get("/admin/billing/invoice/").content.decode()

        assert REPORT in body

    def test_it_shows_the_chosen_periods_report(self, staff_client):
        record(net=10000, tax=2100)
        record(kind="credit_note", net=-2999, tax=-630)
        record(on=date(2026, 10, 1), net=50000, tax=10500)

        response = staff_client.get(REPORT, Q3)

        assert response.status_code == 200
        shown = response.context["report"]
        assert shown.period.key == "2026-Q3"
        assert totals(shown.net) == (2, 7001, 1470, 8471)
        body = response.content.decode()
        assert "70.01" in body and "84.71" in body
        assert f"{EXCEL}?year=2026&amp;period=q3" in body

    def test_it_opens_on_the_current_quarter(self, staff_client):
        from django.utils import timezone

        today = timezone.localdate()

        shown = staff_client.get(REPORT).context["report"]

        assert shown.period.key == f"{today.year}-Q{(today.month - 1) // 3 + 1}"

    def test_a_period_it_does_not_know_is_said_not_a_crash(self, staff_client):
        response = staff_client.get(REPORT, {"year": "2026", "period": "q9"})

        assert response.status_code == 200
        assert response.context["report"] is None
        assert response.context["form"].errors

    def test_the_ones_not_issued_yet_are_named(self, staff_client):
        pending = record(fiscal="issuing")

        body = staff_client.get(REPORT, Q3).content.decode()

        assert pending.number in body

    def test_it_downloads_the_excel_of_the_period(self, staff_client):
        counted = record(net=10000, tax=2100)

        response = staff_client.get(EXCEL, Q3)

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"] == 'attachment; filename="erplora-invoices-2026-Q3.csv"'
        assert counted.number in response.content.decode("utf-8-sig")

    def test_the_excel_of_a_period_it_does_not_know_goes_back_to_the_report(self, staff_client):
        response = staff_client.get(EXCEL, {"year": "2026", "period": "q9"}, follow=True)

        assert response.redirect_chain[-1][0] == f"{REPORT}?year=2026&period=q9"
        assert response.context["form"].errors

    def test_a_reader_of_invoices_sees_and_downloads_it(self, client):
        client.force_login(staff_with("view_invoice"))

        assert client.get(REPORT, Q3).status_code == 200
        assert client.get(EXCEL, Q3).status_code == 200

    def test_staff_who_may_not_read_invoices_does_not(self, client):
        record()
        client.force_login(staff_with())

        assert client.get(REPORT, Q3).status_code == 403
        assert client.get(EXCEL, Q3).status_code == 403

    def test_in_spanish_it_speaks_spanish(self, staff_client):
        record()

        body = staff_client.get(REPORT, Q3, HTTP_ACCEPT_LANGUAGE="es").content.decode()

        assert "Informe de facturación" in body and "Rectificativas" in body
