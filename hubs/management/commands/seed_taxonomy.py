"""Seed of the taxonomy: ``python manage.py seed_taxonomy [--update] [--dry-run]``.

Ported from ERPlora/saas ``public/catalog/management/commands/seed_taxonomy.py`` (origin/develop):
12 sectors and 70 business types (each under its sector, some with a ``vertical``) from
``hubs/data/taxonomy.json``. It runs in the ``saas-migrate`` task on every deploy, so by default it
only creates the rows missing by their stable ``code`` and keeps what staff edited in the admin (names,
icons…); ``--update`` refreshes every field of the existing rows from the file. Idempotent; the file is
checked before the first write and each row is its own short transaction, so it is safe next to the
running web. Business types are never deleted: hubs may reference them. Without functional units,
categories nor subcategories (round 16, PLAN §21), there is no reorg tree to delete.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from hubs.models import BusinessType, Sector

TAXONOMY_FILE = Path(__file__).resolve().parents[2] / "data" / "taxonomy.json"
TEXT_FIELDS = ("name_en", "name_es", "description_en", "description_es", "icon", "color")


def _defaults(row: dict) -> dict:
    texts = {field: row.get(field, "") for field in TEXT_FIELDS}
    return {**texts, "display_order": row.get("display_order", 0), "is_active": True}


def _write(model, rows: list[dict], defaults_of, update: bool) -> int:
    """Create the rows missing by ``code`` (and, with ``update``, overwrite the rest); the number created.

    ``get_or_create`` / ``update_or_create`` each run in their own transaction and survive a concurrent
    insert of the same code (unique), so no lock is held across the whole seed.
    """
    write = model.objects.update_or_create if update else model.objects.get_or_create
    return sum(write(code=row["code"], defaults=defaults_of(row))[1] for row in rows)


def _missing(model, rows: list[dict]) -> int:
    return len(rows) - model.objects.filter(code__in=[row["code"] for row in rows]).count()


class Command(BaseCommand):
    help = "Create the missing sectors and business types of the sign-up; --update also refreshes the existing ones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Also refresh every field of the existing rows from the seed, overwriting admin edits.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Show what would be written, write nothing.")

    def handle(self, *args, **options):
        data = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
        sectors, business_types = data["sectors"], data["activities"]
        update, dry_run = options["update"], options["dry_run"]

        known = {row["code"] for row in sectors} | set(Sector.objects.values_list("code", flat=True))
        for row in business_types:
            if row["sector"] not in known:
                raise CommandError(f"Business type {row['code']!r}: unknown sector {row['sector']!r}.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run, nothing written."))
            created_sectors = _missing(Sector, sectors)
            created_types = _missing(BusinessType, business_types)
        else:
            created_sectors = _write(Sector, sectors, _defaults, update)
            by_code = {sector.code: sector for sector in Sector.objects.all()}
            created_types = _write(
                BusinessType,
                business_types,
                lambda row: {**_defaults(row), "sector": by_code[row["sector"]], "vertical": row.get("vertical", "")},
                update,
            )

        for label, rows, created in (
            ("Sectors", sectors, created_sectors),
            ("Business types", business_types, created_types),
        ):
            self.stdout.write(self.style.SUCCESS(self._counts(label, created, len(rows) - created, update, dry_run)))

    @staticmethod
    def _counts(label: str, created: int, others: int, update: bool, dry_run: bool) -> str:
        if dry_run:
            return f"{label}: {created} to create, {others} {'to update' if update else 'existing'}"
        return f"{label}: {created} created, {others} {'updated' if update else 'existing'}"
