"""The invoices of free months: 0 € each month, recorded, numbered and issued like any other.

Stripe bills the plan at its price and the coupon takes all of it off (captured from the test account,
``fixtures/free_months/``): a line's ``amount`` is the price BEFORE the discount, ``discount_amounts`` what came off,
and the invoice keeps the price in its ``subtotal`` with a ``total`` of 0. Such an invoice (total 0, subtotal above 0)
is ERPlora's invoice: each line with its discount and its base after it, at the plan's rate, posted to the platform
hub with ``discount_cents``. A trial's (subtotal 0) is still none, and the month after the free months is charged as
any other. Nothing was charged, so no ERROR says Stripe left the tax out.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.test import Client

from billing import services, vat
from billing.models import Invoice, InvoiceCounter
from billing.services.invoice_discounts import is_fully_discounted, line_amounts
from billing.tests.stripe_double import event, invoice, signed, subscription
from billing.tests.test_invoice_recording import running  # noqa: F401 - a ready business paying Starter monthly

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures" / "free_months"
PLATFORM = r"^/internal/platform/invoices$"
NO_TAX_ERROR = "fiscal.vat.stripe_charged_no_tax_on_subject_sale"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    return stripe_double


def captured_paid(month: int) -> dict:
    """The ``invoice.paid`` of month ``month`` of a code of six months, as Stripe sent it, billed to ``sub_1`` and
    for the price of Starter."""
    payload = json.loads((FIXTURES / f"invoice_paid_month_{month}.json").read_text())
    stripe_invoice = payload["data"]["object"]
    stripe_invoice["parent"]["subscription_details"]["subscription"] = "sub_1"
    for line in stripe_invoice["lines"]["data"]:
        line["pricing"]["price_details"]["price"] = "price_starter_month"
    return payload


def deliver(payload) -> str:
    body, header = signed(payload)
    response = Client().post("/webhooks/stripe/", body, content_type="application/json",
                             HTTP_STRIPE_SIGNATURE=header, HTTP_HOST="localhost:8001")
    assert response.status_code == 200, response.content
    return response.json()["status"]


# --- A line and an invoice, as Stripe shapes them ------------------------------------------------------


class TestWhatStripeSends:
    def test_a_line_of_a_free_month_is_its_price_all_discounted(self):
        [line] = captured_paid(1)["data"]["object"]["lines"]["data"]

        assert line_amounts(line) == (0, 2999)

    def test_a_line_of_the_month_after_has_no_discount(self):
        [line] = captured_paid(7)["data"]["object"]["lines"]["data"]

        assert line_amounts(line) == (2999, 0)

    def test_a_partial_discount_leaves_the_rest(self):
        line = {"amount": 2999, "discount_amounts": [{"amount": 1000, "discount": "di_1"}, {"amount": 500}]}

        assert line_amounts(line) == (1499, 1500)

    def test_a_line_without_discounts_is_its_amount(self):
        assert line_amounts({"amount": 1000}) == (1000, 0)

    def test_only_an_invoice_zeroed_by_its_discount_is_fully_discounted(self):
        assert is_fully_discounted(captured_paid(1)["data"]["object"])
        assert not is_fully_discounted(captured_paid(7)["data"]["object"])
        assert not is_fully_discounted(invoice(amount_due=0, tax=0))
        assert not is_fully_discounted({"total": -500, "subtotal": 1000})


# --- The 0 € invoice of a free month -------------------------------------------------------------------


@pytest.mark.usefixtures("running")
class TestTheZeroInvoice:
    def test_it_is_numbered_like_any_other_with_its_discount_on_the_line(self, caplog):
        assert deliver(captured_paid(1)) == "processed"

        recorded = Invoice.objects.get()
        assert recorded.number and recorded.series == "ERP"
        assert (recorded.payment_status, recorded.fiscal_status) == ("paid", "issuing")
        assert (recorded.net_cents, recorded.tax_cents, recorded.total_cents) == (0, 0, 0)
        assert (recorded.tax_treatment, recorded.tax_rate, recorded.vat_included_reconciled) == (
            "domestic", Decimal("21.00"), False
        )
        [line] = recorded.lines.all()
        assert (line.item_kind, line.item_slug, line.tax_rate) == ("plan", "starter", Decimal("21.00"))
        assert (line.discount_cents, line.net_cents, line.tax_cents, line.total_cents) == (2999, 0, 0, 0)
        assert not [record for record in caplog.records if getattr(record, "event", "") == NO_TAX_ERROR]

    def test_it_reaches_the_platform_hub_with_the_discount(self, hub_double, django_capture_on_commit_callbacks):
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": "https://example.com/qr"})

        with django_capture_on_commit_callbacks(execute=True):
            deliver(captured_paid(1))

        [call] = [call for call in hub_double.calls_to("POST") if call.path == "/internal/platform/invoices"]
        assert call.body["total_cents"] == 0
        assert {key: call.body["lines"][0][key] for key in ("discount_cents", "net_cents", "tax_cents", "total_cents")} == {
            "discount_cents": 2999, "net_cents": 0, "tax_cents": 0, "total_cents": 0,
        }
        assert Invoice.objects.get().fiscal_status == "issued"

    def test_a_redelivery_is_the_same_invoice_and_spends_no_number(self):
        first = captured_paid(1)
        again = {**captured_paid(1), "id": "evt_free_month_again"}

        assert deliver(first) == "processed"
        assert deliver(again) == "processed"

        assert Invoice.objects.count() == 1
        assert InvoiceCounter.objects.get().last_number == 1

    def test_a_trial_is_still_no_invoice(self):
        deliver(event("invoice.paid", invoice("in_trial", status="paid", amount_due=0, tax=0)))

        assert not Invoice.objects.exists()
        assert not InvoiceCounter.objects.exists()


@pytest.mark.usefixtures("running")
class TestTheMonthAfter:
    def test_it_is_charged_as_any_other(self):
        deliver(captured_paid(7))

        recorded = Invoice.objects.get()
        assert (recorded.net_cents, recorded.tax_cents, recorded.total_cents) == (2999, 630, 3629)
        assert recorded.lines.get().discount_cents == 0


# --- The VAT of nothing charged ------------------------------------------------------------------------


def test_a_subject_sale_of_nothing_is_not_reconciled_nor_reported(caplog):
    breakdown = vat.resolve_vat(
        Decimal("0"), customer_country="ES", customer_postal_code="28001",
        category_key=vat.SAAS_SUBSCRIPTION_CATEGORY, tax_cents=0, tax_included=False,
    )

    assert (breakdown.base, breakdown.tax, breakdown.rate) == (Decimal("0.00"), Decimal("0.00"), Decimal("21.00"))
    assert breakdown.vat_included_reconciled is False
    assert not [record for record in caplog.records if getattr(record, "event", "") == NO_TAX_ERROR]


def test_a_subject_sale_charged_without_tax_is_still_reported(caplog):
    breakdown = vat.resolve_vat(
        Decimal("29.99"), customer_country="ES", customer_postal_code="28001",
        category_key=vat.SAAS_SUBSCRIPTION_CATEGORY, tax_cents=0, tax_included=False,
    )

    assert breakdown.vat_included_reconciled is True
    assert [record for record in caplog.records if getattr(record, "event", "") == NO_TAX_ERROR]


@pytest.mark.usefixtures("running")
def test_the_payload_of_every_line_carries_its_discount():
    deliver(captured_paid(7))

    [line] = services.platform_payload(Invoice.objects.get())["lines"]
    assert line["discount_cents"] == 0
