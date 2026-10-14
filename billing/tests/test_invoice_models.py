"""ERPlora's invoices to its customers, as rows (lot L3-C): ``billing.Invoice`` and ``billing.InvoiceLine``.

Ported from ERPlora/saas ``apps/dashboard/billing/tests/`` (origin/develop): ``test_invoice_money_cents``
(integer cents, the euro is a read-only view, the header is the exact sum of the lines),
``test_invoice_dedup`` (one invoice per Stripe invoice, enforced by the database), ``test_money_contract``
(EUR by default) and ``test_hub_invoices.TestInvoiceModel``; and from ``fiscal/tests/test_vies_contract.py``
the decision half of «The note never lies» (the sentence itself is printed by the platform hub's PDF).

Dropped, with their reason: the admin typing euros into an editable invoice (an invoice here is never
edited: it is recorded from what Stripe charged and issued by the platform hub), the ``invoice_type``
column (one kind of sale: a business's subscription; a credit note is its own ``kind``) and the money
migrations of the old columns (this model is born in cents).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, models, transaction

from billing.models import Invoice, InvoiceLine

pytestmark = pytest.mark.django_db


def make_invoice(**fields) -> Invoice:
    values = {
        "stripe_invoice_id": "in_1",
        "business_name": "Panadería López",
        "payment_status": Invoice.PaymentStatus.PAID,
        "series": "ERP",
        "sequence": 1,
        "number": "ERP-2026-00001",
        "issued_on": date(2026, 10, 1),
        "net_cents": 2999,
        "tax_cents": 630,
        "total_cents": 3629,
        "tax_rate": Decimal("21.00"),
        "tax_country": "ES",
        "payer_country": "ES",
    }
    values.update(fields)
    return Invoice.objects.create(**values)


class TestTheMoneyIsIntegerCents:
    def test_every_money_column_is_an_integer_field(self):
        for model in (Invoice, InvoiceLine):
            money = [
                field
                for field in model._meta.concrete_fields
                if field.name.endswith("_cents")
            ]
            assert money, model
            assert all(isinstance(field, models.BigIntegerField) for field in money), (
                model
            )
            assert not any(
                isinstance(field, models.DecimalField) and field.name != "tax_rate"
                for field in model._meta.concrete_fields
            ), model

    @pytest.mark.parametrize(
        "cents, euros", [(3629, "36.29"), (1, "0.01"), (-2999, "-29.99"), (0, "0.00")]
    )
    def test_the_euro_view_is_the_exact_decimal_of_the_cents(self, cents, euros):
        invoice = make_invoice(net_cents=cents, tax_cents=0, total_cents=cents)

        assert invoice.total == Decimal(euros)
        assert invoice.net == Decimal(euros)

    @pytest.mark.parametrize("name", ["net", "tax", "total"])
    def test_the_euro_properties_are_read_only(self, name):
        invoice = make_invoice()

        with pytest.raises(AttributeError):
            setattr(invoice, name, Decimal("1.00"))

    def test_the_currency_is_the_euro_by_default(self):
        assert make_invoice().currency == "EUR"


class TestTheDatabaseKeepsTheBooks:
    def test_the_same_stripe_invoice_cannot_be_invoiced_twice(self):
        make_invoice()

        with pytest.raises(IntegrityError), transaction.atomic():
            make_invoice(sequence=2, number="ERP-2026-00002")

    def test_a_credit_note_of_that_stripe_invoice_is_another_document(self):
        original = make_invoice()

        make_invoice(
            kind=Invoice.Kind.CREDIT_NOTE,
            rectifies=original,
            stripe_source_id="cn_1",
            series="ERPR",
            number="ERPR-2026-00001",
            net_cents=-2999,
            tax_cents=-630,
            total_cents=-3629,
        )

        assert Invoice.objects.filter(stripe_invoice_id="in_1").count() == 2

    def test_the_same_stripe_credit_note_cannot_be_recorded_twice(self):
        original = make_invoice()
        credit = {
            "kind": Invoice.Kind.CREDIT_NOTE,
            "rectifies": original,
            "stripe_source_id": "cn_1",
            "series": "ERPR",
        }
        make_invoice(number="ERPR-2026-00001", **credit)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_invoice(number="ERPR-2026-00002", sequence=2, **credit)

    def test_a_number_is_given_once(self):
        make_invoice()

        with pytest.raises(IntegrityError), transaction.atomic():
            make_invoice(stripe_invoice_id="in_2")

    def test_invoices_not_numbered_yet_do_not_collide(self):
        """An unpaid Stripe invoice is listed («Not collected») before it has a number: many can wait."""
        unpaid = {
            "payment_status": Invoice.PaymentStatus.OPEN,
            "series": "",
            "sequence": None,
            "number": "",
            "issued_on": None,
        }
        make_invoice(stripe_invoice_id="in_1", **unpaid)
        make_invoice(stripe_invoice_id="in_2", **unpaid)

    def test_a_paid_invoice_always_has_its_number(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            make_invoice(series="", sequence=None, number="", issued_on=None)

    def test_an_unpaid_invoice_has_no_number_yet(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            make_invoice(payment_status=Invoice.PaymentStatus.OPEN)

    def test_the_total_is_the_base_plus_the_quota(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            make_invoice(net_cents=2999, tax_cents=630, total_cents=3630)

    def test_a_line_adds_up_too(self):
        invoice = make_invoice()

        with pytest.raises(IntegrityError), transaction.atomic():
            InvoiceLine.objects.create(
                invoice=invoice,
                position=1,
                description="Starter",
                net_cents=2999,
                tax_cents=630,
                total_cents=3628,
            )

    def test_lookups_by_stripe_invoice_hit_an_index(self):
        indexed = {tuple(index.fields) for index in Invoice._meta.indexes}

        assert ("stripe_invoice_id",) in indexed


class TestTheSealsAreReadNotGuessed:
    def test_reverse_charge_is_what_was_sealed(self):
        assert make_invoice(tax_treatment="reverse_charge").is_reverse_charge is True
        # A Spanish S.L. with a tax id is a domestic sale, whatever type Stripe gives its number (saas#1063).
        assert (
            make_invoice(
                stripe_invoice_id="in_2",
                number="ERP-2026-00002",
                sequence=2,
                payer_tax_id="ESB12345678",
                payer_tax_id_type="eu_vat",
            ).is_reverse_charge
            is False
        )


class TestTheNoteNeverLies:
    """``vat_included_because_unverified``: whether the document must explain that the VAT came out of what
    was charged (saas#1479, saas#1633). The platform hub prints the sentence; the decision is sealed here."""

    def note(self, **fields) -> bool:
        defaults = {
            "vat_included_reconciled": True,
            "payer_tax_id": "DE999999999",
            "payer_tax_id_type": "eu_vat",
            "payer_tax_id_verified": False,
            "payer_country": "DE",
        }
        return make_invoice(**{**defaults, **fields}).vat_included_because_unverified

    def test_the_foreign_unverified_case_carries_it(self):
        assert self.note() is True

    def test_not_reconciled_carries_nothing(self):
        assert self.note(vat_included_reconciled=False) is False

    def test_a_verified_number_carries_nothing(self):
        assert self.note(payer_tax_id_verified=True) is False

    def test_a_spanish_b2b_invoice_carries_nothing(self):
        """Its number is never asked to VIES (nothing to prove), so «unverified» would be a lie."""
        assert self.note(payer_tax_id="ESB12345678", payer_country="ES") is False

    def test_a_sale_without_a_tax_id_carries_nothing(self):
        assert self.note(payer_tax_id="", payer_tax_id_type="") is False

    def test_it_survives_oss(self):
        """Under OSS the sealed jurisdiction IS the customer's country: comparing with it silenced the note."""
        assert self.note(tax_treatment="oss", tax_country="DE") is True
