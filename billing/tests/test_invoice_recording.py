"""What Stripe collects becomes ERPlora's invoice, in the webhook's transaction (lot L3-C; PLAN-SAAS §4).

Ported from ERPlora/saas (origin/develop) ``billing/tests/test_hub_invoices.py`` (``create_hub_invoice``),
``test_invoice_line_tax.py`` (each line its own fiscal snapshot; the header is the sum of the lines),
``test_invoice_vat_breakdown.py``, ``test_invoice_fiscal_treatment.py`` and ``test_renewal_charged_issuer_rate.py``
(the qualification sealed on the invoice), ``fiscal/tests/test_vies_contract.py`` «7. The issued invoice keeps
the consultation number» and ``test_reverse_charge_switch.TestTheInvoiceKeepsTheEvidence``, and the
renewal half of ``test_payer_vat_reaches_the_invoice``, all through the door that writes the invoice now:
Stripe's webhook (``invoice.paid`` / ``invoice.payment_succeeded``, ``invoice.payment_failed``,
``invoice.voided``, ``invoice.marked_uncollectible`` and ``credit_note.created``).

Rules:
- A paid Stripe invoice is ONE invoice, however many deliveries (``invoice.paid`` and
  ``invoice.payment_succeeded`` of one payment included); a zero one (a trial) is none.
- It is written in the transaction that applies the subscription: when that fails (Stripe did not
  answer), there is no invoice and no number was spent.
- The payer is sealed as it was that day; the qualification, rate, base and quota of every line too.
- An unpaid one is listed without a number; paying it numbers that same row.
- A credit note is a rectifying invoice of its own series, with negative amounts, pointing at the invoice.

Changed from the old SaaS: one line per Stripe line (plan, modules, prorations), not one per invoice; the
header is the sum of the lines; the queue to the AEAT is the platform hub (``test_platform_invoices``).
Dropped: ``invoice_type`` (one kind of sale) and the module-purchase webhook (one subscription per business).
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import connections
from django.test import Client
from django.utils import timezone

from billing.models import FiscalPolicy, Invoice, InvoiceCounter
from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    connection_error,
    credit_note,
    credit_note_line,
    event,
    invoice,
    invoice_line,
    signed,
    subscription,
)
from billing.tests.vies_double import NOT_REGISTERED, VALID, no_network, vies_says
from hubs.models import BillingProfile, Hub

pytestmark = pytest.mark.django_db

YEAR = timezone.localdate().year


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    return stripe_double


@pytest.fixture
def running(shop):
    """A ready business paying Starter monthly (``sub_1``), its payer in Madrid."""
    paid = pay(shop)
    Hub.objects.filter(pk=paid.pk).update(
        status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call=""
    )
    return Hub.objects.select_related("billing_profile").get(pk=paid.pk)


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


def paid(invoice_id="in_1", **fields):
    return event("invoice.paid", invoice(invoice_id, status="paid", **fields))


def payer(hub, **fields):
    BillingProfile.objects.filter(pk=hub.billing_profile_id).update(**fields)


def module_line(**fields):
    defaults = {
        "line_id": "il_inventory",
        "price_id": "price_inventory_month",
        "amount": 1000,
        "tax": 210,
        "description": "1 × Inventory (at €10.00 / month)",
        "subscription_item": "si_inventory",
    }
    return invoice_line(**{**defaults, **fields})


class TestAPaidInvoiceIsRecorded:
    def test_it_becomes_an_invoice_with_the_next_number(self, running):
        assert deliver(paid()) == "processed"

        recorded = Invoice.objects.get()
        assert (
            recorded.kind,
            recorded.payment_status,
            recorded.number,
            recorded.series,
            recorded.sequence,
        ) == (
            "invoice",
            "paid",
            f"ERP-{YEAR}-00001",
            "ERP",
            1,
        )
        assert (recorded.net_cents, recorded.tax_cents, recorded.total_cents) == (
            2999,
            630,
            3629,
        )
        assert (recorded.tax_treatment, recorded.tax_country, recorded.tax_rate) == (
            "domestic",
            "ES",
            Decimal("21.00"),
        )
        assert recorded.hub_id == running.id
        assert recorded.business_name == "Panadería López"
        assert recorded.issued_on == timezone.localdate()
        assert recorded.stripe_invoice_id == "in_1"
        assert recorded.hosted_invoice_url == "https://invoice.stripe.com/i/test_1"
        assert recorded.fiscal_status == "issuing"

    def test_each_stripe_line_is_a_line_with_its_own_vat(self, running, inventory):
        deliver(paid(lines=[invoice_line(), module_line()]))

        recorded = Invoice.objects.get()
        lines = list(
            recorded.lines.values_list(
                "position",
                "item_kind",
                "item_slug",
                "tax_category_id",
                "tax_rate",
                "net_cents",
                "tax_cents",
                "total_cents",
            )
        )
        assert lines == [
            (
                1,
                "plan",
                "starter",
                "service.saas_subscription",
                Decimal("21.00"),
                2999,
                630,
                3629,
            ),
            (
                2,
                "module",
                "inventory",
                "service.software_license",
                Decimal("21.00"),
                1000,
                210,
                1210,
            ),
        ]
        assert (recorded.net_cents, recorded.tax_cents, recorded.total_cents) == (
            3999,
            840,
            4839,
        )

    def test_a_proration_credit_is_a_negative_line(self, running):
        deliver(
            paid(
                lines=[
                    invoice_line(),
                    invoice_line(
                        "il_unused",
                        amount=-1500,
                        tax=-315,
                        proration=True,
                        description="Unused time on Starter",
                    ),
                ]
            )
        )

        recorded = Invoice.objects.get()
        assert list(
            recorded.lines.values_list("proration", "net_cents", "tax_cents")
        ) == [
            (False, 2999, 630),
            (True, -1500, -315),
        ]
        assert (recorded.net_cents, recorded.tax_cents, recorded.total_cents) == (
            1499,
            315,
            1814,
        )

    def test_a_zero_invoice_is_not_an_invoice(self, running):
        """A trial is billed at 0: no sale, no invoice, no number spent."""
        deliver(paid(amount_due=0, tax=0))

        assert not Invoice.objects.exists()
        assert not InvoiceCounter.objects.exists()

    def test_the_payer_is_sealed_as_it_was_that_day(self, running, owner):
        payer(
            running,
            billing_name="Panadería López SL",
            tax_id="B12345678",
            billing_address="Calle Mayor 1",
            billing_city="Madrid",
            billing_postal_code="28001",
            billing_country="ES",
            billing_email="pagos@lopez.es",
        )
        with no_network():
            deliver(paid())

        payer(
            running, billing_name="Otra SL", tax_id="B87654321", billing_city="Toledo"
        )
        recorded = Invoice.objects.get()
        assert (
            recorded.payer_name,
            recorded.payer_tax_id,
            recorded.payer_address,
            recorded.payer_city,
            recorded.payer_postal_code,
            recorded.payer_country,
            recorded.payer_email,
        ) == (
            "Panadería López SL",
            "B12345678",
            "Calle Mayor 1",
            "Madrid",
            "28001",
            "ES",
            "pagos@lopez.es",
        )
        assert recorded.payer_account_id == owner.id
        assert recorded.billing_profile_id == running.billing_profile_id
        assert recorded.language == "es"

    def test_every_delivery_of_one_payment_records_it_once(self, running):
        deliver(paid())
        deliver(paid())
        deliver(event("invoice.payment_succeeded", invoice("in_1", status="paid")))

        assert Invoice.objects.count() == 1
        assert InvoiceCounter.objects.get(series="ERP").last_number == 1

    def test_the_next_paid_invoice_takes_the_next_number(self, running):
        deliver(paid("in_1"))
        deliver(paid("in_2"))

        assert sorted(Invoice.objects.values_list("number", flat=True)) == [
            f"ERP-{YEAR}-00001",
            f"ERP-{YEAR}-00002",
        ]

    def test_without_the_live_subscription_nothing_is_written_nor_numbered(
        self, running, stripe_double
    ):
        """The invoice goes in the transaction that applies the subscription: Stripe not answering is a 500 for
        Stripe's retry, and the number goes back to the counter."""
        stripe_double.answer("subscriptions.retrieve", connection_error())

        deliver(paid(), status=500)

        assert not Invoice.objects.exists()
        assert not InvoiceCounter.objects.filter(last_number__gt=0).exists()


class TestTheVatOfEachSale:
    def test_a_verified_eu_business_is_reverse_charge_and_keeps_the_proof(
        self, running
    ):
        payer(
            running,
            billing_country="DE",
            billing_postal_code="91710",
            tax_id="DE812871812",
        )
        with vies_says(**VALID):
            deliver(paid(amount_due=2999, tax=0))

        recorded = Invoice.objects.get()
        assert (recorded.tax_treatment, recorded.tax_cents, recorded.net_cents) == (
            "reverse_charge",
            0,
            2999,
        )
        assert recorded.payer_tax_id_verified is True
        assert recorded.vat_consultation_number == "WAPIAAAAXjHIQOZ"
        assert list(recorded.lines.values_list("tax_rate", "tax_cents")) == [
            (Decimal("0.00"), 0)
        ]

    def test_an_unverified_number_is_charged_vat_and_reconciled_when_stripe_charged_none(
        self, running
    ):
        payer(
            running,
            billing_country="DE",
            billing_postal_code="10115",
            tax_id="DE999999999",
        )
        with vies_says(**NOT_REGISTERED):
            deliver(paid(amount_due=2999, tax=0))

        recorded = Invoice.objects.get()
        assert recorded.tax_treatment == "domestic"
        assert recorded.vat_included_reconciled is True
        assert (recorded.net_cents, recorded.tax_cents, recorded.total_cents) == (
            2479,
            520,
            2999,
        )
        assert recorded.payer_tax_id_verified is False
        assert recorded.vat_consultation_number == ""
        assert recorded.vat_included_because_unverified is True

    def test_the_proof_does_not_change_when_the_customer_edits_their_number(
        self, running
    ):
        payer(
            running,
            billing_country="DE",
            billing_postal_code="91710",
            tax_id="DE812871812",
        )
        with vies_says(**VALID):
            deliver(paid(amount_due=2999, tax=0))
        payer(running, tax_id="DE999999999")

        assert Invoice.objects.get().vat_consultation_number == "WAPIAAAAXjHIQOZ"

    def test_an_oss_sale_carries_the_destination_rate_on_every_line(
        self, running, inventory
    ):
        FiscalPolicy.objects.update(oss_registered=True)
        payer(running, billing_country="DE", billing_postal_code="10115")
        deliver(paid(lines=[invoice_line(tax=570), module_line(tax=190)]))

        recorded = Invoice.objects.get()
        assert (recorded.tax_treatment, recorded.tax_country, recorded.tax_rate) == (
            "oss",
            "DE",
            Decimal("19.00"),
        )
        assert list(recorded.lines.values_list("tax_rate", "tax_cents")) == [
            (Decimal("19.00"), 570),
            (Decimal("19.00"), 190),
        ]

    def test_the_canary_islands_are_not_subject(self, running):
        payer(running, billing_postal_code="35001")
        deliver(paid(amount_due=2999, tax=0))

        recorded = Invoice.objects.get()
        assert (recorded.tax_treatment, recorded.tax_cents, recorded.net_cents) == (
            "not_subject",
            0,
            2999,
        )

    def test_a_customer_outside_the_eu_is_not_subject(self, running):
        payer(running, billing_country="US", billing_postal_code="10001")
        deliver(paid(amount_due=2999, tax=0))

        assert Invoice.objects.get().tax_treatment == "not_subject"


class TestVies_atInvoicing:
    """At invoicing, the VAT number is judged as of the day it was charged (review of L3-C): the last proof VIES
    gave until then, even older than the 30 days a SALE trusts; VIES being down never puts Spanish VAT on an
    intra-EU B2B sale. Without any proof and with VIES down, the invoice waits: 500, Stripe retries."""

    def proof(self, *, days_ago, status="verified", consultation="WAPIAAAAXold"):
        from datetime import timedelta

        from billing.models import VatCheck

        return VatCheck.objects.create(
            vat_number="DE812871812", status=status, consultation_number=consultation,
            requested_at=timezone.now() - timedelta(days=days_ago),
        )

    def german_business(self, hub):
        payer(hub, billing_country="DE", billing_postal_code="91710", tax_id="DE812871812")

    def test_a_proof_older_than_a_month_keeps_the_reverse_charge_while_vies_is_down(self, running):
        from billing.tests.vies_double import MEMBER_STATE_DOWN

        self.german_business(running)
        self.proof(days_ago=31)
        with vies_says(**MEMBER_STATE_DOWN):
            deliver(paid(amount_due=2999, tax=0))

        recorded = Invoice.objects.get()
        assert (recorded.tax_treatment, recorded.tax_cents) == ("reverse_charge", 0)
        assert (recorded.payer_tax_id_verified, recorded.vat_consultation_number) == (True, "WAPIAAAAXold")

    def test_the_proof_of_the_charge_day_needs_nobody_to_ask(self, running):
        self.german_business(running)
        self.proof(days_ago=40)
        with no_network() as network:
            deliver(paid(amount_due=2999, tax=0))

        assert network.call_count == 0
        assert Invoice.objects.get().tax_treatment == "reverse_charge"

    def test_a_number_vies_refused_before_the_charge_pays_vat(self, running):
        self.german_business(running)
        self.proof(days_ago=40)
        self.proof(days_ago=5, status="invalid", consultation="")
        with no_network():
            deliver(paid(amount_due=2999, tax=0))

        assert Invoice.objects.get().tax_treatment == "domestic"

    def test_without_any_proof_and_vies_down_the_invoice_waits(self, running):
        from billing.tests.vies_double import vies_is_down

        self.german_business(running)
        with vies_is_down():
            deliver(paid(amount_due=2999, tax=0), status=500)

        assert not Invoice.objects.exists()
        assert not InvoiceCounter.objects.filter(last_number__gt=0).exists()

    def test_a_proof_after_the_charge_is_still_asked_for_when_none_came_before(self, running):
        self.german_business(running)
        with vies_says(**VALID):
            deliver(paid(amount_due=2999, tax=0))

        assert Invoice.objects.get().vat_consultation_number == "WAPIAAAAXjHIQOZ"


class TestAnUnpaidInvoiceIsListed:
    def failed(self, stripe_double, invoice_id="in_1"):
        from billing.tests.stripe_double import invoice_payment, listing, payment_intent

        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
        stripe_double.answer(
            "invoice_payments.list",
            listing([invoice_payment("pi_1", invoice_id=invoice_id)]),
        )
        stripe_double.answer("payment_intents.retrieve", payment_intent("pi_1"))
        return deliver(event("invoice.payment_failed", invoice(invoice_id)))

    def test_a_failed_renewal_is_listed_without_a_number(self, running, stripe_double):
        self.failed(stripe_double)

        listed = Invoice.objects.get()
        assert (listed.payment_status, listed.number, listed.fiscal_status) == (
            "open",
            "",
            "",
        )
        assert listed.total_cents == 3629
        assert listed.stripe_number == "ABCDIN_1-0001"
        assert listed.hosted_invoice_url == "https://invoice.stripe.com/i/test_1"
        assert not InvoiceCounter.objects.exists()

    def test_paying_it_numbers_the_same_row(self, running, stripe_double):
        self.failed(stripe_double)
        stripe_double.answer("subscriptions.retrieve", subscription())

        deliver(paid())

        recorded = Invoice.objects.get()
        assert (recorded.payment_status, recorded.number) == (
            "paid",
            f"ERP-{YEAR}-00001",
        )

    @pytest.mark.parametrize(
        "event_type", ["invoice.voided", "invoice.marked_uncollectible"]
    )
    def test_one_stripe_gave_up_on_is_void(self, running, stripe_double, event_type):
        self.failed(stripe_double)

        assert deliver(event(event_type, invoice("in_1", status="void"))) == "processed"

        assert Invoice.objects.get().payment_status == "void"

    def test_a_void_one_paid_after_all_is_invoiced(self, running, stripe_double):
        self.failed(stripe_double)
        deliver(
            event(
                "invoice.marked_uncollectible", invoice("in_1", status="uncollectible")
            )
        )
        stripe_double.answer("subscriptions.retrieve", subscription())

        deliver(paid())

        assert Invoice.objects.get().payment_status == "paid"

    def test_voiding_an_invoice_we_do_not_list_changes_nothing(self, running):
        assert (
            deliver(event("invoice.voided", invoice("in_9", status="void")))
            == "ignored"
        )

        assert not Invoice.objects.exists()


class TestEveryPaymentIsInvoiced:
    """A paid Stripe invoice is never forgotten (review of L3-C): one of a business ERPlora knows is invoiced to
    it even when it is not its current subscription (the first invoice of a duplicate checkout, which is
    cancelled with its unused time as credit); one nobody can place is a 500 that Stripe retries, logged."""

    def test_the_first_invoice_of_a_duplicate_checkout_is_invoiced_to_its_business(self, running, stripe_double):
        duplicate = invoice("in_dup", subscription_id="sub_dup", status="paid")
        duplicate["parent"]["subscription_details"]["metadata"] = {"hub_id": str(running.id)}

        assert deliver(event("invoice.paid", duplicate)) == "processed"

        recorded = Invoice.objects.get()
        assert (recorded.hub_id, recorded.stripe_invoice_id, recorded.payment_status) == (running.id, "in_dup", "paid")
        assert stripe_double.calls_to("subscriptions.retrieve") == []

    def test_a_paid_invoice_nobody_can_place_is_retried(self, running):
        stray = invoice("in_stray", subscription_id="sub_unknown", status="paid")

        deliver(event("invoice.paid", stray), status=500)

        assert not Invoice.objects.exists()

    def test_a_paid_invoice_of_nothing_with_nothing_charged_is_ignored(self, running):
        assert deliver(event("invoice.paid", invoice("in_zero", subscription_id="sub_unknown", status="paid",
                                                     amount_due=0, tax=0))) in ("unknown", "ignored")

    def test_lines_that_do_not_add_up_to_the_charge_are_never_invoiced(self, running):
        """The invoice says what was charged or nothing: a 500 for Stripe's retry and support's eyes, no
        number spent (review of L3-C)."""
        odd = invoice("in_odd", status="paid", lines=[invoice_line()])
        odd["total"] = 4000

        deliver(event("invoice.paid", odd), status=500)

        assert not Invoice.objects.exists()
        assert not InvoiceCounter.objects.filter(last_number__gt=0).exists()


class TestCreditNotes:
    def test_a_credit_note_rectifies_the_invoice_in_its_own_series(self, running):
        deliver(paid())

        assert deliver(event("credit_note.created", credit_note())) == "processed"

        original, rectifying = (
            Invoice.objects.get(kind="invoice"),
            Invoice.objects.get(kind="credit_note"),
        )
        assert (rectifying.number, rectifying.rectifies_id) == (
            f"ERPR-{YEAR}-00001",
            original.id,
        )
        assert (rectifying.net_cents, rectifying.tax_cents, rectifying.total_cents) == (
            -2999,
            -630,
            -3629,
        )
        assert (rectifying.tax_treatment, rectifying.tax_rate) == (
            original.tax_treatment,
            original.tax_rate,
        )
        assert (rectifying.payer_name, rectifying.payer_tax_id) == (
            original.payer_name,
            original.payer_tax_id,
        )
        assert rectifying.payment_status == "paid"
        assert list(rectifying.lines.values_list("net_cents", "tax_cents")) == [
            (-2999, -630)
        ]

    def test_a_partial_credit_rectifies_only_what_it_credits(self, running):
        deliver(paid())

        deliver(
            event(
                "credit_note.created",
                credit_note(lines=[credit_note_line(amount=1000, tax=210)]),
            )
        )

        assert Invoice.objects.get(kind="credit_note").total_cents == -1210

    def test_it_is_recorded_once(self, running):
        deliver(paid())
        deliver(event("credit_note.created", credit_note()))
        deliver(event("credit_note.created", credit_note()))

        assert Invoice.objects.filter(kind="credit_note").count() == 1

    def test_a_credit_note_ahead_of_its_invoice_waits_for_it(self, running):
        """Stripe does not order events: a credit note whose invoice is not recorded yet is a 500, retried
        after ``invoice.paid`` (review of L3-C: never «unknown» and forgotten)."""
        deliver(event("credit_note.created", credit_note()), status=500)
        assert not Invoice.objects.exists()

        deliver(paid())
        assert deliver(event("credit_note.created", credit_note())) == "processed"

        assert Invoice.objects.filter(kind="credit_note").count() == 1

    def test_a_credit_note_says_why_it_rectifies(self, running):
        deliver(paid())
        note = credit_note(reason="duplicate")
        note["memo"] = "Cobro duplicado"

        deliver(event("credit_note.created", note))

        rectifying = Invoice.objects.get(kind="credit_note")
        assert (rectifying.rectification_type, rectifying.rectification_reason) == ("R1", "Cobro duplicado")

    def test_a_fraudulent_charge_is_rectified_as_other(self, running):
        deliver(paid())

        deliver(event("credit_note.created", credit_note(reason="fraudulent")))

        assert Invoice.objects.get(kind="credit_note").rectification_type == "R4"


@pytest.mark.django_db(transaction=True)
def test_two_businesses_paid_at_once_take_consecutive_numbers(
    owner, plans, stripe_double, issuer_identity
):
    """Two ``invoice.paid`` of two businesses at the same instant: two consecutive numbers, no gap, none twice."""
    from io import StringIO

    from django.core.management import call_command

    from hubs.tests.conftest import create_business

    # A transactional test starts from a flushed database: the tax data the migration seeds is put back.
    call_command("seed_tax_rules", stdout=StringIO())

    first = pay(create_business(owner, name="Uno"), sub_id="sub_a", customer="cus_a")
    second = pay(create_business(owner, name="Dos"), sub_id="sub_b", customer="cus_b")
    stripe_double.answer(
        "subscriptions.retrieve",
        lambda call: subscription(
            call.args[0], customer={"sub_a": "cus_a", "sub_b": "cus_b"}[call.args[0]]
        ),
    )
    start = threading.Barrier(2)
    outcomes: list = []

    def deliver_paid(invoice_id, subscription_id):
        try:
            start.wait(timeout=5)
            outcomes.append(
                deliver(
                    event(
                        "invoice.paid",
                        invoice(
                            invoice_id, subscription_id=subscription_id, status="paid"
                        ),
                    )
                )
            )
        except BaseException as error:  # noqa: BLE001 - reported below
            outcomes.append(error)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=deliver_paid, args=("in_a", "sub_a")),
        threading.Thread(target=deliver_paid, args=("in_b", "sub_b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert outcomes == ["processed", "processed"]
    assert sorted(Invoice.objects.values_list("sequence", flat=True)) == [1, 2]
    assert set(Invoice.objects.values_list("hub_id", flat=True)) == {
        first.id,
        second.id,
    }
    assert (
        InvoiceCounter.objects.get(series="ERP", year=date.today().year).last_number
        == 2
    )


def test_the_payer_and_the_owner_both_hear_of_a_new_invoice(running, owner, make_user, monkeypatch,
                                                           django_capture_on_commit_callbacks):
    """Review of L3-C: an invoice is seen by its payer and by the owner of its business; when they are two
    accounts, both their Billing lists re-run after the COMMIT."""
    from live import operations

    from billing import services

    payer_account = make_user("payer@example.com")
    BillingProfile.objects.filter(pk=running.billing_profile_id).update(owner=payer_account)
    heard = []
    monkeypatch.setattr(operations, "notify_hook", lambda scope, names: heard.append((scope.key, set(names))))
    monkeypatch.setattr(services, "notify", lambda scope, names: heard.append((scope.key, set(names))))

    with django_capture_on_commit_callbacks(execute=True):
        deliver(paid())

    told = {key for key, names in heard if "billing.invoice.recorded" in names}
    assert told == {str(owner.id), str(payer_account.id)}
