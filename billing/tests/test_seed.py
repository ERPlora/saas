"""Today's tax data, written by the migration and by ``manage.py seed_tax_rules``: only what is missing.

The general rates of the EU-27 in force in 2026 (Estonia 24 % since Jul-2025, Romania 21 % since
Aug-2025, Slovakia 23 % since Jan-2025, Finland 25.5 % since Sep-2024), the three Spanish territories
outside the scope of VAT, the UK as a third country since the end of the Brexit transition, the
categories of what ERPlora sells, the fiscal policy and ERPlora's identity (Modelo 036). Ported from
ERPlora/saas ``fiscal/migrations/0006_seed_tax_rules.py``, ``0020_seed_united_kingdom_tax_rule.py`` and
``management/commands/seed_company_036.py`` (origin/develop).

The seed never overwrites: the admin is where rates are edited, and a seed run after an edit (or the
migration on a database that already has its rules) must not undo what somebody decided there.
"""

from datetime import date
from decimal import Decimal

import pytest

from billing import seed
from billing.models import CompanyConfig, FiscalPolicy, TaxCategory, TaxRule

pytestmark = pytest.mark.django_db

MODELS = {
    "TaxCategory": TaxCategory,
    "TaxRule": TaxRule,
    "FiscalPolicy": FiscalPolicy,
    "CompanyConfig": CompanyConfig,
}


def test_the_rates_are_the_general_ones_in_force_in_2026():
    assert len(seed.EU_VAT_RATES) == 27
    assert seed.EU_VAT_RATES["EE"] == "24"
    assert seed.EU_VAT_RATES["RO"] == "21"
    assert seed.EU_VAT_RATES["SK"] == "23"
    assert seed.EU_VAT_RATES["FI"] == "25.5"


def test_the_seed_copies_the_rates_instead_of_reading_the_live_backstop():
    """A seed describes a date: it cannot change meaning the day ``billing.vat.EU_VAT_RATES`` moves."""
    from billing.vat import EU_VAT_RATES

    assert seed.EU_VAT_RATES is not EU_VAT_RATES
    assert {
        country: Decimal(rate) for country, rate in seed.EU_VAT_RATES.items()
    } == EU_VAT_RATES


def test_an_empty_database_gets_everything():
    TaxRule.objects.all().delete()
    TaxCategory.objects.all().delete()
    FiscalPolicy.objects.all().delete()
    CompanyConfig.objects.all().delete()

    created = seed.seed_tax_data(**MODELS)

    assert created == {"categories": 6, "rules": 31, "fiscal_policy": 1, "company": 1}
    assert TaxRule.objects.get(country_code="GB").valid_from == date(2021, 1, 1)
    assert set(
        TaxRule.objects.filter(is_subject=False).values_list(
            "country_code", "region_code"
        )
    ) == {
        ("ES", "IC"),
        ("ES", "CE"),
        ("ES", "ML"),
        ("GB", ""),
    }
    company = CompanyConfig.objects.get()
    assert (company.legal_name, company.tax_id, company.country) == (
        "ERPLORA CLOUD SL",
        "B27593136",
        "ES",
    )
    assert (company.city, company.postal_code, company.province) == (
        "Coslada",
        "28822",
        "Madrid",
    )


def test_a_second_run_creates_nothing():
    """The migration already seeded the test database."""
    assert seed.seed_tax_data(**MODELS) == {
        "categories": 0,
        "rules": 0,
        "fiscal_policy": 0,
        "company": 0,
    }


def test_it_never_undoes_what_the_admin_decided():
    spain = TaxRule.objects.get(
        country_code="ES", region_code="", category_id="service.generic"
    )
    spain.rate_pct = Decimal("22.00")
    spain.save()
    policy = FiscalPolicy.objects.get()
    policy.oss_registered = True
    policy.save()

    seed.seed_tax_data(**MODELS)

    assert TaxRule.objects.get(pk=spain.pk).rate_pct == Decimal("22.00")
    assert FiscalPolicy.objects.get().oss_registered is True


def test_a_uk_rule_written_by_hand_is_left_alone():
    """The admin may have scheduled the UK on another date: the seed does not add a second one."""
    TaxRule.objects.filter(country_code="GB").delete()
    TaxRule.objects.create(
        category_id="service.generic",
        country_code="GB",
        rate_pct=Decimal("0"),
        is_subject=False,
        valid_from=date(2021, 2, 1),
    )

    seed.seed_tax_data(**MODELS)

    assert TaxRule.objects.filter(country_code="GB").count() == 1
