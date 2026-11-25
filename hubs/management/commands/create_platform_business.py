"""``manage.py create_platform_business <hub id> --owner <email> [--execute]``: ERPlora's own business enters erplora.com.

Once per environment, with the id its row has there in the Hub (its page of the Hub's admin shows it) and an account
that exists already as its owner; from then on its people are its owner's to change in the panel. The Hub is asked
about that id first, and it refuses rather than guesses (``hubs.platform_business.create``). Idempotent, and a dry run
unless ``--execute``: the same steps, taken back.
"""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from live.context import Scope, system_context
from live.errors import OperationError

from hubs.schemas.platform_business import PlatformBusinessIn
from hubs.services.platform_business import platform_business_create


class Command(BaseCommand):
    help = "Take ERPlora's own business from the Hub, for its people. Idempotent; a dry run unless --execute is given."

    def add_arguments(self, parser):
        parser.add_argument("hub_id", type=UUID, help="The id of its row in the Hub.")
        parser.add_argument("--owner", required=True, help="The email of the account that owns it.")
        parser.add_argument("--execute", action="store_true", help="Write. Without it, it only says what it would do.")

    def handle(self, *args, hub_id, owner, execute, **options):
        try:
            with transaction.atomic():
                made = platform_business_create(
                    system_context(Scope("user", "system")), PlatformBusinessIn(id=hub_id, owner_email=owner)
                )
                if not execute:
                    transaction.set_rollback(True)
        except OperationError as refused:
            raise CommandError(f"{refused.code}: {refused.message} Nothing was written.") from refused
        if not made.created:
            self.stdout.write(f"{made.slug} is here already ({made.id}): nothing changed.")
        elif execute:
            self.stdout.write(f"{made.slug} is here ({made.id}): {owner} owns it, and the Hub gets its people now.")
        else:
            self.stdout.write("Dry run: nothing is written without --execute.")
            self.stdout.write(f"- would make {made.slug} ({made.id}), owned by {owner}")
