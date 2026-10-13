"""The SaaS reads the catalog and never writes it (spec §9 and §3.3; plan §3.p).

The Hub writes ``shared.app`` and ``shared.app_doc`` with each release; in the SaaS the role does not
stop a write (``saas_app`` may get more than ``SELECT`` there), the code does:

- outside ``apps/models.py`` (``Module.clean()``), ``apps/queries.py``, ``apps/admin.py`` (read-only),
  ``apps/checks.py`` (``apps.E001``) and the migrations of apps, no module names ``App`` or
  ``AppDoc``: everything else reads the catalog through the operations ``apps.app.*``;
- no module calls a write on them (``create``, ``update``, ``delete``, ``save``…), and there is no
  ``apps/services.py``: the SaaS has no operation that writes the catalog.

Tests are out of the scan: they set up the rows the Hub would have written (``apps/tests/factories.py``).
"""

import ast
import os
from pathlib import Path

import pytest
from django.conf import settings

SAAS_NEXT = Path(settings.BASE_DIR)
CATALOG_MODELS = frozenset({"App", "AppDoc"})
ALLOWED = frozenset(
    {"apps/models.py", "apps/queries.py", "apps/admin.py", "apps/checks.py"}
)
ALLOWED_DIRS = ("apps/migrations/",)
#: Not code of this project (submodules, dependencies, builds) or not production code (tests).
SKIPPED_DIRS = frozenset(
    {"packages", "node_modules", ".venv", ".git", "staticfiles", "tests", "__pycache__"}
)
WRITE_METHODS = frozenset(
    {
        "create",
        "bulk_create",
        "bulk_update",
        "update",
        "update_or_create",
        "get_or_create",
        "delete",
        "save",
    }
)


def python_files() -> list[str]:
    """Every ``.py`` of saas-next as a path relative to it, tests and dependencies left out."""
    found = []
    for root, dirs, files in os.walk(SAAS_NEXT):
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in SKIPPED_DIRS and not name.startswith(".")
        )
        for name in files:
            if name.endswith(".py"):
                found.append((Path(root) / name).relative_to(SAAS_NEXT).as_posix())
    return sorted(found)


def catalog_references(source: str) -> list[str]:
    """Each place ``source`` names ``App`` or ``AppDoc`` of ``apps.models`` (by import, attribute or
    ``get_model``), as ``line: what``."""
    tree = ast.parse(source)
    module_aliases: set[str] = set()
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "apps.models":
            for alias in node.names:
                if alias.name in CATALOG_MODELS or alias.name == "*":
                    found.append(f"{node.lineno}: from apps.models import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module == "apps":
            module_aliases |= {
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "models"
            }
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "apps.models":
                    module_aliases.add(alias.asname or "apps.models")
        elif (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", getattr(node.func, "id", "")) == "get_model"
        ):
            labels = [
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            ]
            if labels[:2] in (["apps", "App"], ["apps", "AppDoc"]) or labels[:1] in (
                ["apps.App"],
                ["apps.AppDoc"],
            ):
                found.append(
                    f"{node.lineno}: get_model({', '.join(map(repr, labels))})"
                )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in CATALOG_MODELS
            and ast.unparse(node.value) in module_aliases
        ):
            found.append(f"{node.lineno}: {ast.unparse(node)}")
    return found


def catalog_writes(source: str) -> list[str]:
    """Each call of a write method on a chain that starts at ``App`` or ``AppDoc``
    (``App.objects.filter(…).update(…)``, ``AppDoc.objects.create(…)``), as ``line: call``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in WRITE_METHODS
        ):
            names = {
                child.id
                for child in ast.walk(node.func.value)
                if isinstance(child, ast.Name)
            }
            if names & CATALOG_MODELS:
                found.append(f"{node.lineno}: {ast.unparse(node.func)}(…)")
    return found


def read(path: str) -> str:
    return (SAAS_NEXT / path).read_text(encoding="utf-8")


# --- The rules, on the project -------------------------------------------------------------------


def test_only_the_catalogs_own_modules_name_app_and_app_doc():
    offenders = {
        path: references
        for path in python_files()
        if path not in ALLOWED and not path.startswith(ALLOWED_DIRS)
        if (references := catalog_references(read(path)))
    }

    assert offenders == {}


def test_nothing_writes_the_catalog():
    offenders = {
        path: writes
        for path in python_files()
        if (writes := catalog_writes(read(path)))
    }

    assert offenders == {}


def test_the_saas_has_no_operation_that_writes_the_catalog():
    """Module is written in the admin and the catalog by the Hub: no services.py (plan §3.p)."""
    assert not (SAAS_NEXT / "apps" / "services.py").exists()


def test_the_scan_sees_the_project():
    """A scan that finds nothing proves nothing: it walks the apps, and leaves tests and packages out."""
    files = python_files()

    assert {
        "apps/queries.py",
        "apps/models.py",
        "accounts/services.py",
        "config/settings.py",
    } <= set(files)
    assert not any(
        path.startswith(("packages/", "node_modules/")) or "/tests/" in path
        for path in files
    )


# --- The detectors: each one catches its positive and lets its negative through ------------------


@pytest.mark.parametrize(
    "source",
    [
        "from apps.models import App",
        "from apps.models import Module, AppDoc as Doc",
        "from apps.models import *",
        "from apps import models\nmodels.App.objects.all()",
        "from apps import models as catalog\ncatalog.AppDoc.objects.all()",
        "import apps.models\napps.models.App.objects.all()",
        "from django.apps import apps\napps.get_model('apps', 'App')",
        "from django.apps import apps\napps.get_model('apps.AppDoc')",
    ],
)
def test_a_reference_to_the_catalog_is_caught(source):
    assert catalog_references(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "from apps.models import Module",
        "from apps import queries\nqueries.app_list",
        "from apps import models\nmodels.Module.objects.all()",
        "from django.apps import apps\napps.get_model('apps', 'Module')",
        "from hubs.models import App",
        "App = 'a name of its own'",
    ],
)
def test_what_is_not_the_catalog_passes(source):
    assert catalog_references(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "App.objects.create(id='x')",
        "App.objects.filter(listed=True).update(listed=False)",
        "AppDoc.objects.filter(lang='en').delete()",
        "AppDoc.objects.update_or_create(app_id='x', lang='es')",
        "App.objects.bulk_create([])",
    ],
)
def test_a_write_on_the_catalog_is_caught(source):
    assert catalog_writes(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "App.objects.filter(listed=True)",
        "AppDoc.objects.exclude(markdown='').values_list('lang')",
        "Module.objects.create(slug='x')",
        "cache.set(key, html)",
    ],
)
def test_a_read_or_another_write_passes(source):
    assert catalog_writes(source) == []
