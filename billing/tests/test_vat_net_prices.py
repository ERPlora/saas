"""Adding VAT to a net price, and believing Stripe's quota when it is zero (saas#1098).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_vat_net_prices.py`` (origin/develop, 10 tests).
Plans are sold at NET prices: ``add_vat`` / ``vat_rate_for`` are the way back («€29.99 + VAT —
€36.29/month») so no template invents its own arithmetic, and Stripe's zero is believed only when OUR
qualification also says there is no quota; on a subject sale it is reconciled as VAT-inclusive.
"""

from decimal import Decimal

import pytest

from billing import queries
from billing.vat import add_vat, resolve_vat, split_gross, vat_rate_for

pytestmark = pytest.mark.django_db


class TestAddVat:
    def test_it_adds_the_rate_to_the_net(self):
        assert add_vat(Decimal("29.99"), Decimal("21")) == Decimal("36.29")

    def test_a_zero_rate_adds_nothing(self):
        assert add_vat(Decimal("29.99"), Decimal("0")) == Decimal("29.99")

    def test_it_is_the_inverse_of_split_gross(self):
        """There and back without losing a cent: it is what is shown next to the price."""
        gross = add_vat(Decimal("100.00"), Decimal("21"))
        base, tax = split_gross(gross, Decimal("21"))

        assert base == Decimal("100.00")
        assert base + tax == gross


class TestVatRateFor:
    def test_the_spanish_general_rate(self):
        assert vat_rate_for(country="ES") == Decimal("21.00")

    def test_the_canary_islands_have_no_rate(self):
        """``None`` is «not subject», which is not a 0 % rate."""
        assert vat_rate_for(country="ES", region="IC") is None

    def test_a_third_country_neither(self):
        assert vat_rate_for(country="US") is None


class TestStripesQuotaRulesEvenWhenZero:
    def test_a_sale_without_quota_invents_no_vat(self):
        """Stripe reverse charged and collected €100 clean, and OUR qualification says the same: the
        €100 are base. 82.64 + 17.36 would be VAT nobody paid."""
        policy = queries.fiscal_policy()
        policy.intra_eu_reverse_charge = True
        policy.save()

        vat = resolve_vat(
            Decimal("100.00"),
            customer_country="FR",
            customer_tax_id="FR12345678901",
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=True,
            tax_cents=0,
            tax_included=False,
        )

        assert vat.treatment == "reverse_charge"
        assert vat.base == Decimal("100.00")
        assert vat.tax == Decimal("0.00")

    def test_a_SUBJECT_sale_without_a_stripe_quota_is_reconciled(self):
        """The reverse (saas#1479): a subject sale at 21 % cannot leave the invoice at 0 % — a Spanish
        domestic sale at 0 % does not exist. What was charged becomes VAT-inclusive; the total stays."""
        vat = resolve_vat(
            Decimal("100.00"), customer_country="ES", tax_cents=0, tax_included=False
        )

        assert vat.treatment == "domestic"
        assert vat.rate == Decimal("21.00")
        assert vat.base == Decimal("82.64")
        assert vat.tax == Decimal("17.36")
        assert vat.base + vat.tax == Decimal("100.00")

    def test_with_a_net_price_the_quota_there_is_respected(self):
        vat = resolve_vat(
            Decimal("121.00"), customer_country="ES", tax_cents=2100, tax_included=False
        )

        assert vat.base == Decimal("100.00")
        assert vat.tax == Decimal("21.00")
        assert vat.rate == Decimal("21.00")

    def test_with_a_gross_price_it_still_splits_as_always(self):
        """Modules are still sold VAT-inclusive: their breakdown does not change."""
        vat = resolve_vat(Decimal("121.00"), customer_country="ES", tax_cents=0)

        assert vat.base == Decimal("100.00")
        assert vat.tax == Decimal("21.00")
