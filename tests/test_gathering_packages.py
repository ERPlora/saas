"""A door split into one module per entity, or another module split into one module per job, only gathers its
modules in its ``__init__``.

A name re-exported from the ``__init__`` would give every operation two import paths again, and a patch through the
package would no longer reach the module that reads the name. A package that re-exports on purpose (``billing``'s, and
an app's ``models``, whose migrations name ``<app>.models.<name>``) is not listed here.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings

#: The packages nothing is re-exported from: a name is imported from its own module.
GATHERING_PACKAGES = (
    "accounts.admin",
    "accounts.queries",
    "accounts.services",
    "assistant.admin",
    "assistant.queries",
    "assistant.services",
    "billing.schemas",
    "billing.services",
    "hubs.queries",
    "hubs.schemas",
    "hubs.services",
    "whatsapp.gateway",
    "whatsapp.services",
)


def _takes_whole_modules(node: ast.stmt, package: str, modules: set[str]) -> bool:
    """``from <package> import <module>, …``: each module whole, under its own name. ``<module> as <module>`` is the
    same import, the way ruff tells an import kept on purpose from an unused one (F401)."""
    return (
        isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == package
        and all(alias.name in modules and alias.asname in (None, alias.name) for alias in node.names)
    )


def statements_beyond_gathering(source: str, package: str, modules: set[str]) -> list[str]:
    """What an ``__init__`` holds besides its docstring and ``from <package> import <module>``."""
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if not _takes_whole_modules(node, package, modules):
            found.append(f"line {node.lineno}: {ast.unparse(node)}")
    return found


def _modules_of(package: str) -> tuple[Path, set[str]]:
    folder = Path(settings.BASE_DIR).joinpath(*package.split("."))
    return folder, {path.stem for path in folder.glob("*.py")} - {"__init__"}


@pytest.mark.parametrize("package", GATHERING_PACKAGES)
def test_the_package_only_gathers_its_modules(package):
    folder, modules = _modules_of(package)

    assert modules, f"{package} has no modules"
    assert statements_beyond_gathering((folder / "__init__.py").read_text(), package, modules) == []


def test_the_scan_catches_a_re_exported_name_and_code_of_its_own():
    source = (
        '"""Docstring."""\n'
        "from hubs.queries import taxonomy\n"
        "from hubs.queries.plan_catalog import free_plan\n"
        "from hubs.queries.taxonomy import *\n"
        "from hubs.queries import taxonomy as groups\n"
        "from hubs.queries import missing\n"
        "LIMIT = 3\n"
    )

    assert statements_beyond_gathering(source, "hubs.queries", {"taxonomy", "plan_catalog"}) == [
        "line 3: from hubs.queries.plan_catalog import free_plan",
        "line 4: from hubs.queries.taxonomy import *",
        "line 5: from hubs.queries import taxonomy as groups",
        "line 6: from hubs.queries import missing",
        "line 7: LIMIT = 3",
    ]


def test_a_module_taken_under_its_own_name_with_as_is_gathering():
    source = '"""Docstring."""\nfrom hubs.queries import taxonomy as taxonomy\nfrom hubs.queries import plan_catalog\n'

    assert statements_beyond_gathering(source, "hubs.queries", {"taxonomy", "plan_catalog"}) == []
