"""``manage.py seed_tax_rules``: today's tax data, idempotent, saying what it wrote (``billing.seed``)."""

from io import StringIO

import pytest
from django.core.management import call_command

from billing.models import TaxRule

pytestmark = pytest.mark.django_db


def _run(*args) -> str:
    out = StringIO()
    call_command("seed_tax_rules", *args, stdout=out)
    return out.getvalue()


def test_on_a_seeded_database_it_writes_nothing_and_says_so():
    before = TaxRule.objects.count()

    output = _run()

    assert TaxRule.objects.count() == before
    assert "0 categories, 0 rules, 0 fiscal policy, 0 company" in output


def test_it_puts_back_a_rule_that_is_missing():
    TaxRule.objects.filter(country_code="DE").delete()

    output = _run()

    assert TaxRule.objects.filter(country_code="DE").exists()
    assert "1 rules" in output


def test_a_dry_run_writes_nothing():
    TaxRule.objects.filter(country_code="DE").delete()

    output = _run("--dry-run")

    assert not TaxRule.objects.filter(country_code="DE").exists()
    assert "Dry run" in output
    assert "1 rules" in output
