"""Only ``queries.py`` and ``services.py`` touch the ORM (plan §6, spec §5.1): the public web's
views, middlewares, helpers, template tags and commands read and write through operations.

The scan walks every ``.py`` of ``public/`` (tests left out) and fails on a module that names a model:

- an import of a ``models`` module (``from apps.models import App``, ``from apps import models``,
  ``import hubs.models``, ``from django.db import models``…);
- a manager (``<anything>.objects``) or ``apps.get_model(…)``, the back door without an import;
- an import from ``django.db`` (``connection``, ``transaction``…): raw SQL is the ORM too.

Allowed: ``queries.py`` and ``services.py`` (where the ORM lives), ``init_cookie_groups`` (it seeds
django-cookie-consent's own tables, which have no operation) and ``errors.py``'s
``from django.db import connections``, nothing else of ``django.db`` (it only closes this thread's
stale connections before the error page renders, it never queries).
"""

import ast
import os
from pathlib import Path

import pytest
from django.conf import settings

SAAS_NEXT = Path(settings.BASE_DIR)
PUBLIC = SAAS_NEXT / "public"
#: Where the ORM may be used: nothing in them is scanned.
ORM_MODULES = frozenset(
    {
        "public/queries.py",
        "public/services.py",
        "public/management/commands/init_cookie_groups.py",
    }
)
#: The names each module may import from ``django.db``; never a model or a manager.
DJANGO_DB_IMPORTS = {"public/errors.py": frozenset({"connections"})}
SKIPPED_DIRS = frozenset({"tests", "__pycache__", "static", "templates", "locale"})


def python_files(root: Path = PUBLIC) -> list[str]:
    """Every ``.py`` under ``root`` as a path relative to its parent (``public/…``), tests out."""
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in SKIPPED_DIRS)
        for name in files:
            if name.endswith(".py"):
                found.append(
                    (Path(directory) / name).relative_to(root.parent).as_posix()
                )
    return sorted(found)


def _is_models_module(name: str) -> bool:
    return name == "models" or name.endswith(".models") or ".models." in name


def orm_uses(source: str, *, django_db_names: frozenset[str] = frozenset()) -> list[str]:
    """Each place ``source`` reaches a model or the database, as ``line: what``.

    ``django_db_names``: what it may import with ``from django.db import …`` (``errors.py``).
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            if _is_models_module(module) or "models" in names:
                found.append(f"{node.lineno}: from {module} import {', '.join(names)}")
            elif module.split(".")[:2] == ["django", "db"] and (
                module != "django.db" or not set(names) <= django_db_names
            ):
                found.append(f"{node.lineno}: from {module} import {', '.join(names)}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_models_module(alias.name) or alias.name.split(".")[:2] == [
                    "django",
                    "db",
                ]:
                    found.append(f"{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Attribute) and node.attr == "objects":
            found.append(f"{node.lineno}: {ast.unparse(node)}")
        elif (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", getattr(node.func, "id", "")) == "get_model"
        ):
            found.append(f"{node.lineno}: {ast.unparse(node.func)}(…)")
    return found


def offenders(root: Path = PUBLIC) -> dict[str, list[str]]:
    return {
        path: uses
        for path in python_files(root)
        if path not in ORM_MODULES
        if (
            uses := orm_uses(
                (root.parent / path).read_text(encoding="utf-8"),
                django_db_names=DJANGO_DB_IMPORTS.get(path, frozenset()),
            )
        )
    }


# --- The rule, on the project --------------------------------------------------------------------


def test_only_queries_and_services_touch_the_orm():
    assert offenders() == {}


def test_the_scan_sees_the_public_web():
    """A scan that finds nothing proves nothing: views, middlewares, tags and commands are in it."""
    files = set(python_files())

    assert {
        "public/store.py",
        "public/landing.py",
        "public/cookies.py",
        "public/errors.py",
        "public/templatetags/icons.py",
        "public/management/commands/indexnow_submit.py",
        "public/queries.py",
    } <= files
    assert not any("/tests/" in path for path in files)


# --- The detector: it catches its positives and lets its negatives through -----------------------


def test_a_module_that_imports_a_model_is_caught(tmp_path):
    """Positive control on a tree of its own: a temporary module that does import a model."""
    public = tmp_path / "public"
    (public / "management" / "commands").mkdir(parents=True)
    (public / "store.py").write_text("from apps.models import App\n", encoding="utf-8")
    (public / "management" / "commands" / "seed.py").write_text(
        "from hubs.models import Plan\nPlan.objects.count()\n", encoding="utf-8"
    )
    (public / "queries.py").write_text(
        "from apps.models import App\n", encoding="utf-8"
    )
    (public / "tests").mkdir()
    (public / "tests" / "test_x.py").write_text(
        "from apps.models import App\n", encoding="utf-8"
    )

    assert set(offenders(public)) == {
        "public/store.py",
        "public/management/commands/seed.py",
    }


@pytest.mark.parametrize(
    "source",
    [
        "from apps.models import App",
        "from hubs.models import Plan as P",
        "from apps import models",
        "import hubs.models",
        "import hubs.models as hub_models",
        "from django.db import models",
        "from django.db.models import Q",
        "from django.db import connection",
        "from django.db import transaction",
        "import django.db",
        "Plan.objects.public()",
        "something.objects",
        "from django.apps import apps\napps.get_model('hubs', 'Plan')",
    ],
)
def test_a_use_of_the_orm_is_caught(source):
    assert orm_uses(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "from apps.schemas import AppListIn",
        "from live.ninja import run_operation_sync",
        "from django.conf import settings",
        '"""Plan.objects.public() in a docstring is prose, not a call."""',
        "# from apps.models import App",
        "modelsish = 1",
    ],
)
def test_what_is_not_the_orm_passes(source):
    assert orm_uses(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "from django.db import models",
        "from django.db import transaction",
        "from django.db import connection",
        "from django.db import connections, transaction",
        "from django.db.models import Q",
        "import django.db",
        "Plan.objects.all()",
    ],
)
def test_errors_may_import_connections_and_nothing_else_of_the_database(source):
    """The exception is the one name ``errors.py`` needs, so it cannot widen unnoticed."""
    errors = DJANGO_DB_IMPORTS["public/errors.py"]

    assert orm_uses("from django.db import connections", django_db_names=errors) == []
    assert orm_uses(source, django_db_names=errors) != []
