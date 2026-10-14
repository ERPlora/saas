"""``python manage.py seed_tax_rules [--dry-run]``: today's tax data (``billing.seed``), only what is missing.

The migration ``billing/0002_seed_tax_data`` already writes it on every database; the command puts back
what somebody deleted (a country's rule, the fiscal policy, ERPlora's identity) without touching what the
admin edited. Idempotent: a second run writes nothing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import CompanyConfig, FiscalPolicy, TaxCategory, TaxRule
from billing.seed import seed_tax_data


class Command(BaseCommand):
    help = "Create the tax categories, rules, fiscal policy and ERPlora's identity that are missing (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say what would be created, write nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            created = seed_tax_data(
                TaxCategory=TaxCategory,
                TaxRule=TaxRule,
                FiscalPolicy=FiscalPolicy,
                CompanyConfig=CompanyConfig,
                dry_run=dry_run,
            )
        summary = (
            f"{created['categories']} categories, {created['rules']} rules, "
            f"{created['fiscal_policy']} fiscal policy, {created['company']} company"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: would create {summary}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created {summary}."))
