"""``python manage.py export_assistant_catalog --language <en|es> [--role account] [--surface web|app] [--apps a,b]``:
the panel assistant's catalogue of a role as JSON (``live.assistant_qa.export_catalog``), for the QA with the real
model (layer 2, docs plan 2026-10-31 §1.5). The tools are those a turn of that role offers on that surface
(``base.assistant.role_catalog``), each with its kind, permission, risk, description, input and the asks in the
language asked; ``--apps`` keeps only those apps' (one without tools there is refused by its name).
"""

import json

from django.core.management.base import BaseCommand, CommandError
from live.assistant_qa import export_catalog
from live.operations import ASK_LANGUAGES

from base import assistant


class Command(BaseCommand):
    help = "Prints the panel assistant's catalogue of a role as JSON, with the asks of each tool in one language."

    def add_arguments(self, parser):
        parser.add_argument("--language", required=True, choices=ASK_LANGUAGES)
        parser.add_argument("--role", default=assistant.ROLES[0], choices=assistant.ROLES)
        parser.add_argument("--surface", default=assistant.SURFACES[0], choices=assistant.SURFACES)
        parser.add_argument("--apps", default="", help="Comma-separated app labels; all the role's by default.")

    def handle(self, *args, language: str, role: str, surface: str, apps: str, **options) -> None:
        tools = assistant.role_catalog(role, surface=surface)
        wanted = {label.strip() for label in apps.split(",") if label.strip()}
        if wanted:
            unknown = sorted(wanted - {op.app_label for op in tools.values()})
            if unknown:
                raise CommandError(f"No tools of {', '.join(unknown)} for the role {role} on the {surface} surface.")
            tools = {name: op for name, op in tools.items() if op.app_label in wanted}
        self.stdout.write(json.dumps(export_catalog(tools, language), ensure_ascii=False, indent=2))
