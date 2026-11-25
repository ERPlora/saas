"""Where a sale is taxed: the customer's place, the issuer's, and which of the two charges a sale to another member
state.

The policy (``FiscalPolicy``) and the table (``TaxRule``) are data of the admin, so the issuer may be moved to another
country or region and a territory may get a rate of its own.
"""

from datetime import date
from decimal import Decimal

import pytest

from billing import queries
from billing.models import TaxCategory, TaxRule
from billing.tests.vat_sales import charged, priced

pytestmark = pytest.mark.django_db

CANARIES = {"country": "ES", "postal_code": "35001"}
FRENCH_BUSINESS = {"country": "FR", "tax_id": "FR12345678901", "tax_id_type": "eu_vat", "tax_id_verified": True}


def _policy(**changes):
    policy = queries.fiscal_policy()
    for field, value in changes.items():
        setattr(policy, field, value)
    policy.save()


def _rate(country, rate, *, region=""):
    """Give a territory of the table a rate of its own."""
    rule = queries.tax_rule(country_code=country, region_code=region)
    assert rule.region_code == region
    rule.rate_pct = Decimal(rate)
    rule.is_subject = True
    rule.save()


def _taxed(breakdown):
    return breakdown.treatment, breakdown.tax_country, breakdown.tax_region, breakdown.rate


NOT_SUBJECT = ("not_subject", "", "", Decimal("0.00"))
SPANISH = ("domestic", "ES", "", Decimal("21.00"))
FRENCH = ("oss", "FR", "", Decimal("20.00"))


class TestTheCustomersCountry:
    @pytest.mark.parametrize("country", ["es", " ES", "ES "])
    def test_it_is_read_however_it_is_written(self, country):
        assert _taxed(charged("121.00", country=country)) == SPANISH

    @pytest.mark.parametrize("country", ["", "  ", None])
    def test_without_one_the_issuers_applies_and_is_said(self, country, caplog):
        with caplog.at_level("INFO", logger="billing.vat"):
            assert _taxed(charged("121.00", country=country)) == SPANISH

        assert "[VAT] No customer country; the issuer's (ES) applies" in caplog.messages


class TestTheIssuer:
    def test_another_country_charges_its_own_rate(self):
        _policy(issuer_country="PT")

        assert _taxed(charged("123.00", country="")) == ("domestic", "PT", "", Decimal("23.00"))
        assert _taxed(charged("123.00", country="PT")) == ("domestic", "PT", "", Decimal("23.00"))
        assert _taxed(charged("123.00", country="FR")) == ("domestic", "PT", "", Decimal("23.00"))

    def test_its_country_is_read_however_it_is_written(self):
        _policy(issuer_country="pt")

        assert _taxed(charged("123.00", country="FR")) == ("domestic", "PT", "", Decimal("23.00"))

    def test_without_a_country_it_is_spain(self):
        _policy(issuer_country="")

        assert _taxed(charged("121.00", country="")) == SPANISH
        assert _taxed(charged("121.00", country="FR")) == SPANISH

    def test_its_own_country_is_never_the_one_stop_shop(self):
        _policy(oss_registered=True)

        assert _taxed(charged("121.00", country="ES")) == SPANISH
        assert _taxed(charged("121.00", country="ES", tax_cents=2100)) == SPANISH

        _policy(issuer_country="PT")
        assert _taxed(charged("123.00", country="")) == ("domestic", "PT", "", Decimal("23.00"))

    @pytest.mark.parametrize("region", ["IC", " ic "])
    def test_one_outside_vat_charges_none_below_the_threshold(self, region):
        _policy(issuer_region=region)

        assert _taxed(priced("100.00", country="FR")) == NOT_SUBJECT
        assert _taxed(charged("100.00", country="FR")) == NOT_SUBJECT

    def test_one_outside_vat_and_in_the_oss_charges_the_customers(self):
        _policy(issuer_region="IC", oss_registered=True)

        assert _taxed(priced("100.00", country="FR")) == FRENCH
        assert _taxed(charged("120.00", country="FR")) == FRENCH

    def test_one_in_a_region_with_a_rate_charges_it_there(self):
        _policy(issuer_region="IC")
        _rate("ES", "7.00", region="IC")

        assert _taxed(priced("100.00", country="FR")) == ("domestic", "ES", "IC", Decimal("7.00"))
        assert _taxed(charged("107.00", country="FR")) == ("domestic", "ES", "IC", Decimal("7.00"))

    def test_one_in_a_region_without_a_rule_cannot_price_a_sale_taxed_there(self):
        _policy(issuer_region="XX")

        assert priced("100.00", country="FR") is None
        assert _taxed(charged("100.00", country="FR")) == NOT_SUBJECT


class TestTheRateTheGatewayCharged:
    """A sale to another member state already charged: the rate it was charged at is the evidence of where."""

    def test_the_customers_rate_is_taxed_there_below_the_threshold(self):
        breakdown = charged("120.00", country="FR", tax_cents=2000)

        assert _taxed(breakdown) == FRENCH
        assert (breakdown.base, breakdown.tax) == (Decimal("100.00"), Decimal("20.00"))

    def test_the_issuers_rate_is_taxed_here_even_in_the_oss(self):
        _policy(oss_registered=True)

        assert _taxed(charged("121.00", country="FR", tax_cents=2100)) == SPANISH

    def test_the_same_rate_in_both_proves_nothing_and_the_policy_decides(self):
        assert _taxed(charged("121.00", country="NL", tax_cents=2100)) == SPANISH

        _policy(oss_registered=True)
        assert _taxed(charged("121.00", country="NL", tax_cents=2100)) == ("oss", "NL", "", Decimal("21.00"))

    def test_a_rate_of_neither_proves_nothing_and_the_policy_decides(self):
        here = ("domestic", "ES", "", Decimal("10.00"))
        assert _taxed(charged("110.00", country="FR", tax_cents=1000)) == here

        _policy(oss_registered=True)
        assert _taxed(charged("110.00", country="FR", tax_cents=1000)) == ("oss", "FR", "", Decimal("10.00"))

    def test_nothing_charged_is_no_evidence_of_a_zero_rate(self):
        _rate("FR", "0.00")

        assert _taxed(charged("121.00", country="FR")) == SPANISH

    def test_the_customers_rate_rules_over_an_issuer_outside_vat_or_without_a_rule(self):
        for region in ("IC", "XX"):
            _policy(issuer_region=region)
            breakdown = charged("120.00", country="FR", tax_cents=2000)

            assert _taxed(breakdown) == FRENCH, region
            assert (breakdown.base, breakdown.tax) == (Decimal("100.00"), Decimal("20.00")), region


class TestTheOneStopShop:
    def test_the_sale_that_crosses_the_threshold_is_taxed_at_destination(self):
        assert _taxed(priced("10000.00", country="FR")) == SPANISH
        assert _taxed(priced("10000.01", country="FR")) == FRENCH

    def test_below_it_the_issuers_rate_is_the_one_of_what_is_sold(self):
        TaxRule.objects.create(
            category=TaxCategory.objects.get(key="service.training"),
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
        )

        training = {"country": "FR", "category_key": "service.training"}
        assert _taxed(priced("100.00", **training)) == ("domestic", "ES", "", Decimal("10.00"))
        assert _taxed(charged("110.00", **training)) == ("domestic", "ES", "", Decimal("10.00"))


class TestATerritory:
    @pytest.mark.parametrize("payer", [CANARIES, {"country": "GB", "postal_code": "SW1A 1AA"}], ids=["IC", "GB"])
    def test_outside_vat_it_has_no_jurisdiction(self, payer):
        assert _taxed(priced("100.00", **payer)) == NOT_SUBJECT
        assert _taxed(charged("100.00", **payer)) == NOT_SUBJECT

    def test_outside_vat_an_issuer_of_another_member_state_charges_none_either(self):
        _policy(issuer_country="PT")

        assert _taxed(priced("100.00", **CANARIES)) == NOT_SUBJECT
        assert _taxed(charged("100.00", **CANARIES)) == NOT_SUBJECT

    def test_without_a_rule_what_was_charged_has_no_jurisdiction_either(self):
        assert _taxed(charged("100.00", country="US")) == NOT_SUBJECT

    def test_a_region_with_a_rate_is_taxed_in_it(self):
        _rate("ES", "7.00", region="IC")

        assert _taxed(priced("100.00", **CANARIES)) == ("domestic", "ES", "IC", Decimal("7.00"))
        assert _taxed(charged("107.00", **CANARIES)) == ("domestic", "ES", "IC", Decimal("7.00"))
        assert _taxed(charged("107.00", tax_cents=700, **CANARIES)) == ("domestic", "ES", "IC", Decimal("7.00"))


class TestReverseCharge:
    def test_it_is_declared_in_the_customers_country(self):
        declared = ("reverse_charge", "FR", "", Decimal("0.00"))

        assert _taxed(priced("100.00", **FRENCH_BUSINESS)) == declared
        assert _taxed(charged("100.00", **FRENCH_BUSINESS)) == declared

    @pytest.mark.parametrize("missing", [{"tax_id": ""}, {"tax_id_type": ""}, {"tax_id_type": "gb_vat"}], ids=str)
    def test_a_verdict_without_an_eu_vat_number_pays_vat(self, missing):
        assert _taxed(priced("100.00", **{**FRENCH_BUSINESS, **missing})) == SPANISH
        assert _taxed(charged("121.00", **{**FRENCH_BUSINESS, **missing})) == SPANISH


class TestAWholeCent:
    def test_a_price_is_read_to_the_cent(self):
        assert priced("29.994", **CANARIES).base == Decimal("29.99")
        assert priced("29.995", country="ES", postal_code="28001").base == Decimal("30.00")

    def test_an_amount_charged_is_read_to_the_cent(self):
        assert charged("29.994", **CANARIES).base == Decimal("29.99")
        assert charged("121.005", country="ES", tax_cents=2100).base == Decimal("100.01")
