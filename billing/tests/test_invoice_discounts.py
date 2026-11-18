"""The invoices of a discount: recorded, numbered and issued like any other, also at 0 €.

Stripe bills each line at its price and the discount takes its part off (captured from the test account,
``fixtures/discounts/``): a line's ``amount`` is the price BEFORE the discount, ``discount_amounts`` what came off,
and the invoice keeps the price in its ``subtotal``. A discount of all of it (100 %, or an amount at least the price,
which Stripe caps) leaves a ``total`` of 0: such an invoice (total 0, subtotal above 0) is ERPlora's invoice too, each
line with its discount and its base after it, posted to the platform hub with ``discount_cents``. A trial's (subtotal 0)
is still none. A proration is priced by Stripe after the discount and comes with no discount of its own; a module the
discount does not name is charged whole. Nothing was charged on a 0 € invoice, so no ERROR says Stripe left the tax
out.
"""

from decimal import Decimal

import pytest

from billing import services, vat
from billing.models import Invoice, InvoiceCounter
from billing.services.invoice_discounts import is_fully_discounted, line_amounts
from billing.tests.stripe_captured import paid
from billing.tests.stripe_double import event, invoice, subscription
from billing.tests.test_invoice_recording import deliver

pytestmark = pytest.mark.django_db

PLATFORM = r"^/internal/platform/invoices$"
NO_TAX_ERROR = "fiscal.vat.stripe_charged_no_tax_on_subject_sale"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    return stripe_double


def lines_of(name: str) -> list[dict]:
    return paid(name)["data"]["object"]["lines"]["data"]


def recorded(name: str) -> Invoice:
    assert deliver(paid(name)) == "processed"
    return Invoice.objects.get()


def amounts(invoice: Invoice) -> list[tuple]:
    return [(line.discount_cents, line.net_cents, line.tax_cents, line.total_cents) for line in invoice.lines.all()]


# --- A line and an invoice, as Stripe shapes them ------------------------------------------------------


class TestWhatStripeSends:
    def test_a_line_all_discounted_is_its_price_and_its_discount(self):
        [line] = lines_of("repeating_100/invoice_paid_1.json")

        assert line_amounts(line) == (0, 2999)

    def test_a_line_after_the_discount_has_none(self):
        [line] = lines_of("repeating_100/invoice_paid_7.json")

        assert line_amounts(line) == (2999, 0)

    def test_a_partial_discount_leaves_the_rest(self):
        line = {"amount": 2999, "discount_amounts": [{"amount": 1000, "discount": "di_1"}, {"amount": 500}]}

        assert line_amounts(line) == (1499, 1500)

    def test_a_line_without_discounts_is_its_amount(self):
        assert line_amounts({"amount": 1000}) == (1000, 0)

    def test_only_an_invoice_zeroed_by_its_discount_is_fully_discounted(self):
        assert is_fully_discounted(paid("repeating_100/invoice_paid_1.json")["data"]["object"])
        assert not is_fully_discounted(paid("repeating_100/invoice_paid_7.json")["data"]["object"])
        assert not is_fully_discounted(invoice(amount_due=0, tax=0))
        assert not is_fully_discounted({"total": -500, "subtotal": 1000})


# --- The 0 € invoice of a discount of all of it ---------------------------------------------------------


@pytest.mark.usefixtures("running")
class TestTheZeroInvoice:
    def test_it_is_numbered_like_any_other_with_its_discount_on_the_line(self, caplog):
        assert deliver(paid("repeating_100/invoice_paid_1.json")) == "processed"

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
            deliver(paid("repeating_100/invoice_paid_1.json"))

        [call] = [call for call in hub_double.calls_to("POST") if call.path == "/internal/platform/invoices"]
        assert call.body["total_cents"] == 0
        assert {key: call.body["lines"][0][key] for key in ("discount_cents", "net_cents", "tax_cents", "total_cents")} == {
            "discount_cents": 2999, "net_cents": 0, "tax_cents": 0, "total_cents": 0,
        }
        assert Invoice.objects.get().fiscal_status == "issued"

    def test_a_redelivery_is_the_same_invoice_and_spends_no_number(self):
        first = paid("repeating_100/invoice_paid_1.json")
        again = {**paid("repeating_100/invoice_paid_1.json"), "id": "evt_all_discounted_again"}

        assert deliver(first) == "processed"
        assert deliver(again) == "processed"

        assert Invoice.objects.count() == 1
        assert InvoiceCounter.objects.get().last_number == 1

    def test_a_trial_is_still_no_invoice(self):
        deliver(event("invoice.paid", invoice("in_trial", status="paid", amount_due=0, tax=0)))

        assert not Invoice.objects.exists()
        assert not InvoiceCounter.objects.exists()


@pytest.mark.usefixtures("running")
class TestEveryDiscount:
    def test_after_a_discount_for_months_the_plan_is_charged_whole(self):
        made = recorded("repeating_100/invoice_paid_7.json")

        assert (made.net_cents, made.tax_cents, made.total_cents) == (2999, 630, 3629)
        assert amounts(made) == [(0, 2999, 630, 3629)]

    def test_a_percentage_once_takes_its_part_off_before_vat(self):
        made = recorded("once_percent/invoice_paid_1.json")

        assert (made.net_cents, made.tax_cents, made.total_cents) == (2399, 504, 2903)
        assert amounts(made) == [(600, 2399, 504, 2903)]

    def test_an_amount_forever_takes_its_amount_off(self):
        assert amounts(recorded("forever_amount/partial/invoice_paid_1.json")) == [(1000, 1999, 420, 2419)]

    def test_an_amount_over_the_price_is_capped_and_the_invoice_is_0(self):
        made = recorded("forever_amount/over_price/invoice_paid_1.json")

        assert made.number and made.total_cents == 0
        assert amounts(made) == [(2999, 0, 0, 0)]

    def test_a_discount_forever_on_a_yearly_plan_takes_its_part_off_each_year(self):
        assert amounts(recorded("annual_forever/invoice_paid_1.json")) == [(2999, 26991, 5668, 32659)]

    @pytest.mark.usefixtures("inventory")
    def test_a_module_the_discount_does_not_name_is_charged_whole(self):
        made = recorded("module_added/invoice_paid_3.json")

        assert made.total_cents == 1089
        assert amounts(made) == [(2999, 0, 0, 0), (0, 900, 189, 1089)]

    @pytest.mark.usefixtures("inventory")
    def test_the_proration_of_a_module_comes_without_a_discount(self):
        assert amounts(recorded("module_added/invoice_paid_2.json")) == [(0, 600, 126, 726)]

    def test_the_proration_of_a_bigger_plan_comes_already_discounted(self):
        made = recorded("upgrade/partial/invoice_paid_2.json")

        assert made.total_cents == 1614
        assert [line.discount_cents for line in made.lines.all()] == [0, 0]
        assert [line.net_cents for line in made.lines.all()] == [-1599, 2933]

    def test_a_proration_all_discounted_charges_nothing_and_is_no_invoice(self):
        deliver(paid("upgrade/full/invoice_paid_2.json"))

        assert not Invoice.objects.exists()


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
    deliver(paid("repeating_100/invoice_paid_7.json"))

    [line] = services.platform_payload(Invoice.objects.get())["lines"]
    assert line["discount_cents"] == 0
