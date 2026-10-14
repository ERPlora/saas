"""The models of billing's VAT engine: what a row is and what it refuses to be.

The rate tables (``TaxCategory``, ``TaxRule``) and the two singletons (``FiscalPolicy``, ``CompanyConfig``)
are ported from ERPlora/saas ``apps/dashboard/fiscal/models.py`` (origin/develop) with UUIDv7 keys;
the singletons stop forcing ``pk=1`` (a UUID key) and keep one row by a unique, always-true column.
``VatCheck`` is the log of VIES queries: a row is the proof that a VAT number was valid on a date.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from billing.models import (
    GENERIC_CATEGORY,
    CompanyConfig,
    FiscalPolicy,
    TaxCategory,
    TaxRule,
    VatCheck,
)

pytestmark = pytest.mark.django_db


def _generic():
    return TaxCategory.objects.get(key=GENERIC_CATEGORY)


class TestKeys:
    def test_every_model_has_a_uuid7_key(self):
        for model in (TaxCategory, TaxRule, FiscalPolicy, CompanyConfig, VatCheck):
            assert model._meta.pk.get_internal_type() == "UUIDField", model
        assert VatCheck(vat_number="DE812871812").pk.version == 7


class TestTaxRule:
    def test_a_rate_is_a_percentage(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            TaxRule.objects.create(
                category=_generic(),
                country_code="DE",
                rate_pct=Decimal("101.00"),
                valid_from=date(2030, 1, 1),
            )
        with pytest.raises(IntegrityError), transaction.atomic():
            TaxRule.objects.create(
                category=_generic(),
                country_code="DE",
                rate_pct=Decimal("-1.00"),
                valid_from=date(2030, 1, 1),
            )

    def test_a_rule_cannot_end_before_it_starts(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            TaxRule.objects.create(
                category=_generic(),
                country_code="DE",
                rate_pct=Decimal("19.00"),
                valid_from=date(2030, 1, 1),
                valid_to=date(2029, 12, 31),
            )

    def test_the_codes_are_upper_case_iso(self):
        """The resolver compares upper case: a rule typed «es» would never be found."""
        from django.core.exceptions import ValidationError

        rule = TaxRule(
            category=_generic(),
            country_code="es",
            region_code="ic",
            rate_pct=Decimal("0"),
            valid_from=date(2030, 1, 1),
        )

        with pytest.raises(ValidationError) as error:
            rule.full_clean()

        assert {"country_code", "region_code"} <= set(error.value.message_dict)

    def test_it_reads_as_where_what_and_how_much(self):
        spain = TaxRule(
            category=_generic(),
            country_code="ES",
            rate_pct=Decimal("21.00"),
            valid_from=date(2020, 1, 1),
        )
        canaries = TaxRule(
            category=_generic(),
            country_code="ES",
            region_code="IC",
            is_subject=False,
            valid_from=date(2020, 1, 1),
        )

        assert str(spain) == "ES · service.generic · 21.00%"
        assert str(canaries) == "ES/IC · service.generic · not subject"


class TestSingletons:
    @pytest.mark.parametrize("model", [FiscalPolicy, CompanyConfig])
    def test_saving_another_row_overwrites_the_one_on_file(self, model):
        model.objects.all().delete()
        first = model()
        first.save()
        model().save()

        assert model.objects.count() == 1
        assert model.objects.get().pk == first.pk

    @pytest.mark.parametrize("model", [FiscalPolicy, CompanyConfig])
    def test_the_database_refuses_a_second_row_whatever_the_path(self, model):
        """``bulk_create`` skips ``save()``: the unique column is what really keeps one row."""
        model.objects.all().delete()
        model().save()

        with pytest.raises(IntegrityError), transaction.atomic():
            model.objects.bulk_create([model()])

    def test_the_policy_defaults_to_spain_in_the_roi_and_below_the_oss_threshold(self):
        policy = FiscalPolicy()

        assert policy.issuer_country == "ES"
        assert policy.issuer_region == ""
        # ERPlora is in the ROI since 08-08-2026 (ESB27593136): on by default (saas#1479).
        assert policy.intra_eu_reverse_charge is True
        assert policy.oss_registered is False
        assert policy.oss_threshold == Decimal("10000.00")


class TestStoredValuesAreEnglish:
    def test_the_vat_regimes_are_stored_in_english(self):
        """No external contract on this new table: its stored values follow the code's language."""
        assert set(CompanyConfig.VatRegime.values) == {"general", "simplified", "equivalence_surcharge", "exempt"}

    def test_the_policy_carries_no_amount_from_the_old_saas_until_somebody_types_it(self):
        policy = FiscalPolicy()

        assert (policy.oss_carried_year, policy.oss_carried_current_cents, policy.oss_carried_previous_cents) == (None, 0, 0)


class TestVatCheck:
    def _row(self, **fields):
        return VatCheck(vat_number="DE812871812", **fields)

    def test_a_verdict_is_current_for_thirty_days(self):
        assert (
            self._row(requested_at=timezone.now() - timedelta(days=29)).is_current
            is True
        )
        assert (
            self._row(requested_at=timezone.now() - timedelta(days=31)).is_current
            is False
        )

    def test_only_a_current_verified_verdict_with_proof_grants_reverse_charge(self):
        proof = {"status": VatCheck.VERIFIED, "consultation_number": "WAPIAAAAX9"}

        assert self._row(**proof).grants_reverse_charge is True
        assert (
            self._row(
                status=VatCheck.VERIFIED, consultation_number=""
            ).grants_reverse_charge
            is False
        )
        assert (
            self._row(**{**proof, "status": VatCheck.INVALID}).grants_reverse_charge
            is False
        )
        assert (
            self._row(
                **proof, requested_at=timezone.now() - timedelta(days=40)
            ).grants_reverse_charge
            is False
        )

    def test_a_manual_override_is_proof_of_another_kind(self):
        row = self._row(
            status=VatCheck.VERIFIED,
            override_by="ioan@erplora.com",
            override_reason="New company",
            override_at=timezone.now(),
        )

        assert row.is_manual_override is True
        assert row.grants_reverse_charge is True

    def test_it_reads_as_number_verdict_and_day(self):
        row = self._row(
            status=VatCheck.INVALID,
            requested_at=timezone.make_aware(timezone.datetime(2026, 8, 25, 10)),
        )

        assert str(row) == "DE812871812 — invalid (2026-08-25)"
