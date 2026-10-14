"""Splitting and qualifying the VAT of a sale (saas#1051, saas#1063).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_vat.py`` (origin/develop, 21 tests), plus the
public helpers of ``billing.vat`` the panel and L2-B read (``BILLING_COUNTRIES``, ``tax_id_type_for``).
The rates come from ``TaxRule``, editable in the admin, so these tests touch the database.
"""

from datetime import date
from decimal import Decimal

import pytest

from billing import queries
from billing.vat import BILLING_COUNTRIES, EU_VAT_RATES, resolve_vat, tax_id_type_for

pytestmark = pytest.mark.django_db


def _resolve(total, **kwargs):
    return resolve_vat(Decimal(total), **kwargs)


def _register_in_oss():
    policy = queries.fiscal_policy()
    policy.oss_registered = True
    policy.save()


class TestDomesticSale:
    def test_spanish_consumer_pays_21_percent(self):
        result = _resolve("1.21", customer_country="ES")

        assert result.rate == Decimal("21.00")
        assert result.base == Decimal("1.00")
        assert result.tax == Decimal("0.21")
        assert result.tax_country == "ES"

    def test_base_plus_tax_always_equals_the_gross(self):
        """The amount charged rules: the breakdown can never alter it."""
        for gross in ["1.21", "29.99", "54.99", "109.99", "419.99", "0.01"]:
            result = _resolve(gross, customer_country="ES")

            assert result.base + result.tax == Decimal(gross), gross

    def test_rounding_is_half_up(self):
        """ADR-0123: explicit HALF_UP; a bare quantize() inherits HALF_EVEN."""
        # 29.99 / 1.21 = 24.7851... → 24.79 (not 24.78)
        result = _resolve("29.99", customer_country="ES")

        assert result.base == Decimal("24.79")
        assert result.tax == Decimal("5.20")

    def test_missing_country_falls_back_to_the_issuer(self):
        """Stripe does not always send a country; a sale without one cannot go out without VAT."""
        result = _resolve("1.21", customer_country="")

        assert result.rate == Decimal("21.00")
        assert result.tax == Decimal("0.21")
        assert result.tax_country == "ES"


class TestOtherEuCountries:
    """The One-Stop Shop threshold rules (saas#1063): below €10,000 a year of cross-border B2C sales
    (and without the voluntary OSS registration) the ISSUER's VAT is charged, not the customer's."""

    def test_b2c_in_another_member_state_pays_the_issuer_rate_below_the_threshold(self):
        result = _resolve("121.00", customer_country="FR")

        assert result.rate == Decimal("21.00")
        assert result.tax == Decimal("21.00")
        assert result.tax_country == "ES"
        assert result.treatment == "domestic"

    def test_above_the_threshold_the_destination_rate_applies(self):
        _register_in_oss()

        result = _resolve("100.00", customer_country="FR")

        assert result.rate == Decimal("20.00")
        assert result.tax_country == "FR"
        assert result.treatment == "oss"
        assert result.base + result.tax == Decimal("100.00")

    def test_germany_is_19_under_oss(self):
        _register_in_oss()

        assert _resolve("100.00", customer_country="DE").rate == Decimal("19.00")


class TestSpanishTerritoriesOutsideTheVatArea:
    """The Canary Islands, Ceuta and Melilla are outside the scope of VAT (saas#1063)."""

    def test_the_canary_islands_are_not_subject(self):
        result = _resolve("100.00", customer_country="ES", customer_postal_code="35001")

        assert result.treatment == "not_subject"
        assert result.rate == Decimal("0.00")
        assert result.tax == Decimal("0.00")
        assert result.base == Decimal("100.00")

    def test_tenerife_too(self):
        assert (
            _resolve(
                "100.00", customer_country="ES", customer_postal_code="38001"
            ).treatment
            == "not_subject"
        )

    def test_ceuta_and_melilla_are_not_subject(self):
        assert (
            _resolve(
                "100.00", customer_country="ES", customer_postal_code="51001"
            ).treatment
            == "not_subject"
        )
        assert (
            _resolve(
                "100.00", customer_country="ES", customer_postal_code="52001"
            ).treatment
            == "not_subject"
        )

    def test_the_mainland_still_pays_21(self):
        result = _resolve("121.00", customer_country="ES", customer_postal_code="28001")

        assert result.treatment == "domestic"
        assert result.tax == Decimal("21.00")

    def test_a_postal_code_from_another_country_does_not_trigger_spanish_regions(self):
        """35001 is Las Palmas in Spain and any code at all in France."""
        _register_in_oss()

        assert (
            _resolve(
                "100.00", customer_country="FR", customer_postal_code="35001"
            ).treatment
            == "oss"
        )


class TestCategories:
    """The rate depends on WHAT is sold, and that is edited in the admin."""

    def test_a_category_with_its_own_rule_uses_it(self):
        from billing.models import TaxCategory, TaxRule

        TaxRule.objects.create(
            category=TaxCategory.objects.get(key="service.training"),
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
        )

        result = _resolve(
            "110.00", customer_country="ES", category_key="service.training"
        )

        assert result.rate == Decimal("10.00")
        assert result.base == Decimal("100.00")
        assert result.tax == Decimal("10.00")

    def test_a_category_without_its_own_rule_uses_the_generic_one(self):
        result = _resolve(
            "121.00", customer_country="ES", category_key="service.saas_subscription"
        )

        assert result.rate == Decimal("21.00")

    def test_editing_the_rule_changes_what_is_charged_without_a_deploy(self):
        """The reason for the table: Estonia 22→24, Romania 19→21…"""
        rule = queries.tax_rule(country_code="ES", category_key="service.generic")
        rule.rate_pct = Decimal("25.00")
        rule.save()

        assert _resolve("125.00", customer_country="ES").rate == Decimal("25.00")


class TestFallbackWhenTheTableIsUnusable:
    def test_a_country_missing_from_the_table_still_charges_the_issuer_rate(self):
        """Deleting Spain's rule cannot stop VAT being charged."""
        from billing.models import TaxRule

        TaxRule.objects.all().delete()

        result = _resolve("121.00", customer_country="ES")

        assert result.rate == Decimal("21.00")
        assert result.tax == Decimal("21.00")
        assert result.treatment == "domestic"


def _enable_reverse_charge():
    """In the ROI. Reverse charge needs that registration and the VAT number checked in VIES."""
    policy = queries.fiscal_policy()
    policy.intra_eu_reverse_charge = True
    policy.save()


class TestReverseCharge:
    def test_b2b_with_eu_vat_id_in_another_country_is_reverse_charge(self):
        _enable_reverse_charge()

        result = _resolve(
            "100.00",
            customer_country="FR",
            customer_tax_id="FR12345678901",
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=True,
        )

        assert result.is_reverse_charge is True
        assert result.treatment == "reverse_charge"
        assert result.rate == Decimal("0.00")
        assert result.tax == Decimal("0.00")
        assert result.base == Decimal("100.00")
        assert result.tax_country == "FR"

    def test_a_spanish_business_is_not_reverse_charge(self):
        """Reverse charge is intra-community: in Spain the VAT is charged."""
        result = _resolve(
            "121.00",
            customer_country="ES",
            customer_tax_id="B27593136",
            customer_tax_id_type="es_cif",
        )

        assert result.is_reverse_charge is False
        assert result.rate == Decimal("21.00")
        assert result.tax == Decimal("21.00")


class TestOutsideTheEu:
    def test_export_carries_no_eu_vat(self):
        result = _resolve("100.00", customer_country="US")

        assert result.treatment == "not_subject"
        assert result.rate == Decimal("0.00")
        assert result.tax == Decimal("0.00")
        assert result.base == Decimal("100.00")
        assert result.tax_country == ""


class TestStripeTakesPrecedence:
    def test_an_explicit_breakdown_from_stripe_is_respected(self):
        result = _resolve("121.00", customer_country="ES", tax_cents=2100)

        assert result.tax == Decimal("21.00")
        assert result.base == Decimal("100.00")
        assert result.rate == Decimal("21.00")

    def test_stripe_supplies_the_amounts_but_not_the_qualification(self):
        """The qualification is ours: Stripe only brings the amounts."""
        _enable_reverse_charge()

        result = _resolve(
            "100.00",
            customer_country="FR",
            customer_tax_id="FR12345678901",
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=True,
            tax_cents=0,
        )

        assert result.treatment == "reverse_charge"


class TestTheCountriesErploraInvoices:
    def test_spain_leads_then_the_rest_of_the_eu_and_the_uk(self):
        assert BILLING_COUNTRIES[0] == "ES"
        assert set(BILLING_COUNTRIES) == set(EU_VAT_RATES) | {"GB"}
        assert len(BILLING_COUNTRIES) == 28
        assert list(BILLING_COUNTRIES[1:]) == sorted(BILLING_COUNTRIES[1:])

    def test_every_member_state_is_an_eu_vat_id_and_the_uk_its_own(self):
        """A wrong type makes Stripe reject the whole tax id: an unknown country is not guessed."""
        assert {tax_id_type_for(country) for country in EU_VAT_RATES} == {"eu_vat"}
        assert tax_id_type_for("gb") == "gb_vat"
        assert tax_id_type_for("US") == ""
        assert tax_id_type_for("") == ""


class TestASpanishPostalCodeIsFiveDigits:
    """The first two digits of a Spanish postal code are its province, but only of a real code: «3500»
    (Benidorm typed without its leading 0) is not Las Palmas (review of L2-A, finding 1)."""

    @pytest.mark.parametrize(
        "postal_code, region",
        [("35001", "IC"), ("38001", "IC"), ("51001", "CE"), ("52001", "ML"), ("03500", ""), ("28001", ""), (" 35 001 ", "IC")],
    )
    def test_a_real_code_names_its_region(self, postal_code, region):
        from billing.vat import spanish_region_for_postal_code

        assert spanish_region_for_postal_code(postal_code) == region

    @pytest.mark.parametrize("postal_code", ["3500", "5100", "5200", "350011", "", "35-001", "ABCDE"])
    def test_anything_else_is_unknown(self, postal_code):
        from billing.vat import spanish_region_for_postal_code

        assert spanish_region_for_postal_code(postal_code) is None

    def test_benidorm_without_its_zero_is_not_sold_at_zero(self):
        """Selling: an unknown Spanish place cannot be priced (the sale door asks for the address)."""
        from billing.vat import quote_vat

        assert quote_vat(Decimal("100.00"), customer_country="ES", customer_postal_code="3500") is None
        assert quote_vat(Decimal("100.00"), customer_country="ES", customer_postal_code="") is None
        assert quote_vat(Decimal("100.00"), customer_country="ES", customer_postal_code="03500").rate == Decimal("21.00")

    def test_what_was_already_charged_to_an_unknown_spanish_place_pays_vat(self, caplog):
        """Invoicing: the money is in, and when in doubt the VAT is charged (never 0 % by a guess)."""
        result = _resolve("121.00", customer_country="ES", customer_postal_code="3500")

        assert (result.treatment, result.tax) == ("domestic", Decimal("21.00"))
        assert any(r.levelname == "WARNING" and "3500" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize(
        "country, postal_code, valid",
        [("ES", "03500", True), ("ES", "3500", False), ("ES", "", False), ("DE", "10115", True), ("GB", "SW1A 1AA", True), ("DE", " ", False), ("", "28001", False)],
    )
    def test_a_billing_location_needs_a_country_and_a_postal_code_of_its_shape(self, country, postal_code, valid):
        from billing.vat import postal_code_is_valid

        assert postal_code_is_valid(country, postal_code) is valid


class TestTheOssIsEuropean:
    def test_a_non_eu_territory_with_its_own_rate_is_never_oss(self):
        """A rate typed in the admin for a third country (a registration there) is that country's rate,
        never the One-Stop Shop, which only covers member states."""
        from billing.models import TaxCategory, TaxRule

        _register_in_oss()
        TaxRule.objects.create(
            category=TaxCategory.objects.get(key="service.generic"), country_code="NO", rate_pct=Decimal("25.00"), valid_from=date(2020, 1, 1)
        )

        result = _resolve("125.00", customer_country="NO")

        assert result.treatment != "oss"
        assert (result.tax_country, result.rate) == ("NO", Decimal("25.00"))


class TestTheReverseChargeRule:
    """One rule for the engine and for the panel's answer (review of L2-A, finding 4)."""

    def test_it_needs_the_roi_a_member_state_that_is_not_ours_and_a_proof(self):
        from billing.vat import reverse_charge_applies

        assert reverse_charge_applies(customer_country="DE", verified=True) is True
        assert reverse_charge_applies(customer_country="de", verified=True) is True
        assert reverse_charge_applies(customer_country="DE", verified=False) is False
        assert reverse_charge_applies(customer_country="ES", verified=True) is False
        assert reverse_charge_applies(customer_country="", verified=True) is False
        assert reverse_charge_applies(customer_country="GB", verified=True) is False

    def test_off_in_the_roi_nobody_is_reverse_charged(self):
        from billing.vat import reverse_charge_applies

        _enable_reverse_charge()
        policy = queries.fiscal_policy()
        policy.intra_eu_reverse_charge = False
        policy.save()

        assert reverse_charge_applies(customer_country="DE", verified=True) is False


class TestAPlaceWithoutARule:
    def test_it_is_said_as_a_warning_not_an_error(self, caplog):
        """Who types a country in a form is not a fault of ours: the sale door logs the refusal itself."""
        from billing.vat import quote_vat

        assert quote_vat(Decimal("100.00"), customer_country="US") is None

        assert not [r for r in caplog.records if r.levelname == "ERROR"]
        assert any(getattr(r, "event", "") == "fiscal.vat.rate_not_resolvable" and r.levelname == "WARNING" for r in caplog.records)
