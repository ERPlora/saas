"""Every euro given back is a rectifying invoice of ERPlora's (RD 1619/2012 art. 15).

An issued invoice is never modified (CLAUDE.md, «Fiscal»): what corrects it is a rectifying invoice of its own
series (``ERPR``), with negative amounts, the qualification and the recipient of the one it rectifies and its
VeriFactu type (R1 for refunds and price changes, art. 80.1/80.2 LIVA; R4 for anything else, such as a
fraudulent charge). Three Stripe doors lead to one:

- a credit note (``credit_note.created``; ``test_invoice_recording``);
- a refund made without a credit note (``charge.refunded``): the gross refunded, split by the rate of the
  invoice it refunds, once per refund; a refund a credit note already covers is that credit note's;
- a Stripe invoice with a negative total (a proration credit larger than what it bills): it rectifies the
  invoice whose period the credited lines belong to. Downgrades no longer produce them (they wait for the end of
  the period, ``test_plan_change``), but a legacy or manual one is invoiced, never only logged.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from live.models import OutboxEvent

from billing.models import Invoice, InvoiceCounter, InvoiceLine
from billing.schemas.invoice_records import CreditNoteRecordIn, RefundRecordIn
from billing.services import invoice_events, invoice_numbering, invoice_sealing, platform_invoices, rectifying_invoices
from billing.tests.stripe_double import (
    MONTH_END,
    NOW,
    credit_note,
    credit_note_line,
    event,
    invoice,
    invoice_line,
    invoice_payment,
    listing,
    signed,
    subscription,
)

pytestmark = pytest.mark.django_db

YEAR = timezone.localdate().year


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    # A credit note is read LIVE before it becomes a rectifying invoice (a voided one never does, BILLING-F26).
    stripe_double.answer("credit_notes.retrieve", lambda call: {"id": call.args[0], "object": "credit_note", "status": "issued"})
    return stripe_double


@pytest.fixture
def invoiced(running):
    deliver(event("invoice.paid", invoice("in_1", status="paid")))
    return Invoice.objects.get(stripe_invoice_id="in_1", kind="invoice")


def deliver(payload, *, status=200):
    body, header = signed(payload)
    response = Client().post(
        "/webhooks/stripe/",
        body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
        HTTP_HOST="localhost:8001",
    )
    assert response.status_code == status, response.content
    return response.json()["status"]


def rectifying():
    return Invoice.objects.filter(kind="credit_note")


def record_note(original, note):
    return rectifying_invoices.credit_note_record(
        invoice_events._invoice_ctx(original), CreditNoteRecordIn(credit_note=note)
    )


def record_refund(original, **fields):
    refund = {"id": "re_1", "object": "refund", "amount": 1000, "charge": "ch_1", "status": "succeeded", **fields}
    return rectifying_invoices.refund_record(
        invoice_events._invoice_ctx(original), RefundRecordIn(invoice_id=original.id, refund=refund)
    )


def taxed(cents: int) -> dict:
    """The tax of a Stripe line, as a field of it."""
    return {"taxes": credit_note_line(tax=cents)["taxes"]}


class TestANegativeStripeInvoice:
    def negative(self):
        return invoice(
            "in_neg",
            status="paid",
            lines=[
                invoice_line(
                    "il_unused",
                    amount=-1500,
                    tax=-315,
                    proration=True,
                    description="Unused time on Standard",
                    period=(NOW, MONTH_END),
                ),
                invoice_line(
                    "il_new",
                    amount=500,
                    tax=105,
                    proration=True,
                    description="Remaining time on Starter",
                    period=(NOW, MONTH_END),
                ),
            ],
        )

    def test_it_rectifies_the_invoice_whose_period_it_credits(self, invoiced):
        assert deliver(event("invoice.paid", self.negative())) == "processed"

        [credit] = rectifying()
        assert (credit.number, credit.rectifies_id, credit.stripe_source_id) == (
            f"ERPR-{YEAR}-00001",
            invoiced.id,
            "in_neg",
        )
        assert (credit.net_cents, credit.tax_cents, credit.total_cents) == (
            -1000,
            -210,
            -1210,
        )
        assert list(credit.lines.values_list("net_cents", "tax_cents")) == [
            (-1500, -315),
            (500, 105),
        ]
        assert (credit.rectification_type, credit.rectification_reason) == (
            "R1",
            "proration",
        )
        assert (credit.tax_treatment, credit.payer_name) == (
            invoiced.tax_treatment,
            invoiced.payer_name,
        )
        assert credit.fiscal_status == "issuing"

    def test_it_carries_stripes_number_and_day(self, invoiced):
        deliver(event("invoice.paid", {**self.negative(), "number": "ERPL-0042", "created": NOW - 60}))

        credit = rectifying().get()
        assert (credit.stripe_number, credit.billed_at) == ("ERPL-0042", datetime.fromtimestamp(NOW - 60, UTC))

    def test_its_description_is_why_it_rectifies(self, invoiced):
        deliver(event("invoice.paid", {**self.negative(), "description": "Ajuste del plan"}))

        assert rectifying().get().rectification_reason == "Ajuste del plan"

    def test_it_is_recorded_once(self, invoiced):
        deliver(event("invoice.paid", self.negative()))
        deliver(event("invoice.payment_succeeded", self.negative()))

        assert rectifying().count() == 1

    def test_without_the_invoice_it_credits_it_waits(self, running):
        deliver(event("invoice.paid", self.negative()), status=500)

        assert not rectifying().exists()


class TestARefundWithoutACreditNote:
    def charge(self, amount_refunded=1000):
        return {
            "id": "ch_1",
            "object": "charge",
            "payment_intent": "pi_1",
            "amount": 3629,
            "amount_refunded": amount_refunded,
            "refunded": amount_refunded == 3629,
        }

    def refund(
        self,
        refund_id="re_1",
        amount=1000,
        reason="requested_by_customer",
        status="succeeded",
    ):
        return {
            "id": refund_id,
            "object": "refund",
            "amount": amount,
            "charge": "ch_1",
            "reason": reason,
            "status": status,
            "created": NOW,
        }

    def stripe_says(self, stripe_double, *, refunds, notes=()):
        stripe_double.answer(
            "invoice_payments.list",
            listing([invoice_payment("pi_1", invoice_id="in_1")]),
        )
        stripe_double.answer("refunds.list", listing(list(refunds)))
        stripe_double.answer("credit_notes.list", listing(list(notes)))

    def test_the_gross_refunded_is_rectified_at_the_invoices_rate(
        self, invoiced, stripe_double
    ):
        self.stripe_says(stripe_double, refunds=[self.refund()])

        assert deliver(event("charge.refunded", self.charge())) == "processed"

        [credit] = rectifying()
        # 10.00 € with 21 % inside: 8.26 + 1.74.
        assert (credit.net_cents, credit.tax_cents, credit.total_cents) == (
            -826,
            -174,
            -1000,
        )
        assert (credit.rectifies_id, credit.stripe_source_id) == (invoiced.id, "re_1")
        assert (credit.rectification_type, credit.rectification_reason) == (
            "R1",
            "requested_by_customer",
        )

    def test_each_refund_once(self, invoiced, stripe_double):
        self.stripe_says(stripe_double, refunds=[self.refund()])
        deliver(event("charge.refunded", self.charge()))
        self.stripe_says(
            stripe_double, refunds=[self.refund(), self.refund("re_2", amount=500)]
        )

        deliver(event("charge.refunded", self.charge(1500)))

        assert sorted(rectifying().values_list("stripe_source_id", "total_cents")) == [
            ("re_1", -1000),
            ("re_2", -500),
        ]

    def test_a_refund_a_credit_note_covers_is_that_credit_notes(
        self, invoiced, stripe_double
    ):
        note = credit_note()
        note["refunds"] = [{"refund": "re_1", "amount_refunded": 1000}]
        self.stripe_says(stripe_double, refunds=[self.refund()], notes=[note])

        deliver(event("charge.refunded", self.charge()))

        assert not rectifying().exists()

    def test_a_refund_still_pending_is_not_rectified_yet(self, invoiced, stripe_double):
        self.stripe_says(stripe_double, refunds=[self.refund(status="pending")])

        deliver(event("charge.refunded", self.charge()))

        assert not rectifying().exists()

    def test_a_fraudulent_charge_refunded_is_other(self, invoiced, stripe_double):
        self.stripe_says(stripe_double, refunds=[self.refund(reason="fraudulent")])

        deliver(event("charge.refunded", self.charge()))

        assert rectifying().get().rectification_type == "R4"

    def test_a_charge_that_paid_no_invoice_is_not_ours(self, running, stripe_double):
        stripe_double.answer("invoice_payments.list", listing([]))

        assert deliver(event("charge.refunded", self.charge())) == "ignored"

    def test_a_refund_ahead_of_its_invoice_waits(self, running, stripe_double):
        self.stripe_says(stripe_double, refunds=[self.refund()])

        deliver(event("charge.refunded", self.charge()), status=500)

        assert not rectifying().exists()


def test_the_payload_carries_the_rectification(
    invoiced, hub_double, django_capture_on_commit_callbacks
):
    from billing.services import platform_invoices

    hub_double.answer(
        "POST", r"^/internal/platform/invoices$", 201, {"status": "issued", "qr": "x"}
    )
    deliver(event("credit_note.created", credit_note(reason="duplicate")))
    credit = rectifying().get()

    platform_invoices.post_platform_invoice(credit.id)

    body = hub_double.calls_to("POST")[-1].body
    assert body["rectification"] == {"type": "R1", "reason": "duplicate"}
    assert body["stripe_source_id"] == "cn_1"


class TestWhatItSays:
    """A rectifying invoice is the one it rectifies, as it was issued, with the amounts of what was given back."""

    #: The seal of the invoice, changed after the sale so that none of it can come from today's payer or policy.
    SEALED = {
        "business_name": "Panadería de antes",
        "payer_name": "Käufer GmbH",
        "payer_tax_id": "DE129273398",
        "payer_tax_id_type": "eu_vat",
        "payer_tax_id_verified": True,
        "vat_consultation_number": "WAPIAAAAYs1234",
        "payer_address": "Unter den Linden 1",
        "payer_city": "Berlin",
        "payer_postal_code": "10117",
        "payer_country": "DE",
        "payer_email": "kauf@example.de",
        "language": "en",
        "currency": "USD",
        "tax_treatment": "reverse_charge",
        "tax_country": "DE",
        "tax_rate": Decimal("7.00"),
    }

    def test_every_field(self, invoiced):
        Invoice.objects.filter(pk=invoiced.pk).update(**self.SEALED)
        before = timezone.now()

        deliver(event("credit_note.created", {**credit_note(), "created": NOW - 60, "memo": "Cobro duplicado"}))

        row = Invoice.objects.values().get(kind="credit_note")
        moment = row["paid_at"]
        assert before <= moment <= timezone.now()
        assert all((invoiced.hub_id, invoiced.billing_profile_id, invoiced.payer_account_id))
        unread = {"id", "created_at", "updated_at"}
        assert {name: value for name, value in row.items() if name not in unread} == {
            **self.SEALED,
            "kind": "credit_note",
            "hub_id": invoiced.hub_id,
            "billing_profile_id": invoiced.billing_profile_id,
            "payer_account_id": invoiced.payer_account_id,
            "rectifies_id": invoiced.id,
            "series": "ERPR",
            "sequence": 1,
            "number": f"ERPR-{YEAR}-00001",
            "issued_on": invoice_numbering.invoice_today(),
            "stripe_invoice_id": "in_1",
            "stripe_source_id": "cn_1",
            "rectification_type": "R1",
            "rectification_reason": "Cobro duplicado",
            "stripe_number": "ABCD-0001-CN-_1",
            "hosted_invoice_url": "",
            "billed_at": datetime.fromtimestamp(NOW - 60, UTC),
            "payment_status": "paid",
            "paid_at": moment,
            "net_cents": -3629,
            "tax_cents": 0,
            "total_cents": -3629,
            "vat_included_reconciled": False,
            "fiscal_status": "issuing",
            "fiscal_status_at": moment,
            "qr": "",
            "fiscal_error_code": "",
            "fiscal_error": "",
            "post_attempts": 0,
            "next_post_at": moment,
            "last_post_error": "",
            "emailed_at": None,
        }

    def test_stripes_number_and_the_memo_are_cut_to_what_fits(self, invoiced):
        deliver(event("credit_note.created", {**credit_note(), "number": "N" * 70, "memo": "m" * 300}))

        credit = rectifying().get()
        assert (credit.stripe_number, credit.rectification_reason) == ("N" * 64, "m" * 255)

    def test_a_note_that_gives_no_reason_is_a_credit_note(self, invoiced):
        deliver(event("credit_note.created", credit_note(reason=None)))

        credit = rectifying().get()
        assert (credit.rectification_type, credit.rectification_reason) == ("R1", "credit_note")

    def test_a_refund_that_gives_no_reason_is_a_refund(self, invoiced):
        record_refund(invoiced, reason=None, created=NOW - 60)

        credit = rectifying().get()
        assert (credit.rectification_type, credit.rectification_reason) == ("R1", "refund")
        assert (credit.stripe_number, credit.billed_at) == ("", datetime.fromtimestamp(NOW - 60, UTC))
        assert list(credit.lines.values_list("description", flat=True)) == ["Refund"]

    def test_a_note_without_lines_is_one_line_of_its_totals(self, invoiced):
        deliver(event("credit_note.created", {**credit_note(), "lines": listing([])}))

        credit = rectifying().get()
        assert (credit.net_cents, credit.tax_cents, credit.total_cents) == (-2999, -630, -3629)
        assert list(credit.lines.values_list("net_cents", "tax_cents")) == [(-2999, -630)]

    def test_a_note_that_says_no_amount_gives_nothing_back(self, invoiced):
        note = {name: value for name, value in credit_note().items() if name not in ("total", "total_taxes")}

        record_note(invoiced, {**note, "lines": listing([])})

        assert rectifying().get().total_cents == 0


class TestItsLines:
    """Each line keeps what the line it corrects was sealed with: what it sells, its rate, its period."""

    @pytest.fixture
    def two_lines(self, running, inventory):
        """An invoice of a plan and a module, the module at its own rate."""
        module = invoice_line(
            "il_module", price_id="price_inventory_month", amount=1000, tax=210, description="1 × Inventory"
        )
        deliver(event("invoice.paid", invoice("in_1", status="paid", lines=[invoice_line(), module])))
        InvoiceLine.objects.filter(stripe_line_id="il_module").update(tax_rate=Decimal("10.00"))
        return Invoice.objects.get(stripe_invoice_id="in_1", kind="invoice")

    def note_line(self, **fields):
        """A line of a credit note that names nothing of the invoice unless ``fields`` says so."""
        price = fields.pop("price", "")
        line = {**credit_note_line(invoice_line_item="", description=""), **fields}
        return {**line, "pricing": {"type": "price_details", "price_details": {"price": price}}} if price else line

    def recorded(self, original, *lines) -> list[dict]:
        record_note(original, credit_note(lines=list(lines)))
        return list(rectifying().get().lines.order_by("position").values())

    def test_every_field_of_the_line_it_names(self, two_lines):
        [line] = self.recorded(
            two_lines, self.note_line(invoice_line_item="il_module", amount=1000, **taxed(100), quantity=3)
        )

        corrected = two_lines.lines.get(stripe_line_id="il_module")
        assert line == {
            "id": line["id"],
            "invoice_id": rectifying().get().id,
            "position": 1,
            "description": "1 × Inventory",
            "item_kind": "module",
            "item_slug": "inventory",
            "quantity": 3,
            "proration": False,
            "period_start": corrected.period_start,
            "period_end": corrected.period_end,
            "tax_category_id": "service.software_license",
            "tax_treatment": "domestic",
            "tax_rate": Decimal("10.00"),
            "net_cents": -1000,
            "tax_cents": -100,
            "total_cents": -1100,
            "discount_cents": 0,
            "stripe_line_id": "cnli_1",
        }
        assert None not in (corrected.period_start, corrected.period_end)

    def test_one_that_names_no_line_corrects_the_one_that_sells_the_same(self, two_lines):
        [line] = self.recorded(two_lines, self.note_line(price="price_inventory_month", amount=1000, **taxed(100)))

        assert (line["description"], line["tax_rate"]) == ("1 × Inventory", Decimal("10.00"))
        assert line["period_start"] == two_lines.lines.get(stripe_line_id="il_module").period_start

    def test_the_line_it_names_goes_before_the_one_that_sells_the_same(self, two_lines):
        [line] = self.recorded(
            two_lines, self.note_line(invoice_line_item="il_module", price="price_starter_month", amount=1000, **taxed(100))
        )

        assert (line["item_kind"], line["item_slug"], line["description"]) == ("module", "inventory", "1 × Inventory")

    def test_of_two_lines_that_sell_the_same_it_corrects_the_first(self, running):
        both = [invoice_line("il_a", description="First"), invoice_line("il_b", description="Second")]
        deliver(event("invoice.paid", invoice("in_1", status="paid", lines=both)))

        [line] = self.recorded(Invoice.objects.get(kind="invoice"), self.note_line(price="price_starter_month"))

        assert line["description"] == "First"

    def test_what_was_not_invoiced_is_what_stripe_says_at_the_invoices_rate(self, invoiced, inventory):
        [line] = self.recorded(invoiced, self.note_line(price="price_inventory_month", amount=1000, **taxed(210)))

        assert (line["item_kind"], line["item_slug"]) == ("module", "inventory")
        assert (line["tax_category_id"], line["tax_rate"]) == ("service.software_license", Decimal("21.00"))
        assert (line["description"], line["period_start"], line["period_end"]) == ("Credit", None, None)

    @pytest.mark.parametrize("unnamed", [{"stripe_line_id": ""}, {"item_kind": "other", "item_slug": ""}])
    def test_one_that_names_nothing_corrects_no_line(self, invoiced, unnamed):
        invoiced.lines.update(**unnamed)

        [line] = self.recorded(invoiced, self.note_line())

        assert (line["description"], line["item_kind"], line["item_slug"]) == ("Credit", "other", "")
        assert (line["tax_category_id"], line["period_start"]) == ("service.saas_subscription", None)

    def test_each_of_several_lines_has_its_place(self, two_lines):
        lines = self.recorded(
            two_lines,
            self.note_line(id="cnli_1", invoice_line_item="il_plan", amount=2999, **taxed(630)),
            self.note_line(id="cnli_2", invoice_line_item="il_module", amount=1000, **taxed(100)),
        )

        assert [(line["position"], line["item_slug"], line["stripe_line_id"]) for line in lines] == [
            (1, "starter", "cnli_1"),
            (2, "inventory", "cnli_2"),
        ]

    def test_a_proration_keeps_the_period_stripe_says(self, invoiced):
        lines = [invoice_line("il_unused", amount=-1500, tax=-315, proration=True, period=(NOW, MONTH_END - 60))]

        deliver(event("invoice.paid", invoice("in_neg", status="paid", lines=lines)))

        [line] = rectifying().get().lines.values()
        assert (line["proration"], line["period_start"], line["period_end"]) == (
            True,
            datetime.fromtimestamp(NOW, UTC),
            datetime.fromtimestamp(MONTH_END - 60, UTC),
        )

    def test_a_long_description_is_cut_to_what_fits(self, invoiced):
        [line] = self.recorded(invoiced, self.note_line(description="d" * 300))

        assert line["description"] == "d" * 255

    def test_a_quantity_below_one_is_one(self, invoiced):
        [line] = self.recorded(invoiced, self.note_line(quantity=-2))

        assert line["quantity"] == 1

    def test_without_tax_of_a_sale_stripe_charged_it_on_all_of_it_is_base(self, invoiced):
        [line] = self.recorded(invoiced, self.note_line(amount=1210, **taxed(0)))

        assert (line["net_cents"], line["tax_cents"]) == (-1210, 0)


class TestWhatStripeChargedWithoutItsTax:
    """A sale Stripe charged no tax on carries the VAT inside what it collected, and so does what is given back."""

    @pytest.fixture
    def inside(self, invoiced):
        Invoice.objects.filter(pk=invoiced.pk).update(vat_included_reconciled=True)
        return invoiced

    def given_back(self, original, *, amount: int, tax: int) -> tuple[int, int]:
        record_note(original, credit_note(lines=[credit_note_line(amount=amount, tax=tax)]))
        return rectifying().get().lines.values_list("net_cents", "tax_cents").get()

    def test_the_vat_inside_is_taken_out(self, inside):
        # 12.10 € with 21 % inside.
        assert self.given_back(inside, amount=1210, tax=0) == (-1000, -210)

    def test_the_tax_stripe_says_rules(self, inside):
        assert self.given_back(inside, amount=1000, tax=200) == (-1000, -200)


class TestItAddsUpOrNothingIsInvoiced:
    def odd(self):
        return {**credit_note(), "total": 4000}

    def test_nothing_is_recorded_and_stripe_retries(self, invoiced):
        deliver(event("credit_note.created", self.odd()), status=500)

        assert not rectifying().exists()
        assert not InvoiceCounter.objects.filter(series="ERPR", last_number__gt=0).exists()

    def test_support_reads_whose_it_is_and_both_amounts(self, invoiced, caplog):
        deliver(event("credit_note.created", self.odd()), status=500)

        [told] = [line for line in caplog.records if getattr(line, "event", "") == "fiscal.invoice.lines_do_not_add_up"]
        assert told.hub_id == str(invoiced.hub_id)
        assert told.args == ("cn_1", -3629, -4000)

    def test_no_number_is_asked_for(self, invoiced, monkeypatch):
        asked = []
        monkeypatch.setattr(invoice_numbering, "issue_number", asked.append)

        with pytest.raises(invoice_sealing.InvoiceDoesNotAddUp):
            record_note(invoiced, self.odd())
        assert asked == []

    def test_a_refund_is_what_stripe_gave_back(self, invoiced):
        record_refund(invoiced, amount=1234)

        credit = rectifying().get()
        assert (credit.net_cents + credit.tax_cents, credit.total_cents) == (-1234, -1234)


class TestOncePerSource:
    def test_the_answer_says_whether_it_is_new(self, invoiced):
        first = record_note(invoiced, credit_note())
        again = record_note(invoiced, credit_note())

        credit = rectifying().get()
        recorded = {"id": credit.id, "number": f"ERPR-{YEAR}-00001", "payment_status": "paid"}
        assert first.model_dump() == {**recorded, "outcome": "numbered"}
        assert again.model_dump() == {**recorded, "outcome": "duplicate"}

    def test_two_partial_notes_of_one_invoice_are_two(self, invoiced):
        half = [credit_note_line(amount=1000, tax=210)]

        record_note(invoiced, credit_note("cn_1", lines=half))
        record_note(invoiced, credit_note("cn_2", lines=half))

        assert sorted(rectifying().values_list("stripe_source_id", "number")) == [
            ("cn_1", f"ERPR-{YEAR}-00001"),
            ("cn_2", f"ERPR-{YEAR}-00002"),
        ]

    def test_an_invoice_is_never_taken_for_its_rectification(self, invoiced):
        Invoice.objects.filter(pk=invoiced.pk).update(stripe_source_id="cn_1")

        assert record_note(invoiced, credit_note()).outcome == "numbered"


class TestWhoHearsOfIt:
    def test_its_payers_channel_with_what_it_rectifies(self, invoiced):
        record_note(invoiced, credit_note())

        told = OutboxEvent.objects.get(name="billing.credit_note.recorded")
        assert (told.scope_kind, told.scope_key) == ("user", str(invoiced.payer_account_id))
        assert told.payload == {"id": str(rectifying().get().id), "rectifies": str(invoiced.id)}

    def test_a_duplicate_tells_nobody_again(self, invoiced):
        record_note(invoiced, credit_note())
        record_note(invoiced, credit_note())

        assert OutboxEvent.objects.filter(name="billing.credit_note.recorded").count() == 1

    def test_the_platform_hub_after_the_commit_and_not_before(
        self, invoiced, monkeypatch, django_capture_on_commit_callbacks
    ):
        posted = []
        monkeypatch.setattr(platform_invoices, "_post_quietly", posted.append)

        with django_capture_on_commit_callbacks() as after_commit:
            record_note(invoiced, credit_note())
            assert posted == []
        for callback in after_commit:
            callback()

        assert posted == [rectifying().get().id]

    def test_a_post_that_breaks_does_not_undo_it(self, invoiced, monkeypatch, django_capture_on_commit_callbacks):
        def broken(invoice_id):
            raise OSError("no route to the platform hub")

        monkeypatch.setattr(platform_invoices, "_post_quietly", broken)

        with django_capture_on_commit_callbacks(execute=True):
            record_note(invoiced, credit_note())

        assert rectifying().count() == 1
