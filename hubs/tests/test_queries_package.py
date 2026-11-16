"""The reads of hubs live one module per entity; the package itself only gathers them.

A name re-exported from ``hubs/queries/__init__.py`` would give every read two import paths again, and a
patch through the package would no longer reach the module that reads the name.
"""

import ast
from pathlib import Path

from django.conf import settings

PACKAGE = Path(settings.BASE_DIR) / "hubs" / "queries"


def statements_beyond_gathering(source: str) -> list[str]:
    """What a package's ``__init__`` holds besides its docstring and ``from hubs.queries import <module>``."""
    modules = {path.stem for path in PACKAGE.glob("*.py")} - {"__init__"}
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        gathers = (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "hubs.queries"
            and all(alias.name in modules and alias.asname is None for alias in node.names)
        )
        if not gathers:
            found.append(f"line {node.lineno}: {ast.unparse(node)}")
    return found


def test_the_package_only_gathers_its_modules():
    assert statements_beyond_gathering((PACKAGE / "__init__.py").read_text()) == []


def test_the_scan_catches_a_re_exported_name_and_code_of_its_own():
    source = (
        '"""Docstring."""\n'
        "from hubs.queries import taxonomy\n"
        "from hubs.queries.plan_catalog import free_plan\n"
        "from hubs.queries.taxonomy import *\n"
        "LIMIT = 3\n"
    )

    assert statements_beyond_gathering(source) == [
        "line 3: from hubs.queries.plan_catalog import free_plan",
        "line 4: from hubs.queries.taxonomy import *",
        "line 5: LIMIT = 3",
    ]
