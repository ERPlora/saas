"""Tax rates are editable DATA, not a constant of the code.

The rates change (Estonia 22→24 in Jul-2025, Romania 19→21 in Aug-2025, Slovakia 20→23 in Jan-2025,
Finland 24→25.5): each change was a deploy, and what is sold decides the rate. The category is the
linkable entity and the % lives in a rule ``(country, region, category, validity)``, as in the Hub.
How a rule is resolved and the fiscal policy are tested with the other reads of tax, in ``test_queries_tax.py``.
"""

from decimal import Decimal

import pytest

from billing import queries
from billing.models import TaxCategory, TaxRule

pytestmark = pytest.mark.django_db


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
