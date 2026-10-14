"""Rates are edited in the admin, not in the code (saas#1063).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_tax_admin.py`` (origin/develop, 6 tests): a
new rate, a country raising its VAT or a service with its own rate are solved by editing data, without
touching ``billing/vat.py`` nor deploying.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.admin.sites import site
from django.db import IntegrityError

from billing import queries
from billing.models import FiscalPolicy, TaxCategory, TaxRule

pytestmark = pytest.mark.django_db


@pytest.fixture
def rule_admin():
    return site._registry[TaxRule]


class TestRegistered:
    def test_the_three_models_are_editable_in_the_admin(self):
        assert TaxRule in site._registry
        assert TaxCategory in site._registry
        assert FiscalPolicy in site._registry

    def test_the_rule_list_shows_what_is_needed_to_operate(self, rule_admin):
        for field in (
            "country_code",
            "region_code",
            "rate_pct",
            "valid_from",
            "is_active",
        ):
            assert field in rule_admin.list_display, field

    def test_rules_can_be_filtered_by_country_and_category(self, rule_admin):
        assert "country_code" in rule_admin.list_filter
        assert "category" in rule_admin.list_filter


class TestOverlapIsRejected:
    """Two rules of the same kind starting at once are an ambiguity, not data."""

    def test_two_rules_with_the_same_start_are_rejected(self):
        generic = TaxCategory.objects.get(key="service.generic")

        with pytest.raises(IntegrityError):
            TaxRule.objects.create(
                category=generic,
                country_code="ES",
                region_code="",
                rate_pct=Decimal("15.00"),
                valid_from=date(2020, 1, 1),  # already seeded by the migration
            )


class TestPolicyAdmin:
    def test_the_policy_is_a_singleton_in_the_admin_too(self):
        policy_admin = site._registry[FiscalPolicy]
        queries.fiscal_policy().save()

        assert policy_admin.has_add_permission(None) is False
        assert policy_admin.has_delete_permission(None) is False

    def test_it_says_the_total_is_unknown_until_somebody_carries_it(self):
        """A 0 shown as a fact would hide a threshold already crossed in the old SaaS (finding 2)."""
        from django.utils import translation

        policy_admin = site._registry[FiscalPolicy]
        policy = queries.fiscal_policy()

        assert "unknown" in str(policy_admin.oss_progress(policy)).lower()
        with translation.override("es"):
            assert "desconocido" in str(policy_admin.oss_progress(policy)).lower()

    def test_it_shows_how_far_the_oss_threshold_is(self):
        """Without the running total in sight, the threshold is crossed without anybody noticing."""
        from django.utils import timezone

        policy_admin = site._registry[FiscalPolicy]
        policy = queries.fiscal_policy()
        policy.oss_carried_year = timezone.localdate().year
        policy.oss_carried_current_cents = 123_456
        policy.save()

        progress = str(policy_admin.oss_progress(policy))

        assert "1234.56" in progress
        assert "10000.00" in progress

    def test_the_singleton_respects_the_permission_to_add(self):
        """No row yet is not a licence: a staff member without ``add_fiscalpolicy`` cannot add it."""
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        FiscalPolicy.objects.all().delete()
        viewer = get_user_model().objects.create_user(email="viewer@erplora.com", password="x", is_staff=True)
        request = RequestFactory().get("/admin/billing/fiscalpolicy/")
        request.user = viewer

        assert site._registry[FiscalPolicy].has_add_permission(request) is False
