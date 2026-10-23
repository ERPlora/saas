"""Write every value kept with the key of the credentials again with the current one (ASSISTANT-F10).

The rotation of ``FERNET_KEY``: put the new key in ``FERNET_KEY`` and the old one in ``FERNET_KEY_PREVIOUS``, deploy,
run this command, and drop ``FERNET_KEY_PREVIOUS`` only once it ends without error. It rotates every column of
``assistant.services.encrypted_columns`` (the AI providers' keys, WhatsApp's tokens and PINs) through
``assistant.encryption.rotate`` as the platform. A value no key opens is never written: it is listed by its row and
the command fails, so the old key is not dropped while something still needs it. It never prints a value nor a token.

    python manage.py rotate_encryption_keys --dry-run
    python manage.py rotate_encryption_keys
"""

from django.core.management.base import BaseCommand, CommandError
from live.errors import OperationError

from assistant import services
from assistant.schemas import EncryptionRotateIn


class Command(BaseCommand):
    help = "Write every value kept with FERNET_KEY again with the current key (never prints a value)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count what would be written again; change nothing.")

    def handle(self, *args, dry_run, **options):
        try:
            out = services.encryption_rotate(services.platform_context(), EncryptionRotateIn(dry_run=dry_run))
        except OperationError as refused:
            raise CommandError(refused.message) from None
        for column in out.columns:
            self.stdout.write(
                f"{column.column}: {column.rotated} rotated, {column.current} already current, "
                f"{len(column.unreadable)} unreadable"
            )
            for pk in column.unreadable:
                self.stdout.write(self.style.ERROR(f"  unreadable: {column.column} {pk}"))
        summary = f"rotated={out.rotated} current={out.current} unreadable={out.unreadable}"
        self.stdout.write(f"(dry run) {summary}" if dry_run else summary)
        if out.unreadable:
            raise CommandError(
                f"{out.unreadable} value no key opens: keep FERNET_KEY_PREVIOUS, bring back the key that wrote it or "
                "type the value again, and run the rotation again."
                if out.unreadable == 1
                else f"{out.unreadable} values no key opens: keep FERNET_KEY_PREVIOUS, bring back the key that wrote "
                "them or type the values again, and run the rotation again."
            )
