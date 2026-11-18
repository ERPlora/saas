"""The Python that the end-to-end specs run inside the SaaS (``djangoPrintWarm``, ``withStripe``) is written as
strings in TypeScript, where neither ruff nor pytest sees it, and a spec nobody edited is not picked for a
branch's run. So what those strings import from a package of the SaaS's apps, and what they read from a module
they imported, is checked here to exist: it is what moves when a file becomes a package.

Each scan is shown to catch its positive.
"""

import importlib
import re
from pathlib import Path

from django.apps import apps
from django.conf import settings

REPO = Path(settings.BASE_DIR).resolve()
E2E = REPO / "tests" / "e2e"
NAME = r"[A-Za-z_]\w*"
IMPORT = re.compile(rf"\bfrom ([a-z_][\w.]*) import ((?:{NAME}(?: as {NAME})?)(?:, ?{NAME}(?: as {NAME})?)*)")
COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*).*$", re.MULTILINE)


def own_apps() -> set[str]:
    return {config.name.split(".")[0] for config in apps.get_app_configs() if Path(config.path).resolve().parent == REPO}


def _module(dotted: str):
    try:
        return importlib.import_module(dotted)
    except ImportError:
        return None


def _bound(part: str) -> tuple[str, str]:
    name, _, alias = part.strip().partition(" as ")
    return name, alias or name


def missing_names(text: str, own: set[str]) -> list[str]:
    """What the Python written in ``text`` imports from a package of the apps in ``own``, or reads from a module
    it imported, that is not there. A module's name stands for the last import that bound it, as a spec writes
    one script after another in the same file."""
    text = COMMENT_LINE.sub("", text)
    imports = [match for match in IMPORT.finditer(text) if match[1].split(".")[0] in own]
    missing = []
    for position, found in enumerate(imports):
        source = _module(found[1])
        if source is None:
            missing.append(found[1])
            continue
        for name, bound in map(_bound, found[2].split(",")):
            module = _module(f"{found[1]}.{name}")
            if module is None:
                if hasattr(source, "__path__") and not hasattr(source, name):
                    missing.append(f"{found[1]}.{name}")
                continue
            later = (other.start() for other in imports[position + 1 :] if bound in dict(map(_bound, other[2].split(","))).values())
            script = text[found.end() : next(later, len(text))]
            reads = re.findall(rf"(?<![\w./-]){bound}\.({NAME})\b", script)
            missing += [f"{found[1]}.{name}.{read}" for read in reads if not hasattr(module, read)]
    return sorted(set(missing))


def e2e_sources() -> list[Path]:
    return sorted(path for path in E2E.rglob("*.ts") if "node_modules" not in path.parts)


def test_what_a_script_imports_and_reads_is_found():
    text = """
      'from hubs import services',
      `services.reconcile(ctx_for("${id}"))`,
      'from billing import services',
      'assert services.checkout_completed({})',
      'from hubs.queries import businesses, no_such_module',
      'from hubs.gone import anything',
    """

    assert missing_names(text, {"hubs", "billing"}) == ["hubs.gone", "hubs.queries.no_such_module", "hubs.services.reconcile"]


def test_a_module_read_under_another_name_is_found():
    text = "'from hubs import services as writes', 'writes.reconcile()', 'services.anything()'"

    assert missing_names(text, {"hubs"}) == ["hubs.services.reconcile"]


def test_what_is_not_the_saas_s_or_not_a_module_is_left_alone():
    text = """
      import { expect } from '@playwright/test';
      // The mail, as reconciliation.sends_it after the COMMIT.
      'from django.conf import settings', 'print(settings.NOT_A_SETTING)',
      'from hubs.hub_client import HubAnswer, OnlyInTheHubService', 'HubAnswer.anything()',
      'from hubs.services import reconciliation', 'reconciliation.reconcile()', // see hubs/reconciliation.py
    """

    assert missing_names(text, {"hubs"}) == []


def test_the_sweep_reads_the_specs_and_their_helpers():
    names = {path.relative_to(E2E).as_posix() for path in e2e_sources()}

    assert {"panel/hubs-people.spec.ts", "panel/accounts.ts"} <= names
    assert sum("from hubs" in path.read_text(encoding="utf-8") for path in e2e_sources()) > 10


def test_what_the_e2e_scripts_import_and_read_is_there():
    own = own_apps()
    missing = {}
    for path in e2e_sources():
        if gone := missing_names(path.read_text(encoding="utf-8"), own):
            missing[path.relative_to(REPO).as_posix()] = gone

    assert missing == {}
