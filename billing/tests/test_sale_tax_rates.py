"""The TWO doors that sell charge the same tax to the same buyer (saas#1992).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_sale_tax_rates.py`` (origin/develop, 6 tests).
The SaaS sells a business's plan and a paid module, and each door used to decide the tax on its own:
the same customer in Las Palmas got a right plan invoice and a module overcharged by 21 %. The decision
lives in ONE place, ``billing.services.sale_tax_rates``, and is tested here.

Adapted: it answers with the rates Stripe must charge as ``TaxRateSpec`` (``billing.stripe_tax_rates``),
which lot L2-B mirrors into Stripe ``TaxRate`` ids; a sale that cannot be priced raises the 409
``billing.tax_engine_missing`` / ``billing.billing_location_required`` instead of returning a refusal
dict. The old ``test_si_el_espejo_de_stripe_falla_se_niega_la_venta`` (the Stripe mirror down) moves
to L2-B with the mirror.
"""

from decimal import Decimal

import pytest
from live.errors import Conflict

from billing import services

pytestmark = pytest.mark.django_db

#: The two categories sold today: the SAME keys the invoices of each door use.
PLAN = "service.saas_subscription"
MODULE = "service.software_license"

MADRID = "28001"
LAS_PALMAS = "35001"


def _percentages(specs) -> list[Decimal]:
    return [spec.percentage for spec in specs]


class TestBothDoorsChargeTheSame:
    def test_the_mainland_pays_21_percent_whatever_it_buys(self, business_paid_by):
        business = business_paid_by("ES", MADRID)

        plan = services.sale_tax_rates(
            business, category_key=PLAN, price=Decimal("29.99")
        )
        module = services.sale_tax_rates(
            business, category_key=MODULE, price=Decimal("100.00")
        )

        assert _percentages(plan) == _percentages(module) == [Decimal("21.00")]

    def test_the_canaries_pay_none_whatever_they_buy(self, business_paid_by):
        """An EMPTY list is an answer, not a failure: outside the scope of VAT."""
        business = business_paid_by("ES", LAS_PALMAS)

        assert (
            services.sale_tax_rates(business, category_key=PLAN, price=Decimal("29.99"))
            == []
        )
        assert (
            services.sale_tax_rates(
                business, category_key=MODULE, price=Decimal("100.00")
            )
            == []
        )


class TestWhatIsFreeIsNeverRefused:
    """21 % of nothing is nothing, and the Free plan is the only way in (ADR-0154)."""

    def test_a_zero_amount_needs_neither_rate_nor_address(self, business_paid_by):
        nowhere = business_paid_by(None)

        assert (
            services.sale_tax_rates(nowhere, category_key=MODULE, price=Decimal("0.00"))
            == []
        )
        assert services.require_billing_location(nowhere, price=Decimal("0.00")) is None


class TestWithoutKnowingWhereThePayerIsNothingIsSold:
    def test_without_country_and_postal_code_it_is_refused(self, business_paid_by):
        """saas#1972: the postal code is the ONLY thing that tells Las Palmas from Madrid."""
        nowhere = business_paid_by(None)

        with pytest.raises(Conflict) as refused:
            services.require_billing_location(
                nowhere, price=Decimal("100.00"), what="module"
            )

        assert refused.value.status == 409
        assert refused.value.code == "billing.billing_location_required"

    def test_a_country_without_postal_code_is_not_a_location(self, business_paid_by):
        with pytest.raises(Conflict):
            services.require_billing_location(
                business_paid_by("ES", ""), price=Decimal("100.00")
            )

    def test_with_the_address_on_file_it_is_not_refused(self, business_paid_by):
        assert (
            services.require_billing_location(
                business_paid_by("ES", MADRID), price=Decimal("100.00")
            )
            is None
        )


class TestASpanishPostalCodeHasFiveDigits:
    """«3500» is Benidorm without its leading 0, not Las Palmas (review of L2-A, finding 1)."""

    def test_benidorm_without_its_zero_is_asked_for_its_address(self, business_paid_by):
        business = business_paid_by("ES", "3500")

        with pytest.raises(Conflict) as refused:
            services.sale_tax_rates(business, category_key=PLAN, price=Decimal("29.99"))

        assert refused.value.code == "billing.billing_location_required"
        with pytest.raises(Conflict):
            services.require_billing_location(business, price=Decimal("29.99"))

    def test_benidorm_with_its_zero_pays_21_percent(self, business_paid_by):
        assert _percentages(services.sale_tax_rates(business_paid_by("ES", "03500"), category_key=PLAN, price=Decimal("29.99"))) == [
            Decimal("21.00")
        ]


class TestASaleThatCannotKnowItsRateIsNotMade:
    def test_a_territory_without_a_rule_is_refused_naming_what_was_sold(
        self, business_paid_by
    ):
        """The rate would be a guess and the price is net: refusing is loud and reversible."""
        abroad = business_paid_by("US", "10001")

        with pytest.raises(Conflict) as refused:
            services.sale_tax_rates(
                abroad, category_key=MODULE, price=Decimal("100.00"), what="module"
            )

        assert refused.value.code == "billing.tax_engine_missing"
        assert "this module cannot be sold" in refused.value.message

    def test_the_refusal_is_a_whole_sentence_in_the_buyers_language(self, business_paid_by):
        """No noun glued into a sentence: each thing sold has its own translated sentence."""
        from django.utils import translation

        abroad = business_paid_by("US", "10001")

        with translation.override("es"), pytest.raises(Conflict) as refused:
            services.sale_tax_rates(abroad, category_key=PLAN, price=Decimal("29.99"), what="plan")

        assert "este plan" in refused.value.message
