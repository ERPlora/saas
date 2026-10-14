"""The payer's VAT id is what prices the sale, even when Stripe's session does not echo it (saas#1621).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_payer_vat_reaches_the_invoice.py``
(origin/develop, 6 tests). The VAT id is typed in OUR form (``hubs.BillingProfile.tax_id``), contrasted
against VIES, and only a cleared one reaches Stripe: the fact that survives is the payer's profile,
which ``billing.queries.payer_of`` reads for every door that sells. The verdict is never seeded: only
the network is faked.

Adapted (no ``Invoice`` in this lot): the four cases are proved on what the sale door decides
(``billing.services.sale_quote``) and on the clearance that carries the proof. Moved: «a UK business with
no VAT number is named by its Companies House number» needs ``BillingProfile.uk_business_*`` (L2-B) and
«the renewal invoice keeps the payer's VAT id» needs the ``invoice.payment_succeeded`` webhook (L2-B)
and ``Invoice`` (L3-C).
"""

from decimal import Decimal

import pytest

from billing import queries, services
from billing.tests.vies_double import (
    FAKE_VAT,
    NOT_REGISTERED,
    REAL_VAT,
    VALID,
    no_network,
    vies_says,
)

pytestmark = pytest.mark.django_db

PLAN = "service.saas_subscription"


@pytest.fixture(autouse=True)
def _issuer(issuer_identity):
    return issuer_identity


def _quote(business):
    return services.sale_quote(business, category_key=PLAN, price=Decimal("100.00"))


class TestThePayerIsTheSource:
    def test_a_proved_vat_id_prices_the_sale_and_keeps_its_proof(
        self, business_paid_by
    ):
        business = business_paid_by("DE", "10115", tax_id=REAL_VAT)

        with vies_says(**VALID):
            quote = _quote(business)
            payer = queries.payer_of(business)
            clearance = services.clear_tax_id_for_stripe(
                payer.tax_id, customer_country=payer.country
            )

        assert (payer.tax_id, payer.tax_id_type) == (REAL_VAT, "eu_vat")
        assert quote.treatment == "reverse_charge"
        assert clearance.check.consultation_number, "the proof travels with the sale"

    def test_an_unproved_vat_id_is_kept_but_grants_nothing(self, business_paid_by):
        """It identifies the buyer; it just does not buy reverse charge."""
        business = business_paid_by("DE", "10115", tax_id=FAKE_VAT)

        with vies_says(**NOT_REGISTERED):
            quote = _quote(business)

        assert queries.payer_of(business).tax_id == FAKE_VAT
        assert quote.treatment != "reverse_charge"

    def test_a_payer_with_no_vat_id_changes_nothing(self, business_paid_by):
        business = business_paid_by("DE", "10115")

        with no_network() as network:
            quote = _quote(business)

        network.assert_not_called()
        assert queries.payer_of(business).tax_id == ""
        assert quote.treatment == "domestic"

    def test_a_country_stripe_has_no_tax_id_type_for_is_not_guessed(
        self, business_paid_by
    ):
        """A wrong type makes Stripe reject the number, so an unknown country's id stays out."""
        business = business_paid_by("US", "10001", tax_id="US-123456")

        with no_network() as network:
            payer = queries.payer_of(business)

        network.assert_not_called()
        assert (payer.country, payer.tax_id, payer.tax_id_type) == ("US", "", "")
