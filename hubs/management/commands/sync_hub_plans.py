"""``python manage.py sync_hub_plans``: an empty command, kept for the deploy that still calls it.

The plans live only in the database since 2026-10-15 (Ioan): migration ``hubs/0013_plans_in_the_database`` seeds
them and staff keep them in the admin, so this command seeds nothing and never touches the database. It stays
because the ``saas-migrate`` task of pre and prod runs ``migrate && sync_hub_plans && …`` until the Terraform of
ERPlora/aws#4 (which drops the call) is applied; without it the task would stop the deploy with «Unknown
command». It goes once that apply is done (PLAN-SAAS §3.6 and §8).
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Does nothing: the plans live in the database (seeded by migration hubs/0013, kept in the admin). Kept only "
        "for the saas-migrate task until ERPlora/aws#4 is applied."
    )

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="Accepted and ignored: nothing is seeded.")

    def handle(self, *args, **options):
        if options["update"]:
            self.stderr.write(self.style.WARNING("--update is ignored: nothing is seeded."))
        self.stdout.write("Plans live in the database; nothing to seed (hubs/0013).")
