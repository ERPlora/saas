"""Every euro given back is a rectifying invoice of ERPlora's (review of L3-C; RD 1619/2012 art. 15).

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

import pytest
from django.test import Client
from django.utils import timezone

from billing.models import Invoice
from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    MONTH_END,
    NOW,
    credit_note,
    event,
    invoice,
    invoice_line,
    invoice_payment,
    listing,
    signed,
    subscription,
)
from hubs.models import Hub

pytestmark = pytest.mark.django_db

YEAR = timezone.localdate().year


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    return stripe_double


@pytest.fixture
def running(shop):
    paid = pay(shop)
    Hub.objects.filter(pk=paid.pk).update(
        status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call=""
    )
    return Hub.objects.get(pk=paid.pk)


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
    from billing import services

    hub_double.answer(
        "POST", r"^/internal/platform/invoices$", 201, {"status": "issued", "qr": "x"}
    )
    deliver(event("credit_note.created", credit_note(reason="duplicate")))
    credit = rectifying().get()

    services.post_platform_invoice(credit.id)

    body = hub_double.calls_to("POST")[-1].body
    assert body["rectification"] == {"type": "R1", "reason": "duplicate"}
    assert body["stripe_source_id"] == "cn_1"
