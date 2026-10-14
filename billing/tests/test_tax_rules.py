"""Tax rates are editable DATA, not a constant of the code (saas#1063).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_tax_rules.py`` (origin/develop, 20 tests).
The rates change (Estonia 22→24 in Jul-2025, Romania 19→21 in Aug-2025, Slovakia 20→23 in Jan-2025,
Finland 24→25.5): each change was a deploy, and what is sold decides the rate. The category is the
linkable entity and the % lives in a rule ``(country, region, category, validity)``, as in the Hub
(ADR-0085). The resolution moved from ``TaxRule.resolve`` to ``billing.queries.tax_rule`` (only
``services.py`` and ``queries.py`` touch the ORM) and the policy's threshold to
``billing.queries.uses_destination_rate``.

Adapted: the two tests that summed real invoices into the OSS threshold
(``test_crossing_the_threshold_switches_to_destination_rates``,
``test_domestic_and_b2b_sales_do_not_count_towards_the_threshold``) need ``billing.Invoice``, which is
lot L3-C; here a tripwire fails the day that model exists, so the sum cannot stay at zero unnoticed.
The failing threshold query raises ``DatabaseError`` (the only failure it may swallow) instead of a
bare ``RuntimeError``.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError

from billing import queries
from billing.models import FiscalPolicy, TaxCategory, TaxRule

pytestmark = pytest.mark.django_db


@pytest.fixture
def category(db):
    return TaxCategory.objects.get(key="service.saas_subscription")


class TestSeed:
    """The migration leaves the table usable without anybody touching the admin."""

    def test_the_eu_27_general_rates_are_seeded(self):
        countries = set(TaxRule.objects.values_list("country_code", flat=True))

        assert len(countries) >= 27
        assert {"ES", "DE", "FR", "IT", "PT"} <= countries

    def test_spain_is_21_percent(self):
        assert queries.tax_rule(
            country_code="ES", category_key="service.generic"
        ).rate_pct == Decimal("21.00")

    def test_the_categories_describe_what_erplora_sells(self):
        keys = set(TaxCategory.objects.values_list("key", flat=True))

        assert {
            "service.generic",
            "service.saas_subscription",
            "service.software_license",
        } <= keys

    def test_the_special_spanish_territories_are_seeded_as_not_subject(self):
        """The Canary Islands, Ceuta and Melilla are OUTSIDE the VAT area."""
        for region in ("IC", "CE", "ML"):
            rule = queries.tax_rule(
                country_code="ES", region_code=region, category_key="service.generic"
            )

            assert rule is not None, region
            assert rule.is_subject is False, region


class TestResolution:
    def test_a_rule_for_the_category_beats_the_generic_one(self, category):
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2026, 1, 1),
        )

        assert queries.tax_rule(
            country_code="ES", category_key="service.saas_subscription"
        ).rate_pct == Decimal("10.00")
        assert queries.tax_rule(
            country_code="ES", category_key="service.generic"
        ).rate_pct == Decimal("21.00")

    def test_a_category_without_its_own_rule_falls_back_to_the_generic(self, category):
        assert queries.tax_rule(
            country_code="DE", category_key="service.saas_subscription"
        ).rate_pct == Decimal("19.00")

    def test_the_region_wins_over_the_country_wide_rule(self):
        mainland = queries.tax_rule(
            country_code="ES", region_code="", category_key="service.generic"
        )
        canaries = queries.tax_rule(
            country_code="ES", region_code="IC", category_key="service.generic"
        )

        assert mainland.rate_pct == Decimal("21.00")
        assert canaries.is_subject is False

    def test_a_rule_that_is_not_yet_in_force_does_not_apply(self, category):
        """A change of rate is SCHEDULED; it does not rewrite the past."""
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("23.00"),
            valid_from=date(2027, 1, 1),
        )

        today = queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2026, 8, 2),
        )
        later = queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2027, 3, 1),
        )

        assert today.rate_pct == Decimal("21.00")
        assert later.rate_pct == Decimal("23.00")

    def test_an_expired_rule_does_not_apply(self, category):
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("18.00"),
            valid_from=date(2010, 7, 1),
            valid_to=date(2012, 8, 31),
        )

        assert queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2011, 1, 1),
        ).rate_pct == Decimal("18.00")
        assert queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2026, 8, 2),
        ).rate_pct == Decimal("21.00")

    def test_an_inactive_rule_does_not_apply(self, category):
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
            is_active=False,
        )

        assert queries.tax_rule(
            country_code="ES", category_key="service.saas_subscription"
        ).rate_pct == Decimal("21.00")

    def test_an_unknown_country_has_no_rule(self):
        assert (
            queries.tax_rule(country_code="US", category_key="service.generic") is None
        )

    def test_the_most_recent_rule_in_force_wins(self, category):
        """Two rules in force at once: the one that started later wins."""
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
        )
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("12.00"),
            valid_from=date(2024, 1, 1),
        )

        assert queries.tax_rule(
            country_code="ES", category_key="service.saas_subscription"
        ).rate_pct == Decimal("12.00")

    def test_lower_case_codes_find_the_rule(self):
        assert (
            queries.tax_rule(
                country_code="es", region_code="ic", category_key="service.generic"
            ).is_subject
            is False
        )


class TestFiscalPolicy:
    def test_it_is_a_singleton_defaulting_to_spain_without_oss(self):
        policy = queries.fiscal_policy()

        assert FiscalPolicy.objects.count() == 1
        assert policy.pk == FiscalPolicy.objects.get().pk
        assert policy.issuer_country == "ES"
        assert policy.oss_registered is False
        assert policy.oss_threshold == Decimal("10000.00")

    def test_saving_a_second_row_overwrites_the_first(self):
        queries.fiscal_policy()
        FiscalPolicy(issuer_country="PT").save()

        assert FiscalPolicy.objects.count() == 1
        assert queries.fiscal_policy().issuer_country == "PT"

    def test_without_a_row_the_defaults_apply_and_nothing_is_written(self):
        """A READ ONLY query (``billing.tax.preview``) reads the policy: it may not create it."""
        FiscalPolicy.objects.all().delete()

        policy = queries.fiscal_policy()

        assert (
            policy.issuer_country,
            policy.intra_eu_reverse_charge,
            policy.oss_registered,
        ) == ("ES", True, False)
        assert FiscalPolicy.objects.count() == 0

    def test_below_the_threshold_the_issuer_rate_applies(self):
        """€10,000 threshold of cross-border B2C sales: below it, Spanish VAT."""
        assert queries.uses_destination_rate(queries.fiscal_policy()) is False

    def test_registering_in_oss_switches_to_destination_rates(self):
        policy = queries.fiscal_policy()
        policy.oss_registered = True
        policy.save()

        assert queries.uses_destination_rate(queries.fiscal_policy()) is True

    def test_the_sale_being_priced_counts_towards_the_threshold(self):
        """The sale that crosses already goes to destination (art. 59c(2), saas#1969)."""
        policy = queries.fiscal_policy()

        assert queries.uses_destination_rate(policy, pending_cents=1_000_001) is True
        assert queries.uses_destination_rate(policy, pending_cents=1_000_000) is False

    def test_pricing_falls_back_to_the_issuer_rate_when_the_threshold_query_fails(
        self, monkeypatch, caplog
    ):
        """Invoicing must not break on this query: a failed total prices at origin and is logged."""

        def _boom(policy, year):
            raise DatabaseError("database went away")

        monkeypatch.setattr(queries, "cross_border_b2c_cents", _boom)

        assert queries.uses_destination_rate(queries.fiscal_policy()) is False
        assert any(
            "[FISCAL]" in r.getMessage() and r.levelname == "ERROR"
            for r in caplog.records
        )

    def test_acting_on_the_regime_must_not_mistake_a_failed_query_for_origin(
        self, monkeypatch
    ):
        """Whoever ACTS on «the year is back to origin» asks the raising variant: an error is not «below»."""

        def _boom(policy, year):
            raise DatabaseError("database went away")

        monkeypatch.setattr(queries, "cross_border_b2c_cents", _boom)

        with pytest.raises(DatabaseError):
            queries.destination_rate_applies(queries.fiscal_policy())

    def _carry(self, year, *, current=0, previous=0):
        policy = queries.fiscal_policy()
        policy.oss_carried_year = year
        policy.oss_carried_current_cents = current
        policy.oss_carried_previous_cents = previous
        policy.save()
        return policy

    def test_the_amount_carried_from_the_old_saas_counts_this_year(self):
        """Until the invoices live here (L3-C) the year's cross-border B2C base comes from the old SaaS,
        typed in the admin (review of L2-A, finding 2)."""
        year = date.today().year
        policy = self._carry(year, current=1_000_001)

        assert queries.cross_border_b2c_cents(policy, year) == 1_000_001
        assert queries.uses_destination_rate(policy, year=year) is True

    def test_a_previous_year_above_the_threshold_makes_the_whole_year_destination(self):
        year = date.today().year
        policy = self._carry(year, previous=1_200_000)

        assert queries.cross_border_b2c_cents(policy, year - 1) == 1_200_000
        assert queries.uses_destination_rate(policy, year=year) is True

    def test_amounts_carried_for_another_year_are_not_this_years(self):
        year = date.today().year
        policy = self._carry(year - 2, current=5_000_000, previous=5_000_000)

        assert queries.cross_border_b2c_cents(policy, year) == 0
        assert queries.cross_border_b2c_cents(policy, year - 1) == 0
        assert queries.oss_total_is_known(policy, year) is False

    def test_without_invoices_nor_carried_amounts_the_total_is_unknown(self):
        """Zero is not a fact until somebody says it: the admin shows «unknown», not 0."""
        year = date.today().year

        assert queries.oss_total_is_known(queries.fiscal_policy(), year) is False
        assert queries.oss_total_is_known(self._carry(year), year) is True

    def test_the_threshold_counts_the_invoices_the_day_they_exist(self):
        """Tripwire for lot L3-C: ``cross_border_b2c_cents`` sums ERPlora's paid invoices, and until
        ``billing.Invoice`` exists the new SaaS has issued none (0). The day the model lands this test
        fails: port ``test_crossing_the_threshold_switches_to_destination_rates`` and
        ``test_domestic_and_b2b_sales_do_not_count_towards_the_threshold`` (fiscal/tests/test_tax_rules.py)
        and make the sum read the invoices, or the OSS threshold stays at zero for ever."""
        from django.apps import apps

        assert "invoice" not in apps.get_app_config("billing").models
        assert (
            queries.cross_border_b2c_cents(queries.fiscal_policy(), date.today().year)
            == 0
        )
