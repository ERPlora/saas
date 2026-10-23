"""Keep the AI providers' keys of the environment encrypted in the database (ASSISTANT-F09).

Reads ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY`` and ``DEEPSEEK_API_KEY`` (``config/settings.py``)
and keeps each one in its provider through ``assistant.credential.import`` as the platform, adding the provider if
missing. A key already kept with the label stays unless ``--force``. It never prints a key, only its last four
characters.

    python manage.py import_ai_keys_from_env
    python manage.py import_ai_keys_from_env --providers openai,anthropic --label default --force
    python manage.py import_ai_keys_from_env --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from live.errors import OperationError

from assistant import services
from assistant.schemas import CredentialImportIn

#: Each provider's API and the setting holding its key, in the order they are loaded.
SETTINGS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


class Command(BaseCommand):
    help = "Keep the AI providers' keys of the environment encrypted in the database (never prints a key)."

    def add_arguments(self, parser):
        parser.add_argument("--providers", default="", help="Comma-separated providers to load (default: all four).")
        parser.add_argument("--label", default="default", help="Label of the key in its provider (default: 'default').")
        parser.add_argument("--force", action="store_true", help="Replace a key already kept with the same label.")
        parser.add_argument("--dry-run", action="store_true", help="Say what would happen without writing.")

    def handle(self, *args, providers, label, force, dry_run, **options):
        wanted = [slug.strip() for slug in providers.split(",") if slug.strip()] or list(SETTINGS)
        unknown = [slug for slug in wanted if slug not in SETTINGS]
        if unknown:
            raise CommandError(f"Unknown provider(s): {', '.join(unknown)}. Known: {', '.join(SETTINGS)}.")
        label = label.strip() or "default"
        ctx = services.platform_context()
        counts = {"created": 0, "rotated": 0, "kept": 0, "skipped": 0}
        for slug in wanted:
            name = SETTINGS[slug]
            value = (getattr(settings, name, "") or "").strip()
            if not value:
                counts["skipped"] += 1
                self.stdout.write(self.style.WARNING(f"{slug}: skipped, {name} is empty"))
                continue
            try:
                out = services.credential_import(
                    ctx, CredentialImportIn(kind=slug, api_key=value, label=label, force=force, dry_run=dry_run)
                )
            except OperationError as refused:
                raise CommandError(refused.message) from None
            counts[out.action] += 1
            if out.action == "kept":
                self.stdout.write(f"{slug}: kept key '{out.label}' ({out.masked_key}); --force replaces it")
                continue
            verb = f"would {out.action.removesuffix('d')}" if dry_run else out.action
            self.stdout.write(self.style.SUCCESS(f"{slug}: {verb} key '{out.label}' ({out.masked_key})"))
        summary = " ".join(f"{action}={count}" for action, count in counts.items())
        self.stdout.write(f"(dry run) {summary}" if dry_run else summary)
