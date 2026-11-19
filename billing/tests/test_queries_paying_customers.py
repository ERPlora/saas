"""The paying customers of the admin (BILLING-F41): which businesses pay, on what plan, since when and how much.

One row per business Stripe charges today, with its payer, their country and kind of customer, the plan and how
often it is billed, the monthly amount before VAT (the base of its last invoice collected for a whole period, a
year's divided by 12) and the date of its first collected invoice. The list filters by plan, status and country and
downloads what it shows as an Excel in the format of the billing report's. Whoever may read the subscriptions in the
admin sees it.
"""

import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from billing import queries
from billing.models import Invoice, InvoiceLine
from billing.tests.conftest import pay, staff_with

pytestmark = pytest.mark.django_db

LIST = "/admin/billing/payingcustomer/"
EXCEL = "/admin/billing/payingcustomer/excel/"

_numbers = {"ERP": 0, "ERPR": 0, "stripe": 0}


@pytest.fixture(autouse=True)
def _fresh_numbers():
    _numbers.update({"ERP": 0, "ERPR": 0, "stripe": 0})


@pytest.fixture
def customer(plans, business_paid_by):
    """A business paid by a payer in ``country`` and charged by Stripe on ``plan`` every ``interval``."""
    made = []

    def make(*, plan="starter", interval="month", status="active", country="ES", tax_id="", payer="Payer SL"):
        hub = business_paid_by(country, "28001" if country == "ES" else "1000-001", tax_id=tax_id)
        profile = hub.billing_profile
        profile.billing_name = payer
        profile.save()
        made.append(hub)
        return pay(hub, plan=plan, interval=interval, status=status, sub_id=f"sub_{len(made)}",
                   customer=f"cus_{len(made)}")

    return make


def invoiced(hub, *, on=date(2026, 8, 10), net=2900, kind="invoice", payment="paid", lines=None,
             period=(None, None)) -> Invoice:
    """An invoice of ``hub`` as the webhook records it. ``lines`` are ``(net, proration)`` pairs; by default one
    line for the whole period carrying the whole amount. ``period`` is the ``(from, until)`` its lines bill."""
    paid = payment == "paid"
    series = ("ERPR" if kind == "credit_note" else "ERP") if paid else ""
    sequence = None
    if paid:
        _numbers[series] += 1
        sequence = _numbers[series]
    _numbers["stripe"] += 1
    invoice = Invoice.objects.create(
        kind=kind,
        hub=hub,
        business_name=hub.name,
        stripe_invoice_id=f"in_{_numbers['stripe']}",
        stripe_source_id=f"cn_{_numbers['stripe']}" if kind == "credit_note" else "",
        series=series,
        sequence=sequence,
        number=f"{series}-{on.year}-{sequence:05d}" if paid else "",
        issued_on=on,
        payment_status=payment,
        net_cents=net,
        tax_cents=0,
        total_cents=net,
        payer_country="ES",
        fiscal_status="accepted" if paid else "",
    )
    for position, (line_net, proration) in enumerate(lines or [(net, False)], start=1):
        InvoiceLine.objects.create(
            invoice=invoice,
            position=position,
            description="1 × Starter",
            proration=proration,
            period_start=period[0],
            period_end=period[1],
            tax_rate=Decimal("21.00"),
            net_cents=line_net,
            tax_cents=0,
            total_cents=line_net,
        )
    return invoice


def listed():
    return {row.hub.name: row for row in queries.paying_customers()}


class TestWhoIsAPayingCustomer:
    def test_every_business_stripe_charges_and_no_other(self, customer, business_paid_by):
        active = customer()
        trialing = customer(status="trialing")
        past_due = customer(status="past_due")
        ended = customer(status="canceled")
        never_paid = customer(status="incomplete_expired")
        free = business_paid_by("ES")

        names = set(listed())

        assert {active.name, trialing.name, past_due.name} <= names
        assert not names & {ended.name, never_paid.name, free.name}

    def test_a_business_without_a_stripe_subscription_is_not_one(self, customer):
        from hubs.models import Subscription

        hub = customer()
        Subscription.objects.filter(hub=hub).update(stripe_subscription_id="")

        assert hub.name not in listed()


class TestTheMonthlyAmount:
    """The base of its last invoice collected for a whole period, before VAT; a yearly one, divided by 12."""

    def test_a_monthly_plan_pays_its_last_collected_invoice(self, customer):
        hub = customer()
        invoiced(hub, on=date(2026, 7, 10), net=2900)
        invoiced(hub, on=date(2026, 8, 10), net=3900)

        assert queries.monthly_cents(listed()[hub.name]) == 3900

    def test_a_yearly_plan_pays_a_twelfth_of_it_a_month(self, customer):
        hub = customer(interval="year")
        invoiced(hub, net=29000)

        assert queries.monthly_cents(listed()[hub.name]) == 2417

    def test_the_prorations_of_a_change_mid_period_do_not_count(self, customer):
        hub = customer()
        invoiced(hub, on=date(2026, 8, 10), net=2900)
        invoiced(hub, on=date(2026, 8, 20), net=-967 + 1300, lines=[(-967, True), (1300, True)])

        assert queries.monthly_cents(listed()[hub.name]) == 2900

    def test_a_full_period_invoice_counts_only_its_full_period_lines(self, customer):
        hub = customer(interval="year")
        invoiced(hub, net=29000 - 1500, lines=[(29000, False), (-1500, True)])

        assert queries.monthly_cents(listed()[hub.name]) == 2417

    def test_a_year_charged_before_moving_to_monthly_is_still_divided_by_twelve(self, customer):
        """A business that moved from yearly to monthly and whose first monthly charge failed: its last collected
        invoice billed a year, whatever the subscription says today."""
        hub = customer(interval="month", status="past_due")
        invoiced(hub, on=date(2025, 8, 10), net=29000, period=(datetime(2025, 8, 10, tzinfo=UTC),
                                                               datetime(2026, 8, 10, tzinfo=UTC)))
        invoiced(hub, on=date(2026, 8, 10), net=2900, payment="open")

        assert queries.monthly_cents(listed()[hub.name]) == 2417

    def test_a_month_charged_before_moving_to_yearly_is_not_divided(self, customer):
        hub = customer(interval="year")
        invoiced(hub, net=2900, period=(datetime(2026, 8, 10, tzinfo=UTC), datetime(2026, 9, 10, tzinfo=UTC)))

        assert queries.monthly_cents(listed()[hub.name]) == 2900

    def test_an_invoice_not_collected_or_a_credit_note_is_not_what_it_pays(self, customer):
        hub = customer()
        invoiced(hub, on=date(2026, 7, 10), net=2900)
        invoiced(hub, on=date(2026, 8, 10), net=3900, payment="open")
        invoiced(hub, on=date(2026, 8, 12), net=-2900, kind="credit_note")

        assert queries.monthly_cents(listed()[hub.name]) == 2900

    def test_without_a_collected_invoice_it_is_not_known(self, customer):
        hub = customer(status="trialing")

        assert queries.monthly_cents(listed()[hub.name]) is None

    def test_another_business_invoices_are_not_its(self, customer):
        hub = customer()
        other = customer()
        invoiced(hub, net=2900)
        invoiced(other, net=9900, on=date(2026, 8, 20))

        rows = listed()

        assert queries.monthly_cents(rows[hub.name]) == 2900
        assert queries.monthly_cents(rows[other.name]) == 9900


class TestCustomerSince:
    def test_it_is_the_date_of_its_first_collected_invoice(self, customer):
        hub = customer()
        invoiced(hub, on=date(2026, 3, 1), payment="open")
        invoiced(hub, on=date(2026, 2, 1), net=-2900, kind="credit_note")
        invoiced(hub, on=date(2026, 5, 10))
        invoiced(hub, on=date(2026, 4, 10))
        invoiced(hub, on=date(2026, 6, 10))

        assert listed()[hub.name].customer_since == date(2026, 4, 10)

    def test_without_a_collected_invoice_it_is_not_known(self, customer):
        hub = customer(status="trialing")

        assert listed()[hub.name].customer_since is None


class TestTheKindOfCustomer:
    @pytest.mark.parametrize(
        ("country", "tax_id", "kind"),
        [("ES", "B12345678", "company"), ("ES", "12345678Z", "self_employed"), ("ES", "", "individual"),
         ("PT", "PT123456789", "company")],
    )
    def test_it_is_told_from_its_payers_tax_id_as_in_the_billing_report(self, customer, country, tax_id, kind):
        hub = customer(country=country, tax_id=tax_id)

        assert queries.paying_customer_kind(listed()[hub.name]) == kind


def rows_of(document, delimiter):
    return list(csv.reader(io.StringIO(document["content"].decode("utf-8-sig")), delimiter=delimiter))


class TestTheExcel:
    """One row per paying customer with the list's columns, in the billing report's format: UTF-8 with its BOM, the
    separator and the decimals of the language."""

    def test_one_row_per_customer_with_the_lists_columns(self, customer):
        hub = customer(interval="year", tax_id="B12345678", payer="Panadería López SL")
        invoiced(hub, on=date(2026, 4, 10), net=29000)
        trial = customer(plan="standard", status="trialing")

        document = queries.paying_customers_csv(queries.paying_customers(), "en")
        header, *rows = rows_of(document, ",")

        assert document["content"].startswith("﻿".encode())
        assert document["content_type"] == "text/csv; charset=utf-8"
        assert document["filename"].startswith("erplora-paying-customers-") and document["filename"].endswith(".csv")
        assert header == ["Business", "Payer", "Country", "Customer", "Plan", "Billing frequency", "Monthly tax base (€)",
                          "Customer since", "Status"]
        assert rows == [
            [hub.name, "Panadería López SL", "ES", "Company", "Starter", "Annual", "24.17", "2026-04-10", "Active"],
            [trial.name, "Payer SL", "ES", "Individual without a tax ID", "Standard", "Monthly", "", "", "Trial"],
        ]

    def test_in_spanish_semicolons_and_a_decimal_comma(self, customer):
        hub = customer(interval="year")
        invoiced(hub, net=29000)

        header, row = rows_of(queries.paying_customers_csv(queries.paying_customers(), "es"), ";")

        assert header[:2] == ["Negocio", "Pagador"]
        assert row[5:7] == ["Anual", "24,17"]

    def test_a_payer_that_looks_like_a_formula_is_text(self, customer):
        customer(payer='=HYPERLINK("http://evil.example","x")')

        _, row = rows_of(queries.paying_customers_csv(queries.paying_customers(), "en"), ",")

        assert row[1] == "'=HYPERLINK(\"http://evil.example\",\"x\")"

    def test_a_business_that_looks_like_a_formula_is_text(self, customer):
        hub = customer()
        hub.name = "=1+1"
        hub.save()

        _, row = rows_of(queries.paying_customers_csv(queries.paying_customers(), "en"), ",")

        assert row[0] == "'=1+1"


class TestTheAdminList:
    def test_it_lists_the_paying_customers_with_their_columns(self, staff_client, customer):
        hub = customer(interval="year", payer="Panadería López SL")
        invoiced(hub, on=date(2026, 4, 10), net=29000)
        customer(status="canceled", payer="Gone SL")

        response = staff_client.get(LIST)

        assert response.status_code == 200
        body = response.content.decode()
        assert hub.name in body and "Panadería López SL" in body and "Gone SL" not in body
        assert "24.17" in body and "Annual" in body and "Individual without a tax ID" in body

    def test_the_admin_index_offers_it_under_billing(self, staff_client):
        assert LIST in staff_client.get("/admin/").content.decode()

    def test_it_filters_by_country_offering_only_the_countries_it_has(self, staff_client, customer):
        spain = customer(payer="Madrid SL")
        portugal = customer(country="PT", payer="Lisboa Lda")

        response = staff_client.get(LIST, {"country": "PT"})

        body = response.content.decode()
        assert portugal.name in body and spain.name not in body
        assert "Portugal" in body and "Spain" in body and "France" not in body

    def test_it_filters_by_status_offering_only_the_statuses_it_has(self, staff_client, customer):
        active = customer()
        trialing = customer(status="trialing")

        response = staff_client.get(LIST, {"status": "trialing"})

        assert [row.hub.name for row in response.context["cl"].result_list] == [trialing.name]
        assert active.name not in response.content.decode()
        status = next(spec for spec in response.context["cl"].filter_specs if spec.parameter_name == "status")
        offered = [value for value, _label in status.lookup_choices]
        assert offered == ["active", "trialing"]

    def test_its_filters_do_not_offer_what_only_an_ended_subscription_has(self, staff_client, customer):
        customer()
        customer(status="canceled", country="PT")

        specs = staff_client.get(LIST).context["cl"].filter_specs

        offered = {getattr(spec, "parameter_name", ""): [value for value, _label in spec.lookup_choices]
                   for spec in specs}
        assert offered["status"] == ["active"]
        assert offered["country"] == ["ES"]

    def test_it_filters_by_plan(self, staff_client, customer):
        from hubs.models import Plan

        customer()
        standard = customer(plan="standard")

        response = staff_client.get(LIST, {"plan__id__exact": str(Plan.objects.get(slug="standard").pk)})

        assert [row.hub.name for row in response.context["cl"].result_list] == [standard.name]

    def test_it_links_the_excel_of_what_it_shows(self, staff_client, customer):
        customer()

        body = staff_client.get(LIST, {"country": "ES"}).content.decode()

        assert f"{EXCEL}?country=ES" in body

    def test_in_spanish_it_speaks_spanish(self, staff_client, customer):
        hub = customer(interval="year")
        invoiced(hub, net=29000)

        body = staff_client.get(LIST, HTTP_ACCEPT_LANGUAGE="es").content.decode()

        assert "Clientes de pago" in body and "Cliente desde" in body and "Descargar Excel" in body
        assert "24,17" in body


class TestTheAdminExcel:
    def test_it_downloads_what_the_list_shows(self, staff_client, customer):
        spain = customer(payer="Madrid SL")
        portugal = customer(country="PT", payer="Lisboa Lda")

        response = staff_client.get(EXCEL, {"country": "PT"})

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"].startswith('attachment; filename="erplora-paying-customers-')
        text = response.content.decode("utf-8-sig")
        assert portugal.name in text and spain.name not in text

    def test_in_spanish_the_excel_is_the_spanish_one(self, staff_client, customer):
        hub = customer(interval="year")
        invoiced(hub, net=29000)

        text = staff_client.get(EXCEL, HTTP_ACCEPT_LANGUAGE="es").content.decode("utf-8-sig")

        assert text.startswith("Negocio;Pagador;") and ";Anual;24,17;" in text

    def test_a_filter_it_does_not_know_goes_back_to_the_list(self, staff_client, customer):
        customer()

        response = staff_client.get(EXCEL, {"nonsense": "1"})

        assert response.status_code == 302
        assert response["Location"].startswith(LIST)


class TestWhoSeesIt:
    def test_a_reader_of_subscriptions_sees_and_downloads_it(self, client, customer):
        hub = customer()
        client.force_login(staff_with("view_subscription"))

        assert hub.name in client.get(LIST).content.decode()
        assert client.get(EXCEL).status_code == 200
        assert LIST in client.get("/admin/").content.decode()

    def test_staff_who_may_not_read_subscriptions_does_not(self, client, customer):
        customer()
        client.force_login(staff_with("view_invoice"))

        assert client.get(LIST).status_code == 403
        assert client.get(EXCEL).status_code == 403
        assert LIST not in client.get("/admin/").content.decode()

    def test_nothing_is_added_changed_or_deleted_here(self, staff_client, customer):
        hub = customer()

        body = staff_client.get(LIST).content.decode()

        assert f"{LIST}add/" not in body
        assert staff_client.get(f"{LIST}add/").status_code == 403
        assert staff_client.post(LIST, {"action": "delete_selected", "_selected_action": [str(hub.subscription.pk)]}
                                 ).status_code in (200, 302)
        from hubs.models import Subscription

        assert Subscription.objects.filter(hub=hub).exists()
