"""For now ERPlora sells only to payers billed in Spain (BILLING-F02).

Every new sale reads where the payer is before Stripe is called: a plan, a change of plan or a module. A payer
of another country is refused with 409 ``billing.country_not_sold``. That includes a business whose VAT number
VIES proves, so no sale is reverse charged. The Canary Islands, Ceuta and Melilla are sold to without VAT, but
only to businesses and professionals. A consumer there would owe IGIC or IPSI that only a supplier registered
there may charge, so a payer without a tax ID gets 409 ``billing.business_required``. What a payer of another
country already pays keeps renewing: the daily retax still prices it with the engine and is never refused for
the country.
"""

import pytest

from billing.models import CheckoutAttempt
from billing.services import live_rates
from billing.tests.checkout_calls import payer, refused, session_params, start
from billing.tests.conftest import pay
from billing.tests.stripe_double import item, preview, subscription
from billing.tests.vies_double import REAL_VAT, VALID, vies_says

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def paying(shop, stripe_double):
    paid = pay(shop)
    line = [item("si_plan", "price_starter_month")]
    stripe_double.answer("subscriptions.retrieve", subscription("sub_1", customer="cus_1", items=line))
    stripe_double.answer("subscriptions.update", subscription("sub_1", customer="cus_1", items=line))
    stripe_double.answer("invoices.create_preview", preview())
    return paid


class TestOnlyAPayerInSpainBuys:
    @pytest.mark.parametrize("country, postal_code", [("DE", "10115"), ("PT", "1000-001"), ("FR", "75001")])
    def test_a_payer_elsewhere_in_the_eu_is_not_sold_a_plan(self, shop, owner, stripe_double, country, postal_code):
        payer(shop, billing_country=country, billing_postal_code=postal_code)

        error = refused("billing.country_not_sold", lambda: start(owner, shop, plan="starter"))

        assert error.status == 409
        assert stripe_double.calls == []
        assert CheckoutAttempt.objects.count() == 0

    def test_nor_a_module(self, shop, owner, inventory, stripe_double):
        payer(shop, billing_country="DE", billing_postal_code="10115")

        refused("billing.country_not_sold", lambda: start(owner, shop, module="inventory"))

        assert stripe_double.calls == []

    def test_nor_a_business_whose_vat_number_vies_proves(self, shop, owner, stripe_double):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

        with vies_says(**VALID):
            refused("billing.country_not_sold", lambda: start(owner, shop, plan="starter"))

        assert stripe_double.calls_to("checkout.sessions.create") == []

    def test_a_business_already_paying_from_elsewhere_cannot_change_its_plan(self, shop, owner, stripe_double):
        paid = paying(shop, stripe_double)
        payer(paid, billing_country="DE", billing_postal_code="10115")

        refused("billing.country_not_sold", lambda: start(owner, paid, plan="standard"))

        assert stripe_double.calls_to("invoices.create_preview") == []

    def test_a_payer_in_spain_buys(self, shop, owner, stripe_double):
        assert start(owner, shop, plan="starter")["flow"] == "checkout"


class TestTheCanaryIslandsCeutaAndMelilla:
    @pytest.mark.parametrize("postal_code", ["35001", "38001", "51001", "52001"])
    def test_a_consumer_there_is_not_sold_to(self, shop, owner, stripe_double, postal_code):
        payer(shop, billing_postal_code=postal_code, tax_id="")

        error = refused("billing.business_required", lambda: start(owner, shop, plan="starter"))

        assert error.status == 409
        assert stripe_double.calls == []

    @pytest.mark.parametrize("postal_code", ["35001", "38001", "51001", "52001"])
    def test_a_business_there_pays_the_net_without_vat(self, shop, owner, stripe_double, postal_code):
        payer(shop, billing_postal_code=postal_code, tax_id="ESB27593136")

        start(owner, shop, plan="starter")

        assert session_params(stripe_double)["line_items"][0]["tax_rates"] == []

    def test_a_consumer_on_the_mainland_still_buys_with_vat(self, shop, owner, stripe_double):
        payer(shop, billing_postal_code="28001", tax_id="")

        start(owner, shop, plan="starter")

        assert stripe_double.last("tax_rates.create").params["percentage"] == 21.0


class TestWhatIsAlreadyPaidKeepsRenewing:
    def test_a_payer_elsewhere_in_the_eu_is_still_retaxed_by_the_engine(self, shop, stripe_double):
        paid = paying(shop, stripe_double)
        payer(paid, billing_country="DE", billing_postal_code="10115")

        assert live_rates.retax_subscription(paid) == "retaxed"
        rate = stripe_double.tax_rates[0]
        assert (rate["country"], rate["percentage"]) == ("ES", 21.0)

    def test_a_consumer_in_the_canary_islands_is_still_retaxed_by_the_engine(self, shop, stripe_double):
        paid = paying(shop, stripe_double)
        payer(paid, billing_postal_code="35001", tax_id="")

        assert live_rates.retax_subscription(paid) in {"retaxed", "unchanged"}
