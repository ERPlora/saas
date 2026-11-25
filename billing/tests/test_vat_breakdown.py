"""How an amount charged splits into base and quota: what Stripe collected rules, and a subject sale on which it
collected nothing is reconciled and reported."""

from decimal import Decimal

import pytest

from billing import queries
from billing.tests.vat_sales import charged

pytestmark = pytest.mark.django_db

NO_TAX = "fiscal.vat.stripe_charged_no_tax_on_subject_sale"
BERLIN = {"country": "DE", "postal_code": "10115"}


def _reports(caplog):
    return [record for record in caplog.records if getattr(record, "event", "") == NO_TAX]


class TestWhatStripeCollected:
    @pytest.mark.parametrize("tax_included", [True, False])
    def test_its_amounts_rule_though_they_are_not_our_rate(self, tax_included, caplog):
        breakdown = charged("121.00", country="ES", tax_cents=2000, tax_included=tax_included)

        assert (breakdown.base, breakdown.tax, breakdown.rate) == (
            Decimal("101.00"),
            Decimal("20.00"),
            Decimal("19.80"),
        )
        assert breakdown.vat_included_reconciled is False
        assert _reports(caplog) == []

    def test_a_price_with_the_vat_inside_is_split_without_a_report(self, caplog):
        breakdown = charged("121.00", country="ES")

        assert (breakdown.base, breakdown.tax, breakdown.rate) == (
            Decimal("100.00"),
            Decimal("21.00"),
            Decimal("21.00"),
        )
        assert breakdown.vat_included_reconciled is False
        assert _reports(caplog) == []


class TestASubjectSaleWithoutTax:
    def _report(self, caplog, **payer):
        with caplog.at_level("ERROR", logger="billing.vat"):
            charged("29.99", tax_included=False, **payer)
        [record] = _reports(caplog)
        return record

    def test_the_report_says_the_whole_sale(self, caplog):
        record = self._report(caplog, **BERLIN)

        assert record.levelname == "ERROR"
        assert record.getMessage().startswith(
            "[VAT] Stripe charged no tax on a domestic sale of 29.99 EUR at 21.00% to a DE customer: reconciled as "
            "VAT-inclusive, so the quota comes out of our margin."
        )
        assert (record.treatment, record.gross, record.expected_rate) == ("domestic", "29.99", "21.00")
        assert (record.tax_country, record.customer_country, record.reconciled) == ("ES", "DE", True)

    def test_at_destination_the_jurisdiction_is_the_customers(self, caplog):
        policy = queries.fiscal_policy()
        policy.oss_registered = True
        policy.save()

        record = self._report(caplog, **BERLIN)

        assert "a oss sale of 29.99 EUR at 19.00% to a DE customer" in record.getMessage()
        assert (record.treatment, record.expected_rate) == ("oss", "19.00")
        assert (record.tax_country, record.customer_country) == ("DE", "DE")

    @pytest.mark.parametrize("country", ["ES", ""])
    def test_at_home_the_customer_is_the_issuers(self, country, caplog):
        record = self._report(caplog, country=country, postal_code="28001")

        assert (record.tax_country, record.customer_country) == ("ES", "ES")
