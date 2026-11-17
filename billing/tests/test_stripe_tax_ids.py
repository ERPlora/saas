"""A payer's tax id on its Stripe customer: in the form Stripe takes, and never in the way of a sale.

Stripe takes an ``eu_vat`` only with its country's prefix: ``X1234567L`` is refused (``tax_id_invalid``, «Invalid
value for eu_vat.»), ``ESX1234567L`` taken. A Spanish payer's NIF, NIE or CIF is kept as typed, without ``ES``, so it
travels with the prefix in front. Whatever Stripe still refuses is logged and the checkout or the save goes on:
ERPlora's invoices take the tax id from the billing profile, never from Stripe. Stripe not answering is not a
refusal, and still asks to try again.

Every payer can pay: a person with a NIE or a DNI, a company VIES does not know and anyone while VIES is down are
charged Spanish VAT and named on ERPlora's invoice as they typed it.
"""

import logging

import pytest

from billing.models import Invoice
from billing.tests.conftest import pay
from billing.tests.stripe_double import connection_error, event, invoice, subscription, tax_id_invalid
from billing.tests.test_checkout import payer, refused, session_params, start
from billing.tests.test_invoice_recording import deliver
from billing.tests.test_payer_details_to_stripe import paying, save
from billing.tests.vies_double import NOT_REGISTERED, no_network, vies_is_down, vies_says

pytestmark = pytest.mark.django_db

#: Made-up numbers with their right control character: a foreigner's NIE, a DNI and a company's CIF.
NIE, DNI, CIF = "X1234567L", "12345678Z", "B12345674"
REFUSED_EVENT = "billing.stripe_tax_id_refused"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def events(caplog, name):
    return [record for record in caplog.records if getattr(record, "event", "") == name]


def save_in_madrid(owner, hub, tax_id, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        save(owner, hub, billing_postal_code="28001", billing_city="Madrid", tax_id=tax_id)


def charged(hub, stripe_double):
    """Stripe charges the first month and says so: ERPlora's invoice is recorded from its webhook."""
    pay(hub)
    stripe_double.answer("subscriptions.retrieve", subscription())
    deliver(event("invoice.paid", invoice("in_1", status="paid")))
    return Invoice.objects.get()


class TestEveryPayerCanPay:
    """VIES only decides whether a customer of another member state is reverse charged, never who may buy."""

    @pytest.mark.parametrize(
        "typed, vies",
        [
            (NIE, no_network),
            (DNI, no_network),
            (CIF, lambda: vies_says(**{**NOT_REGISTERED, "countryCode": "ES", "vatNumber": CIF})),
            ("ESB12345674", vies_is_down),
        ],
        ids=["a person with a NIE", "a person with a DNI", "a company VIES does not know", "VIES not answering"],
    )
    def test_the_payment_opens_with_spanish_vat_and_the_invoice_names_them(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks, typed, vies
    ):
        with vies():
            save_in_madrid(owner, shop, typed, django_capture_on_commit_callbacks)
            answer = start(owner, shop, plan="starter")
            vat_rate = stripe_double.last("tax_rates.create").params["percentage"]
            recorded = charged(shop, stripe_double)

        assert answer["flow"] == "checkout"
        assert vat_rate == 21.0
        assert (recorded.payer_tax_id, recorded.tax_treatment, recorded.tax_rate, recorded.tax_cents) == (
            typed,
            "domestic",
            21,
            630,
        )

    def test_a_tax_id_stripe_refuses_is_still_on_erplora_s_invoice(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        stripe_double.answer("customers.tax_ids.create", tax_id_invalid("eu_vat"))

        with no_network():
            save_in_madrid(owner, shop, CIF, django_capture_on_commit_callbacks)
            answer = start(owner, shop, plan="starter")
            recorded = charged(shop, stripe_double)

        assert answer["flow"] == "checkout"
        assert stripe_double.customer_tax_ids == {}
        assert recorded.payer_tax_id == CIF


class TestASpanishTaxIdTravelsWithItsPrefix:
    @pytest.mark.parametrize(
        "typed, sent", [(NIE, "ESX1234567L"), (DNI, "ES12345678Z"), (CIF, "ESB12345674")]
    )
    def test_the_payment_opens_and_the_customer_takes_it(self, shop, owner, stripe_double, typed, sent):
        payer(shop, tax_id=typed)

        with no_network():
            answer = start(owner, shop, plan="starter")

        assert answer["flow"] == "checkout"
        assert stripe_double.last("customers.tax_ids.create").params == {"type": "eu_vat", "value": sent}

    def test_the_billing_profile_keeps_it_as_typed(self, shop, owner, django_capture_on_commit_callbacks):
        from hubs.models import BillingProfile

        with no_network():
            save_in_madrid(owner, shop, "x-1234567-l", django_capture_on_commit_callbacks)

        assert BillingProfile.objects.get(pk=shop.billing_profile_id).tax_id == NIE

    def test_saving_the_billing_details_brings_it_to_the_customer(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks, caplog
    ):
        paid = paying(shop, stripe_double)

        with caplog.at_level(logging.ERROR, logger="billing"), no_network():
            save_in_madrid(owner, paid, "x-1234567-l", django_capture_on_commit_callbacks)

        created = stripe_double.last("customers.tax_ids.create")
        assert created.args[0] == "cus_1"
        assert created.params == {"type": "eu_vat", "value": "ESX1234567L"}
        assert events(caplog, "billing.customer_push_failed") == []

    def test_one_already_on_the_customer_with_its_prefix_is_not_added_again(self, shop, owner, stripe_double):
        payer(shop, tax_id=NIE, stripe_customer_id="cus_known")
        stripe_double.customer_tax_ids["cus_known"] = [{"id": "txi_1", "type": "eu_vat", "value": "ESX1234567L"}]

        start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.tax_ids.create") == []

    def test_one_typed_with_its_prefix_travels_as_it_is(self, shop, owner, stripe_double):
        payer(shop, tax_id="ESX1234567L")

        start(owner, shop, plan="starter")

        assert stripe_double.last("customers.tax_ids.create").params == {"type": "eu_vat", "value": "ESX1234567L"}


class TestStripeRefusingTheTaxIdStopsNothing:
    def test_the_payment_still_opens_and_the_refusal_is_logged(self, shop, owner, stripe_double, caplog):
        payer(shop, tax_id=CIF)
        stripe_double.answer("customers.tax_ids.create", tax_id_invalid("eu_vat"))

        with caplog.at_level(logging.ERROR, logger="billing"):
            answer = start(owner, shop, plan="starter")

        assert answer["flow"] == "checkout"
        assert session_params(stripe_double)["customer"] == "cus_new"
        [logged] = events(caplog, REFUSED_EVENT)
        assert logged.levelno == logging.ERROR
        assert logged.code == "tax_id_invalid"
        assert CIF not in logged.getMessage()

    def test_saving_the_billing_details_still_updates_the_customer(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks, caplog
    ):
        paid = paying(shop, stripe_double)
        stripe_double.answer("customers.tax_ids.create", tax_id_invalid("eu_vat"))

        with caplog.at_level(logging.ERROR, logger="billing"), no_network():
            save_in_madrid(owner, paid, CIF, django_capture_on_commit_callbacks)

        assert stripe_double.last("customers.update").params["address"]["city"] == "Madrid"
        assert events(caplog, "billing.customer_push_failed") == []
        assert len(events(caplog, REFUSED_EVENT)) == 1

    def test_stripe_not_answering_still_asks_to_try_again(self, shop, owner, stripe_double):
        payer(shop, tax_id=CIF)
        stripe_double.answer("customers.tax_ids.create", connection_error())

        refused("billing.stripe_unavailable", lambda: start(owner, shop, plan="starter"))

        assert stripe_double.calls_to("checkout.sessions.create") == []
