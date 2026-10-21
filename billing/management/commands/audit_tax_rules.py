"""``python manage.py audit_tax_rules``: does the rate table price every sale we can make? (BILLING-F04)

Ported from ERPlora/saas ``apps/dashboard/fiscal/management/commands/audit_tax_rules.py`` (saas#1968,
saas#1995). The checks are a read-only query (``billing.queries.tax_rule_audit``); this is the human door and
the daily scheduled task's: it prints what was looked at and exits non-zero on the first problem, so the
``task_failed`` alarm tells the team before a customer is refused (or overcharged) at checkout.
"""

from django.core.management.base import BaseCommand, CommandError

from billing import queries


class Command(BaseCommand):
    help = "Check that the tax rule table prices every sale we can make (exits non-zero when it does not)."

    def handle(self, *args, **options):
        report = queries.tax_rule_audit()

        self.stdout.write(f"Issuer country: {report.issuer}")
        self.stdout.write(f"Category audited: {report.category}")
        for line in report.lines:
            self.stdout.write(self.style.WARNING(line.text) if line.is_warning else line.text)

        if report.is_red:
            raise CommandError("\n".join(report.problems))

        self.stdout.write(
            self.style.SUCCESS("OK — every sale we can make has a rate that comes from the table.")
        )
