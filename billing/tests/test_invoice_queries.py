"""Billing → Invoices: ERPlora's invoices of the account's businesses (lot L3-C; round 17 §2.7).

Ported from ERPlora/saas ``apps/dashboard/billing/tests/`` (origin/develop): ``test_api.TestInvoiceAPI`` (the
list is the account's own, filtered by status; another account's invoice is a 404; the PDF), ``test_hub_filter``
(the per-business filter, only among the account's businesses), ``test_views`` (the invoices page and the
CSV export of the datatable, as operations now) and ``test_money_json_shape`` (amounts in integer cents).

Who sees an invoice: the account that paid it (its payer that day, ``payer_account``) and the current owner
of its business; nobody else, whatever their role (a 404, never a hint). The row's actions are the server's:
«Pay» for one not collected (enabled for its payer, unless the bank declined the card), «PDF» once the
platform hub issued it. Dropped: staff downloading any invoice (the admin is where staff work), the
``invoice_type`` filter and the vendor's earnings.
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from live.errors import Conflict, NotFound, OperationError, Unauthorized

from billing import queries, services
from billing.models import Invoice, InvoiceLine, PaymentFailure
from billing.schemas import InvoiceByIdIn, InvoiceFilterIn, InvoiceListIn, InvoicePayIn
from billing.tests.conftest import ctx_for, pay
from hubs.models import BillingProfile, HubMember
from hubs.tests.conftest import add_member, create_business

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
PDF = b"%PDF-1.7\n% ERPlora test\n%%EOF\n"


@pytest.fixture
def business(owner, plans):
    return create_business(owner, name="Panadería López")


def issue(
    hub,
    sequence,
    *,
    on=date(2026, 10, 1),
    status="paid",
    fiscal_status="accepted",
    total=3629,
    tax=630,
    payer=None,
    **fields,
) -> Invoice:
    paid = status == "paid"
    invoice = Invoice.objects.create(
        stripe_invoice_id=f"in_{hub.slug}_{sequence}",
        hub=hub,
        business_name=hub.name,
        billing_profile=hub.billing_profile,
        payer_account=payer if payer is not None else hub.billing_profile.owner,
        payment_status=status,
        series="ERP" if paid else "",
        sequence=sequence if paid else None,
        number=f"ERP-{on.year}-{sequence:05d}" if paid else "",
        issued_on=on if paid else None,
        billed_at=timezone.make_aware(timezone.datetime(on.year, on.month, on.day, 9)),
        stripe_number=f"ABCD-{sequence:04d}",
        hosted_invoice_url=f"https://invoice.stripe.com/i/{hub.slug}_{sequence}",
        net_cents=total - tax,
        tax_cents=tax,
        total_cents=total,
        tax_rate=Decimal("21.00"),
        tax_country="ES",
        fiscal_status=fiscal_status if paid else "",
        payer_name="Panadería López SL",
        payer_country="ES",
        **fields,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        position=1,
        description="1 × Starter",
        item_kind="plan",
        item_slug="starter",
        tax_rate=Decimal("21.00"),
        net_cents=total - tax,
        tax_cents=tax,
        total_cents=total,
    )
    return invoice


def listing(user, language="en", **filters) -> dict:
    return queries.invoice_list(
        ctx_for(user, language), InvoiceListIn(**filters)
    ).model_dump(mode="json")


def numbers(result) -> list:
    return [row["number"] or row["reference"] for row in result["rows"]]


class TestWhoSeesWhat:
    def test_a_visitor_sees_nothing(self, business):
        issue(business, 1)

        response = Client().get("/api/billing/invoices", HTTP_HOST=HOST)

        assert (response.status_code, response.json()["error"]["code"]) == (
            401,
            "unauthorized",
        )

    def test_without_an_account_the_operation_refuses(self):
        from live.context import OperationContext, Scope

        signed_out = OperationContext(
            scope=Scope("user", "anonymous"), actor=None, permissions={"billing.view"}
        )

        with pytest.raises(Unauthorized):
            queries.invoice_list(signed_out, InvoiceListIn())

    def test_the_owner_sees_the_invoices_of_their_businesses(self, owner, business):
        issue(business, 1)

        assert numbers(listing(owner)) == ["ERP-2026-00001"]

    def test_another_account_sees_none(self, business, make_user):
        issue(business, 1)

        assert listing(make_user("other@example.com"))["total"] == 0

    @pytest.mark.parametrize(
        "role", [HubMember.Role.ADMIN, HubMember.Role.MANAGER, HubMember.Role.EMPLOYEE]
    )
    def test_a_member_who_neither_owns_nor_pays_sees_none(
        self, business, make_user, role
    ):
        member = make_user("team@example.com")
        add_member(business, member, role)
        issue(business, 1)

        assert listing(member)["total"] == 0

    def test_the_payer_keeps_seeing_what_it_paid_after_a_transfer(
        self, owner, business, make_user
    ):
        issue(business, 1)
        new_owner = make_user("new@example.com")
        HubMember.objects.filter(hub=business, user=owner).update(
            role=HubMember.Role.ADMIN
        )
        add_member(business, new_owner, HubMember.Role.OWNER)

        assert numbers(listing(owner)) == ["ERP-2026-00001"]
        assert numbers(listing(new_owner)) == ["ERP-2026-00001"]

    def test_another_accounts_invoice_is_not_found(self, business, make_user):
        invoice = issue(business, 1)

        with pytest.raises(NotFound):
            queries.invoice_get(
                ctx_for(make_user("other@example.com")), InvoiceByIdIn(id=invoice.id)
            )


class TestTheList:
    def test_the_newest_first(self, owner, business):
        issue(business, 1, on=date(2026, 8, 1))
        issue(business, 3, on=date(2026, 10, 1))
        issue(business, 2, on=date(2026, 9, 1))

        assert numbers(listing(owner)) == [
            "ERP-2026-00003",
            "ERP-2026-00002",
            "ERP-2026-00001",
        ]

    def test_one_not_collected_has_no_number_yet(self, owner, business):
        issue(business, 7, status="open")

        [row] = listing(owner)["rows"]
        assert (row["number"], row["reference"], row["payment_status"]) == (
            None,
            "ABCD-0007",
            "open",
        )
        assert row["date"] == "2026-10-01"

    def test_the_amounts_are_integer_cents(self, owner, business):
        issue(business, 1)

        [row] = listing(owner)["rows"]
        assert (
            row["net_cents"],
            row["tax_cents"],
            row["total_cents"],
            row["currency"],
        ) == (2999, 630, 3629, "EUR")

    def test_the_labels_speak_the_accounts_language(self, owner, business):
        issue(business, 1)
        issue(business, 2, status="open")

        labels = {
            row["payment_status"]: row["payment_status_label"]
            for row in listing(owner, "es")["rows"]
        }
        assert labels == {"paid": "Pagada", "open": "No cobrada"}

    def test_the_business_name_is_the_one_on_the_invoice(self, owner, business):
        issue(business, 1)
        business.name = "Panadería Nueva"
        business.save()

        assert listing(owner)["rows"][0]["business"] == {
            "id": str(business.id),
            "name": "Panadería López",
        }

    def test_it_pages(self, owner, business):
        for sequence in range(1, 6):
            issue(business, sequence, on=date(2026, 1, sequence))

        page = listing(owner, limit=2, offset=2)
        assert (page["total"], page["limit"], page["offset"]) == (5, 2, 2)
        assert numbers(page) == ["ERP-2026-00003", "ERP-2026-00002"]


class TestTheFilters:
    def test_by_business_among_the_accounts(self, owner, business, plans):
        pay(business)
        other = create_business(owner, name="Bar Norte")
        issue(business, 1)
        issue(other, 2)

        assert numbers(listing(owner, hub_id=other.id)) == ["ERP-2026-00002"]

    def test_a_business_that_is_not_the_accounts_shows_nothing(
        self, owner, business, make_user, plans
    ):
        stranger = create_business(make_user("stranger@example.com"), name="Ajeno")
        issue(stranger, 9)
        issue(business, 1)

        assert listing(owner, hub_id=stranger.id)["total"] == 0

    def test_by_payment(self, owner, business):
        issue(business, 1)
        issue(business, 2, status="open")

        assert numbers(listing(owner, status="open")) == ["ABCD-0002"]
        assert numbers(listing(owner, status="paid")) == ["ERP-2026-00001"]

    def test_by_year(self, owner, business):
        issue(business, 1, on=date(2025, 12, 31))
        issue(business, 2, on=date(2026, 1, 1))

        assert numbers(listing(owner, year=2025)) == ["ERP-2025-00001"]

    def test_by_number(self, owner, business):
        issue(business, 117)
        issue(business, 119)

        assert numbers(listing(owner, search="0119")) == ["ERP-2026-00119"]


class TestTheRowActions:
    def row(self, owner, **fields):
        return listing(owner)["rows"][0]

    def test_an_accepted_invoice_downloads_its_pdf(self, owner, business):
        issue(business, 1, fiscal_status="accepted")

        row = listing(owner)["rows"][0]
        assert (row["actions"], row["can"]) == (["pdf"], {"pay": False, "pdf": True})

    @pytest.mark.parametrize("fiscal_status", ["issuing", "rejected"])
    def test_one_not_issued_has_no_pdf_yet(self, owner, business, fiscal_status):
        issue(business, 1, fiscal_status=fiscal_status)

        row = listing(owner)["rows"][0]
        assert (row["actions"], row["can"]["pdf"]) == ([], False)
        assert row["fiscal_status"] == fiscal_status

    def test_one_not_collected_is_paid_by_its_payer(self, owner, business):
        issue(business, 1, status="open")

        row = listing(owner)["rows"][0]
        assert (row["actions"], row["can"], row["pay_blocked_reason"]) == (
            ["pay"],
            {"pay": True, "pdf": False},
            None,
        )

    def test_with_the_card_declined_pay_waits_for_another_card(self, owner, business):
        invoice = issue(business, 1, status="open")
        failure = PaymentFailure.objects.create(
            hub=business,
            stripe_invoice_id=invoice.stripe_invoice_id,
            reason="card_declined",
            payment_method_id="pm_old",
            invoice_created_at=timezone.now(),
        )

        row = listing(owner)["rows"][0]
        assert (row["can"]["pay"], row["pay_blocked_reason"]) == (
            False,
            "card_change_required",
        )

        PaymentFailure.objects.filter(pk=failure.pk).update(
            card_changed_at=timezone.now()
        )
        assert listing(owner)["rows"][0]["can"]["pay"] is True

    def test_an_owner_who_does_not_pay_cannot_pay(self, owner, business, make_user):
        invoice = issue(business, 1, status="open")
        new_payer = make_user("payer@example.com")
        BillingProfile.objects.filter(pk=business.billing_profile_id).update(
            owner=new_payer
        )
        Invoice.objects.filter(pk=invoice.pk).update(payer_account=new_payer)

        row = listing(owner)["rows"][0]
        assert (row["can"]["pay"], row["pay_blocked_reason"]) == (
            False,
            "payer_required",
        )


class TestTheDetail:
    def test_it_carries_the_lines_the_recipient_and_the_qr(self, owner, business):
        invoice = issue(business, 1, qr="https://aeat.example/qr")

        detail = queries.invoice_get(
            ctx_for(owner), InvoiceByIdIn(id=invoice.id)
        ).model_dump(mode="json")

        assert detail["number"] == "ERP-2026-00001"
        assert detail["recipient"]["name"] == "Panadería López SL"
        assert [line["item_slug"] for line in detail["lines"]] == ["starter"]
        assert detail["qr"] == "https://aeat.example/qr"
        assert detail["rectifies"] is None

    def test_a_credit_note_names_what_it_rectifies(self, owner, business):
        original = issue(business, 1)
        credit = Invoice.objects.create(
            kind="credit_note",
            rectifies=original,
            stripe_invoice_id=original.stripe_invoice_id,
            stripe_source_id="cn_1",
            hub=business,
            business_name=business.name,
            payer_account=owner,
            payment_status="paid",
            series="ERPR",
            sequence=1,
            number="ERPR-2026-00001",
            issued_on=date(2026, 10, 2),
            net_cents=-2999,
            tax_cents=-630,
            total_cents=-3629,
        )

        detail = queries.invoice_get(
            ctx_for(owner, "es"), InvoiceByIdIn(id=credit.id)
        ).model_dump(mode="json")

        assert detail["rectifies"] == {
            "id": str(original.id),
            "number": "ERP-2026-00001",
        }
        assert (detail["kind"], detail["kind_label"]) == (
            "credit_note",
            "Factura rectificativa",
        )



class TestTheRectification:
    """A credit note says which kind of rectifying invoice it is (VeriFactu's ``TipoFactura`` R1–R4) and
    why, in the list and in the detail, with the Stripe object it came from (``cn_…``, ``re_…``)."""

    def credit_note(self, owner, business, original, **fields) -> Invoice:
        return Invoice.objects.create(
            kind="credit_note",
            rectifies=original,
            stripe_invoice_id=original.stripe_invoice_id,
            hub=business,
            business_name=business.name,
            payer_account=owner,
            payment_status="paid",
            series="ERPR",
            sequence=1,
            number="ERPR-2026-00001",
            issued_on=date(2026, 10, 2),
            net_cents=-2999,
            tax_cents=-630,
            total_cents=-3629,
            **fields,
        )

    def test_an_invoice_rectifies_nothing(self, owner, business):
        invoice = issue(business, 1)

        row = listing(owner)["rows"][0]
        detail = queries.invoice_get(ctx_for(owner), InvoiceByIdIn(id=invoice.id)).model_dump(mode="json")

        assert (row["rectification"], row["stripe_source_id"]) == (None, "")
        assert (detail["rectification"], detail["stripe_source_id"]) == (None, "")

    def test_a_credit_note_carries_its_type_its_reason_and_its_source(self, owner, business):
        original = issue(business, 1)
        credit = self.credit_note(
            owner,
            business,
            original,
            stripe_source_id="cn_1",
            rectification_type="R1",
            rectification_reason="Duplicate charge",
        )

        row = next(r for r in listing(owner)["rows"] if r["id"] == str(credit.id))
        detail = queries.invoice_get(ctx_for(owner), InvoiceByIdIn(id=credit.id)).model_dump(mode="json")

        expected = ({"type": "R1", "reason": "Duplicate charge"}, "cn_1")
        assert (row["rectification"], row["stripe_source_id"]) == expected
        assert (detail["rectification"], detail["stripe_source_id"]) == expected

    def test_a_credit_note_without_a_reason_keeps_its_type(self, owner, business):
        original = issue(business, 1)
        self.credit_note(owner, business, original, stripe_source_id="re_1", rectification_type="R4")

        row = next(r for r in listing(owner)["rows"] if r["kind"] == "credit_note")

        assert (row["rectification"], row["stripe_source_id"]) == ({"type": "R4", "reason": ""}, "re_1")

    def test_the_route_answers_it(self, owner, business):
        original = issue(business, 1)
        self.credit_note(
            owner, business, original, stripe_source_id="cn_1", rectification_type="R1", rectification_reason="Refund"
        )
        client = Client()
        client.force_login(owner)

        rows = client.get("/api/billing/invoices", HTTP_HOST=HOST).json()["rows"]

        assert [(r["kind"], r["rectification"], r["stripe_source_id"]) for r in rows] == [
            ("credit_note", {"type": "R1", "reason": "Refund"}, "cn_1"),
            ("invoice", None, ""),
        ]


class TestThePdf:
    def pdf(self, user, invoice):
        return queries.invoice_pdf(ctx_for(user), InvoiceByIdIn(id=invoice.id))

    def test_it_is_the_platform_hubs_once_issued(self, owner, business, monkeypatch):
        from hubs import hub_client

        asked = []
        monkeypatch.setattr(
            hub_client,
            "get_platform_invoice_pdf",
            lambda invoice_id: asked.append(invoice_id) or PDF,
        )
        invoice = issue(business, 1)

        document = self.pdf(owner, invoice)

        assert (document.filename, document.content_type, document.content) == (
            "ERP-2026-00001.pdf",
            "application/pdf",
            PDF,
        )
        assert asked == [str(invoice.id)]

    @pytest.mark.parametrize(
        "fields",
        [
            {"fiscal_status": "issuing"},
            {"fiscal_status": "rejected"},
            {"status": "open"},
        ],
    )
    def test_not_found_until_it_is_issued(self, owner, business, fields):
        invoice = issue(business, 1, **fields)

        with pytest.raises(NotFound) as error:
            self.pdf(owner, invoice)

        assert error.value.code == "billing.invoice_not_issued"

    def test_the_hub_away_is_a_503(self, owner, business, offline_hub):
        invoice = issue(business, 1)

        with pytest.raises(OperationError) as error:
            self.pdf(owner, invoice)

        assert (error.value.status, error.value.code) == (
            503,
            "billing.platform_unavailable",
        )

    def test_the_route_answers_the_file(self, owner, business, monkeypatch):
        from hubs import hub_client

        monkeypatch.setattr(
            hub_client, "get_platform_invoice_pdf", lambda invoice_id: PDF
        )
        invoice = issue(business, 1)
        client = Client()
        client.force_login(owner)

        response = client.get(
            f"/api/billing/invoices/pdf?id={invoice.id}", HTTP_HOST=HOST
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert (
            response["Content-Disposition"]
            == 'attachment; filename="ERP-2026-00001.pdf"'
        )
        assert response.content == PDF


class TestTheCsv:
    def export(self, user, language="en", **filters):
        return queries.invoice_csv(ctx_for(user, language), InvoiceFilterIn(**filters))

    def rows(self, document, delimiter):
        text = document.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text), delimiter=delimiter))

    def test_it_opens_in_excel_with_its_accents(self, owner, business):
        """UTF-8 with its BOM: without it Excel reads «Panadería» as «PanaderÃ­a» (W-F9, «Download Excel»)."""
        issue(business, 1)

        document = self.export(owner)

        assert document.content.startswith("﻿".encode())
        assert document.content_type == "text/csv; charset=utf-8"
        assert (
            document.filename
            == f"erplora-invoices-{timezone.localdate().isoformat()}.csv"
        )
        assert "Panadería López" in document.content.decode("utf-8-sig")

    def test_in_english_comma_separated_with_a_decimal_point(self, owner, business):
        issue(business, 1)

        header, row = self.rows(self.export(owner), ",")

        assert header == [
            "Invoice",
            "Date",
            "Business",
            "Tax base",
            "VAT",
            "Total",
            "Currency",
            "Payment",
            "Status",
        ]
        assert row == [
            "ERP-2026-00001",
            "2026-10-01",
            "Panadería López",
            "29.99",
            "6.30",
            "36.29",
            "EUR",
            "Paid",
            "Accepted",
        ]

    def test_in_spanish_semicolons_and_a_decimal_comma_as_excel_expects(
        self, owner, business
    ):
        issue(business, 1)

        header, row = self.rows(self.export(owner, "es"), ";")

        assert header[0] == "Factura"
        assert row[3:6] == ["29,99", "6,30", "36,29"]

    def test_it_exports_what_the_filters_show_without_pages(
        self, owner, business, plans
    ):
        pay(business)
        other = create_business(owner, name="Bar Norte")
        for sequence in range(1, 61):
            issue(business, sequence)
        issue(other, 99)

        rows = self.rows(self.export(owner, hub_id=business.id), ",")

        assert len(rows) == 61
        assert "Bar Norte" not in {row[2] for row in rows}

    def test_only_the_accounts_invoices(self, business, make_user):
        issue(business, 1)

        assert len(self.rows(self.export(make_user("other@example.com")), ",")) == 1


class TestTheCsvIsNotAFormula:
    """Review of L3-C (CSV injection, OWASP): a business called «=HYPERLINK(…)» must not run in the accountant's
    Excel. A text cell that starts with ``= + - @`` (or a tab or carriage return) is prefixed with ``'``;
    amounts are numbers, a negative one stays a number."""

    def test_a_name_that_looks_like_a_formula_is_text(self, owner, business):
        first, second = issue(business, 1), issue(business, 2, total=-3629, tax=-630)
        Invoice.objects.filter(pk=first.pk).update(business_name='=HYPERLINK("http://evil.example","x")')
        Invoice.objects.filter(pk=second.pk).update(business_name="@SUM(1+1)")

        rows = list(csv.reader(io.StringIO(
            queries.invoice_csv(ctx_for(owner), InvoiceFilterIn()).content.decode("utf-8-sig"))))

        names = {row[2] for row in rows[1:]}
        assert names == {"'=HYPERLINK(\"http://evil.example\",\"x\")", "'@SUM(1+1)"}
        assert {row[5] for row in rows[1:]} == {"36.29", "-36.29"}


class TestPay:
    def pay(self, user, invoice):
        return services.invoice_pay(ctx_for(user), InvoicePayIn(id=invoice.id))

    def test_the_payer_gets_stripes_page(self, owner, business):
        invoice = issue(business, 1, status="open")

        assert self.pay(owner, invoice).url == invoice.hosted_invoice_url

    def test_a_declined_card_must_change_first(self, owner, business):
        invoice = issue(business, 1, status="open")
        PaymentFailure.objects.create(
            hub=business,
            stripe_invoice_id=invoice.stripe_invoice_id,
            reason="card_declined",
            payment_method_id="pm_old",
            invoice_created_at=timezone.now(),
        )

        with pytest.raises(Conflict) as error:
            self.pay(owner, invoice)

        assert error.value.code == "billing.card_change_required"

    def test_a_paid_invoice_has_nothing_to_pay(self, owner, business):
        with pytest.raises(Conflict) as error:
            self.pay(owner, issue(business, 1))

        assert error.value.code == "billing.invoice_paid"

    def test_only_its_payer_pays_it(self, owner, business, make_user):
        invoice = issue(business, 1, status="open")
        BillingProfile.objects.filter(pk=business.billing_profile_id).update(
            owner=make_user("payer@example.com")
        )

        with pytest.raises(Conflict) as error:
            self.pay(owner, invoice)

        assert error.value.code == "billing.payer_required"

    def test_another_account_does_not_find_it(self, business, make_user):
        with pytest.raises(NotFound):
            self.pay(make_user("other@example.com"), issue(business, 1, status="open"))


@pytest.mark.parametrize(
    ("moment", "billed_on"),
    [
        # A week after summer time ends: billed at 00:42 summer time, looked at 23:42 winter time.
        (datetime(2026, 10, 28, 22, 42, tzinfo=UTC), "2026-10-22"),
        (datetime(2026, 10, 28, 23, 10, tzinfo=UTC), "2026-10-22"),
        # A week after it starts: billed at 23:30 winter time, looked at 00:30 summer time.
        (datetime(2026, 4, 1, 22, 30, tzinfo=UTC), "2026-03-25"),
    ],
)
def test_a_week_old_open_invoice_keeps_its_date(owner, business, monkeypatch, moment, billed_on):
    """An open invoice is dated the day it was billed in the SaaS's zone (Europe/Madrid), whatever the clock
    says now: «today minus seven days» is a day off for an hour a night during the week after a clock change
    (saas#148's CI, 22:42Z on 2026-10-28)."""
    monkeypatch.setattr(timezone, "now", lambda: moment)
    invoice = issue(business, 1, status="open")
    Invoice.objects.filter(pk=invoice.pk).update(billed_at=moment - timedelta(days=7))

    assert listing(owner)["rows"][0]["date"] == billed_on


class TestAnApiKey:
    """An account's key with ``billing.read`` («Invoices · read», ``accounts.models.API_KEY_SCOPES``) reads the
    account's invoices, as the account; without the scope it reads nothing."""

    def key(self, user, *scopes):
        from accounts.models import ApiKey

        secret, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=user, name="gestoría", prefix=prefix, key_hash=key_hash, scopes=list(scopes))
        return secret

    def get(self, path, secret, **params):
        return Client(enforce_csrf_checks=True).get(
            f"/api{path}", params, HTTP_HOST=HOST, HTTP_AUTHORIZATION=f"Bearer {secret}"
        )

    def test_billing_read_lists_the_accounts_invoices(self, owner, business):
        issue(business, 1)

        response = self.get("/billing/invoices", self.key(owner, "billing.read"))

        assert response.status_code == 200
        assert [row["number"] for row in response.json()["rows"]] == ["ERP-2026-00001"]

    def test_without_the_scope_it_reads_nothing(self, owner, business):
        issue(business, 1)

        response = self.get("/billing/invoices", self.key(owner, "hubs.read"))

        assert (response.status_code, response.json()["error"]["code"]) == (403, "api_key_missing_scope")

    def test_it_never_pays(self, owner, business):
        invoice = issue(business, 1, status="open")

        response = Client(enforce_csrf_checks=True).post(
            "/api/billing/invoices/pay", {"id": str(invoice.id)}, content_type="application/json", HTTP_HOST=HOST,
            HTTP_AUTHORIZATION=f"Bearer {self.key(owner, 'billing.read')}",
        )

        assert response.status_code in (401, 403)
