"""What Stripe must charge for a quote OUR engine resolved, in Stripe's vocabulary (saas#1968).

The rate is decided by ``billing.TaxRule``; Stripe only charges it, and on a net price it needs it as a
``TaxRate`` object (``default_tax_rates``). This lot (L2-A) stops before Stripe: ``tax_rate_specs_for``
says WHICH rates (country, region, percentage, exclusive), and ``matches`` says whether an existing
Stripe ``TaxRate`` is the one; lot L2-B finds or creates them (``TaxRate.list``/``create``) by
``spec.cache_key``. The cases are those of ERPlora/saas ``fiscal/services/stripe_tax_rates.py``
(origin/develop), which had no test file of its own (its cases ran inside ``test_sale_tax_rates``).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from billing.stripe_tax_rates import TaxRateSpec, matches, tax_rate_specs_for
from billing.vat import DOMESTIC, NOT_SUBJECT, OSS, REVERSE_CHARGE, VatBreakdown


def _quote(treatment, rate, country="ES", region=""):
    return VatBreakdown(
        base=Decimal("100.00"),
        tax=Decimal("0.00"),
        rate=Decimal(rate),
        tax_country=country,
        treatment=treatment,
        tax_region=region,
    )


class TestWhichRates:
    def test_a_subject_sale_carries_its_rate_on_top_of_the_net_price(self):
        assert tax_rate_specs_for(_quote(DOMESTIC, "21.00")) == [
            TaxRateSpec(country="ES", region="", percentage=Decimal("21.00"))
        ]

    def test_an_oss_sale_carries_the_customers_rate_and_country(self):
        [spec] = tax_rate_specs_for(_quote(OSS, "19.00", country="DE"))

        assert (spec.country, spec.percentage, spec.inclusive) == (
            "DE",
            Decimal("19.00"),
            False,
        )

    @pytest.mark.parametrize("treatment", [NOT_SUBJECT, REVERSE_CHARGE])
    def test_a_sale_without_quota_carries_nothing(self, treatment):
        """An empty list is an answer: the Canaries pay the net, the reverse charge is the customer's."""
        assert tax_rate_specs_for(_quote(treatment, "0.00", country="")) == []


class TestTheSpec:
    def test_it_is_never_inclusive_because_the_price_is_net(self):
        assert (
            TaxRateSpec(country="ES", region="", percentage=Decimal("21")).inclusive
            is False
        )

    def test_it_names_the_tax_as_the_invoice_does(self):
        """One TaxRate is shared by every buyer, so its name cannot follow a language: the tax's own name."""
        assert (
            TaxRateSpec(country="ES", region="", percentage=Decimal("21")).display_name
            == "IVA"
        )
        assert (
            TaxRateSpec(country="DE", region="", percentage=Decimal("19")).display_name
            == "VAT"
        )

    def test_it_describes_where_and_how_much(self):
        assert (
            TaxRateSpec(
                country="ES", region="", percentage=Decimal("21.00")
            ).description
            == "ERPlora — ES 21.00%"
        )

    def test_its_cache_key_is_where_and_how_much(self):
        assert (
            TaxRateSpec(country="ES", region="", percentage=Decimal("21")).cache_key
            == "billing:stripe-tax-rate:ES::21.0000"
        )


class TestFindingTheMirror:
    def _stripe(self, **fields):
        return SimpleNamespace(
            **{"inclusive": False, "country": "ES", "percentage": 21.0, **fields}
        )

    def test_the_same_country_rate_and_exclusive_is_the_one(self):
        assert (
            matches(
                self._stripe(),
                TaxRateSpec(country="ES", region="", percentage=Decimal("21.00")),
            )
            is True
        )

    def test_an_inclusive_rate_is_never_the_one(self):
        """An inclusive 21 % on a net price charges the net and gives the quota away."""
        assert (
            matches(
                self._stripe(inclusive=True),
                TaxRateSpec(country="ES", region="", percentage=Decimal("21")),
            )
            is False
        )

    def test_another_country_or_percentage_is_not_the_one(self):
        spec = TaxRateSpec(country="ES", region="", percentage=Decimal("21"))

        assert matches(self._stripe(country="PT"), spec) is False
        assert matches(self._stripe(percentage=23.0), spec) is False

    def test_an_unreadable_percentage_is_not_the_one(self):
        assert (
            matches(
                self._stripe(percentage="n/a"),
                TaxRateSpec(country="ES", region="", percentage=Decimal("21")),
            )
            is False
        )
