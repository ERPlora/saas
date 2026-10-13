"""Seed of the taxonomy: ``python manage.py seed_taxonomy [--dry-run]``.

Ported from ERPlora/saas ``public/catalog/management/commands/seed_taxonomy.py`` (origin/develop):
12 sectors and 70 business types (each under its sector, some with a ``vertical``) from
``hubs/data/taxonomy.json``. Idempotent (``update_or_create`` on the stable ``code``). Business
types are upserted and never deleted: hubs may reference them. Without functional units,
categories nor subcategories (round 16, PLAN §21), there is no reorg tree to delete.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hubs.models import BusinessType, Sector

TAXONOMY_FILE = Path(__file__).resolve().parents[2] / "data" / "taxonomy.json"
TEXT_FIELDS = ("name_en", "name_es", "description_en", "description_es", "icon", "color")


def _defaults(row: dict) -> dict:
    texts = {field: row.get(field, "") for field in TEXT_FIELDS}
    return {**texts, "display_order": row.get("display_order", 0), "is_active": True}


class Command(BaseCommand):
    help = "Create or update the sectors and business types of the sign-up (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be written, write nothing.")

    def handle(self, *args, **options):
        data = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
        sectors, business_types = data["sectors"], data["activities"]
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: would upsert {len(sectors)} sectors and {len(business_types)} business types."
                )
            )
            return

        with transaction.atomic():
            for row in sectors:
                Sector.objects.update_or_create(code=row["code"], defaults=_defaults(row))
            by_code = {sector.code: sector for sector in Sector.objects.all()}
            for row in business_types:
                sector = by_code.get(row["sector"])
                if sector is None:
                    raise CommandError(f"Business type {row['code']!r}: unknown sector {row['sector']!r}.")
                BusinessType.objects.update_or_create(
                    code=row["code"],
                    defaults={**_defaults(row), "sector": sector, "vertical": row.get("vertical", "")},
                )
        self.stdout.write(self.style.SUCCESS(f"Taxonomy seeded: {len(sectors)} sectors, {len(business_types)} business types."))
