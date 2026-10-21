"""The audit of the table that prices every sale (BILLING-F04, saas#1968, saas#1995).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_audit_tax_rules.py`` (origin/develop, 12 cases).
The rate a sale is charged comes from ``billing.TaxRule``; the table can break without anything shouting —
the issuer's rule deleted (the backstop in ``vat.py`` keeps charging, but the rate stops being editable),
a territory outside VAT unticked from the admin list (Las Palmas would take the mainland 21 %, so the sale is
refused), a payer on file in a country without a rule (refused at checkout). ``manage.py audit_tax_rules``
looks at every sale we can make and exits non-zero on the first problem, so the daily scheduled task raises
the team's ``task_failed`` alarm instead of a customer finding it.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from billing.models import TaxRule

pytestmark = pytest.mark.django_db

PLAN = "service.saas_subscription"


def _run() -> str:
    out = StringIO()
    call_command("audit_tax_rules", stdout=out)
    return out.getvalue()


def _problems() -> str:
    with pytest.raises(CommandError) as failure:
        _run()
    return str(failure.value)


class TestTheSeededTable:
    def test_with_the_rules_of_the_migration_it_is_green(self):
        output = _run()

        assert "OK" in output
        assert "Issuer country: ES" in output
        assert f"Category audited: {PLAN}" in output

    def test_the_report_comes_from_a_read_only_query(self):
        """The command is the human door: the checks are a query, so another caller (a staff page, a task)
        asks the same thing."""
        from billing import queries

        report = queries.tax_rule_audit()

        assert report.issuer == "ES"
        assert report.category == PLAN
        assert report.problems == []
        assert not report.is_red


class TestTheIssuerHasToBeInTheTable:
    """The backstop does NOT count as cover: while ``EU_VAT_RATES`` carries the issuer, the rate is no longer
    the admin's and a rate change cannot be scheduled."""

    def test_without_the_issuer_rule_it_fails(self):
        TaxRule.objects.filter(country_code="ES", region_code="").delete()

        problems = _problems()

        assert "No TaxRule in force for ES" in problems


class TestTheTerritoriesOutsideVat:
    """``queries.tax_rule`` falls from the region to the country: right for a province, catastrophic for the
    Canary Islands. ``_lookup_rate`` refuses that fallback, so a broken ES/IC rule REFUSES every sale there."""

    @pytest.mark.parametrize("region", ["IC", "CE", "ML"])
    def test_deleting_the_rule_fails(self, region):
        TaxRule.objects.filter(country_code="ES", region_code=region).delete()

        problems = _problems()

        assert f"No TaxRule for ES/{region}" in problems

    @pytest.mark.parametrize("region", ["IC", "CE", "ML"])
    def test_marking_it_subject_in_the_admin_fails(self, region):
        """A hand-made ``is_subject=True`` is the same damage as deleting it."""
        TaxRule.objects.filter(country_code="ES", region_code=region).update(
            is_subject=True, rate_pct="21.00"
        )

        problems = _problems()

        assert f"The ES/{region} rule is marked subject to VAT" in problems

    @pytest.mark.parametrize("region", ["IC", "CE", "ML"])
    def test_unticking_active_from_the_list_fails(self, region):
        """The break that really happens: one click on the list's checkbox (saas#1995). The message says the
        rule is there but does not answer, so nobody creates a duplicate."""
        TaxRule.objects.filter(country_code="ES", region_code=region).update(is_active=False)

        problems = _problems()

        assert f"The ES/{region} rule is in the table but does not answer" in problems
        assert "active=False" in problems

    def test_the_message_describes_the_rule_that_had_to_answer(self):
        """With another row of the same territory (another category), the message looked at the newest row
        instead of the one ``tax_rule`` asks for, and reported ``active=True`` about a row never in play."""
        hardware = TaxRule.objects.create(
            country_code="ES",
            region_code="IC",
            category_id="product.hardware",
            rate_pct="0.00",
            is_subject=False,
            valid_from="2026-01-01",
            is_active=True,
        )
        TaxRule.objects.filter(country_code="ES", region_code="IC").exclude(
            pk=hardware.pk
        ).update(is_active=False)

        problems = _problems()

        assert "active=False" in problems
        assert "active=True" not in problems


class TestThePostalCodeMap:
    """The table can be perfect and a Canarian still be charged 21 %: the territory comes from the POSTAL
    CODE, so the audit asks through the same door as the checkout."""

    def test_if_a_canarian_postal_code_stops_being_canarian_it_fails(self, monkeypatch):
        from billing import vat

        monkeypatch.setattr(vat, "spanish_region_for_postal_code", lambda postal_code: "")

        problems = _problems()

        assert "ES/IC (postal code 35001)" in problems


class TestTheCountriesThatAlreadyHaveAPayer:
    """The countries we sell to are not a list: they are the payers on file."""

    def test_a_payer_in_a_country_without_a_rule_fails(self, business_paid_by):
        business_paid_by("US", "10001")

        problems = _problems()

        assert "A payer is on file in US and no rule resolves there" in problems

    def test_a_payer_in_the_canary_islands_is_not_a_problem(self, business_paid_by):
        """Not subject is an answer, not a hole."""
        business_paid_by("ES", "35001")

        output = _run()

        assert "ES/IC: not_subject" in output
        assert "OK" in output

    def test_a_spanish_payer_with_a_postal_code_that_is_not_one_fails(self, business_paid_by):
        """Without a real postal code the territory is unknown and the sale is refused: the audit names the
        payer's postal code instead of crashing on a territory it cannot place."""
        business_paid_by("ES", "ABC")

        problems = _problems()

        assert "postal code 'ABC', which is not a Spanish postal code" in problems

    def test_a_country_carried_by_the_backstop_is_a_warning_not_a_failure(self, business_paid_by):
        business_paid_by("DE", "10115")
        TaxRule.objects.filter(country_code="DE").delete()

        output = _run()

        assert "comes from the backstop" in output
        assert "OK" in output
